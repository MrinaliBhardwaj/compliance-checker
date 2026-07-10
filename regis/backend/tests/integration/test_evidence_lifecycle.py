"""
Integration — M7: evidence + Maker-Checker daily loop (SQLite, AI seam off).

Covers the real customer loop:
  generate calendar -> assign -> start -> (try to approve with no evidence: BLOCKED)
  -> upload challan -> classify (manual, AI-off) -> link (validated) -> completeness
  -> submit (maker) -> approve (checker, gate satisfied) -> completed with trail.
Plus: exact-duplicate upload is blocked; entity-mismatch link is blocked.
"""
import tempfile
from datetime import date

import pytest
from sqlalchemy import func, select

import app.core.storage as storage_mod
from app.core.security import Principal
from app.core.storage import LocalStorage
from app.models.compliance import ObligationInstance
from app.models.evidence import Document, DocumentLink
from app.models.system import AuditLog
from app.modules.documents import service as docsvc
from app.modules.obligations import service as obsvc
from app.modules.obligations.lifecycle import RolePermissionError
from app.modules.onboarding.service import generate_calendar

CTX = {
    "window_start": date(2026, 4, 1), "window_end": date(2027, 3, 31),
    "anchors": {"agm_date": date(2026, 9, 25), "tds_return_date": date(2026, 7, 31)},
    "license_expiry": date(2026, 11, 30),
}


@pytest.fixture(autouse=True)
def _local_storage(monkeypatch):
    """Force the local storage adapter into a temp dir for every test here."""
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(storage_mod, "_storage", LocalStorage(root=d))
        yield


def _admin(seeded):
    return Principal(user_id=str(seeded["user_id"]), organization_id=str(seeded["org_id"]),
                     role="compliance_admin")


def _tds_instance(db, seeded, profile_b):
    """Generate the calendar and return a TDS-deposit instance to evidence."""
    generate_calendar(db, organization_id=seeded["org_id"], entity_id=seeded["entity_id"],
                      profile=profile_b, ctx=CTX)
    inst = db.execute(
        select(ObligationInstance)
        .join(ObligationInstance.company_obligation)
        .where(ObligationInstance.organization_id == seeded["org_id"])
    ).scalars().first()
    # pick a TDS-deposit instance specifically (has challan + computation required)
    rows = db.execute(select(ObligationInstance)
                      .where(ObligationInstance.organization_id == seeded["org_id"])).scalars().all()
    for i in rows:
        if i.company_obligation.template_id == "it_tds_deposit":
            return i
    return inst


def test_full_evidence_and_maker_checker(db, seeded_org, profile_b):
    admin = _admin(seeded_org)
    inst = _tds_instance(db, seeded_org, profile_b)

    # cannot approve before submit (state machine)
    obsvc.transition(db, organization_id=seeded_org["org_id"], instance_id=inst.id,
                     action="start", principal=admin)

    # upload a challan
    up = docsvc.upload_document(db, organization_id=seeded_org["org_id"],
                                entity_id=seeded_org["entity_id"], uploaded_by=admin.user_id,
                                file_name="challan.pdf", mime="application/pdf",
                                content=b"%PDF challan bytes", run_processing=True)
    doc = up["document"]
    # AI off in tests -> parked unprocessed for manual classification
    assert doc.processing_status == "unprocessed"

    # human classifies it as a PAYMENT_CHALLAN with extracted fields
    docsvc.classify_manually(db, doc=doc, doc_type="PAYMENT_CHALLAN",
                             extracted={"period": inst.period_label, "amount": 245000,
                                        "payment_date": (inst.due_date or date(2026, 4, 30)).isoformat()},
                             actor_user_id=admin.user_id)

    # link (human-confirmed) -> deterministic validation + completeness
    res = docsvc.link_document(db, organization_id=seeded_org["org_id"], document_id=doc.id,
                               instance_id=inst.id, confirmed_by=admin.user_id, role="compliance_admin")
    assert res["blocked"] is False
    assert res["completeness"]["primary_present"] is True
    assert res["completeness"]["eligible_for_completion"] is True

    # maker submits, checker approves (gate satisfied)
    obsvc.transition(db, organization_id=seeded_org["org_id"], instance_id=inst.id,
                     action="submit", principal=admin)
    obsvc.transition(db, organization_id=seeded_org["org_id"], instance_id=inst.id,
                     action="approve", principal=admin)
    db.refresh(inst)
    assert inst.status == "completed"
    assert inst.completed_at is not None and inst.approved_by is not None

    # full audit chain present
    actions = db.execute(
        select(AuditLog.action).where(AuditLog.entity_id == str(inst.id))
    ).scalars().all()
    assert "instance_status_change" in actions


