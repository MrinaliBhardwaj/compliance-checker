"""
Arq worker (PRD background-jobs backbone): a nightly overdue count and the daily
reminder/escalation run, both per org under its RLS scope.

Overdue is computed on read (`lifecycle.effective_status`), never stored, so the
worker writes no status. Job bodies call the same services the API uses.
"""

from __future__ import annotations

from datetime import date

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal, set_tenant
from app.models.compliance import ObligationInstance
from app.models.tenancy import Organization
from app.modules.obligations.lifecycle import STORED_OPEN, effective_status


async def nightly_sweep(ctx) -> dict:
    """Count overdue instances org-by-org (RLS-scoped). Read-only.

    It used to store `overdue`, which hid those rows from run_reminders (it selects
    STORED_OPEN) and so silenced the escalation ladder. Each org is read in its own
    transaction because the tenant GUC is transaction-local.
    """
    today = date.today()
    overdue = 0
    with SessionLocal() as session:
        org_ids = session.execute(select(Organization.id)).scalars().all()
        for org_id in org_ids:
            try:
                set_tenant(session, str(org_id))
                rows = session.execute(
                    select(ObligationInstance.status, ObligationInstance.due_date).where(
                        ObligationInstance.organization_id == org_id,
                        ObligationInstance.status.in_(STORED_OPEN),
                    )
                ).all()
                overdue += sum(
                    1 for status, due in rows if effective_status(status, due, today) == "overdue"
                )
            finally:
                session.rollback()  # end this org's transaction (and its tenant scope)
    return {"overdue": overdue}


async def enqueue_due_reminders(ctx) -> dict:
    """Materialize + dispatch today's reminders/escalations per org (idempotent)."""
    from app.modules.notify.service import run_reminders

    today = date.today()
    total = 0
    with SessionLocal() as session:
        org_ids = session.execute(select(Organization.id)).scalars().all()
        for org_id in org_ids:
            try:
                set_tenant(session, str(org_id))
                total += run_reminders(session, org_id, today)["notifications"]
                session.commit()  # per-org: reminder INSERTs must land under this org's RLS scope
            except Exception:
                session.rollback()
    return {"reminders_created": total}


class WorkerSettings:
    """arq entrypoint: `arq app.jobs.worker.WorkerSettings`."""

    functions = [nightly_sweep, enqueue_due_reminders]
    cron_jobs = [
        cron(nightly_sweep, hour=0, minute=30),  # 00:30 IST daily
        cron(enqueue_due_reminders, hour=6, minute=0),  # 06:00 IST daily
    ]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
