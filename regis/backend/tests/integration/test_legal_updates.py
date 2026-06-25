"""
Integration — M10 legal updates feed (SQLite, AI summarization off).

- publish a master update; it is matched per-org against the entity profile;
- a middle-layer-only update shows APPLICABLE for a middle-layer org, NOT_APPLICABLE
  for a base-layer org; an unknown-field filter routes to review (never dropped);
- review upserts the per-org status (idempotent) and is audited.
"""
import pytest
from sqlalchemy import func, select

from app.engines.applicability import Decision
from app.models.legal_updates import LegalUpdate, LegalUpdateStatus
from app.models.profile import CompanyProfile
from app.models.system import AuditLog
from app.modules.legal_updates import service as svc


def _profile(db, seeded, profile):
    db.add(CompanyProfile(organization_id=seeded["org_id"], entity_id=seeded["entity_id"],
                          profile=profile))
    db.flush()


def test_publish_and_match_middle(db, seeded_org, profile_b):
    _profile(db, seeded_org, profile_b)
    svc.publish_update(db, title="SBR CCO appointment tightened",
                       affects_filter={"rbi_layer": ["middle", "upper"]},
                       actor_user_id=seeded_org["user_id"],
                       organization_id=seeded_org["org_id"])
    feed = svc.list_for_org(db, organization_id=seeded_org["org_id"])
    assert len(feed) == 1
    assert feed[0]["match"] == Decision.APPLICABLE.value
    assert feed[0]["review_status"] == "new"


def test_match_not_applicable_for_base(db, seeded_org, profile_a):
    _profile(db, seeded_org, profile_a)  # base layer
    svc.publish_update(db, title="Middle-layer-only change",
                       affects_filter={"rbi_layer": ["middle", "upper"]},
                       organization_id=seeded_org["org_id"])
    feed = svc.list_for_org(db, organization_id=seeded_org["org_id"])
    assert feed[0]["match"] == Decision.NOT_APPLICABLE.value


def test_unknown_field_routes_to_review(db, seeded_org, profile_b):
    # profile_b dict has has_ecb True, so use a field not in the stored profile
    p = dict(profile_b)
    p.pop("has_odi", None)
    _profile(db, seeded_org, p)
    svc.publish_update(db, title="ODI reporting change", affects_filter={"has_odi": True},
                       organization_id=seeded_org["org_id"])
    feed = svc.list_for_org(db, organization_id=seeded_org["org_id"])
    assert feed[0]["match"] == Decision.NEEDS_REVIEW.value


def test_review_upsert_and_audit(db, seeded_org, profile_b):
    _profile(db, seeded_org, profile_b)
    u = svc.publish_update(db, title="X", affects_filter={}, organization_id=seeded_org["org_id"])
    svc.review_update(db, organization_id=seeded_org["org_id"], legal_update_id=u.id,
                      status="applicable", reviewed_by=seeded_org["user_id"])
    # re-review updates the same row (no duplicate)
    svc.review_update(db, organization_id=seeded_org["org_id"], legal_update_id=u.id,
                      status="not_applicable", reviewed_by=seeded_org["user_id"],
                      reason="handled by parent entity")
    n_status = db.execute(select(func.count()).select_from(LegalUpdateStatus)).scalar_one()
    assert n_status == 1
    row = db.execute(select(LegalUpdateStatus)).scalar_one()
    assert row.status == "not_applicable"
    n_audit = db.execute(
        select(func.count()).select_from(AuditLog)
        .where(AuditLog.action == "legal_update_reviewed")
    ).scalar_one()
    assert n_audit == 2


def test_invalid_review_status_rejected(db, seeded_org, profile_b):
    _profile(db, seeded_org, profile_b)
    u = svc.publish_update(db, title="X", affects_filter={}, organization_id=seeded_org["org_id"])
    with pytest.raises(ValueError):
        svc.review_update(db, organization_id=seeded_org["org_id"], legal_update_id=u.id,
                          status="bogus", reviewed_by=seeded_org["user_id"])
