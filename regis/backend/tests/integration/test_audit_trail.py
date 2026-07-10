"""
Integration — audit trail read side (SQLite, AI off).

The append-only writes already happen inside the module services; here we verify
the reader projects them faithfully: actor-name resolution, obligation target
labels, action filtering, the entity timeline, and pagination/has_more.
"""
import os

os.environ.setdefault("REGIS_DATABASE_URL", "sqlite+pysqlite:///:memory:")

from datetime import date  # noqa: E402

from app.core.security import Principal  # noqa: E402
from app.models.compliance import ObligationInstance  # noqa: E402
from app.modules.audit import service as audit  # noqa: E402
from app.modules.obligations import service as obsvc  # noqa: E402
from app.modules.onboarding.service import generate_calendar  # noqa: E402
from sqlalchemy import select  # noqa: E402

CTX = {
    "window_start": date(2026, 4, 1), "window_end": date(2027, 3, 31),
    "anchors": {"agm_date": date(2026, 9, 25), "tds_return_date": date(2026, 7, 31)},
    "license_expiry": date(2026, 11, 30),
}


def _admin(seeded):
    return Principal(user_id=str(seeded["user_id"]), organization_id=str(seeded["org_id"]),
                     role="compliance_admin")


def _seed_activity(db, seeded, profile_b):
    """Generate a calendar and drive one obligation through start → submit → approve."""
    org = seeded["org_id"]
    admin = _admin(seeded)
    generate_calendar(db, organization_id=org, entity_id=seeded["entity_id"],
                      profile=profile_b, ctx=CTX)
    inst = db.execute(select(ObligationInstance)
                      .where(ObligationInstance.organization_id == org)).scalars().first()
    obsvc.assign_owner(db, organization_id=org, instance_id=inst.id,
                       owner_user_id=seeded["user_id"], principal=admin)
    for action in ("start", "submit"):
        obsvc.transition(db, organization_id=org, instance_id=inst.id,
                         action=action, principal=admin)
    obsvc.transition(db, organization_id=org, instance_id=inst.id, action="approve",
                     principal=admin, override_evidence=True, reason="filed via portal")
    db.flush()
    return org, inst


def test_feed_enriches_actor_and_target(db, seeded_org, profile_b):
    org, inst = _seed_activity(db, seeded_org, profile_b)
    page = audit.list_events(db, org)
    assert page["events"], "expected audit rows"

    # newest-first ordering
    times = [e["created_at"] for e in page["events"]]
    assert times == sorted(times, reverse=True)

    # actor names resolve to the seeded admin, not a raw UUID
    status_rows = [e for e in page["events"] if e["action"] == "instance_status_change"]
    assert status_rows
    assert all(e["actor_name"] == "CS Officer" for e in status_rows)
    # obligation rows carry a human target label (title — period), not just an id
    assert all(e["target_label"] and "—" in e["target_label"] for e in status_rows)
    # human label + transition detail survive into the projection
    assert any(e["meta"].get("from") and e["meta"].get("to") for e in status_rows)


def test_action_filter_and_entity_timeline(db, seeded_org, profile_b):
    org, inst = _seed_activity(db, seeded_org, profile_b)

    only_assigned = audit.list_events(db, org, action="instance_assigned")
    assert only_assigned["events"]
    assert {e["action"] for e in only_assigned["events"]} == {"instance_assigned"}

    timeline = audit.events_for_entity(
        db, org, entity_type="obligation_instance", entity_id=str(inst.id))
    # chronological (oldest first) and covers the whole lifecycle for this item
    times = [e["created_at"] for e in timeline]
    assert times == sorted(times)
    verbs = [e["meta"].get("action") for e in timeline if e["action"] == "instance_status_change"]
    assert verbs == ["start", "submit", "approve"]


def test_pagination_has_more(db, seeded_org, profile_b):
    org, _ = _seed_activity(db, seeded_org, profile_b)
    first = audit.list_events(db, org, limit=2, offset=0)
    assert len(first["events"]) == 2
    assert first["has_more"] is True
    second = audit.list_events(db, org, limit=2, offset=2)
    # disjoint pages
    assert {e["id"] for e in first["events"]}.isdisjoint({e["id"] for e in second["events"]})


def test_tenant_isolation(db, seeded_org, profile_b):
    org, _ = _seed_activity(db, seeded_org, profile_b)
    other_org = "00000000-0000-0000-0000-0000000000ff"
    assert audit.list_events(db, other_org)["events"] == []
