"""notifications: record delivery outcome, not just a send timestamp

Revision ID: 0004_delivery_status
Revises: 0003_bootstrap_policy
Create Date: 2026-08-18

`sent_at IS NULL` conflated "never attempted" with "attempted and failed" —
and the channel seam raised straight into the worker loop, so a failure left no
trace at all. `delivery_status` (pending|sent|failed) plus `delivery_error`
make the outcome a recorded fact. Backfill maps existing rows from sent_at.

**Idempotent on purpose.** Baseline 0001 was rebased on the models *after* this
revision landed, so a fresh database already gets both columns from 0001 and
this becomes a no-op. A database still stamped at 0003 has neither and needs
them added. Guarding on the live column list is what lets one chain serve both,
and it is the standard cost of rebaselining a migration history.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004_delivery_status"
down_revision = "0003_bootstrap_policy"
branch_labels = None
depends_on = None

TABLE = "notifications"


def _columns() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    existing = _columns()
    if "delivery_status" not in existing:
        op.add_column(TABLE, sa.Column(
            "delivery_status", sa.String(10), nullable=False, server_default="pending"))
    if "delivery_error" not in existing:
        op.add_column(TABLE, sa.Column("delivery_error", sa.Text(), nullable=True))

    # Existing rows: a sent_at means it went out; anything else stays pending
    # rather than being asserted as failed, which we cannot know retroactively.
    op.execute(
        f"UPDATE {TABLE} SET delivery_status = 'sent' "
        "WHERE sent_at IS NOT NULL AND delivery_status = 'pending'")


def downgrade() -> None:
    existing = _columns()
    if "delivery_error" in existing:
        op.drop_column(TABLE, "delivery_error")
    if "delivery_status" in existing:
        op.drop_column(TABLE, "delivery_status")
