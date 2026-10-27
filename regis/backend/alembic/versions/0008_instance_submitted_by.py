"""Record who submitted an instance (maker), for the maker != checker rule

Revision ID: 0008_submitted_by
Revises: 0007_unstore_overdue
Create Date: 2026-10-27

0001 builds the baseline with create_all() of the live models, so on a fresh DB the
column already exists when this runs. Guard every step (see CURRENT_STATUS §8 rule 6).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_submitted_by"
down_revision = "0007_unstore_overdue"
branch_labels = None
depends_on = None


def _has_column() -> bool:
    cols = sa.inspect(op.get_bind()).get_columns("obligation_instances")
    return any(c["name"] == "submitted_by" for c in cols)


def upgrade() -> None:
    if _has_column():
        return
    op.add_column("obligation_instances", sa.Column("submitted_by", sa.Uuid(), nullable=True))
    if op.get_bind().dialect.name == "postgresql":
        op.create_foreign_key(
            "fk_obligation_instances_submitted_by",
            "obligation_instances",
            "users",
            ["submitted_by"],
            ["id"],
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        # Drops the FK too, whichever name it has (create_all's or this revision's).
        op.execute("ALTER TABLE obligation_instances DROP COLUMN IF EXISTS submitted_by")
    elif _has_column():
        # SQLite can't drop a column that carries a FK in place; batch mode rebuilds the table.
        with op.batch_alter_table("obligation_instances") as batch:
            batch.drop_column("submitted_by")
