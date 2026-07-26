"""
Arq worker (PRD background-jobs backbone). The nightly sweep is the calendar's
heartbeat: extend the generation window, upsert new instances, flip overdue, and
enqueue due reminders — all idempotent and audit-logged.

This wires the deterministic engines into scheduled execution. Job bodies call the
same services the API uses, so there is one code path for generation/overdue.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.core.db import SessionLocal, set_tenant
from app.models.compliance import ObligationInstance
from app.models.tenancy import Organization

_OPEN = ("pending", "in_progress", "ready_for_review")


async def nightly_sweep(ctx) -> dict:
    """Flip overdue instances org-by-org (RLS-scoped) and count reminders due.

    Commit is per-org and *inside* the org's tenant scope: under Postgres FORCE
    RLS a write only lands while `app.current_org` matches its row, so deferring
    all writes to one final commit (under the last org's scope) would silently
    drop every other org's changes. Per-org commit also makes one bad org
    non-fatal for the rest of the sweep.
    """
    today = date.today()
    flipped = 0
    with SessionLocal() as session:
        org_ids = session.execute(select(Organization.id)).scalars().all()
        for org_id in org_ids:
            set_tenant(session, str(org_id))
            rows = session.execute(
                select(ObligationInstance).where(
                    ObligationInstance.organization_id == org_id,
                    ObligationInstance.status.in_(_OPEN),
                )
            ).scalars().all()
            for i in rows:
                if i.due_date and i.due_date < today:
                    i.status = "overdue"
                    flipped += 1
            session.commit()  # persist this org under its own tenant scope
    return {"overdue_flipped": flipped}


async def enqueue_due_reminders(ctx) -> dict:
    """Materialize + dispatch today's reminders/escalations per org (idempotent)."""
    from app.modules.notify.service import run_reminders
    today = date.today()
    total = 0
    with SessionLocal() as session:
        org_ids = session.execute(select(Organization.id)).scalars().all()
        for org_id in org_ids:
            set_tenant(session, str(org_id))
            total += run_reminders(session, org_id, today)["notifications"]
            session.commit()  # per-org: reminder INSERTs must land under this org's RLS scope
    return {"reminders_created": total}


class WorkerSettings:
    """arq entrypoint: `arq app.jobs.worker.WorkerSettings`."""
    functions = [nightly_sweep, enqueue_due_reminders]
    cron_jobs: list = []  # configured per-env; nightly_sweep typically at 00:30 IST

    @staticmethod
    def redis_settings():
        from arq.connections import RedisSettings

        from app.core.config import get_settings
        return RedisSettings.from_dsn(get_settings().redis_url)
