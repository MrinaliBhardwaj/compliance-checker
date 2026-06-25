"""
Auth API: self-serve signup (creates org + first admin) and login.

Signup is the only endpoint that opens a non-tenant-scoped session — it creates
the org. Everything else runs under the JWT's org scope. First signup defaults to
`compliance_admin` (the org super-user, per PRD §10).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.security import (
    CurrentPrincipal,
    Principal,
    create_access_token,
    hash_password,
    verify_password,
)
from app.models.tenancy import Entity, Membership, Organization, User

router = APIRouter(prefix="/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None
    organization_name: str
    entity_legal_name: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    organization_id: str
    entity_id: str
    role: str


@router.post("/signup", response_model=TokenResponse)
def signup(body: SignupRequest) -> TokenResponse:
    with SessionLocal() as db:
        exists = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
        if exists:
            raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
        org = Organization(name=body.organization_name)
        db.add(org)
        db.flush()
        user = User(email=body.email, full_name=body.full_name,
                    auth_provider="password", password_hash=hash_password(body.password))
        db.add(user)
        db.flush()
        db.add(Membership(user_id=user.id, organization_id=org.id,
                          role="compliance_admin", status="active"))
        entity = Entity(organization_id=org.id, legal_name=body.entity_legal_name)
        db.add(entity)
        db.flush()
        principal = Principal(user_id=str(user.id), organization_id=str(org.id),
                              role="compliance_admin", email=body.email)
        token = create_access_token(principal)
        db.commit()
        return TokenResponse(access_token=token, organization_id=str(org.id),
                             entity_id=str(entity.id), role="compliance_admin")


@router.get("/me")
def me(principal: CurrentPrincipal) -> dict:
    """Resolve the bearer token to the current principal + the org's entities
    (so the SPA can verify session validity and populate the entity selector)."""
    with SessionLocal() as db:
        entities = db.execute(
            select(Entity).where(Entity.organization_id == principal.organization_id)
        ).scalars().all()
        org = db.get(Organization, principal.organization_id)
    return {
        "user_id": principal.user_id, "email": principal.email,
        "organization_id": principal.organization_id, "role": principal.role,
        "organization_name": org.name if org else None,
        "entities": [{"id": str(e.id), "legal_name": e.legal_name} for e in entities],
    }


class AcceptInviteRequest(BaseModel):
    token: str
    password: str | None = None
    full_name: str | None = None


@router.post("/accept-invite", response_model=TokenResponse)
def accept_invite(body: AcceptInviteRequest) -> TokenResponse:
    """Public: an invited teammate activates their membership (sets a password if
    they're a brand-new user) and receives a session token."""
    from app.modules.team import service as team_svc
    with SessionLocal() as db:
        try:
            res = team_svc.accept_invite(db, token=body.token, password=body.password,
                                         full_name=body.full_name)
        except team_svc.NotFound:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Invite not found")
        except team_svc.TeamError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
        db.commit()
    return TokenResponse(access_token=res["access_token"], organization_id=res["organization_id"],
                         entity_id=res["entity_id"], role=res["role"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest) -> TokenResponse:
    with SessionLocal() as db:
        user = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
        if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
        membership = db.execute(
            select(Membership).where(Membership.user_id == user.id)
        ).scalars().first()
        if not membership:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No organization membership")
        entity = db.execute(
            select(Entity).where(Entity.organization_id == membership.organization_id)
        ).scalars().first()
        principal = Principal(user_id=str(user.id), organization_id=str(membership.organization_id),
                              role=membership.role, email=user.email)
        return TokenResponse(access_token=create_access_token(principal),
                             organization_id=str(membership.organization_id),
                             entity_id=str(entity.id) if entity else "",
                             role=membership.role)
