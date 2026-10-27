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


def test_failing_org_is_logged_and_others_still_run(db, seeded_org, monkeypatch, caplog):
    """BUG-20: one org's failure must be visible in the worker log, not swallowed."""
    import logging

    from app.models.tenancy import Organization
    from app.modules.notify import service as notify

    other = Organization(name="Second NBFC")
    db.add(other)
    db.commit()
    bad = str(seeded_org["org_id"])

    def flaky(session, org_id, today):
        if str(org_id) == bad:
            raise RuntimeError("smtp down")
        return {"notifications": 2}

    monkeypatch.setattr(notify, "run_reminders", flaky)
    with caplog.at_level(logging.ERROR, logger="app.jobs.worker"):
        out = _run_job(monkeypatch, db, worker.enqueue_due_reminders, date(2026, 10, 27))
    assert out == {"reminders_created": 2}  # the healthy org still ran
    assert any(bad in r.getMessage() and r.exc_info for r in caplog.records)


def test_cron_runs_on_india_time():
    """BUG-21: arq defaults to the host zone (UTC in python:3.12-slim), which ran the
    '00:30 IST' sweep at 06:00 IST."""
    from datetime import timedelta

    tz = worker.WorkerSettings.timezone
    assert tz.utcoffset(None) == timedelta(hours=5, minutes=30)
