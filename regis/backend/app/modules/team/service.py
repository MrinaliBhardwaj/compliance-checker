"""
Team service: invite, list, role change, remove (with reassignment), accept.

Preserves the 3-role RBAC model (compliance_admin | head | preparer) and the
existing assignment endpoint. Invariants:
  - an org always keeps >= 1 active compliance_admin (can't demote/remove the last);
  - removing a member never orphans obligations — their owned instances reassign;
  - everything is audited; invites are signed, time-limited tokens (no email needed
    locally — the admin shares the returned link).
"""
from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core import audit
from app.core.security import create_invite_token, hash_password
from app.models.compliance import ObligationInstance
from app.models.tenancy import Entity, Membership, User

ROLES = {"compliance_admin", "head", "preparer"}


class TeamError(Exception):
    """Business-rule violation (HTTP 409)."""


class NotFound(Exception):
    ...


def _active_admin_count(session: Session, organization_id, exclude_membership=None) -> int:
    q = select(func.count()).select_from(Membership).where(
        Membership.organization_id == organization_id,
        Membership.role == "compliance_admin",
        Membership.status == "active",
    )
    if exclude_membership is not None:
        q = q.where(Membership.id != exclude_membership)
    return session.execute(q).scalar_one()


def invite_member(session: Session, *, organization_id, email: str, role: str,
                  full_name: str | None, invited_by) -> dict:
    if role not in ROLES:
        raise TeamError(f"invalid role '{role}'")
    email = email.strip().lower()

    user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        user = User(email=email, full_name=full_name, auth_provider="password")
        session.add(user)
        session.flush()

    membership = session.execute(
        select(Membership).where(Membership.user_id == user.id,
                                 Membership.organization_id == organization_id)
    ).scalar_one_or_none()
    if membership and membership.status == "active":
        raise TeamError("user is already an active member of this organization")
    if membership is None:
        membership = Membership(user_id=user.id, organization_id=organization_id,
                                role=role, status="invited")
        session.add(membership)
    else:
        membership.role = role
        membership.status = "invited"
    session.flush()

    token = create_invite_token(membership_id=str(membership.id),
                                organization_id=str(organization_id), email=email)
    audit.record(session, action="member_invited", organization_id=organization_id,
                 actor_user_id=invited_by, entity_type="membership",
                 entity_id=str(membership.id), meta={"email": email, "role": role})
    return {"membership_id": str(membership.id), "user_id": str(user.id), "email": email,
            "role": role, "status": "invited", "invite_token": token,
            "invite_url": f"/accept?token={token}"}


def list_members(session: Session, *, organization_id) -> list[dict]:
    rows = session.execute(
        select(Membership, User)
        .join(User, Membership.user_id == User.id)
        .where(Membership.organization_id == organization_id)
        .order_by(Membership.created_at)
    ).all()
    return [
        {"membership_id": str(m.id), "user_id": str(u.id), "email": u.email,
         "full_name": u.full_name, "role": m.role, "status": m.status}
        for m, u in rows
    ]


def assignable_users(session: Session, *, organization_id) -> list[dict]:
    """Members eligible to own obligations (active only) — drives the owner picker."""
    return [m for m in list_members(session, organization_id=organization_id)
            if m["status"] == "active"]


def update_role(session: Session, *, organization_id, membership_id, role: str, actor) -> dict:
    if role not in ROLES:
        raise TeamError(f"invalid role '{role}'")
    m = session.get(Membership, membership_id)
    if not m or str(m.organization_id) != str(organization_id):
        raise NotFound()
    # never strip the last admin
    if (m.role == "compliance_admin" and role != "compliance_admin"
            and m.status == "active" and _active_admin_count(session, organization_id) <= 1):
        raise TeamError("cannot change role of the last active admin")
    prior = m.role
    m.role = role
    audit.record(session, action="member_role_changed", organization_id=organization_id,
                 actor_user_id=actor, entity_type="membership", entity_id=str(m.id),
                 meta={"from": prior, "to": role})
    return {"membership_id": str(m.id), "role": role, "status": m.status}


