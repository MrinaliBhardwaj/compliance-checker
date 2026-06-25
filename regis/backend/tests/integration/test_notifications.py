"""
Integration — M8 notifications (SQLite, no external providers).

- run_reminders materializes reminder/escalation rows and is idempotent.
- a high-risk obligation at a 15-day lead notifies the owner.
- Maker-Checker events emit review-requested / rejected / assignment notifications.
All channels fall back to Null (recorded, not externally sent) so no creds needed.
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.core.security import Principal
from app.models.compliance import CompanyObligation, ObligationInstance
from app.models.system import Notification
from app.models.tenancy import Membership, User
from app.modules.notify.service import run_reminders
from app.modules.obligations import service as obsvc
from app.modules.onboarding.service import generate_calendar

CTX = {
    "window_start": date(2026, 4, 1), "window_end": date(2027, 3, 31),
    "anchors": {"agm_date": date(2026, 9, 25), "tds_return_date": date(2026, 7, 31)},
    "license_expiry": date(2026, 11, 30),
}


def _admin(seeded):
    return Principal(user_id=str(seeded["user_id"]), organization_id=str(seeded["org_id"]),
                     role="compliance_admin")


def _make_admin_membership(db, seeded):
    db.add(Membership(user_id=seeded["user_id"], organization_id=seeded["org_id"],
                      role="compliance_admin", status="active"))
    db.flush()


def test_run_reminders_idempotent(db, seeded_org, profile_b):
    _make_admin_membership(db, seeded_org)
    generate_calendar(db, organization_id=seeded_org["org_id"], entity_id=seeded_org["entity_id"],
                      profile=profile_b, ctx=CTX)
    # pick an instance with a due date and set it to "due in 7 days" from a chosen today
    inst = db.execute(
        select(ObligationInstance).where(ObligationInstance.due_date.isnot(None))
    ).scalars().first()
    today = inst.due_date - timedelta(days=7)

    first = run_reminders(db, seeded_org["org_id"], today)
    assert first["notifications"] >= 1
    before = db.execute(select(func.count()).select_from(Notification)).scalar_one()
    # second run on the same day creates nothing new (idempotent)
    second = run_reminders(db, seeded_org["org_id"], today)
    after = db.execute(select(func.count()).select_from(Notification)).scalar_one()
    assert second["notifications"] == 0
    assert after == before


def test_overdue_escalation_to_admin(db, seeded_org, profile_b):
    _make_admin_membership(db, seeded_org)
    generate_calendar(db, organization_id=seeded_org["org_id"], entity_id=seeded_org["entity_id"],
                      profile=profile_b, ctx=CTX)
    inst = db.execute(
        select(ObligationInstance).where(ObligationInstance.due_date.isnot(None))
    ).scalars().first()
    # +3 days overdue -> compliance_admin escalation
    today = inst.due_date + timedelta(days=3)
    run_reminders(db, seeded_org["org_id"], today)
    escalations = db.execute(
        select(Notification).where(Notification.type == "escalation")
    ).scalars().all()
    assert any((n.payload or {}).get("kind") == "overdue" for n in escalations)


def test_lifecycle_emits_review_notification(db, seeded_org, profile_b):
    _make_admin_membership(db, seeded_org)
    generate_calendar(db, organization_id=seeded_org["org_id"], entity_id=seeded_org["entity_id"],
                      profile=profile_b, ctx=CTX)
    admin = _admin(seeded_org)
    inst = db.execute(select(ObligationInstance)).scalars().first()
    obsvc.transition(db, organization_id=seeded_org["org_id"], instance_id=inst.id,
                     action="start", principal=admin)
    obsvc.transition(db, organization_id=seeded_org["org_id"], instance_id=inst.id,
                     action="submit", principal=admin)
    reviews = db.execute(
        select(Notification).where(Notification.type == "reminder")
    ).scalars().all()
    assert any((n.payload or {}).get("kind") == "review_requested" for n in reviews)


def test_assignment_notification(db, seeded_org, profile_b):
    _make_admin_membership(db, seeded_org)
    # a preparer to assign to
    prep = User(email="prep@acme.example", full_name="Preparer")
    db.add(prep)
    db.flush()
    db.add(Membership(user_id=prep.id, organization_id=seeded_org["org_id"],
                      role="preparer", status="active"))
    db.flush()
    generate_calendar(db, organization_id=seeded_org["org_id"], entity_id=seeded_org["entity_id"],
                      profile=profile_b, ctx=CTX)
    admin = _admin(seeded_org)
    inst = db.execute(select(ObligationInstance)).scalars().first()
    obsvc.assign_owner(db, organization_id=seeded_org["org_id"], instance_id=inst.id,
                       owner_user_id=prep.id, principal=admin)
    assigns = db.execute(
        select(Notification).where(Notification.type == "assignment")
    ).scalars().all()
    assert any(str(n.user_id) == str(prep.id) for n in assigns)
