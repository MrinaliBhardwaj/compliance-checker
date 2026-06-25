"""
Integration — M4 persist chain end-to-end (SQLite).

Profile B -> 100 company_obligations + 367 obligation_instances persisted; the
21 event-driven obligations register as listeners (not instances); re-running is
idempotent; a profile change produces a correct add/remove diff with deactivation.
"""
from datetime import date

from sqlalchemy import func, select

from app.models.calendar import EventListener
from app.models.compliance import CompanyObligation, ObligationInstance
from app.models.content import ObligationTemplate
from app.models.system import AuditLog
from app.modules.onboarding.service import generate_calendar, save_profile

CTX = {
    "window_start": date(2026, 4, 1), "window_end": date(2027, 3, 31),
    "anchors": {"agm_date": date(2026, 9, 25), "tds_return_date": date(2026, 7, 31)},
    "license_expiry": date(2026, 11, 30),
}


def _count(db, model):
    return db.execute(select(func.count()).select_from(model)).scalar_one()


def test_seed_loaded(db, seeded_org):
    assert _count(db, ObligationTemplate) == 106
    # all DRAFT_UNVERIFIED on load
    n_unverified = db.execute(
        select(func.count()).select_from(ObligationTemplate)
        .where(ObligationTemplate.verification_status == "DRAFT_UNVERIFIED")
    ).scalar_one()
    assert n_unverified == 106


def test_persist_chain_profile_b(db, seeded_org, profile_b):
    res = generate_calendar(db, organization_id=seeded_org["org_id"],
                            entity_id=seeded_org["entity_id"], profile=profile_b, ctx=CTX)
    assert res.company_obligations == 100
    assert res.instances == 367
    assert res.event_listeners == 21
    # persisted, not just returned
    assert _count(db, CompanyObligation) == 100
    assert _count(db, ObligationInstance) == 367
    assert _count(db, EventListener) == 21
    # the generation was audited with run id + library version
    audit = db.execute(
        select(AuditLog).where(AuditLog.action == "calendar_generated")
    ).scalars().all()
    assert len(audit) == 1
    assert audit[0].meta["library_version"] == "0.1-draft"
    assert audit[0].meta["summary"]["applicable"] == 100


def test_idempotent_rerun(db, seeded_org, profile_b):
    generate_calendar(db, organization_id=seeded_org["org_id"],
                      entity_id=seeded_org["entity_id"], profile=profile_b, ctx=CTX)
    before_co = _count(db, CompanyObligation)
    before_inst = _count(db, ObligationInstance)
    # second run: no new rows (upsert on natural keys)
    res2 = generate_calendar(db, organization_id=seeded_org["org_id"],
                             entity_id=seeded_org["entity_id"], profile=profile_b, ctx=CTX)
    assert _count(db, CompanyObligation) == before_co == 100
    assert _count(db, ObligationInstance) == before_inst == 367
    assert res2.instances == 0  # nothing newly created


def test_profile_change_diff_and_deactivation(db, seeded_org, profile_a, profile_b):
    """B (100) -> A (69): obligations drop out and deactivate, never delete."""
    generate_calendar(db, organization_id=seeded_org["org_id"],
                      entity_id=seeded_org["entity_id"], profile=profile_b, ctx=CTX)
    res = generate_calendar(db, organization_id=seeded_org["org_id"],
                            entity_id=seeded_org["entity_id"], profile=profile_a, ctx=CTX)
    assert res.diff["removed"], "downgrade should remove obligations"
    # rows preserved; some are now inactive (history kept)
    active = db.execute(
        select(func.count()).select_from(CompanyObligation)
        .where(CompanyObligation.is_active.is_(True))
    ).scalar_one()
    inactive = db.execute(
        select(func.count()).select_from(CompanyObligation)
        .where(CompanyObligation.is_active.is_(False))
    ).scalar_one()
    assert active == 69
    assert inactive > 0  # deactivated, not deleted


def test_save_profile_persists_provenance(db, seeded_org):
    raw = {"cin": "U65999MH2018PTC123456", "pan": "AAACT1234A",
           "asset_size": "3000", "deposit_taking": "No", "operating_states": ["MH", "KA"],
           "employee_count": 260, "gst_registered": "Yes"}
    prof = save_profile(db, organization_id=seeded_org["org_id"],
                        entity_id=seeded_org["entity_id"], raw_input=raw)
    assert prof.profile["rbi_layer"] == "middle"
    assert prof.provenance["rbi_layer"]["source"] == "DERIVED"
    # extraction was audited
    n = db.execute(
        select(func.count()).select_from(AuditLog)
        .where(AuditLog.action == "profile_extracted")
    ).scalar_one()
    assert n == 1
