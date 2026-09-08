"""Add organization_id to document_links + enable RLS

Revision ID: 0006_document_link_org_id
Revises: 0005_audit_log_null_org
Create Date: 2026-09-08
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006_document_link_org_id"
down_revision = "0005_audit_log_null_org"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # Add the column (both SQLite and Postgres)
    op.add_column("document_links", sa.Column("organization_id", sa.Uuid(), nullable=True))
    # Backfill from parent document
    op.execute("""
        UPDATE document_links SET organization_id = (
            SELECT d.organization_id FROM documents d
            WHERE d.id = document_links.document_id
        )
    """)
    if bind.dialect.name != "postgresql":
        return
    # Make non-nullable and add RLS
    op.alter_column("document_links", "organization_id", nullable=False)
    op.create_index("ix_document_links_organization_id", "document_links", ["organization_id"])
    op.create_foreign_key("fk_document_links_org", "document_links", "organizations", ["organization_id"], ["id"])
    op.execute("ALTER TABLE document_links ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE document_links FORCE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY document_links_tenant_isolation ON document_links
        USING (organization_id::text = current_setting('app.current_org', true))
        WITH CHECK (organization_id::text = current_setting('app.current_org', true));
    """)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS document_links_tenant_isolation ON document_links;")
        op.execute("ALTER TABLE document_links DISABLE ROW LEVEL SECURITY;")
        op.drop_constraint("fk_document_links_org", "document_links", type_="foreignkey")
        op.drop_index("ix_document_links_organization_id", "document_links")
    op.drop_column("document_links", "organization_id")
