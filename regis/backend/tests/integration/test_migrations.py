"""
Postgres-only migration tests: the baseline must describe the models exactly.

Skipped unless REGIS_TEST_PG_URL points at a real Postgres. Run locally with:

    REGIS_TEST_PG_URL=postgresql+psycopg://regis:regis@localhost:5432/regis_test \
        python -m pytest tests/integration/test_migrations.py
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import NullPool

PG_URL = os.getenv("REGIS_TEST_PG_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="REGIS_TEST_PG_URL not set (needs Postgres)")


@pytest.fixture
def cfg():
    from alembic.config import Config
    c = Config("alembic.ini")
    c.set_main_option("sqlalchemy.url", PG_URL)
    return c


@pytest.fixture
def migrated(cfg):
    from alembic import command
    command.upgrade(cfg, "head")
    engine = create_engine(PG_URL, future=True, poolclass=NullPool)
    yield engine
    engine.dispose()
    command.downgrade(cfg, "base")


def test_baseline_has_no_drift_from_the_models(migrated, cfg):
    """
    The check `Base.metadata.create_all()` could never provide.

    The old baseline called create_all on the reasoning that migration and ORM
    "can never drift". That held only for a fresh database: create_all skips
    existing tables and never issues an ALTER, so from the second deploy a model
    change applied to nothing, silently. It also left autogenerate with no
    baseline to diff, so every generated migration tried to recreate everything.

    With explicit DDL, autogenerate against a migrated database must produce an
    empty diff. A non-empty one means the models moved without a migration.
    """
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.models import Base

    with migrated.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)

    assert diff == [], (
        "models and migrations have drifted; generate a revision:\n"
        + "\n".join(str(d) for d in diff)
    )


def test_full_chain_applies_and_reverses(cfg):
    """upgrade head then downgrade base must both run clean."""
    from alembic import command

    command.upgrade(cfg, "head")
    engine = create_engine(PG_URL, future=True, poolclass=NullPool)
    with engine.connect() as conn:
        tables = set(inspect(conn).get_table_names())
    assert "organizations" in tables and "audit_log" in tables
    engine.dispose()

    command.downgrade(cfg, "base")
    engine = create_engine(PG_URL, future=True, poolclass=NullPool)
    with engine.connect() as conn:
        remaining = set(inspect(conn).get_table_names()) - {"alembic_version"}
    assert remaining == set(), f"downgrade left tables behind: {sorted(remaining)}"
    engine.dispose()


def test_delivery_status_migration_is_idempotent(cfg, migrated):
    """
    0004 must serve both chains: a fresh database already has the columns from
    the rebased baseline, while one stamped at 0003 does not. Re-running it
    against a database that already has them must not fail.
    """
    from alembic import command

    with migrated.begin() as conn:
        conn.execute(text("ALTER TABLE notifications DROP COLUMN delivery_status"))
        conn.execute(text("ALTER TABLE notifications DROP COLUMN delivery_error"))
        conn.execute(text("UPDATE alembic_version SET version_num = '0003_bootstrap_policy'"))

    command.upgrade(cfg, "head")  # must add them back

    with migrated.connect() as conn:
        cols = {c["name"] for c in inspect(conn).get_columns("notifications")}
    assert {"delivery_status", "delivery_error"} <= cols
