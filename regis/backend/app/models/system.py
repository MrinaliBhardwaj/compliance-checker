"""System & AI (PRD §6.6): audit_log (append-only), notifications, copilot_messages."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, uuid_pk
from app.models.types import JSONB


class AuditLog(Base):
    """
    Append-only, immutable. The migration revokes UPDATE/DELETE and installs a
    trigger blocking mutation — the audit trail IS the compliance evidence.
    """
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(40), nullable=False)  # created|completed|approved|...
    entity_type: Mapped[str | None] = mapped_column(String(40))      # obligation_instance|document|...
    entity_id: Mapped[str | None] = mapped_column(String(120))
    meta: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = created_at_col()


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    type: Mapped[str] = mapped_column(String(20))     # reminder|escalation|legal_update|assignment
    channel: Mapped[str] = mapped_column(String(10))  # email|slack
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()


class CopilotMessage(Base):
    """Append-only conversation log + traceability (retrieved_context, citations)."""
    __tablename__ = "copilot_messages"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String(10))  # user|assistant
    content: Mapped[str | None] = mapped_column(Text)
    intent: Mapped[str | None] = mapped_column(String(30))
    retrieved_context: Mapped[dict] = mapped_column(JSONB, default=dict)  # grounding set
    citations: Mapped[list] = mapped_column(JSONB, default=list)
    confidence: Mapped[float | None] = mapped_column()
    provisional: Mapped[bool | None] = mapped_column()
    escalation: Mapped[str | None] = mapped_column(String(30))
    grounding: Mapped[dict] = mapped_column(JSONB, default=dict)
    model_version: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = created_at_col()
