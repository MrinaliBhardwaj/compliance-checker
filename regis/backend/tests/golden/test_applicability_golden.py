"""
Golden regression — applicability engine.

These three profiles + their exact summary numbers are the contract. Any engine
or library change that shifts them fails CI. Verified against the live seed.
"""
import pytest

from app.engines.applicability import diff_universe, generate_compliance_universe
from app.engines.profile_extraction import derive_regulatory_category

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
    """
    61 -> 63: CRAR and concentration were re-keyed onto rbi_layer (they are
    Middle/Upper Layer prudential norms), so Profile C -- declared Middle Layer
    -- now picks them up. CRILC and CRILC-SMA stay on the Rs.500cr keying and
    Profile C does NOT pick those up, because its fixture declares
    nbfc_category 'icc'. See test_profile_c_fixture_is_internally_inconsistent:
    at Rs.520cr the engine's own derivation says 'nd_si', so this number rests
    on a fixture bug, not on the rule.

    Profiles A and B are unmoved by either change.
    """
    s = generate_compliance_universe(library, profile_c)["summary"]
    assert s["applicable"] == 63
    assert s["needs_review"] == 27
    assert s["not_applicable"] == 16


def test_prudential_norms_key_off_layer(library, profile_c):
    """CRAR and concentration are Middle/Upper Layer norms -- they follow rbi_layer."""
    got = {r["template_id"] for r in generate_compliance_universe(library, profile_c)["applicable"]}
    assert {"sbr_crar", "rbi_concentration"} <= got


def test_crilc_keys_off_the_notified_threshold_not_layer(library, profile_b):
    """
    CRILC applies to deposit-taking NBFCs and non-deposit-taking NBFCs at
    Rs.500cr and above -- independent of SBR layer, so a Base Layer NBFC
    between Rs.500cr and Rs.1000cr is still in scope. It must NOT be keyed on
    rbi_layer.
    """
    lib_rule = {t["template_id"]: t["applicability_rule"]
                for t in library["obligation_templates"]}
    for tid in ("rbi_crilc", "rbi_crilc_sma_weekly"):
        assert "rbi_layer" not in lib_rule[tid], f"{tid} must not gate on layer"
        assert lib_rule[tid] == {"nbfc_category": ["nd_si", "deposit_taking"]}

    got = {r["template_id"] for r in generate_compliance_universe(library, profile_b)["applicable"]}
    assert {"rbi_crilc", "rbi_crilc_sma_weekly"} <= got


def test_profile_c_fixture_is_internally_inconsistent(profile_c):
    """
    Documents a known fixture bug rather than hiding it: Profile C declares
    nbfc_category 'icc' at Rs.520cr, but derive_regulatory_category returns
    'nd_si' at >= Rs.500cr. consistency_checks does not catch category/asset
    disagreement (it only checks layer/asset), so nothing flags it at runtime.

    Fixing the fixture would move the Profile C golden from 63 to 65 and put
    CRILC back in scope. Left for the content reviewer to decide -- delete this
    test in the same change that fixes the fixture.
    """
    derived = derive_regulatory_category(
        profile_c["asset_size_cr"], profile_c["deposit_taking"]).value
    assert profile_c["nbfc_category"] == "icc"
    assert derived == "nd_si"
    assert profile_c["nbfc_category"] != derived


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
