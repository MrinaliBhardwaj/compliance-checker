"""
Coverage contract for the launch segment (Startup / Growth-Stage NBFC).

The library has always had 107 templates. What it did not have was a guarantee
that a customer could ever find out which of them apply to them. Three separate
holes made 23 of 107 obligations undecidable for a real onboarding:

  1. `has_eq_levy` gated `it_equalisation` but was not in PROFILE_FIELDS at all,
     so the field could never hold a value and the obligation sat in
     NEEDS_REVIEW permanently.
  2. Eight soft flags had no entry in FOLLOWUP_TEXT, so `gap_questions` never
     surfaced them — CHG-1/CHG-4, CERSAI, the DLG cap, bonus, ISD and Large
     Corporate were all silently unanswerable.
  3. `derive_csr` tested only the turnover limb of s.135(1), so CSR was unknown
     for every company under Rs.1000cr turnover — which is the entire launch
     segment.

These tests pin the invariant that closes all three: **every obligation must be
decidable by a customer who answers the questions we ask.** They do not assert
that any obligation is legally correct — no test can do that.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.engines.applicability import (
    MIN_ALIASES,
    PROFILE_FIELDS,
    STATE_KEYS,
    generate_compliance_universe,
)
from app.engines.profile_extraction import (
    FOLLOWUP_TEXT,
    SOFT_FLAGS,
    derive_csr,
    extract_profile,
)
from app.engines.thresholds import (
    CSR_NET_PROFIT_CR,
    CSR_NET_WORTH_CR,
    CSR_TURNOVER_CR,
)

LIBRARY = json.loads(
    (Path(__file__).parents[2] / "app/seed/nbfc_obligation_library_seed.json").read_text()
)

# Rule keys the engine resolves structurally rather than from a profile field.
_STRUCTURAL_KEYS = {"all"} | STATE_KEYS | set(MIN_ALIASES)


def _rule_keys() -> set[str]:
    keys: set[str] = set()
    for tpl in LIBRARY["obligation_templates"]:
        keys |= set((tpl.get("applicability_rule") or {}).keys())
    return keys


# ---------------------------------------------------------------------------
# 1. Nothing may be gated on a field that cannot exist
# ---------------------------------------------------------------------------

def test_every_rule_key_resolves_to_a_profile_field():
    """The `has_eq_levy` bug: a rule key with no profile field is unanswerable.

    It does not fail loudly — the obligation just sits in NEEDS_REVIEW for
    every customer forever, which reads as caution rather than a defect.
    """
    orphans = sorted(
        k for k in _rule_keys()
        if k not in PROFILE_FIELDS
        and k not in _STRUCTURAL_KEYS
        and not k.endswith("_min_cr")
    )
    assert not orphans, (
        "applicability rule keys with no profile field — these obligations can "
        f"never be decided: {orphans}"
    )


# ---------------------------------------------------------------------------
# 2. Nothing may be unanswerable for want of a question
# ---------------------------------------------------------------------------

def test_every_soft_flag_has_a_question():
    """A soft flag is only ever set by asking. No question means no answer."""
    missing = sorted(f for f in SOFT_FLAGS if f not in FOLLOWUP_TEXT)
    assert not missing, (
        "soft flags with no gap question — nobody is ever asked, so the "
        f"obligations they gate stay undecided: {missing}"
    )


def test_questions_are_not_asked_about_derived_fields():
    """Derived fields are resolved by asking for their inputs, not for the
    conclusion. Asking 'is CSR applicable?' just relays our own uncertainty."""
    for derived in ("csr_applicable", "esi_applicable", "gst_scheme",
                    "rbi_layer", "nbfc_category"):
        assert derived not in FOLLOWUP_TEXT, (
            f"{derived} is derived; ask for its inputs instead"
        )


# ---------------------------------------------------------------------------
# 3. The end-to-end promise for the launch segment
# ---------------------------------------------------------------------------

def _answered_segment_profile(**overrides) -> dict:
    """A growth-stage NBFC that answers every question the product asks.

    Built from SOFT_FLAGS rather than a hand-written list, so a newly added
    flag makes this profile incomplete and trips the coverage test below
    instead of quietly slipping through.
    """
    raw = {
        "cin": "U65999MH2021PTC123456", "pan": "AABCU9603R",
        "asset_size": "450", "turnover": "80",
        "net_worth": "120", "net_profit": "9",
        "employee_count": 45, "branch_count": 6,
        "deposit_taking": "No", "is_listed": "No", "has_listed_debt": "No",
        "gst_registered": "Yes", "operating_states": ["MH", "KA"],
        "nbfc_type": "loan company",
    }
    raw.update({flag: "No" for flag in SOFT_FLAGS})
    raw.update(overrides)
    return raw


def test_answering_every_question_decides_every_obligation():
    """The launch contract: answer what we ask, and nothing is left undecided.

    This is the test that would have caught all three holes at once.
    """
    prof = extract_profile(_answered_segment_profile(), LIBRARY)
    universe = generate_compliance_universe(LIBRARY, prof["profile"])
    undecided = [
        (r["template_id"], r["missing_fields"]) for r in universe["needs_review"]
    ]
    assert not undecided, (
        "obligations still undecidable after answering every question: "
        f"{undecided}"
    )


def test_no_gap_questions_remain_once_answered():
    prof = extract_profile(_answered_segment_profile(), LIBRARY)
    assert prof["gap_questions"] == []


def test_unanswered_flag_stays_undecided_rather_than_defaulting_to_no():
    """The honesty invariant. Silently reading 'unknown' as 'No' would drop the
    obligation off the calendar entirely — a missed filing presented as a clean
    dashboard, which is the worst failure this product has.
    """
    raw = _answered_segment_profile()
    del raw["is_secured_lender"]
    prof = extract_profile(raw, LIBRARY)
    universe = generate_compliance_universe(LIBRARY, prof["profile"])

    stuck = {r["template_id"] for r in universe["needs_review"]}
    assert "cersai_security" in stuck, "an unanswered flag must stay undecided"
    assert "is_secured_lender" in {g["field"] for g in prof["gap_questions"]}


def test_explicit_unknown_is_honoured_as_unknown():
    """'Not sure' in the UI must land as unknown, not as a parse failure that
    happens to look the same. The distinction shows up in provenance."""
    prof = extract_profile(
        _answered_segment_profile(is_secured_lender="unknown"), LIBRARY
    )
    assert prof["profile"]["is_secured_lender"] is None
    assert "unknown" in prof["provenance"]["is_secured_lender"]["note"]


# ---------------------------------------------------------------------------
# 4. CSR — all three limbs of s.135(1)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "turnover, net_worth, net_profit, limb",
    [
        (CSR_TURNOVER_CR.value, 1, 1, "turnover"),
        (1, CSR_NET_WORTH_CR.value, 1, "net worth"),
        (1, 1, CSR_NET_PROFIT_CR.value, "net profit"),
    ],
)
def test_csr_triggers_on_any_single_limb(turnover, net_worth, net_profit, limb):
    """s.135(1) is an OR across three limbs. Testing turnover alone under-reported
    CSR for every profitable company below Rs.1000cr turnover."""
    field = derive_csr(turnover, net_worth, net_profit)
    assert field.value is True
    assert limb in field.note


def test_csr_is_false_only_when_every_limb_is_known_and_below():
    below = derive_csr(1, 1, 1)
    assert below.value is False

    # A limb we were never told is not a limb that passed.
    assert derive_csr(1, None, 1).value is None
    assert derive_csr(None, None, None).value is None


def test_growth_stage_profit_triggers_csr_despite_small_turnover():
    """The concrete launch-segment case: Rs.80cr turnover, Rs.9cr profit. Under
    the turnover-only derivation this company was told 'unknown'."""
    prof = extract_profile(_answered_segment_profile(), LIBRARY)
    assert prof["profile"]["csr_applicable"] is True
    assert "net profit" in prof["provenance"]["csr_applicable"]["note"]


# ---------------------------------------------------------------------------
# 5. The guards must be able to fail
# ---------------------------------------------------------------------------

def test_guards_are_not_vacuous():
    assert _rule_keys(), "no rule keys found — the library did not load"
    assert SOFT_FLAGS and FOLLOWUP_TEXT
    # the orphan check would catch a reintroduced unanswerable key
    assert "definitely_not_a_field" not in PROFILE_FIELDS
    # and the segment profile really does exercise the whole flag set
    raw = _answered_segment_profile()
    assert all(flag in raw for flag in SOFT_FLAGS)
