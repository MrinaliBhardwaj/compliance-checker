"""
Per-organization compliance data (PRD §6.3): company_obligations + obligation_instances.

The key data-model insight: a template applied once as a company_obligation spawns
many dated obligation_instances (the recurring occurrences the tracker/dashboard/
reminders run on). Removal is deactivation (is_active=False), never deletion.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, created_at_col, uuid_pk

# obligation_instances.status values (mirrors the instance-generator state machine)
INSTANCE_STATUSES = (
    "pending", "in_progress", "ready_for_review",
    "completed", "overdue", "not_applicable",
)


class CompanyObligation(Base):
    __tablename__ = "company_obligations"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), index=True, nullable=False)
    template_id: Mapped[str] = mapped_column(
        ForeignKey("obligation_templates.template_id"), nullable=False)
    # The (possibly state-expanded) applicability result id, e.g. "lab_pt_deposit__MH".
    applicability_id: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[str | None] = mapped_column(String(4))  # set for state-expanded rows
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # user can mark not-applicable
    applicability_confidence: Mapped[float | None] = mapped_column(Numeric(4, 2))
    rationale: Mapped[str | None] = mapped_column(Text)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_at_col()

    instances: Mapped[list[ObligationInstance]] = relationship(back_populates="company_obligation")

    __table_args__ = (
        # one applicability result per entity (idempotent re-generation)
        Index("uq_company_obl_entity_appl", "entity_id", "applicability_id", unique=True),
    )


class ObligationInstance(Base):
    __tablename__ = "obligation_instances"

    id: Mapped[uuid.UUID] = uuid_pk()
    company_obligation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("company_obligations.id", ondelete="CASCADE"), index=True, nullable=False)
    # denormalized for RLS + fast dashboard queries (PRD)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    period_label: Mapped[str] = mapped_column(String(40), nullable=False)  # "2026-07","2026Q1",...
    due_date: Mapped[date | None] = mapped_column(Date)  # null while awaiting an anchor
    status: Mapped[str] = mapped_column(String(20), default="pending")
    working_day_adjusted: Mapped[bool] = mapped_column(Boolean, default=False)
    generation_source: Mapped[str] = mapped_column(String(20), default="scheduled")
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_at_col()

    company_obligation: Mapped[CompanyObligation] = relationship(back_populates="instances")

    __table_args__ = (
        # the idempotency key from the instance generator
        Index("uq_instance_co_period", "company_obligation_id", "period_label", unique=True),
        # the PRD's dashboard/reminder query index
        Index("ix_instance_org_due_status", "organization_id", "due_date", "status"),
    )
