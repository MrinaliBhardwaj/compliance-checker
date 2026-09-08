"""Allow NULL organization_id in audit_log RLS policy

Revision ID: 0005_audit_log_allow_null_org
Revises: 0004_notifications_payload
Create Date: 2026-09-08

System-level audit events (e.g. failed auth attempts) have no organization_id.
The original policy rejects NULL because NULL = 'anything' is NULL (fails check).
"""
from __future__ import annotations

from alembic import op

revision = "0005_audit_log_null_org"
down_revision = "0004_notifications_payload"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP POLICY IF EXISTS audit_log_tenant_isolation ON audit_log;")
    op.execute("""
        CREATE POLICY audit_log_tenant_isolation ON audit_log
        USING (
            organization_id IS NULL
            OR organization_id::text = current_setting('app.current_org', true)
        )
        WITH CHECK (
            organization_id IS NULL
            OR organization_id::text = current_setting('app.current_org', true)
        );
    """)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP POLICY IF EXISTS audit_log_tenant_isolation ON audit_log;")
    op.execute("""
        CREATE POLICY audit_log_tenant_isolation ON audit_log
        USING (organization_id::text = current_setting('app.current_org', true))
        WITH CHECK (organization_id::text = current_setting('app.current_org', true));
    """)
