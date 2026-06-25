"""
Unit tests — legal-update matcher. Proves it reuses the obligation engine's
three-state semantics (the same DSL, one evaluator).
"""
from app.engines.applicability import Decision
from app.modules.legal_updates.matcher import match_org, match_update

MIDDLE = {"rbi_layer": "middle", "asset_size_cr": 3000, "has_foreign_investment": True}
BASE = {"rbi_layer": "base", "asset_size_cr": 200, "has_foreign_investment": False}


def test_empty_filter_affects_everyone():
    assert match_update({}, BASE)["decision"] == Decision.APPLICABLE.value
    assert match_update(None, BASE)["decision"] == Decision.APPLICABLE.value


def test_enum_membership_match_and_miss():
    f = {"rbi_layer": ["middle", "upper"]}
    assert match_update(f, MIDDLE)["decision"] == Decision.APPLICABLE.value
    assert match_update(f, BASE)["decision"] == Decision.NOT_APPLICABLE.value


def test_numeric_min_and_boolean_anded():
    f = {"asset_size_min_cr": 1000, "has_foreign_investment": True}
    assert match_update(f, MIDDLE)["decision"] == Decision.APPLICABLE.value
    # base fails both -> not applicable
    assert match_update(f, BASE)["decision"] == Decision.NOT_APPLICABLE.value


def test_missing_field_routes_to_review_not_dropped():
    f = {"has_ecb": True}  # not present in BASE/MIDDLE
    m = match_update(f, MIDDLE)
    assert m["decision"] == Decision.NEEDS_REVIEW.value
    assert "has_ecb" in m["missing_fields"]


def test_match_org_strongest_signal_wins():
    f = {"rbi_layer": ["middle", "upper"]}
    # one base entity (no), one middle entity (yes) -> org is affected
    assert match_org(f, [BASE, MIDDLE])["decision"] == Decision.APPLICABLE.value


def test_match_org_no_profile_routes_to_review():
    assert match_org({"rbi_layer": ["middle"]}, [])["decision"] == Decision.NEEDS_REVIEW.value
