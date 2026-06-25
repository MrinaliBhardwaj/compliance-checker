"""
Team API. Invite / role / remove are compliance_admin only (PRD §10: invite &
manage team). Listing members is admin + head (head needs team visibility for
oversight). Owner assignment itself stays on the obligations router (admin only).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from app.core.deps import DbSession
from app.core.security import Principal, require_role
from app.modules.team import service as svc

router = APIRouter(prefix="/team", tags=["team"])

_admin = require_role("compliance_admin")
_viewer = require_role("compliance_admin", "head")


class InviteBody(BaseModel):
    email: EmailStr
    role: str
    full_name: str | None = None


@router.post("/invite")
def invite(body: InviteBody, db: DbSession, principal: Principal = Depends(_admin)) -> dict:
    try:
        return svc.invite_member(db, organization_id=principal.organization_id,
                                 email=str(body.email), role=body.role,
                                 full_name=body.full_name, invited_by=principal.user_id)
    except svc.TeamError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))


@router.get("/members")
def members(db: DbSession, principal: Principal = Depends(_viewer)) -> list[dict]:
    return svc.list_members(db, organization_id=principal.organization_id)


@router.get("/assignable")
def assignable(db: DbSession, principal: Principal = Depends(_viewer)) -> list[dict]:
    """Active members eligible to own obligations (owner picker)."""
    return svc.assignable_users(db, organization_id=principal.organization_id)


class RoleBody(BaseModel):
    role: str


@router.patch("/members/{membership_id}/role")
def change_role(membership_id: str, body: RoleBody, db: DbSession,
                principal: Principal = Depends(_admin)) -> dict:
    try:
        return svc.update_role(db, organization_id=principal.organization_id,
                               membership_id=membership_id, role=body.role,
                               actor=principal.user_id)
    except svc.NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    except svc.TeamError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))


class RemoveBody(BaseModel):
    reassign_to: str | None = None   # membership id or user id of the new owner


@router.post("/members/{membership_id}/remove")
def remove(membership_id: str, body: RemoveBody, db: DbSession,
           principal: Principal = Depends(_admin)) -> dict:
    try:
        return svc.remove_member(db, organization_id=principal.organization_id,
                                 membership_id=membership_id, reassign_to=body.reassign_to,
                                 actor=principal.user_id)
    except svc.NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    except svc.TeamError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
