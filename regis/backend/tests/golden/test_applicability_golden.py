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
    61 -> 65. Two independent corrections landed on this profile: CRAR and
    concentration moved onto rbi_layer (Middle/Upper Layer prudential norms),
    and the fixture's nbfc_category was corrected from 'icc' to 'nd_si', which
    is what derive_regulatory_category actually returns at Rs.520cr -- putting
    CRILC and CRILC-SMA back in scope.

    Profiles A and B are unmoved by either change.
    """
    s = generate_compliance_universe(library, profile_c)["summary"]
    assert s["applicable"] == 65
    assert s["needs_review"] == 27
    assert s["not_applicable"] == 14


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


@pytest.mark.parametrize("name", ["profile_a", "profile_b", "profile_c"])
def test_fixture_categories_agree_with_the_engine(request, name):
    """
    Replaces the pin on Profile C's old 'icc'/Rs.520cr contradiction. A fixture
    that declares a category the engine would not derive makes every golden
    resting on it meaningless -- and consistency_checks never compares category
    against asset size, so nothing catches it at runtime.
    """
    p = request.getfixturevalue(name)
    derived = derive_regulatory_category(p["asset_size_cr"], p["deposit_taking"]).value
    assert p["nbfc_category"] == derived, (
        f"{name} declares nbfc_category {p['nbfc_category']!r} but the engine "
        f"derives {derived!r} from asset_size_cr={p['asset_size_cr']}"
    )


def test_crilc_covers_base_layer_above_the_notified_threshold(library, profile_a):
    """
    The case the layer keying got wrong: a Base Layer NBFC at Rs.700cr is below
    the Rs.1000cr Middle-Layer line but at or above the Rs.500cr CRILC
    threshold, so CRILC applies while the ML/UL prudential norms do not.
    """
    p = dict(profile_a, asset_size_cr=700, nbfc_category="nd_si", rbi_layer="base")
    got = {r["template_id"] for r in generate_compliance_universe(library, p)["applicable"]}

    assert {"rbi_crilc", "rbi_crilc_sma_weekly"} <= got, "CRILC must not depend on layer"
    assert not ({"sbr_crar", "rbi_concentration"} & got), "ML/UL norms must not reach Base Layer"


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