def test_approve_blocked_without_evidence(db, seeded_org, profile_b):
    admin = _admin(seeded_org)
    inst = _tds_instance(db, seeded_org, profile_b)
    obsvc.transition(db, organization_id=seeded_org["org_id"], instance_id=inst.id,
                     action="start", principal=admin)
    obsvc.transition(db, organization_id=seeded_org["org_id"], instance_id=inst.id,
                     action="submit", principal=admin)
    with pytest.raises(obsvc.EvidenceGateError):
        obsvc.transition(db, organization_id=seeded_org["org_id"], instance_id=inst.id,
                         action="approve", principal=admin)
    # admin override is allowed (and audited)
    obsvc.transition(db, organization_id=seeded_org["org_id"], instance_id=inst.id,
                     action="approve", principal=admin, override_evidence=True,
                     reason="filed via portal, ack to follow")
    db.refresh(inst)
    assert inst.status == "completed"


def test_exact_duplicate_upload_blocked(db, seeded_org):
    admin = _admin(seeded_org)
    content = b"identical bytes"
    a = docsvc.upload_document(db, organization_id=seeded_org["org_id"],
                               entity_id=seeded_org["entity_id"], uploaded_by=admin.user_id,
                               file_name="a.pdf", mime="application/pdf", content=content)
    assert a["document"] is not None
    b = docsvc.upload_document(db, organization_id=seeded_org["org_id"],
                               entity_id=seeded_org["entity_id"], uploaded_by=admin.user_id,
                               file_name="a-again.pdf", mime="application/pdf", content=content)
    assert b["document"] is None
    assert b["duplicate"]["verdict"] == "EXACT_DUPLICATE"
    # only one document stored
    assert db.execute(select(func.count()).select_from(Document)).scalar_one() == 1


def test_entity_mismatch_link_blocked(db, seeded_org, profile_b):
    """A document whose identifier isn't the org's is blocked unless overridden."""
    admin = _admin(seeded_org)
    # set an org master identifier so entity_match can fail
    from app.models.tenancy import Entity
    entity = db.get(Entity, seeded_org["entity_id"])
    entity.pan = "AAACT1234A"
    db.flush()

    inst = _tds_instance(db, seeded_org, profile_b)
    up = docsvc.upload_document(db, organization_id=seeded_org["org_id"],
                                entity_id=seeded_org["entity_id"], uploaded_by=admin.user_id,
                                file_name="wrong.pdf", mime="application/pdf", content=b"x")
    docsvc.classify_manually(db, doc=up["document"], doc_type="PAYMENT_CHALLAN",
                             extracted={"tan_or_pan": "ZZZZZ9999Z", "amount": 1,
                                        "period": inst.period_label}, actor_user_id=admin.user_id)
    res = docsvc.link_document(db, organization_id=seeded_org["org_id"],
                               document_id=up["document"].id, instance_id=inst.id,
                               confirmed_by=admin.user_id, role="compliance_admin")
    assert res["blocked"] is True and res["reason"] == "entity_match_fail"
    assert db.execute(select(func.count()).select_from(DocumentLink)).scalar_one() == 0


def test_preparer_scope_enforced(db, seeded_org, profile_b):
    _admin(seeded_org)
    inst = _tds_instance(db, seeded_org, profile_b)
    other = Principal(user_id="00000000-0000-0000-0000-000000000099",
                      organization_id=str(seeded_org["org_id"]), role="preparer")
    with pytest.raises(RolePermissionError):
        obsvc.transition(db, organization_id=seeded_org["org_id"], instance_id=inst.id,
                         action="start", principal=other)
