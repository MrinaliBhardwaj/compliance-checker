"""
Audit trail API: the evidence trail auditors/RBI inspection ask for (PRD §3).
Read-only over the append-only log. Restricted to admin + head — the audit feed
is a CFO/compliance-owner artifact, not a preparer surface (PRD role matrix).
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query

from app.core.deps import DbSession
from app.core.security import Principal, require_role
from app.modules.audit import service as svc

router = APIRouter(prefix="/audit", tags=["audit"])

# Audit visibility = compliance owners only.
_viewer = require_role("compliance_admin", "head")


@router.get("/actions")
def action_catalog(_: Principal = Depends(_viewer)) -> dict:
    """Labels + groupings so the viewer can build its filter dropdown."""
    return {"labels": svc.ACTION_LABELS, "groups": svc.ACTION_GROUPS}


@router.get("")
def list_audit(
    db: DbSession,
    principal: Principal = Depends(_viewer),
    action: str | None = None,
    actor_user_id: str | None = None,
    entity_type: str | None = None,
    since: date | None = None,
    until: date | None = None,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    return svc.list_events(
        db, principal.organization_id, action=action, actor_user_id=actor_user_id,
        entity_type=entity_type, since=since, until=until, q=q, limit=limit, offset=offset)


@router.get("/entity/{entity_type}/{entity_id}")
def entity_timeline(entity_type: str, entity_id: str, db: DbSession,
                    principal: Principal = Depends(_viewer)) -> list[dict]:
    """Chronological history for a single entity (e.g. an obligation instance)."""
    return svc.events_for_entity(
        db, principal.organization_id, entity_type=entity_type, entity_id=entity_id)
