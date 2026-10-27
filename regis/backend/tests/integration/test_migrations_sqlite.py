"""Integration — the Alembic chain runs on SQLite too (the tests-only dialect).

Postgres-only steps (RLS, triggers, jsonb defaults) must skip themselves on SQLite,
so `alembic upgrade head` / `downgrade base` work for local quickstarts and here.
"""

import os
import tempfile

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_upgrade_and_downgrade_on_sqlite():
    """BUG-30: 0004 ran `ALTER COLUMN ... SET DEFAULT '{}'::jsonb` unguarded."""
    with tempfile.TemporaryDirectory() as d:
        url = f"sqlite+pysqlite:///{os.path.join(d, 'chain.db')}"
        cfg = Config(os.path.join(_BACKEND, "alembic.ini"))
        cfg.set_main_option("script_location", os.path.join(_BACKEND, "alembic"))
        cfg.set_main_option("sqlalchemy.url", url)

        command.upgrade(cfg, "head")
        eng = create_engine(url)
        tables = set(inspect(eng).get_table_names())
        assert {"obligation_instances", "users", "notifications"} <= tables
        cols = {c["name"] for c in inspect(eng).get_columns("obligation_instances")}
        assert "submitted_by" in cols

        command.downgrade(cfg, "base")
        assert set(inspect(eng).get_table_names()) <= {"alembic_version"}
        eng.dispose()


def test_migrated_schema_matches_the_models():
    """BUG-29: 0001 is frozen DDL, so the chain itself must produce the models' schema.
    Any model change without a migration shows up here as a difference."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.models import Base

    with tempfile.TemporaryDirectory() as d:
        url = f"sqlite+pysqlite:///{os.path.join(d, 'chain.db')}"
        cfg = Config(os.path.join(_BACKEND, "alembic.ini"))
        cfg.set_main_option("script_location", os.path.join(_BACKEND, "alembic"))
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "head")
        eng = create_engine(url)
        with eng.connect() as c:
            ctx = MigrationContext.configure(c, opts={"compare_type": True})
            assert compare_metadata(ctx, Base.metadata) == []
        eng.dispose()
