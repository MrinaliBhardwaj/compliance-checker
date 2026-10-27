"""Reset stored `overdue` statuses to `pending`

Revision ID: 0007_unstore_overdue
Revises: 0006_document_link_org_id
Create Date: 2026-10-27

Overdue is computed on read (lifecycle.effective_status), but the nightly worker
used to store it, which hid those rows from the escalation run. Put them back to
`pending`; the read path shows them as overdue again. The pending/in_progress
distinction for these rows is lost, which is accepted.

obligation_instances is under FORCE ROW LEVEL SECURITY, so on Postgres an UPDATE
without `app.current_org` would match no rows and succeed silently. Run it once per
org inside that org's scope (organizations itself has no RLS).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_unstore_overdue"
down_revision = "0006_document_link_org_id"
branch_labels = None
depends_on = None

_RESET = "UPDATE obligation_instances SET status = 'pending' WHERE status = 'overdue'"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        bind.execute(sa.text(_RESET))
        return
    org_ids = bind.execute(sa.text("SELECT id FROM organizations")).scalars().all()
    for org_id in org_ids:
        bind.execute(
            sa.text("SELECT set_config('app.current_org', :org, true)"), {"org": str(org_id)}
        )
        bind.execute(sa.text(_RESET + " AND organization_id = :org"), {"org": org_id})
    # Don't leave a tenant scope behind for the rest of the migration transaction.
    bind.execute(sa.text("SELECT set_config('app.current_org', '', true)"))


def downgrade() -> None:
    # Data-only fix: which rows were overdue isn't recorded, and nothing needs it back.
    pass
