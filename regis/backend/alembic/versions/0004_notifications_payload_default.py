"""add server default for notifications.payload

Revision ID: 0004_notifications_payload_default
Revises: 0003_bootstrap_policy
Create Date: 2026-09-08

Sets a server-side default for the `payload` JSONB column so raw SQL
inserts that omit the column receive an empty JSON object instead of NULL.
"""
from __future__ import annotations

from alembic import op

revision = "0004_notifications_payload"
down_revision = "0003_bootstrap_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE notifications ALTER COLUMN payload SET DEFAULT '{}'::jsonb;")


def downgrade() -> None:
    op.execute("ALTER TABLE notifications ALTER COLUMN payload DROP DEFAULT;")
