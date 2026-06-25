"""
Golden regression — applicability engine.

These three profiles + their exact summary numbers are the contract. Any engine
or library change that shifts them fails CI. Verified against the live seed.
"""
import pytest

from app.engines.applicability import diff_universe, generate_compliance_universe

pytestmark = pytest.mark.golden


def test_profile_a_summary(library, profile_a):
    s = generate_compliance_universe(library, profile_a)["summary"]
    assert s["applicable"] == 69
    assert s["needs_review"] == 1
    assert s["not_applicable"] == 39
    assert s["laws_touched"] == 22
    assert s["library_provisional"] is True  # all templates DRAFT_UNVERIFIED


def test_profile_b_summary(library, profile_b):
    s = generate_compliance_universe(library, profile_b)["summary"]
    assert s["applicable"] == 100
    assert s["needs_review"] == 1
    assert s["not_applicable"] == 13
    assert s["laws_touched"] == 26
    assert s["library_provisional"] is True


def test_profile_c_summary(library, profile_c):
    s = generate_compliance_universe(library, profile_c)["summary"]
    assert s["applicable"] == 61
    assert s["needs_review"] == 27
    assert s["not_applicable"] == 18


def test_profile_b_state_expansion(library, profile_b):
    """PT expands MH/KA/TN (DL excluded — not a PT state)."""
    res = generate_compliance_universe(library, profile_b)
    pt = sorted(r["template_id"] for r in res["applicable"]
                if r["template_id"].startswith("lab_pt_deposit__"))
    assert pt == ["lab_pt_deposit__KA", "lab_pt_deposit__MH", "lab_pt_deposit__TN"]
    # DL correctly excluded from PT expansion
    assert "lab_pt_deposit__DL" not in {r["template_id"] for r in res["applicable"]}


def test_unverified_confidence_cap(library, profile_b):
    """Every applicable item rests on a DRAFT_UNVERIFIED template -> confidence <= 0.70."""
    res = generate_compliance_universe(library, profile_b)
    assert res["applicable"], "expected applicable obligations"
    assert all(r["confidence"] <= 0.70 for r in res["applicable"])
    assert all(r["template_verified"] is False for r in res["applicable"])


def test_determinism(library, profile_b):
    """Identical (profile, library) -> identical output."""
    a = generate_compliance_universe(library, profile_b)
    b = generate_compliance_universe(library, profile_b)
    assert a == b


def test_diff_added_removed(library, profile_a, profile_b):
    """Reclassify A->B style change surfaces as added/removed, never silent."""
    res_a = generate_compliance_universe(library, profile_a)
    res_b = generate_compliance_universe(library, profile_b)
    old_ids = {r["template_id"] for r in res_a["applicable"]}
    d = diff_universe(old_ids, res_b)
    assert d["added"], "middle-layer profile should add obligations"
    # added/removed/unchanged partition the union with no overlap
    assert not (set(d["added"]) & set(d["removed"]))
    assert not (set(d["added"]) & set(d["unchanged"]))
