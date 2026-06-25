"""Declarative base + shared column helpers."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class GUID(TypeDecorator):
    """UUID column that also accepts string input (e.g. ids decoded from a JWT).

    Native uuid on Postgres, CHAR(32) on SQLite — and either a `uuid.UUID` or a
    `str` binds cleanly, so the API boundary never has to coerce by hand.
    """

    impl = Uuid
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None or isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


class Base(DeclarativeBase):
    # Every `Mapped[uuid.UUID]` column uses GUID (string-tolerant) automatically.
    type_annotation_map = {uuid.UUID: GUID}


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, default=uuid.uuid4)


def created_at_col() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
