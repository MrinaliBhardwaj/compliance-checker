"""
Notification service.

Deterministic core: `reminder_intents` is a pure function of (instances, today,
config) — the same risk-weighted schedule the spec defines (default 7/3/1 pre-due,
high-risk 15/7/3/1, overdue escalation +1 owner / +3 admin / +7 head). It is fully
unit-tested and channel-agnostic.

DB orchestration: `run_reminders` materializes intents into Notification rows,
de-duplicates against what was already queued (idempotent — safe to run nightly),
and dispatches via the channel seam. Lifecycle helpers emit assignment / review /
rejection notifications on Maker-Checker events.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.config import get_settings
from app.models.compliance import CompanyObligation, ObligationInstance
from app.models.system import Notification
from app.models.tenancy import Membership, User
from app.modules.notify.channels import get_channel

_OPEN = ("pending", "in_progress", "ready_for_review")

DEFAULT_LEADS = (7, 3, 1)
HIGH_RISK_LEADS = (15, 7, 3, 1)
OVERDUE_ESCALATION = ((1, "owner"), (3, "compliance_admin"), (7, "head"))


# ---------------------------------------------------------------------------
# Pure: which notifications fall on `today` for a set of instances
# ---------------------------------------------------------------------------
def reminder_intents(instances: list[dict], today: date) -> list[dict]:
    """Pure schedule. Each intent: {instance_id, kind, target_role, lead, scheduled_for}."""
    out: list[dict] = []
    for i in instances:
        if i.get("status") not in _OPEN or not i.get("due_date"):
            continue
        due = date.fromisoformat(i["due_date"]) if isinstance(i["due_date"], str) else i["due_date"]
        leads = HIGH_RISK_LEADS if i.get("risk_level") == "high" else DEFAULT_LEADS

        # pre-due reminders to the owner
        for d in leads:
            if due - timedelta(days=d) == today:
                out.append({"instance_id": i["id"], "kind": "pre_due", "target_role": "owner",
                            "lead": d, "scheduled_for": today.isoformat()})
        # due-day reminder to the owner
        if due == today:
            out.append({"instance_id": i["id"], "kind": "due_day", "target_role": "owner",
                        "lead": 0, "scheduled_for": today.isoformat()})
        # overdue escalation ladder
        if due < today:
            for d, role in OVERDUE_ESCALATION:
                if due + timedelta(days=d) == today:
                    out.append({"instance_id": i["id"], "kind": "overdue", "target_role": role,
                                "lead": -d, "scheduled_for": today.isoformat()})
    return out


# ---------------------------------------------------------------------------
# DB orchestration
# ---------------------------------------------------------------------------
def _channels() -> list[str]:
    chans = ["email"]
    if get_settings().slack_webhook_url:
        chans.append("slack")
    return chans


def _already_sent(session: Session, *, organization_id, user_id, type_: str, channel: str,
                  instance_id: str, scheduled_for: str, kind: str) -> bool:
    rows = session.execute(
        select(Notification).where(
            Notification.organization_id == organization_id,
            Notification.user_id == user_id,
            Notification.type == type_,
            Notification.channel == channel,
        )
    ).scalars().all()
    for r in rows:
        p = r.payload or {}
        if (p.get("instance_id") == instance_id and p.get("scheduled_for") == scheduled_for
                and p.get("kind") == kind):
            return True
    return False


def emit(session: Session, *, organization_id, user_id, type_: str, channel: str,
         payload: dict, to_email: str | None, subject: str, body: str) -> Notification:
    """Record a Notification row, then best-effort dispatch via the channel seam."""
    row = Notification(organization_id=organization_id, user_id=user_id, type=type_,
                       channel=channel, payload=payload)
    session.add(row)
    session.flush()
    delivered = get_channel(channel).send(to=to_email, subject=subject, body=body,
                                          meta={"from": get_settings().email_from})
    if delivered:
        row.sent_at = datetime.now(timezone.utc)
    payload["delivered"] = delivered
    return row


def _role_users(session: Session, organization_id, role: str) -> list[User]:
    return session.execute(
        select(User).join(Membership, Membership.user_id == User.id)
        .where(Membership.organization_id == organization_id, Membership.role == role)
    ).scalars().all()


def _resolve_targets(session: Session, organization_id, target_role: str,
                     owner_user_id) -> list[User]:
    if target_role == "owner":
        if owner_user_id:
            u = session.get(User, owner_user_id)
            if u:
                return [u]
        return _role_users(session, organization_id, "compliance_admin")  # fallback
    return _role_users(session, organization_id, target_role)


def run_reminders(session: Session, organization_id, today: date) -> dict:
    """Materialize today's reminder/escalation intents into notifications (idempotent)."""
    rows = session.execute(
        select(ObligationInstance).where(
            ObligationInstance.organization_id == organization_id,
            ObligationInstance.status.in_(_OPEN),
        )
    ).scalars().all()
    risk_by_co: dict = {}

    def _risk(inst: ObligationInstance) -> str:
        co = risk_by_co.get(inst.company_obligation_id)
        if co is None:
            co = session.get(CompanyObligation, inst.company_obligation_id)
            risk_by_co[inst.company_obligation_id] = co
        # risk lives on the template; carried into rationale at generation time.
        tpl = co.template_id if co else None
        return "high" if tpl in _HIGH_RISK_TEMPLATES else "medium"

    inst_dicts = [{"id": str(i.id), "due_date": i.due_date.isoformat() if i.due_date else None,
                   "status": i.status, "owner_user_id": i.owner_user_id, "risk_level": _risk(i)}
                  for i in rows]
    inst_by_id = {str(i.id): i for i in rows}
    intents = reminder_intents(inst_dicts, today)

    created = 0
    for intent in intents:
        inst = inst_by_id[intent["instance_id"]]
        type_ = "escalation" if intent["kind"] == "overdue" else "reminder"
        targets = _resolve_targets(session, organization_id, intent["target_role"],
                                   inst.owner_user_id)
        for user in targets:
            for channel in _channels():
                if _already_sent(session, organization_id=organization_id, user_id=user.id,
                                 type_=type_, channel=channel, instance_id=intent["instance_id"],
                                 scheduled_for=intent["scheduled_for"], kind=intent["kind"]):
                    continue
                subject, body = _compose(intent, inst)
                emit(session, organization_id=organization_id, user_id=user.id, type_=type_,
                     channel=channel, payload={**intent}, to_email=user.email,
                     subject=subject, body=body)
                created += 1
    if created:
        audit.record(session, action="reminders_run", organization_id=organization_id,
                     meta={"date": today.isoformat(), "notifications": created})
    session.flush()
    return {"notifications": created, "intents": len(intents)}


