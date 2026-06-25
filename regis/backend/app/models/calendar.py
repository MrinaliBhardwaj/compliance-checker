"""
Calendar support (spec additions): holiday_calendar + event_listeners.

- holiday_calendar feeds the instance generator's working-day adjuster (national/
  RBI/state). Seeded; ops-maintained.
- event_listeners registers the event-driven obligations (21 in the golden run)
  that are NOT pre-generated; an instance is created when the event fires.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, uuid_pk


class HolidayCalendar(Base):
    __tablename__ = "holiday_calendar"

    id: Mapped[uuid.UUID] = uuid_pk()
    holiday_date: Mapped[date] = mapped_column(Date, nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(String(10), default="national")  # national|rbi|state
    state: Mapped[str | None] = mapped_column(String(4))  # set when scope=state

    __table_args__ = (
        Index("uq_holiday_date_scope_state", "holiday_date", "scope", "state", unique=True),
    )


class EventListener(Base):
    __tablename__ = "event_listeners"

    id: Mapped[uuid.UUID] = uuid_pk()
    company_obligation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("company_obligations.id", ondelete="CASCADE"), index=True, nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    due_rule_type: Mapped[str] = mapped_column(String(40))  # days_after_event|before_event|...
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = created_at_col()
