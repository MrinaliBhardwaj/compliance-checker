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
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

PG_URL = os.getenv("REGIS_TEST_PG_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="REGIS_TEST_PG_URL not set (needs Postgres)")


@pytest.fixture
def pg_engine():
    from alembic.config import Config

    from alembic import command

    # NullPool: session GUCs (app.current_org / app.bootstrap) must not leak
    # between logical connections via pooling — "fresh connection" tests rely
    # on genuinely fresh sessions.
    engine = create_engine(PG_URL, future=True, poolclass=NullPool)
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
        conn.execute(text("INSERT INTO notifications (id, organization_id, type, channel, payload, created_at) "
                          "VALUES (:i,:o,'reminder','email','{}'::jsonb,now())"),
                     {"i": uuid.uuid4(), "o": org_a})
    with pg_engine.connect() as conn:
        _set_org(conn, org_a)
        seen_a = conn.execute(text("SELECT count(*) FROM notifications")).scalar_one()
        _set_org(conn, org_b)
        seen_b = conn.execute(text("SELECT count(*) FROM notifications")).scalar_one()
    assert seen_a == 1
    assert seen_b == 0  # org B cannot see org A's rows


def _new_org(conn) -> uuid.UUID:
    org = uuid.uuid4()
    conn.execute(text("INSERT INTO organizations (id, name, plan_tier, created_at) "
                      "VALUES (:o,'A','starter',now())"), {"o": org})
    return org


def test_signup_pattern_requires_org_scope(pg_engine):
    """H1: a tenant insert with no GUC set is blocked by FORCE RLS; scoping the
    session to the just-created org (the signup pattern) lets it through."""
    with pg_engine.begin() as conn:
        org = _new_org(conn)
        user = uuid.uuid4()
        conn.execute(text("INSERT INTO users (id, email, auth_provider, created_at) "
                          "VALUES (:u,'a@x.example','password',now())"), {"u": user})
        # no app.current_org set -> membership insert violates the policy
        with pytest.raises(DBAPIError):
            conn.execute(text(
                "INSERT INTO memberships (id, user_id, organization_id, role, status, created_at) "
                "VALUES (:i,:u,:o,'compliance_admin','active',now())"),
                {"i": uuid.uuid4(), "u": user, "o": org})
    with pg_engine.begin() as conn:
        org = _new_org(conn)
        user = uuid.uuid4()
        conn.execute(text("INSERT INTO users (id, email, auth_provider, created_at) "
                          "VALUES (:u,'b@x.example','password',now())"), {"u": user})
        _set_org(conn, org)  # signup scopes to the new org before inserting
        conn.execute(text(
            "INSERT INTO memberships (id, user_id, organization_id, role, status, created_at) "
            "VALUES (:i,:u,:o,'compliance_admin','active',now())"),
            {"i": uuid.uuid4(), "u": user, "o": org})
        conn.execute(text("INSERT INTO entities (id, organization_id, legal_name, created_at) "
                          "VALUES (:e,:o,'Acme Ltd',now())"), {"e": uuid.uuid4(), "o": org})


def test_login_bootstrap_reads_membership_cross_tenant(pg_engine):
    """H1: login resolves user->org via a bootstrap-scoped membership read; without
    bootstrap and without a tenant GUC the same read returns nothing. Bootstrap is
    read-only — it must not permit forging a membership."""
    with pg_engine.begin() as conn:
        org = _new_org(conn)
        user = uuid.uuid4()
        conn.execute(text("INSERT INTO users (id, email, auth_provider, created_at) "
                          "VALUES (:u,'c@x.example','password',now())"), {"u": user})
        _set_org(conn, org)
        conn.execute(text(
            "INSERT INTO memberships (id, user_id, organization_id, role, status, created_at) "
            "VALUES (:i,:u,:o,'preparer','active',now())"),
            {"i": uuid.uuid4(), "u": user, "o": org})

    with pg_engine.connect() as conn:
        # no scope at all -> RLS hides the row (the original H1 failure at login)
        blind = conn.execute(text("SELECT count(*) FROM memberships WHERE user_id=:u"),
                             {"u": user}).scalar_one()
        assert blind == 0
        # bootstrap scope -> login can resolve the membership
        conn.execute(text("SELECT set_config('app.bootstrap','on',false)"))
        seen = conn.execute(text("SELECT count(*) FROM memberships WHERE user_id=:u"),
                            {"u": user}).scalar_one()
        assert seen == 1
        # bootstrap is read-only: WITH CHECK still blocks a cross-tenant insert
        with pytest.raises(DBAPIError):
            conn.execute(text(
                "INSERT INTO memberships (id, user_id, organization_id, role, status, created_at) "
                "VALUES (:i,:u,:o,'compliance_admin','active',now())"),
                {"i": uuid.uuid4(), "u": user, "o": uuid.uuid4()})


def test_audit_log_is_append_only(pg_engine):
    org = uuid.uuid4()
    with pg_engine.begin() as conn:
        conn.execute(text("INSERT INTO organizations (id, name, plan_tier, created_at) "
                          "VALUES (:o,'A','starter',now())"), {"o": org})
        _set_org(conn, org)
        aid = uuid.uuid4()
        conn.execute(text("INSERT INTO audit_log (id, organization_id, action, metadata, created_at) "
                          "VALUES (:i,:o,'created','{}'::jsonb,now())"), {"i": aid, "o": org})
    with pg_engine.connect() as conn:
        _set_org(conn, org)
        with pytest.raises(Exception, match="append-only"):
            conn.execute(text("UPDATE audit_log SET action='tampered'"))
    with pg_engine.connect() as conn:
        _set_org(conn, org)
        with pytest.raises(Exception, match="append-only"):
            conn.execute(text("DELETE FROM audit_log"))
