"""
Integration — the nightly sweep must survive a bad organisation.

Before per-org isolation, both worker jobs walked every organisation with no
exception handling: one failing org aborted the loop and every organisation
after it silently got no overdue flips and no reminders. Committing per-org
made completed orgs durable but did nothing to keep the loop running.

These tests pin the behaviour that replaced it.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.jobs.worker import _flip_overdue, _for_each_org
from app.models import Base
from app.models.compliance import ObligationInstance
from app.models.tenancy import Organization

TODAY = date(2026, 8, 18)


@pytest.fixture
def factory(monkeypatch):
    """A session factory over a shared in-memory DB, mirroring SessionLocal.

    set_tenant is stubbed out: app.core.db computes _IS_PG once from the
    module-level engine (Postgres by default), so it would try Postgres'
    set_config against this SQLite session. RLS itself is covered by
    test_postgres_hardening.py against live Postgres; what is under test here is
    the isolation of the loop, not the tenant scoping inside it.
    """
    monkeypatch.setattr("app.jobs.worker.set_tenant", lambda session, org_id: None)
    engine = create_engine("sqlite+pysqlite://", future=True)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, future=True, expire_on_commit=False)
    Base.metadata.drop_all(engine)


def _orgs(factory, n: int) -> list:
    with factory() as s:
        ids = []
        for i in range(n):
            o = Organization(name=f"NBFC {i}")
            s.add(o)
            s.flush()
            ids.append(o.id)
        s.commit()
        return ids


def test_one_failing_org_does_not_stop_the_others(factory):
    ids = _orgs(factory, 5)
    seen = []

    def fn(session, org_id, today):
        seen.append(org_id)
        if org_id == ids[1]:
            raise RuntimeError("simulated bad org")
        return 1

    out = _for_each_org("test_job", fn, session_factory=factory, today=TODAY)

    assert len(seen) == 5, "every org must be attempted, not just those before the failure"
    assert out["processed"] == 4
    assert out["failed"] == 1
    assert out["affected"] == 4
    assert out["failures"][0]["organization_id"] == str(ids[1])
    assert "simulated bad org" in out["failures"][0]["error"]


def test_a_failing_org_is_rolled_back_not_half_written(factory):
    """The session must be usable for the next org after a failure."""
    ids = _orgs(factory, 3)

    def fn(session, org_id, today):
        session.add(Organization(name=f"side-effect-{org_id}"))
        session.flush()
        if org_id == ids[0]:
            raise RuntimeError("fail after a write")
        return 1

    out = _for_each_org("test_job", fn, session_factory=factory, today=TODAY)
    assert out["processed"] == 2 and out["failed"] == 1

    with factory() as s:
        names = set(s.execute(select(Organization.name)).scalars().all())
    assert f"side-effect-{ids[0]}" not in names, "failed org's write must be rolled back"
    assert f"side-effect-{ids[1]}" in names, "healthy org's write must persist"


def test_every_org_is_committed_independently(factory):
    """A later failure must not roll back an earlier org's committed work."""
    ids = _orgs(factory, 3)

    def fn(session, org_id, today):
        session.add(Organization(name=f"ok-{org_id}"))
        session.flush()
        if org_id == ids[2]:
            raise RuntimeError("last org fails")
        return 1

    _for_each_org("test_job", fn, session_factory=factory, today=TODAY)
    with factory() as s:
        names = set(s.execute(select(Organization.name)).scalars().all())
    assert f"ok-{ids[0]}" in names and f"ok-{ids[1]}" in names


def test_flip_overdue_marks_only_past_due_open_instances(factory):
    ids = _orgs(factory, 1)
    with factory() as s:
        for status, due in (("pending", TODAY - timedelta(days=1)),
                            ("pending", TODAY + timedelta(days=1)),
                            ("completed", TODAY - timedelta(days=5))):
            # SQLite does not enforce the FK; a synthetic parent id keeps this
            # focused on the overdue predicate rather than calendar fixtures.
            s.add(ObligationInstance(organization_id=ids[0], status=status, due_date=due,
                                     period_label="2026-Q2",
                                     company_obligation_id=uuid.uuid4()))
        s.commit()

    out = _for_each_org("nightly_sweep", _flip_overdue, session_factory=factory, today=TODAY)
    assert out["affected"] == 1 and out["failed"] == 0

    with factory() as s:
        statuses = sorted(s.execute(select(ObligationInstance.status)).scalars().all())
    assert statuses == ["completed", "overdue", "pending"]