def _compose(intent: dict, inst: ObligationInstance) -> tuple[str, str]:
    due = inst.due_date.isoformat() if inst.due_date else "n/a"
    if intent["kind"] == "overdue":
        return ("Overdue compliance obligation",
                f"{inst.period_label} was due {due} and is not complete. Please action.")
    if intent["kind"] == "due_day":
        return ("Compliance obligation due today", f"{inst.period_label} is due today ({due}).")
    return (f"Compliance reminder — due in {intent['lead']} day(s)",
            f"{inst.period_label} is due {due}.")


# ---------------------------------------------------------------------------
# Lifecycle event notifications (called from the Maker-Checker service)
# ---------------------------------------------------------------------------
def notify_assignment(session: Session, *, organization_id, instance: ObligationInstance,
                      owner_user_id) -> None:
    user = session.get(User, owner_user_id)
    if not user:
        return
    for channel in _channels():
        emit(session, organization_id=organization_id, user_id=user.id, type_="assignment",
             channel=channel,
             payload={"instance_id": str(instance.id), "kind": "assignment"},
             to_email=user.email, subject="You've been assigned a compliance obligation",
             body=f"{instance.period_label} (due {instance.due_date}) is now assigned to you.")


def notify_review_requested(session: Session, *, organization_id,
                            instance: ObligationInstance) -> None:
    for role in ("compliance_admin", "head"):
        for user in _role_users(session, organization_id, role):
            for channel in _channels():
                emit(session, organization_id=organization_id, user_id=user.id, type_="reminder",
                     channel=channel,
                     payload={"instance_id": str(instance.id), "kind": "review_requested"},
                     to_email=user.email, subject="Obligation ready for your review",
                     body=f"{instance.period_label} was submitted and awaits approval.")


def notify_rejected(session: Session, *, organization_id, instance: ObligationInstance) -> None:
    if not instance.owner_user_id:
        return
    user = session.get(User, instance.owner_user_id)
    if not user:
        return
    for channel in _channels():
        emit(session, organization_id=organization_id, user_id=user.id, type_="reminder",
             channel=channel, payload={"instance_id": str(instance.id), "kind": "rejected"},
             to_email=user.email, subject="Obligation sent back for changes",
             body=f"{instance.period_label} was returned for revision.")


# High-risk template ids drive the denser reminder cadence. Sourced from the seed
# (risk_level == "high"); cached at import for the pure schedule path.
def _load_high_risk() -> set[str]:
    from app.seed.library_loader import load_library
    return {t["template_id"] for t in load_library()["obligation_templates"]
            if t.get("risk_level") == "high"}


_HIGH_RISK_TEMPLATES = _load_high_risk()
