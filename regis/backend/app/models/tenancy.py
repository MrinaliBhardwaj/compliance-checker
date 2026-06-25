"""Tenancy & identity (PRD §6.1): organizations, entities, locations, users, memberships."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, created_at_col, uuid_pk
from app.models.types import EncryptedStr


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    plan_tier: Mapped[str] = mapped_column(String(20), default="starter")  # starter|growth|scale
    created_at: Mapped[datetime] = created_at_col()

    entities: Mapped[list[Entity]] = relationship(back_populates="organization")


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    legal_name: Mapped[str] = mapped_column(Text, nullable=False)
    # Field-level encryption for sensitive identifiers (PRD security baseline).
    cin: Mapped[str | None] = mapped_column(EncryptedStr(255))
    nbfc_cor_number: Mapped[str | None] = mapped_column(EncryptedStr(255))
    pan: Mapped[str | None] = mapped_column(EncryptedStr(255))
    nbfc_type: Mapped[str | None] = mapped_column(String(40))
    rbi_layer: Mapped[str | None] = mapped_column(String(10))  # base|middle|upper
    deposit_taking: Mapped[bool | None] = mapped_column(Boolean)
    is_listed: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = created_at_col()

    organization: Mapped[Organization] = relationship(back_populates="entities")
    locations: Mapped[list[Location]] = relationship(back_populates="entity")


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[uuid.UUID] = uuid_pk()
    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(20))  # registered_office | branch
    state: Mapped[str | None] = mapped_column(String(4))  # ISO-style code, e.g. MH
    city: Mapped[str | None] = mapped_column(Text)

    entity: Mapped[Entity] = relationship(back_populates="locations")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(Text)
    auth_provider: Mapped[str] = mapped_column(String(20), default="password")  # password|google|microsoft
    password_hash: Mapped[str | None] = mapped_column(Text)  # null for SSO users
    created_at: Mapped[datetime] = created_at_col()


class Membership(Base):
    __tablename__ = "memberships"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # compliance_admin|head|preparer
    status: Mapped[str] = mapped_column(String(20), default="invited")  # invited|active
    created_at: Mapped[datetime] = created_at_col()
