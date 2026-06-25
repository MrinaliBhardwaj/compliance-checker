"""Unit tests — one per predicate type + the three-state decision logic."""
from app.engines.applicability import (
    Decision,
    eval_condition,
    evaluate_template,
    score_confidence,
)


def _tpl(rule, **kw):
    base = dict(template_id="t1", title="T", category="rbi", law_id="l1",
                applicability_rule=rule, verification_status="DRAFT_UNVERIFIED")
    base.update(kw)
    return base


# --- predicate types ---
def test_universal():
    c = eval_condition("all", True, {})
    assert c.passed and c.predicate == "universal"


def test_numeric_min_cr_pass_and_boundary():
    assert eval_condition("asset_size_min_cr", 500, {"asset_size_cr": 600}).passed
    near = eval_condition("asset_size_min_cr", 500, {"asset_size_cr": 520})
    assert near.passed and near.near_boundary  # within +10%


def test_numeric_min_cr_missing():
    c = eval_condition("asset_size_min_cr", 500, {})
    assert c.missing and not c.passed


def test_alias_min():
    assert eval_condition("has_employees_min", 20, {"employee_count": 35}).passed
    assert not eval_condition("has_employees_min", 20, {"employee_count": 5}).passed


def test_state_intersection():
    c = eval_condition("pt_states", ["MH", "KA"], {"operating_states": ["KA", "DL"]})
    assert c.passed and c.actual == ["KA"]
    c2 = eval_condition("pt_states", ["MH"], {"operating_states": ["DL"]})
    assert not c2.passed


def test_enum_membership():
    assert eval_condition("rbi_layer", ["middle", "upper"], {"rbi_layer": "middle"}).passed
    assert not eval_condition("rbi_layer", ["middle", "upper"], {"rbi_layer": "base"}).passed


def test_boolean():
    assert eval_condition("gst_registered", True, {"gst_registered": True}).passed
    assert not eval_condition("gst_registered", True, {"gst_registered": False}).passed


def test_scalar_equality():
    assert eval_condition("gst_scheme", "qrmp", {"gst_scheme": "qrmp"}).passed
    assert not eval_condition("gst_scheme", "qrmp", {"gst_scheme": "regular"}).passed


# --- three-state decision logic ---
def test_decision_applicable():
    r = evaluate_template(_tpl({"all": True}), {})[0]
    assert r.decision == Decision.APPLICABLE.value


def test_decision_not_applicable_on_hard_fail():
    r = evaluate_template(_tpl({"rbi_layer": ["middle", "upper"]}), {"rbi_layer": "base"})[0]
    assert r.decision == Decision.NOT_APPLICABLE.value


def test_decision_needs_review_on_missing():
    r = evaluate_template(_tpl({"has_international_transactions": True}), {})[0]
    assert r.decision == Decision.NEEDS_REVIEW.value
    assert "has_international_transactions" in r.missing_fields


# --- confidence model ---
def test_unverified_cap_applies():
    conds = [eval_condition("all", True, {})]
    assert score_confidence(conds, template_verified=False) == 0.70
    assert score_confidence(conds, template_verified=True) == 1.0


def test_missing_field_low_confidence():
    conds = [eval_condition("has_ecb", True, {})]
    assert score_confidence(conds, template_verified=True) == 0.40
