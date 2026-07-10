"""Login bootstrap: allow reading memberships across tenants before scope exists

Revision ID: 0003_bootstrap_policy
Revises: 0002_rls_audit
Create Date: 2026-07-08

Login must resolve which org a user belongs to before any tenant scope exists,
so it reads `memberships` under a dedicated `app.bootstrap` GUC (set by
app.core.db.set_bootstrap, used only on the login path, filtered by user
identity). This adds that read-only bypass to the memberships policy — WITH CHECK
is unchanged, so bootstrap can never forge or move a membership. No-op off Postgres.
"""
from __future__ import annotations

from alembic import op

revision = "0003_bootstrap_policy"
down_revision = "0002_rls_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP POLICY IF EXISTS memberships_tenant_isolation ON memberships")
    op.execute("""
        CREATE POLICY memberships_tenant_isolation ON memberships
        USING (
            current_setting('app.bootstrap', true) = 'on'
            OR organization_id::text = current_setting('app.current_org', true)
        )
        WITH CHECK (organization_id::text = current_setting('app.current_org', true))
    """)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP POLICY IF EXISTS memberships_tenant_isolation ON memberships")
    op.execute("""
        CREATE POLICY memberships_tenant_isolation ON memberships
        USING (organization_id::text = current_setting('app.current_org', true))
        WITH CHECK (organization_id::text = current_setting('app.current_org', true))
    """)
