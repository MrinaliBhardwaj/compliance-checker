"""Append-only audit helper. Every state-changing action routes through here."""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.system import AuditLog


def record(
    session: Session,
    *,
    action: str,
    organization_id: uuid.UUID | str | None = None,
    actor_user_id: uuid.UUID | str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    meta: dict | None = None,
) -> AuditLog:
    """Append one immutable audit row. Caller commits with the surrounding txn."""
    row = AuditLog(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        meta=meta or {},
    )
    session.add(row)
    return row
