"""
Auth API: self-serve signup (creates org + first admin) and login.

Signup is the only endpoint that opens a non-tenant-scoped session — it creates
the org. Everything else runs under the JWT's org scope. First signup defaults to
`compliance_admin` (the org super-user, per PRD §10).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from app.core.db import SessionLocal, set_bootstrap, set_tenant
from app.core.security import (
    CurrentPrincipal,
    Principal,
    clear_auth_cookie,
    create_access_token,
    hash_password,
    set_auth_cookie,
    verify_password,
)
from app.models.tenancy import Entity, Membership, Organization, User

router = APIRouter(prefix="/auth", tags=["auth"])


MIN_PASSWORD_LEN = 8


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LEN, max_length=200)
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
def signup(body: SignupRequest, response: Response) -> TokenResponse:
    with SessionLocal() as db:
        exists = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
        if exists:
            raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
        org = Organization(name=body.organization_name)  # organizations/users: no RLS
        db.add(org)
        db.flush()
        # Everything below belongs to the new org — scope the session to it so the
        # membership/entity inserts satisfy RLS (WITH CHECK) on production Postgres.
        set_tenant(db, str(org.id))
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
        set_auth_cookie(response, token)
        return TokenResponse(access_token=token, organization_id=str(org.id),
                             entity_id=str(entity.id), role="compliance_admin")


@router.get("/me")
def me(principal: CurrentPrincipal) -> dict:
    """Resolve the bearer token to the current principal + the org's entities
    (so the SPA can verify session validity and populate the entity selector)."""
    with SessionLocal() as db:
        set_tenant(db, principal.organization_id)  # scope the entities read to the caller's org
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
def accept_invite(body: AcceptInviteRequest, response: Response) -> TokenResponse:
    """Public: an invited teammate activates their membership (sets a password if
    they're a brand-new user) and receives a session token."""
    from app.modules.team import service as team_svc
    with SessionLocal() as db:
        try:
            res = team_svc.accept_invite(db, token=body.token, password=body.password,
                                         full_name=body.full_name)
        except team_svc.NotFound:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Invite not found") from None
        except team_svc.TeamError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
        db.commit()
    set_auth_cookie(response, res["access_token"])
    return TokenResponse(access_token=res["access_token"], organization_id=res["organization_id"],
                         entity_id=res["entity_id"], role=res["role"])


@router.post("/logout")
def logout(response: Response) -> dict:
    """Clear the session cookie. (httpOnly means the browser JS can't clear it.)"""
    clear_auth_cookie(response)
    return {"ok": True}


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, response: Response) -> TokenResponse:
    with SessionLocal() as db:
        # users carries no RLS; resolving the user's org needs the pre-tenant
        # bootstrap scope (memberships crosses tenants until we know the org).
        set_bootstrap(db)
        user = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
        if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
        # Only ACTIVE memberships grant access — a removed/invited membership must
        # never mint a session (removal IS revocation). Deterministic pick: oldest.
        membership = db.execute(
            select(Membership).where(Membership.user_id == user.id,
                                     Membership.status == "active")
            .order_by(Membership.created_at)
        ).scalars().first()
        if not membership:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No active organization membership")
        # Org resolved — narrow to it for the entity read (no longer bootstrap-wide).
        set_tenant(db, str(membership.organization_id))
        entity = db.execute(
            select(Entity).where(Entity.organization_id == membership.organization_id)
        ).scalars().first()
        principal = Principal(user_id=str(user.id), organization_id=str(membership.organization_id),
                              role=membership.role, email=user.email)
        token = create_access_token(principal)
        set_auth_cookie(response, token)
        return TokenResponse(access_token=token,
                             organization_id=str(membership.organization_id),
                             entity_id=str(entity.id) if entity else "",
                             role=membership.role)