def remove_member(session: Session, *, organization_id, membership_id, reassign_to, actor) -> dict:
    m = session.get(Membership, membership_id)
    if not m or str(m.organization_id) != str(organization_id):
        raise NotFound()
    if (m.role == "compliance_admin" and m.status == "active"
            and _active_admin_count(session, organization_id) <= 1):
        raise TeamError("cannot remove the last active admin")

    # reassign owned obligations so nothing is orphaned (PRD edge case)
    reassigned = 0
    if reassign_to:
        session.get(Membership, reassign_to) if _is_membership(session, reassign_to) else None
        target_user = _resolve_user(session, organization_id, reassign_to)
        if target_user is None:
            raise TeamError("reassign_to is not an active member")
        reassigned = session.execute(
            update(ObligationInstance)
            .where(ObligationInstance.organization_id == organization_id,
                   ObligationInstance.owner_user_id == m.user_id)
            .values(owner_user_id=target_user)
        ).rowcount or 0
    else:
        # no target -> unassign (surfaces as unowned for an admin to pick up)
        reassigned = session.execute(
            update(ObligationInstance)
            .where(ObligationInstance.organization_id == organization_id,
                   ObligationInstance.owner_user_id == m.user_id)
            .values(owner_user_id=None)
        ).rowcount or 0

    m.status = "removed"
    audit.record(session, action="member_removed", organization_id=organization_id,
                 actor_user_id=actor, entity_type="membership", entity_id=str(m.id),
                 meta={"reassigned_instances": reassigned,
                       "reassigned_to": str(reassign_to) if reassign_to else None})
    return {"membership_id": str(m.id), "status": "removed", "reassigned_instances": reassigned}


def _is_membership(session: Session, ident) -> bool:
    return session.get(Membership, ident) is not None


def _resolve_user(session: Session, organization_id, ident):
    """Accept either a membership id or a user id for reassignment target; return the
    active user_id in this org or None."""
    m = session.get(Membership, ident)
    if m and str(m.organization_id) == str(organization_id) and m.status == "active":
        return m.user_id
    # maybe a user id directly
    direct = session.execute(
        select(Membership).where(Membership.user_id == ident,
                                 Membership.organization_id == organization_id,
                                 Membership.status == "active")
    ).scalar_one_or_none()
    return direct.user_id if direct else None


def accept_invite(session: Session, *, token: str, password: str | None,
                  full_name: str | None) -> dict:
    from app.core.db import set_tenant
    from app.core.security import (
        Principal, create_access_token, decode_invite_token, verify_password)
    claims = decode_invite_token(token)
    # The invite token carries its org — scope the session to it so the membership
    # read/update, entity read, and audit insert all satisfy RLS on Postgres. The
    # token is signed, so its org claim is trustworthy for scoping.
    set_tenant(session, str(claims["org"]))
    membership = session.get(Membership, claims["mid"])
    if not membership:
        raise NotFound()
    user = session.get(User, membership.user_id)
    if user is None:
        raise NotFound()

    # Single-use: only a pending invite is acceptable. An already-used token never
    # mints another session, and a removed member's old link never reinstates them.
    if membership.status != "invited":
        raise TeamError("this invite has already been used or is no longer valid")
    if claims.get("email") != user.email:
        raise TeamError("invite does not match this account")

    if user.password_hash is None:
        # brand-new user: first acceptance sets their password
        if not password:
            raise TeamError("a password is required to accept this invite")
        user.password_hash = hash_password(password)
    elif not password or not verify_password(password, user.password_hash):
        # existing account: possession of the link is not identity — the invitee
        # proves the account password (blocks the inviter accepting on their behalf).
        raise TeamError("enter this account's existing password to accept the invite")

    if full_name and not user.full_name:
        user.full_name = full_name
    membership.status = "active"
    audit.record(session, action="invite_accepted",
                 organization_id=membership.organization_id, actor_user_id=user.id,
                 entity_type="membership", entity_id=str(membership.id), meta={})

    entity = session.execute(
        select(Entity).where(Entity.organization_id == membership.organization_id)
    ).scalars().first()
    principal = Principal(user_id=str(user.id), organization_id=str(membership.organization_id),
                          role=membership.role, email=user.email)
    return {"access_token": create_access_token(principal),
            "organization_id": str(membership.organization_id),
            "entity_id": str(entity.id) if entity else "", "role": membership.role,
            "email": user.email}
