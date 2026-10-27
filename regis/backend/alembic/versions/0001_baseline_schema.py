"""baseline schema — all Phase-1 tables

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-24

The baseline is materialized from the SQLAlchemy metadata so the migration and
the ORM models can never drift. Postgres-specific hardening (RLS + append-only
audit_log) is a separate revision (0002) so it can be tested in isolation.
"""
from __future__ import annotations

from alembic import op

from app.models import Base

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
