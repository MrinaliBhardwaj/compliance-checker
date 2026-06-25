"""Evidence & documents (PRD §6.4): documents + document_links."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, uuid_pk
from app.models.types import JSONB


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"))
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    file_url: Mapped[str] = mapped_column(Text, nullable=False)  # S3 key (ap-south-1)
    file_name: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str | None] = mapped_column(String(120))
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)  # exact-dupe detection
    ai_doc_type: Mapped[str | None] = mapped_column(String(40))   # canonical DocType
    ai_extracted: Mapped[dict] = mapped_column(JSONB, default=dict)  # typed per-field extraction
    processing_status: Mapped[str] = mapped_column(String(20), default="processing")  # processing|done|unprocessed|low_ocr_quality
    expiry_date: Mapped[date | None] = mapped_column(Date)  # AI-extracted valid_until
    created_at: Mapped[datetime] = created_at_col()


class DocumentLink(Base):
    __tablename__ = "document_links"

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False)
    obligation_instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("obligation_instances.id", ondelete="CASCADE"), index=True, nullable=False)
    # human-confirmed link (AI only suggests); who confirmed, for audit
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        Index("uq_doc_link", "document_id", "obligation_instance_id", unique=True),
    )
