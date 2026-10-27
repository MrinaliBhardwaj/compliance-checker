"""Lowercase stored user emails (emails now match case-insensitively)

Revision ID: 0009_lowercase_emails
Revises: 0008_submitted_by
Create Date: 2026-10-27

Signup used to store the email as typed while invites lowercased it. The API now
lowercases everywhere, so existing rows are brought in line. A mixed-case row whose
lowercase form already belongs to another user is left alone: those are two accounts
for one person and need a human to merge them (`users` has no RLS, so this is one
statement on either dialect).
"""

from __future__ import annotations

from alembic import op

revision = "0009_lowercase_emails"
down_revision = "0008_submitted_by"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE users SET email = lower(email)
        WHERE email <> lower(email)
          AND NOT EXISTS (
              SELECT 1 FROM users other
              WHERE lower(other.email) = lower(users.email) AND other.id <> users.id
          )
        """)


def downgrade() -> None:
    # The original casing isn't recorded, and lowercase addresses still work.
    pass
