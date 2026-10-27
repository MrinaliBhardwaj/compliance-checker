"""One membership per (organization, user)

Revision ID: 0010_membership_unique
Revises: 0009_lowercase_emails
Create Date: 2026-10-27

The model gained UniqueConstraint("organization_id", "user_id") in 90f81a0 with no
migration. DBs whose 0001 ran the old create_all() after that change already have it;
older ones don't. Guarded on the constraint's name.

If duplicate memberships exist, this stops with the offending pairs rather than
deleting rows: which duplicate to keep (role, status, history) is a human decision.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_membership_unique"
down_revision = "0009_lowercase_emails"
branch_labels = None
depends_on = None

_NAME = "uq_membership_org_user"


def _exists() -> bool:
    insp = sa.inspect(op.get_bind())
    names = {u["name"] for u in insp.get_unique_constraints("memberships")}
    names |= {i["name"] for i in insp.get_indexes("memberships") if i.get("unique")}
    return _NAME in names


def upgrade() -> None:
    if _exists():
        return
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # memberships is under FORCE RLS; the bootstrap scope (0003) lets this read all orgs.
        bind.execute(sa.text("SELECT set_config('app.bootstrap', 'on', true)"))
    dupes = bind.execute(
        sa.text(
            "SELECT organization_id, user_id, count(*) FROM memberships "
            "GROUP BY organization_id, user_id HAVING count(*) > 1"
        )
    ).all()
    if dupes:
        raise RuntimeError(
            f"{len(dupes)} (organization_id, user_id) pairs have duplicate memberships; "
            f"resolve them before upgrading: {[tuple(map(str, d[:2])) for d in dupes[:10]]}"
        )
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("SELECT set_config('app.bootstrap', '', true)"))
        op.create_unique_constraint(_NAME, "memberships", ["organization_id", "user_id"])
    else:
        with op.batch_alter_table("memberships") as batch:
            batch.create_unique_constraint(_NAME, ["organization_id", "user_id"])


def downgrade() -> None:
    if not _exists():
        return
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint(_NAME, "memberships", type_="unique")
    else:
        with op.batch_alter_table("memberships") as batch:
            batch.drop_constraint(_NAME, type_="unique")
