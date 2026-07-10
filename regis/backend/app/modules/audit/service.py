"""
Read side of the append-only audit log (PRD §6.6, job-to-be-done §3:
"get an evidence trail for auditors/RBI inspection, review what changed").

The writes live in app.core.audit; this module only queries. Rows are immutable,
so reads are pure projection + enrichment (actor names, human labels, target
titles). Tenant isolation is enforced by the org filter + the RLS GUC set in
get_db; we never trust the caller for the org id.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.compliance import CompanyObligation, ObligationInstance
from app.models.content import ObligationTemplate
from app.models.evidence import Document
from app.models.system import AuditLog
from app.models.tenancy import Entity, User

# Human-readable labels for the action vocabulary written across the modules.
# Anything missing falls back to a title-cased version of the raw action.
ACTION_LABELS: dict[str, str] = {
    "calendar_generated": "Compliance calendar generated",
    "profile_extracted": "Company profile confirmed",
    "instance_assigned": "Obligation assigned",
    "instance_status_change": "Obligation status changed",
    "document_uploaded": "Evidence uploaded",
    "document_classified": "Evidence classified (AI)",
    "document_classified_manual": "Evidence classified",
    "document_unprocessed": "Evidence parked for manual review",
    "document_linked": "Evidence linked to obligation",
    "document_link_blocked": "Evidence link blocked",
    "document_upload_blocked": "Duplicate upload blocked",
    "member_invited": "Teammate invited",
    "invite_accepted": "Invite accepted",
    "member_role_changed": "Member role changed",
    "member_removed": "Member removed",
    "legal_update_published": "Legal update published",
    "legal_update_reviewed": "Legal update reviewed",
    "reminders_run": "Reminder sweep run",
}

# Actions grouped for the viewer's filter dropdown.
ACTION_GROUPS: dict[str, list[str]] = {
    "Obligations": ["calendar_generated", "instance_assigned", "instance_status_change"],
    "Evidence": ["document_uploaded", "document_classified", "document_classified_manual",
                 "document_unprocessed", "document_linked", "document_link_blocked",
                 "document_upload_blocked"],
    "Team": ["member_invited", "invite_accepted", "member_role_changed", "member_removed"],
    "Legal & system": ["legal_update_published", "legal_update_reviewed",
                        "reminders_run", "profile_extracted"],
}


def label_for(action: str) -> str:
    return ACTION_LABELS.get(action, action.replace("_", " ").capitalize())


def _day_bounds(d: date, *, end: bool) -> datetime:
    """Inclusive day → UTC datetime bound (since=start-of-day, until=end-of-day)."""
    return datetime.combine(d, time.max if end else time.min, tzinfo=timezone.utc)


def _resolve_actors(session: Session, rows: list[AuditLog]) -> dict[str, User]:
    ids = {r.actor_user_id for r in rows if r.actor_user_id is not None}
    if not ids:
        return {}
    users = session.execute(select(User).where(User.id.in_(ids))).scalars().all()
    return {str(u.id): u for u in users}


def _resolve_targets(session: Session, rows: list[AuditLog]) -> dict[tuple[str, str], str]:
    """Best-effort human label per (entity_type, entity_id), batched per type."""
    out: dict[tuple[str, str], str] = {}

    def ids_for(t: str) -> list[str]:
        return [r.entity_id for r in rows if r.entity_type == t and r.entity_id]

    inst_ids = ids_for("obligation_instance")
    if inst_ids:
        for inst, tpl in session.execute(
            select(ObligationInstance, ObligationTemplate)
            .join(CompanyObligation,
                  ObligationInstance.company_obligation_id == CompanyObligation.id)
            .join(ObligationTemplate,
                  CompanyObligation.template_id == ObligationTemplate.template_id)
            .where(ObligationInstance.id.in_(inst_ids))
        ).all():
            label = tpl.title
            if inst.period_label:
                label = f"{tpl.title} — {inst.period_label}"
            out[("obligation_instance", str(inst.id))] = label

    doc_ids = ids_for("document")
    if doc_ids:
        for d in session.execute(
            select(Document).where(Document.id.in_(doc_ids))
        ).scalars().all():
            out[("document", str(d.id))] = d.file_name or "Document"

    ent_ids = ids_for("entity")
    if ent_ids:
        for e in session.execute(
            select(Entity).where(Entity.id.in_(ent_ids))
        ).scalars().all():
            out[("entity", str(e.id))] = e.legal_name

    return out


def _serialize(row: AuditLog, actors: dict[str, User],
               targets: dict[tuple[str, str], str]) -> dict:
    actor = actors.get(str(row.actor_user_id)) if row.actor_user_id else None
    target = targets.get((row.entity_type or "", row.entity_id or ""))
    # membership rows usually carry the affected email in meta — surface it as label.
    if target is None and row.entity_type == "membership":
        target = (row.meta or {}).get("email")
    return {
        "id": str(row.id),
        "action": row.action,
        "action_label": label_for(row.action),
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
        "actor_name": (actor.full_name or actor.email) if actor else "System",
        "actor_email": actor.email if actor else None,
        "target_label": target,
        "meta": row.meta or {},
        "created_at": row.created_at.isoformat(),
    }


def list_events(
    session: Session,
    organization_id: str | uuid.UUID,
    *,
    action: str | None = None,
    actor_user_id: str | None = None,
    entity_type: str | None = None,
    since: date | None = None,
    until: date | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Filtered, paginated audit feed for the org. Newest first."""
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    base = select(AuditLog).where(AuditLog.organization_id == organization_id)
    if action:
        base = base.where(AuditLog.action == action)
    if actor_user_id:
        base = base.where(AuditLog.actor_user_id == actor_user_id)
    if entity_type:
        base = base.where(AuditLog.entity_type == entity_type)
    if since:
        base = base.where(AuditLog.created_at >= _day_bounds(since, end=False))
    if until:
        base = base.where(AuditLog.created_at <= _day_bounds(until, end=True))

    ordered = base.order_by(AuditLog.created_at.desc())
    rows = session.execute(ordered.limit(limit + 1).offset(offset)).scalars().all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    actors = _resolve_actors(session, rows)
    targets = _resolve_targets(session, rows)
    events = [_serialize(r, actors, targets) for r in rows]

    # Free-text filter is applied post-enrichment so it can match actor/target text
    # the DB row doesn't hold. Pagination stays DB-driven; this only narrows a page.
    if q:
        needle = q.lower()
        events = [e for e in events if needle in
                  f"{e['action_label']} {e['actor_name']} {e['target_label'] or ''}".lower()]

    return {"events": events, "limit": limit, "offset": offset, "has_more": has_more}


def events_for_entity(
    session: Session,
    organization_id: str | uuid.UUID,
    *,
    entity_type: str,
    entity_id: str,
) -> list[dict]:
    """Full chronological history for one entity (e.g. an obligation drawer timeline)."""
    rows = session.execute(
        select(AuditLog)
        .where(AuditLog.organization_id == organization_id,
               AuditLog.entity_type == entity_type,
               AuditLog.entity_id == str(entity_id))
        .order_by(AuditLog.created_at.asc())
    ).scalars().all()
    actors = _resolve_actors(session, rows)
    targets = _resolve_targets(session, rows)
    return [_serialize(r, actors, targets) for r in rows]
