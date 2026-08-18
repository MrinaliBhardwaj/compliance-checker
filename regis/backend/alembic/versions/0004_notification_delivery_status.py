"""notifications: record delivery outcome, not just a send timestamp

Revision ID: 0004_delivery_status
Revises: 0003_bootstrap_policy
Create Date: 2026-08-18

`sent_at IS NULL` conflated "never attempted" with "attempted and failed" —
and the channel seam raised straight into the worker loop, so a failure left no
trace at all. `delivery_status` (pending|sent|failed) plus `delivery_error`
make the outcome a recorded fact. Backfill maps existing rows from sent_at.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004_delivery_status"
down_revision = "0003_bootstrap_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column(
        "delivery_status", sa.String(10), nullable=False, server_default="pending"))
    op.add_column("notifications", sa.Column("delivery_error", sa.Text(), nullable=True))
    # Existing rows: a sent_at means it went out; anything else stays pending
    # rather than being asserted as failed, which we cannot know retroactively.
    op.execute("UPDATE notifications SET delivery_status = 'sent' WHERE sent_at IS NOT NULL")


def downgrade() -> None:
    op.drop_column("notifications", "delivery_error")
    op.drop_column("notifications", "delivery_status")
