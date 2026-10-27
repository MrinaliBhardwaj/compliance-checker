"""Integration — Arq worker jobs run against the test session (SQLite)."""

import asyncio
from contextlib import nullcontext
from datetime import date

from sqlalchemy import func, select

from app.jobs import worker
from app.models.compliance import ObligationInstance
from app.modules.onboarding.service import generate_calendar, save_profile


def _run_job(monkeypatch, db, job, today):
    class _Today(date):
        @classmethod
        def today(cls):
            return today

    # The job opens its own session and sets the Postgres tenant GUC; point it at the
    # test session and skip the GUC (set_tenant keys off the configured PG URL).
    monkeypatch.setattr(worker, "SessionLocal", lambda: nullcontext(db))
    monkeypatch.setattr(worker, "set_tenant", lambda session, org: None)
    monkeypatch.setattr(worker, "date", _Today)
    return asyncio.run(job(None))


def test_extend_calendars_adds_next_fy_near_fy_end(db, seeded_org, profile_b, monkeypatch):
    prof = save_profile(
        db,
        organization_id=seeded_org["org_id"],
        entity_id=seeded_org["entity_id"],
        raw_input=profile_b,
    )
    generate_calendar(
        db,
        organization_id=seeded_org["org_id"],
        entity_id=seeded_org["entity_id"],
        profile=prof.profile,
        today=date(2026, 10, 27),
    )
    db.commit()
    before = db.execute(select(func.count()).select_from(ObligationInstance)).scalar_one()

    # Mid-year: nothing to extend yet.
    assert _run_job(monkeypatch, db, worker.extend_calendars, date(2026, 12, 1)) == {"extended": 0}

    # Inside the FY's last 60 days: next FY is added; this FY's rows are untouched.
    assert _run_job(monkeypatch, db, worker.extend_calendars, date(2027, 3, 1)) == {"extended": 1}
    dues = db.execute(select(ObligationInstance.due_date)).scalars().all()
    assert len(dues) > before
    assert max(dues) > date(2027, 3, 31)
    assert sum(1 for d in dues if d <= date(2027, 3, 31)) == before
