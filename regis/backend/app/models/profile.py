"""
Company profile (spec addition, profile-extraction §11 "Audit").

Stores the structured 32-field profile the applicability engine consumes, PLUS
the raw onboarding input and per-field provenance/confidence — so the profile's
origin is fully reconstructable and the onboarding review screen + re-extraction/
diff flow have a home. One row per entity (the latest committed profile); history
is captured in audit_log.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, uuid_pk
from app.models.types import JSONB


class CompanyProfile(Base):
    __tablename__ = "company_profiles"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), unique=True, nullable=False)
    raw_input: Mapped[dict] = mapped_column(JSONB, default=dict)        # what the user gave
    profile: Mapped[dict] = mapped_column(JSONB, default=dict)          # engine-consumed values
    provenance: Mapped[dict] = mapped_column(JSONB, default=dict)       # per-field source/conf/note
    issues: Mapped[list] = mapped_column(JSONB, default=list)           # consistency contradictions/warnings
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
