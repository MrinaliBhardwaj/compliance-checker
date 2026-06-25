"""
Notifications API: list the caller's notifications + mark read. Reminder/escalation
generation runs in the worker (idempotent nightly); this is the in-app inbox.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.core.deps import DbSession
from app.core.security import CurrentPrincipal, Principal, require_role
from app.models.system import Notification
from app.modules.notify.service import run_reminders

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
def list_notifications(db: DbSession, principal: CurrentPrincipal,
                       unread_only: bool = False) -> list[dict]:
    q = select(Notification).where(
        Notification.organization_id == principal.organization_id,
        Notification.user_id == principal.user_id,
    ).order_by(Notification.created_at.desc())
    rows = db.execute(q).scalars().all()
    if unread_only:
        rows = [n for n in rows if n.read_at is None]
    return [{"id": str(n.id), "type": n.type, "channel": n.channel, "payload": n.payload,
             "sent_at": n.sent_at.isoformat() if n.sent_at else None,
             "read_at": n.read_at.isoformat() if n.read_at else None,
             "created_at": n.created_at.isoformat()} for n in rows]


@router.post("/{notification_id}/read")
def mark_read(notification_id: str, db: DbSession, principal: CurrentPrincipal) -> dict:
    n = db.get(Notification, notification_id)
    if not n or str(n.organization_id) != principal.organization_id \
            or str(n.user_id) != principal.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    n.read_at = datetime.now(timezone.utc)
    return {"id": str(n.id), "read_at": n.read_at.isoformat()}


@router.post("/run-reminders")
def trigger_reminders(db: DbSession,
                      principal: Principal = Depends(require_role("compliance_admin"))) -> dict:
    """Manual trigger for the org's reminder sweep (admin) — same path the worker runs."""
    return run_reminders(db, principal.organization_id, date.today())
