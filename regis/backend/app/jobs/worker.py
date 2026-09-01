"""
Arq worker (PRD background-jobs backbone). The nightly sweep is the calendar's
heartbeat: extend the generation window, upsert new instances, flip overdue, and
enqueue due reminders — all idempotent and audit-logged.

This wires the deterministic engines into scheduled execution. Job bodies call the
same services the API uses, so there is one code path for generation/overdue.

**Per-organisation failure isolation is the point of `_for_each_org`.** Before it,
both jobs walked every org with no exception handling: one bad row, one null due
date, or one SES failure propagated out of the loop and every organisation after
it silently received no overdue flips and no reminders — with no log line, because
there was no logging either. Committing per-org made *completed* orgs durable but
did nothing to keep the loop alive. Now a failing org is rolled back, logged with
its id, counted, and skipped; the sweep continues.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal, set_tenant
from app.core.logging import bind, configure_logging, get_logger
from app.models.compliance import ObligationInstance
from app.models.tenancy import Organization
from app.engines.statuses import OPEN_STATUSES

log = get_logger(__name__)

_OPEN = OPEN_STATUSES


def _for_each_org(job: str, fn: Callable[[Session, object, date], int],
                  *, session_factory=None, today: date | None = None) -> dict:
    """Run `fn` once per organisation, isolated. Returns a per-org outcome tally.

    Enumerating `organizations` is safe outside tenant scope — that table has no
    RLS policy. Every write inside `fn` happens under `set_tenant`, and the commit
    is per-org so it lands while `app.current_org` still matches its rows.
    """
    configure_logging()
    today = today or date.today()
    processed = failed = total = 0
    failures: list[dict] = []

    with (session_factory or SessionLocal)() as session:
        org_ids = session.execute(select(Organization.id)).scalars().all()
        log.info("job started", extra={"job": job, "organizations": len(org_ids)})

        for org_id in org_ids:
            with bind(job=job, organization_id=str(org_id)):
                try:
                    set_tenant(session, str(org_id))
                    n = fn(session, org_id, today)
                    session.commit()
                    total += n
                    processed += 1
                    log.info("org ok", extra={"affected": n})
                except Exception as exc:
                    # Roll back so the session is usable for the next org, then
                    # carry on: one tenant's bad data must not silently deprive
                    # every later tenant of its reminders.
                    session.rollback()
                    failed += 1
                    failures.append({"organization_id": str(org_id),
                                     "error": f"{type(exc).__name__}: {exc}"})
                    log.exception("org failed; continuing sweep")

    result = {"processed": processed, "failed": failed, "affected": total,
              "failures": failures}
    log.log(30 if failed else 20, "job finished", extra={"job": job, **result})
    return result


def _flip_overdue(session: Session, org_id, today: date) -> int:
    rows = session.execute(
        select(ObligationInstance).where(
            ObligationInstance.organization_id == org_id,
            ObligationInstance.status.in_(_OPEN),
        )
    ).scalars().all()
    flipped = 0
    for i in rows:
        if i.due_date and i.due_date < today:
            i.status = "overdue"
            flipped += 1
    return flipped


async def nightly_sweep(ctx) -> dict:
    """Flip overdue instances org-by-org (RLS-scoped), isolated per organisation."""
    out = _for_each_org("nightly_sweep", _flip_overdue)
    return {"overdue_flipped": out["affected"], **out}


def _send_reminders(session: Session, org_id, today: date) -> int:
    from app.modules.notify.service import run_reminders
    return run_reminders(session, org_id, today)["notifications"]


async def enqueue_due_reminders(ctx) -> dict:
    """Materialize + dispatch today's reminders/escalations per org (idempotent)."""
    out = _for_each_org("enqueue_due_reminders", _send_reminders)
    return {"reminders_created": out["affected"], **out}


def _cron_jobs() -> list:
    """Schedules are UTC. IST is UTC+5:30, so 00:30 IST == 19:00 UTC (prev day)."""
    from arq import cron
    return [
        cron(nightly_sweep, hour=19, minute=0),          # 00:30 IST
        cron(enqueue_due_reminders, hour=3, minute=30),  # 09:00 IST
    ]


class WorkerSettings:
    """arq entrypoint: `arq app.jobs.worker.WorkerSettings`."""

    functions = [nightly_sweep, enqueue_due_reminders]

    @staticmethod
    def cron_jobs():
        return _cron_jobs()

    @staticmethod
    def on_startup(ctx) -> None:
        configure_logging()
        log.info("worker started")

    @staticmethod
    def redis_settings():
        from arq.connections import RedisSettings

        from app.core.config import get_settings
        return RedisSettings.from_dsn(get_settings().redis_url)
