"""
Integration — enriched tracker API the frontend depends on (no fake data).

- /obligations/instances rows carry title/category/risk_level/form so the UI can
  render names + risk indicators; filters (status/category/q) work.
- /obligations/instances/{id} detail carries completeness + linked documents +
  rationale + verification_status.
- legal updates list carries affected_obligations counts.
"""

import os

# Bind app.core.db (imported transitively via the router) to SQLite before import,
# so this module is runnable standalone (no Postgres driver needed locally).
os.environ.setdefault("REGIS_DATABASE_URL", "sqlite+pysqlite:///:memory:")

from datetime import date  # noqa: E402

from app.core.security import Principal  # noqa: E402
from app.models.profile import CompanyProfile
from app.modules.legal_updates import service as lusvc
from app.modules.obligations.router import instance_detail, list_instances
from app.modules.onboarding.service import generate_calendar

CTX = {
    "window_start": date(2026, 4, 1),
    "window_end": date(2027, 3, 31),
    "anchors": {"agm_date": date(2026, 9, 25), "tds_return_date": date(2026, 7, 31)},
    "license_expiry": date(2026, 11, 30),
}


def _admin(seeded):
    return Principal(
        user_id=str(seeded["user_id"]),
        organization_id=str(seeded["org_id"]),
        role="compliance_admin",
    )


def test_instances_enriched_and_filterable(db, seeded_org, profile_b):
    generate_calendar(
        db,
        organization_id=seeded_org["org_id"],
        entity_id=seeded_org["entity_id"],
        profile=profile_b,
        ctx=CTX,
    )
    rows = list_instances(db=db, principal=_admin(seeded_org))
    assert rows
    sample = rows[0]
    for key in ("title", "category", "risk_level", "form_reference", "status", "due_date"):
        assert key in sample
    # category filter narrows the set
    rbi = list_instances(db=db, principal=_admin(seeded_org), category="rbi")
    assert rbi and all(r["category"] == "rbi" for r in rbi)
    # search filter matches by title
    hit_title = rows[0]["title"].split()[0]
    found = list_instances(db=db, principal=_admin(seeded_org), q=hit_title)
    assert found


def test_instance_detail_has_completeness_and_docs(db, seeded_org, profile_b):
    generate_calendar(
        db,
        organization_id=seeded_org["org_id"],
        entity_id=seeded_org["entity_id"],
        profile=profile_b,
        ctx=CTX,
    )
    rows = list_instances(db=db, principal=_admin(seeded_org))
    detail = instance_detail(instance_id=rows[0]["id"], db=db, principal=_admin(seeded_org))
    assert "completeness" in detail and "linked_documents" in detail
    assert detail["verification_status"] == "DRAFT_UNVERIFIED"
    assert detail["linked_documents"] == []  # none linked yet


def test_legal_update_affected_count(db, seeded_org, profile_b):
    generate_calendar(
        db,
        organization_id=seeded_org["org_id"],
        entity_id=seeded_org["entity_id"],
        profile=profile_b,
        ctx=CTX,
    )
    db.add(
        CompanyProfile(
            organization_id=seeded_org["org_id"],
            entity_id=seeded_org["entity_id"],
            profile=profile_b,
        )
    )
    db.flush()
    lusvc.publish_update(
        db,
        title="RBI returns change",
        law_id="law_rbi_returns",
        affects_filter={"rbi_registered": True},
        organization_id=seeded_org["org_id"],
    )
    feed = lusvc.list_for_org(db, organization_id=seeded_org["org_id"])
    assert feed[0]["affected_obligations"] >= 1  # org holds obligations under law_rbi_returns


def test_deactivated_obligations_drop_out_everywhere(db, seeded_org, profile_a, profile_b):
    """BUG-07: B -> A deactivates ~31 obligations; their instances must leave the
    tracker, dashboard, report, Copilot context and reminder run."""
    from datetime import timedelta

    from sqlalchemy import select

    from app.models.compliance import CompanyObligation, ObligationInstance
    from app.models.system import Notification
    from app.modules.copilot.router import _load_instance_rows
    from app.modules.notify.service import run_reminders
    from app.modules.obligations.router import dashboard
    from app.modules.reports.service import build_compliance_report

    kw = {"organization_id": seeded_org["org_id"], "entity_id": seeded_org["entity_id"]}
    generate_calendar(db, profile=profile_b, ctx=CTX, **kw)
    generate_calendar(db, profile=profile_a, ctx=CTX, **kw)
    active, inactive = (
        db.execute(
            select(ObligationInstance.id)
            .join(CompanyObligation)
            .where(CompanyObligation.is_active.is_(flag))
        )
        .scalars()
        .all()
        for flag in (True, False)
    )
    assert active and inactive

    admin = _admin(seeded_org)
    assert {r["id"] for r in list_instances(db=db, principal=admin)} == {str(i) for i in active}
    assert dashboard(db=db, principal=admin)["total_instances"] == len(active)
    report = build_compliance_report(
        db, organization_id=seeded_org["org_id"], today=date(2026, 6, 1)
    )
    assert report["totals"]["instances"] == len(active)
    assert {r["id"] for r in _load_instance_rows(db, seeded_org["org_id"])} == {
        str(i) for i in active
    }

    # a reminder day for a deactivated instance sends nothing about it
    gone = db.get(ObligationInstance, inactive[0])
    run_reminders(db, seeded_org["org_id"], gone.due_date - timedelta(days=7))
    sent = db.execute(select(Notification.payload)).scalars().all()
    assert all(p.get("instance_id") != str(gone.id) for p in sent)
