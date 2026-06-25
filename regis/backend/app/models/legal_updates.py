"""Legal updates (PRD §6.5): legal_updates (master feed) + legal_update_status (per-org)."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, uuid_pk
from app.models.types import JSONB


class LegalUpdate(Base):
    __tablename__ = "legal_updates"

    id: Mapped[uuid.UUID] = uuid_pk()
    law_id: Mapped[str | None] = mapped_column(ForeignKey("law_library.id"))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    published_date: Mapped[date | None] = mapped_column(Date)
    ai_summary: Mapped[str | None] = mapped_column(Text)       # content-team reviewed before publish
    ai_impact_note: Mapped[str | None] = mapped_column(Text)
    affects_filter: Mapped[dict] = mapped_column(JSONB, default=dict)  # profile match criteria
    created_at: Mapped[datetime] = created_at_col()


class LegalUpdateStatus(Base):
    __tablename__ = "legal_update_status"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    legal_update_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("legal_updates.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(Text, default="new")  # new|reviewed|applicable|not_applicable
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("uq_legal_status_org_update", "organization_id", "legal_update_id", unique=True),
    )
