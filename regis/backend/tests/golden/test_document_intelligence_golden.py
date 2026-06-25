"""
Golden regression — document intelligence (deterministic core).

Locked: 192 evidence strings mapped, 3 OTHER (98.4% typed); ITNS-281 challan vs
TDS-Mar-2026 instance all-PASS; dedupe exact->block / near->warn; completeness
50% / primary_present / eligible.
"""
import pytest

from app.engines.document_intelligence import (
    completeness,
    dedupe,
    map_evidence_to_type,
    route,
    validate,
)

pytestmark = pytest.mark.golden


def test_evidence_taxonomy_coverage(library):
    all_ev = [e for o in library["obligation_templates"] for e in o["required_evidence"]]
    mapped = [(e, map_evidence_to_type(e).value) for e in all_ev]
    other = [e for e, t in mapped if t == "OTHER"]
    assert len(all_ev) == 192
    assert len(other) == 3  # 98.4% typed; 3 contract-like items legitimately OTHER


def test_tds_challan_validates_all_pass(library):
    tpl = next(o for o in library["obligation_templates"] if o["template_id"] == "it_tds_deposit")
    instance = {"period_label": "2026-03", "due_date": "2026-04-30"}  # March special
    org = {"cin": "U65999MH2015PTC000001", "pan": "AAACT1234A", "tan": "MUMT01234A",
           "gstin": "27AAACT1234A1Z5"}
    extracted = {
        "document_date": "2026-04-07", "period": "Mar 2026", "payment_date": "2026-04-07",
        "challan_number": "00123", "bsr_code": "0510308", "amount": 245000,
        "assessment_year": "2026-27", "tan_or_pan": "MUMT01234A", "authority": "Income Tax",
    }
    checks = {c.name: c.result for c in validate(extracted, instance, tpl, org)}
    assert checks["period_match"] == "pass"
    assert checks["date_in_window"] == "pass"
    assert checks["entity_match"] == "pass"
    assert checks["amount_sanity"] == "pass"


def test_entity_mismatch_fails():
    tpl = {"form_reference": "ITNS-281"}
    instance = {"period_label": "2026-03", "due_date": "2026-04-30"}
    org = {"tan": "MUMT01234A"}
    extracted = {"tan_or_pan": "DELT99999Z", "amount": 1000, "period": "Mar 2026"}
    checks = {c.name: c.result for c in validate(extracted, instance, tpl, org)}
    assert checks["entity_match"] == "fail"


def test_classification_routes_auto_suggest():
    assert route(0.93) == "AUTO_SUGGEST"
    assert route(0.70) == "SUGGEST_REVIEW"
    assert route(0.40) == "MANUAL"


def test_completeness_challan_only(library):
    tpl = next(o for o in library["obligation_templates"] if o["template_id"] == "it_tds_deposit")
    comp = completeness(tpl, linked_doc_types=["PAYMENT_CHALLAN"])
    assert comp["pct"] == 50
    assert comp["primary_present"] is True
    assert comp["eligible_for_completion"] is True
    assert comp["missing"]  # TDS computation outstanding


def test_dedupe_exact_blocks_near_warns():
    d1 = {"id": "doc1", "sha256": "abc", "entity_id": "e1",
          "ai_extracted": {"form_number": "ITNS-281", "period": "Mar 2026",
                           "reference_number": "00123"}}
    d2_exact = {"id": "doc2", "sha256": "abc"}
    d2_near = {"id": "doc3", "sha256": "xyz", "entity_id": "e1",
               "ai_extracted": {"form_number": "ITNS-281", "period": "Mar 2026",
                                "reference_number": "00123"}}
    assert dedupe(d2_exact, [d1])["action"] == "block"
    assert dedupe(d2_near, [d1])["action"] == "warn"


def test_dedupe_sparse_tuple_no_false_positive():
    """Near-dupe tuple fires only when fully populated."""
    d1 = {"id": "doc1", "sha256": "abc", "entity_id": "e1",
          "ai_extracted": {"form_number": None, "period": "Mar 2026", "reference_number": None}}
    d_new = {"id": "doc2", "sha256": "xyz", "entity_id": "e1",
             "ai_extracted": {"form_number": None, "period": "Mar 2026", "reference_number": None}}
    assert dedupe(d_new, [d1])["verdict"] == "UNIQUE"
