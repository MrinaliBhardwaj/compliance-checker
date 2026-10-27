"""baseline schema — all Phase-1 tables, frozen as explicit DDL (schema as of 0005)

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-22

This used to run Base.metadata.create_all() of the *live* models, so a fresh DB
got every later model change up front and the later migrations had to be guarded
against their own changes (BUG-03), while existing DBs never got model-only changes
(BUG-29). It is now the schema as it stood at 0005, written out, so later revisions
are ordinary: 0006 adds document_links.organization_id, 0008 obligation_instances.
submitted_by, and 0010 the memberships (organization_id, user_id) unique constraint.

Rendered with Alembic autogenerate from the models, then frozen. GUID and EncryptedStr
are plain Uuid / String(255) at the database level. RLS and the audit trigger are
separate revisions (0002...).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "holiday_calendar",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("holiday_date", sa.Date(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("scope", sa.String(length=10), nullable=False),
        sa.Column("state", sa.String(length=4), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_holiday_date_scope_state",
        "holiday_calendar",
        ["holiday_date", "scope", "state"],
        unique=True,
    )
    op.create_table(
        "law_library",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("regulator", sa.String(length=40), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("reference_url", sa.Text(), nullable=True),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("plan_tier", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=True),
        sa.Column("auth_provider", sa.String(length=20), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=True),
        sa.Column("entity_id", sa.String(length=120), nullable=True),
        sa.Column(
            "metadata",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_audit_log_organization_id"), "audit_log", ["organization_id"], unique=False
    )
    op.create_table(
        "copilot_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("intent", sa.String(length=30), nullable=True),
        sa.Column(
            "retrieved_context",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "citations",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("provisional", sa.Boolean(), nullable=True),
        sa.Column("escalation", sa.String(length=30), nullable=True),
        sa.Column(
            "grounding",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("model_version", sa.String(length=40), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_copilot_messages_organization_id"),
        "copilot_messages",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "entities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("legal_name", sa.Text(), nullable=False),
        sa.Column("cin", sa.String(length=255), nullable=True),
        sa.Column("nbfc_cor_number", sa.String(length=255), nullable=True),
        sa.Column("pan", sa.String(length=255), nullable=True),
        sa.Column("nbfc_type", sa.String(length=40), nullable=True),
        sa.Column("rbi_layer", sa.String(length=10), nullable=True),
        sa.Column("deposit_taking", sa.Boolean(), nullable=True),
        sa.Column("is_listed", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_entities_organization_id"), "entities", ["organization_id"], unique=False
    )
    op.create_table(
        "legal_updates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("law_id", sa.String(length=80), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("published_date", sa.Date(), nullable=True),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("ai_impact_note", sa.Text(), nullable=True),
        sa.Column(
            "affects_filter",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["law_id"],
            ["law_library.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_memberships_organization_id"), "memberships", ["organization_id"], unique=False
    )
    op.create_index(op.f("ix_memberships_user_id"), "memberships", ["user_id"], unique=False)
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("channel", sa.String(length=10), nullable=False),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_notifications_organization_id"), "notifications", ["organization_id"], unique=False
    )
    op.create_table(
        "obligation_templates",
        sa.Column("template_id", sa.String(length=80), nullable=False),
        sa.Column("law_id", sa.String(length=80), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("frequency", sa.String(length=20), nullable=False),
        sa.Column(
            "due_rule",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "applicability_rule",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "required_evidence",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("default_owner_role", sa.String(length=20), nullable=False),
        sa.Column("risk_level", sa.String(length=10), nullable=False),
        sa.Column("penalty_note", sa.Text(), nullable=True),
        sa.Column("form_reference", sa.String(length=80), nullable=True),
        sa.Column(
            "dependencies",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("verification_status", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(
            ["law_id"],
            ["law_library.id"],
        ),
        sa.PrimaryKeyConstraint("template_id"),
    )
    op.create_index(
        op.f("ix_obligation_templates_law_id"), "obligation_templates", ["law_id"], unique=False
    )
    op.create_table(
        "company_obligations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.String(length=80), nullable=False),
        sa.Column("applicability_id", sa.String(length=120), nullable=False),
        sa.Column("state", sa.String(length=4), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("applicability_confidence", sa.Numeric(precision=4, scale=2), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["obligation_templates.template_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_company_obligations_entity_id"), "company_obligations", ["entity_id"], unique=False
    )
    op.create_index(
        op.f("ix_company_obligations_organization_id"),
        "company_obligations",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "uq_company_obl_entity_appl",
        "company_obligations",
        ["entity_id", "applicability_id"],
        unique=True,
    )
    op.create_table(
        "company_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column(
            "raw_input",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "profile",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "provenance",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "issues",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("confirmed_by", sa.Uuid(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entity_id"),
    )
    op.create_index(
        op.f("ix_company_profiles_organization_id"),
        "company_profiles",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("uploaded_by", sa.Uuid(), nullable=True),
        sa.Column("file_url", sa.Text(), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.String(length=120), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("ai_doc_type", sa.String(length=40), nullable=True),
        sa.Column(
            "ai_extracted",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("processing_status", sa.String(length=20), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_documents_organization_id"), "documents", ["organization_id"], unique=False
    )
    op.create_index(op.f("ix_documents_sha256"), "documents", ["sha256"], unique=False)
    op.create_table(
        "legal_update_status",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("legal_update_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["legal_update_id"], ["legal_updates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_legal_update_status_organization_id"),
        "legal_update_status",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "uq_legal_status_org_update",
        "legal_update_status",
        ["organization_id", "legal_update_id"],
        unique=True,
    )
    op.create_table(
        "locations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("state", sa.String(length=4), nullable=True),
        sa.Column("city", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_locations_entity_id"), "locations", ["entity_id"], unique=False)
    op.create_table(
        "event_listeners",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_obligation_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("due_rule_type", sa.String(length=40), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["company_obligation_id"], ["company_obligations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_event_listeners_company_obligation_id"),
        "event_listeners",
        ["company_obligation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_event_listeners_organization_id"),
        "event_listeners",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "obligation_instances",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_obligation_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("period_label", sa.String(length=40), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("working_day_adjusted", sa.Boolean(), nullable=False),
        sa.Column("generation_source", sa.String(length=20), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by", sa.Uuid(), nullable=True),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["company_obligation_id"], ["company_obligations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["completed_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_instance_org_due_status",
        "obligation_instances",
        ["organization_id", "due_date", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_obligation_instances_company_obligation_id"),
        "obligation_instances",
        ["company_obligation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_obligation_instances_organization_id"),
        "obligation_instances",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "uq_instance_co_period",
        "obligation_instances",
        ["company_obligation_id", "period_label"],
        unique=True,
    )
    op.create_table(
        "document_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("obligation_instance_id", sa.Uuid(), nullable=False),
        sa.Column("confirmed_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["obligation_instance_id"], ["obligation_instances.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_document_links_document_id"), "document_links", ["document_id"], unique=False
    )
    op.create_index(
        op.f("ix_document_links_obligation_instance_id"),
        "document_links",
        ["obligation_instance_id"],
        unique=False,
    )
    op.create_index(
        "uq_doc_link", "document_links", ["document_id", "obligation_instance_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_doc_link", table_name="document_links")
    op.drop_index(op.f("ix_document_links_obligation_instance_id"), table_name="document_links")
    op.drop_index(op.f("ix_document_links_document_id"), table_name="document_links")
    op.drop_table("document_links")
    op.drop_index("uq_instance_co_period", table_name="obligation_instances")
    op.drop_index(
        op.f("ix_obligation_instances_organization_id"), table_name="obligation_instances"
    )
    op.drop_index(
        op.f("ix_obligation_instances_company_obligation_id"), table_name="obligation_instances"
    )
    op.drop_index("ix_instance_org_due_status", table_name="obligation_instances")
    op.drop_table("obligation_instances")
    op.drop_index(op.f("ix_event_listeners_organization_id"), table_name="event_listeners")
    op.drop_index(op.f("ix_event_listeners_company_obligation_id"), table_name="event_listeners")
    op.drop_table("event_listeners")
    op.drop_index(op.f("ix_locations_entity_id"), table_name="locations")
    op.drop_table("locations")
    op.drop_index("uq_legal_status_org_update", table_name="legal_update_status")
    op.drop_index(op.f("ix_legal_update_status_organization_id"), table_name="legal_update_status")
    op.drop_table("legal_update_status")
    op.drop_index(op.f("ix_documents_sha256"), table_name="documents")
    op.drop_index(op.f("ix_documents_organization_id"), table_name="documents")
    op.drop_table("documents")
    op.drop_index(op.f("ix_company_profiles_organization_id"), table_name="company_profiles")
    op.drop_table("company_profiles")
    op.drop_index("uq_company_obl_entity_appl", table_name="company_obligations")
    op.drop_index(op.f("ix_company_obligations_organization_id"), table_name="company_obligations")
    op.drop_index(op.f("ix_company_obligations_entity_id"), table_name="company_obligations")
    op.drop_table("company_obligations")
    op.drop_index(op.f("ix_obligation_templates_law_id"), table_name="obligation_templates")
    op.drop_table("obligation_templates")
    op.drop_index(op.f("ix_notifications_organization_id"), table_name="notifications")
    op.drop_table("notifications")
    op.drop_index(op.f("ix_memberships_user_id"), table_name="memberships")
    op.drop_index(op.f("ix_memberships_organization_id"), table_name="memberships")
    op.drop_table("memberships")
    op.drop_table("legal_updates")
    op.drop_index(op.f("ix_entities_organization_id"), table_name="entities")
    op.drop_table("entities")
    op.drop_index(op.f("ix_copilot_messages_organization_id"), table_name="copilot_messages")
    op.drop_table("copilot_messages")
    op.drop_index(op.f("ix_audit_log_organization_id"), table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_table("users")
    op.drop_table("organizations")
    op.drop_table("law_library")
    op.drop_index("uq_holiday_date_scope_state", table_name="holiday_calendar")
    op.drop_table("holiday_calendar")
