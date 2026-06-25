"""
Postgres-only hardening tests: RLS tenant isolation + append-only audit_log.

Skipped unless REGIS_TEST_PG_URL points at a real Postgres (these enforce
guarantees SQLite cannot model). Run locally with:

    REGIS_TEST_PG_URL=postgresql+psycopg://regis:regis@localhost:5432/regis_test \
        python -m pytest tests/integration/test_postgres_hardening.py
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, text

PG_URL = os.getenv("REGIS_TEST_PG_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="REGIS_TEST_PG_URL not set (needs Postgres)")


@pytest.fixture
def pg_engine():
    from alembic import command
    from alembic.config import Config

    engine = create_engine(PG_URL, future=True)
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", PG_URL)
    command.upgrade(cfg, "head")
    yield engine
    command.downgrade(cfg, "base")


def _set_org(conn, org):
    conn.execute(text("SELECT set_config('app.current_org', :o, false)"), {"o": str(org)})


def test_rls_blocks_cross_tenant(pg_engine):
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    with pg_engine.begin() as conn:
        # seed two orgs' rows bypassing RLS as table owner is tricky; use FORCE so even
        # owner is subject to policy — insert under each org scope.
        conn.execute(text("INSERT INTO organizations (id, name, plan_tier, created_at) "
                          "VALUES (:a,'A','starter',now()),(:b,'B','starter',now())"),
                     {"a": org_a, "b": org_b})
        _set_org(conn, org_a)
        conn.execute(text("INSERT INTO notifications (id, organization_id, type, channel, created_at) "
                          "VALUES (:i,:o,'reminder','email',now())"),
                     {"i": uuid.uuid4(), "o": org_a})
    with pg_engine.connect() as conn:
        _set_org(conn, org_a)
        seen_a = conn.execute(text("SELECT count(*) FROM notifications")).scalar_one()
        _set_org(conn, org_b)
        seen_b = conn.execute(text("SELECT count(*) FROM notifications")).scalar_one()
    assert seen_a == 1
    assert seen_b == 0  # org B cannot see org A's rows


def test_audit_log_is_append_only(pg_engine):
    org = uuid.uuid4()
    with pg_engine.begin() as conn:
        conn.execute(text("INSERT INTO organizations (id, name, plan_tier, created_at) "
                          "VALUES (:o,'A','starter',now())"), {"o": org})
        _set_org(conn, org)
        aid = uuid.uuid4()
        conn.execute(text("INSERT INTO audit_log (id, organization_id, action, created_at) "
                          "VALUES (:i,:o,'created',now())"), {"i": aid, "o": org})
    with pg_engine.connect() as conn:
        _set_org(conn, org)
        with pytest.raises(Exception, match="append-only"):
            conn.execute(text("UPDATE audit_log SET action='tampered'"))
    with pg_engine.connect() as conn:
        _set_org(conn, org)
        with pytest.raises(Exception, match="append-only"):
            conn.execute(text("DELETE FROM audit_log"))
