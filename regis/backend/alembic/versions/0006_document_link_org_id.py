"""Add organization_id to document_links + enable RLS

Revision ID: 0006_document_link_org_id
Revises: 0005_audit_log_null_org
Create Date: 2026-09-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_document_link_org_id"
down_revision = "0005_audit_log_null_org"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    columns = [c["name"] for c in insp.get_columns("document_links")]

    if "organization_id" not in columns:
        # Add the column (both SQLite and Postgres)
        op.add_column("document_links", sa.Column("organization_id", sa.Uuid(), nullable=True))
        # Backfill from parent document
        op.execute("""
            UPDATE document_links SET organization_id = (
                SELECT d.organization_id FROM documents d
                WHERE d.id = document_links.document_id
            )
        """)
        if bind.dialect.name == "postgresql":
            # Make non-nullable and add constraints
            op.alter_column("document_links", "organization_id", nullable=False)
            op.create_index(
                "ix_document_links_organization_id", "document_links", ["organization_id"]
            )
            op.create_foreign_key(
                "fk_document_links_org",
                "document_links",
                "organizations",
                ["organization_id"],
                ["id"],
            )
        else:
            # SQLite: same end state via a table rebuild (no in-place NOT NULL / FK).
            with op.batch_alter_table("document_links") as batch:
                batch.alter_column("organization_id", existing_type=sa.Uuid(), nullable=False)
                batch.create_foreign_key(
                    "fk_document_links_org", "organizations", ["organization_id"], ["id"]
                )
            op.create_index(
                "ix_document_links_organization_id", "document_links", ["organization_id"]
            )

    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE document_links ENABLE ROW LEVEL SECURITY;")
        op.execute("ALTER TABLE document_links FORCE ROW LEVEL SECURITY;")
        op.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_policies
                    WHERE tablename = 'document_links' AND policyname = 'document_links_tenant_isolation'
                ) THEN
                    CREATE POLICY document_links_tenant_isolation ON document_links
                    USING (organization_id::text = current_setting('app.current_org', true))
                    WITH CHECK (organization_id::text = current_setting('app.current_org', true));
                END IF;
            END $$;
        """)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS document_links_tenant_isolation ON document_links;")
        op.execute("ALTER TABLE document_links NO FORCE ROW LEVEL SECURITY;")
        op.execute("ALTER TABLE document_links DISABLE ROW LEVEL SECURITY;")
        # The FK is `fk_document_links_org` when this revision added it, but
        # `document_links_organization_id_fkey` on fresh DBs where 0001's create_all
        # already built the column. Dropping the column takes its index and FK with
        # it under either name.
        op.execute("ALTER TABLE document_links DROP COLUMN IF EXISTS organization_id;")
    else:
        # SQLite: the column has an index and FK, so drop it via a table rebuild (index
        # first, or the rebuild re-creates it on the missing column).
        indexes = {i["name"] for i in sa.inspect(bind).get_indexes("document_links")}
        with op.batch_alter_table("document_links") as batch:
            if "ix_document_links_organization_id" in indexes:
                batch.drop_index("ix_document_links_organization_id")
            batch.drop_column("organization_id")
