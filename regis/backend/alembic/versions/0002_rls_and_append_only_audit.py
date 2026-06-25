"""Postgres hardening: RLS tenant isolation + append-only audit_log

Revision ID: 0002_rls_audit
Revises: 0001_baseline
Create Date: 2026-06-24

No-op on non-Postgres dialects (SQLite test path). On Postgres:
  - enable RLS on every tenant table and add a policy keyed to the
    `app.current_org` session GUC (set per request in app.core.db);
  - block UPDATE/DELETE on audit_log via a trigger so the audit trail is
    truly append-only (the audit trail IS the compliance evidence).
"""
from __future__ import annotations

from alembic import op

revision = "0002_rls_audit"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

# Tables scoped directly by organization_id.
TENANT_TABLES = [
    "entities", "memberships", "company_obligations", "obligation_instances",
    "company_profiles", "documents", "legal_update_status", "audit_log",
    "notifications", "copilot_messages", "event_listeners",
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # --- Row-level security: one tenant per session GUC ---
    for tbl in TENANT_TABLES:
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY {tbl}_tenant_isolation ON {tbl}
            USING (organization_id::text = current_setting('app.current_org', true))
            WITH CHECK (organization_id::text = current_setting('app.current_org', true))
        """)

    # --- Append-only audit_log: block UPDATE and DELETE ---
    op.execute("""
        CREATE OR REPLACE FUNCTION regis_block_audit_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only (% blocked)', TG_OP;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER audit_log_no_update_delete
        BEFORE UPDATE OR DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION regis_block_audit_mutation()
    """)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_update_delete ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS regis_block_audit_mutation()")
    for tbl in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {tbl}_tenant_isolation ON {tbl}")
        op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY")
