"""
Compliance content library (PRD §6.2): law_library + obligation_templates.

This is the curated master content. `verification_status` is the DRAFT_UNVERIFIED
content gate, encoded as a column the engines read at runtime — not a doc note.
A template is promoted to VERIFIED only by a content-team action (its own audited
mutation), never by application code or the seed loader.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.types import JSONB


class LawLibrary(Base):
    __tablename__ = "law_library"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)  # natural key, e.g. law_rbi_sbr
    name: Mapped[str] = mapped_column(Text, nullable=False)
    regulator: Mapped[str] = mapped_column(String(40))  # RBI|MCA|Income Tax|EPFO|State|SEBI...
    category: Mapped[str] = mapped_column(String(20))    # rbi|corporate|tax|labour|fema
    reference_url: Mapped[str | None] = mapped_column(Text)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    templates: Mapped[list[ObligationTemplate]] = relationship(back_populates="law")


class ObligationTemplate(Base):
    __tablename__ = "obligation_templates"

    template_id: Mapped[str] = mapped_column(String(80), primary_key=True)  # natural key
    law_id: Mapped[str] = mapped_column(ForeignKey("law_library.id"), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    frequency: Mapped[str] = mapped_column(String(20))  # one_time|monthly|quarterly|...|event_based
    due_rule: Mapped[dict] = mapped_column(JSONB, nullable=False)
    applicability_rule: Mapped[dict] = mapped_column(JSONB, nullable=False)
    required_evidence: Mapped[list] = mapped_column(JSONB, default=list)
    default_owner_role: Mapped[str] = mapped_column(String(20))  # preparer|compliance_admin
    risk_level: Mapped[str] = mapped_column(String(10), default="medium")
    penalty_note: Mapped[str | None] = mapped_column(Text)
    form_reference: Mapped[str | None] = mapped_column(String(80))
    dependencies: Mapped[list] = mapped_column(JSONB, default=list)
    # The content gate. Ships DRAFT_UNVERIFIED; only content team flips it.
    verification_status: Mapped[str] = mapped_column(String(20), default="DRAFT_UNVERIFIED")

    law: Mapped[LawLibrary] = relationship(back_populates="templates")
