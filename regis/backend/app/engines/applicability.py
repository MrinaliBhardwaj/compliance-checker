"""
NBFC Applicability-Rule Engine — Phase 1 (ported verbatim from the verified
reference `applicability_engine.py`).

Deterministic core: maps a structured company profile against the
obligation_templates library and decides, per obligation:
    APPLICABLE | NOT_APPLICABLE | NEEDS_REVIEW
with a confidence score, the matched/failed conditions, any missing
profile fields, a plain-language rationale, and per-state expansion.

The engine is deterministic and auditable. The LLM layer (profile
extraction, rationale polish, review questions) sits AROUND this core
and never overrides a deterministic decision.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

# ---------------------------------------------------------------------------
# Profile schema — the canonical onboarding output the engine consumes.
# Every field referenced by any applicability rule is represented here.
# `None` means "not answered" -> drives NEEDS_REVIEW rather than a silent No.
# ---------------------------------------------------------------------------
PROFILE_FIELDS = {
    # hard identity (high trust)
    "rbi_registered": bool,
    "nbfc_category": str,        # "icc" | "nd_si" | "deposit_taking" | ...
    "rbi_layer": str,            # "base" | "middle" | "upper"
    "deposit_taking": bool,
    "is_listed": bool,
    "has_listed_debt": bool,
    "asset_size_cr": (int, float),
    "turnover_cr": (int, float),
    "employee_count": int,
    "branch_count": int,
    "operating_states": list,    # ["MH","KA",...]
    "gst_registered": bool,
    "gst_scheme": str,           # "regular" | "qrmp"
    "is_isd": bool,
    "esi_applicable": bool,
    # self-declared operational flags (softer -> may need review if absent)
    "has_foreign_investment": bool,
    "has_nonresident_payments": bool,
    "has_international_transactions": bool,
    "has_reportable_accounts": bool,
    "has_msme_dues": bool,
    "csr_applicable": bool,
    "has_sbo": bool,
    "has_capital_changes": bool,
    "has_ecb": bool,
    "has_odi": bool,
    "has_eligible_bonus_employees": bool,
    "does_digital_lending": bool,
    "has_dlg_arrangements": bool,
    "has_floating_rate_retail": bool,
    "is_secured_lender": bool,
    "is_large_corporate": bool,
    "has_borrowings": bool,
}

# Fields treated as "hard" (objective, asked directly, high trust when present)
HARD_FIELDS = {
    "rbi_registered", "nbfc_category", "rbi_layer", "deposit_taking",
    "is_listed", "has_listed_debt", "asset_size_cr", "turnover_cr",
    "employee_count", "branch_count", "operating_states",
    "gst_registered", "gst_scheme", "is_isd", "esi_applicable",
}

# Alias map: rule-key shorthand -> profile field for irregular numeric mins
MIN_ALIASES = {
    "has_employees_min": "employee_count",
    "has_branches_min": "branch_count",
}

# State-scoped condition keys -> the obligation expands per matching state
STATE_KEYS = {"pt_states", "lwf_states"}

# Templates that are inherently per-location even without a *_states rule
# (Shops & Establishment is registered per establishment/state).
PER_STATE_TEMPLATE_IDS = {"lab_shops_renewal"}

# Numeric-threshold proximity (%) within which we down-rank confidence,
# because a near-boundary classification is the riskiest to get wrong.
BOUNDARY_BAND = 0.10

# Confidence caps
CONF_HARD = 1.0
CONF_SOFT_PRESENT = 0.9
CONF_BOUNDARY = 0.6
CONF_MISSING = 0.4
# A DRAFT_UNVERIFIED template can never be presented as fully certain.
CONF_UNVERIFIED_CAP = 0.7


class Decision(StrEnum):
    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NEEDS_REVIEW = "NEEDS_REVIEW"


@dataclass
class ConditionResult:
    key: str
    predicate: str
    expected: Any
    actual: Any
    passed: bool
    missing: bool = False
    near_boundary: bool = False


@dataclass
class ObligationResult:
    template_id: str
    title: str
    category: str
    decision: str
    confidence: float
    rationale: str
    conditions: list = field(default_factory=list)
    missing_fields: list = field(default_factory=list)
    state: str | None = None          # set when expanded per state
    template_verified: bool = True


# ---------------------------------------------------------------------------
# Predicate evaluation — one (key, value) condition vs the profile.
# Returns a ConditionResult. The 7 predicate types cover 100% of the
# live library's rule surface.
# ---------------------------------------------------------------------------
def eval_condition(key: str, value: Any, profile: dict) -> ConditionResult:
    # 1. universal
    if key == "all":
        return ConditionResult(key, "universal", True, True, True)

    # 2. numeric min on *_min_cr  (asset_size_min_cr -> asset_size_cr)
    if key.endswith("_min_cr"):
        pf = key.replace("_min", "")            # asset_size_min_cr -> asset_size_cr
        actual = profile.get(pf)
        if actual is None:
            return ConditionResult(key, ">=", value, None, False, missing=True)
        passed = actual >= value
        nb = passed and value > 0 and actual < value * (1 + BOUNDARY_BAND)
        nb = nb or ((not passed) and actual > value * (1 - BOUNDARY_BAND))
        return ConditionResult(key, ">=", value, actual, passed, near_boundary=nb)

    # 3. numeric min via alias  (has_employees_min -> employee_count)
    if key.endswith("_min"):
        pf = MIN_ALIASES.get(key)
        actual = profile.get(pf) if pf else None
        if actual is None:
            return ConditionResult(key, ">=", value, None, False, missing=True)
        passed = actual >= value
        nb = passed and value > 0 and actual < value * (1 + BOUNDARY_BAND)
        nb = nb or ((not passed) and value > 0 and actual > value * (1 - BOUNDARY_BAND))
        return ConditionResult(key, ">=", value, actual, passed, near_boundary=nb)

    # 4. state-set intersection  (pt_states / lwf_states)
    if key in STATE_KEYS:
        actual = profile.get("operating_states")
        if actual is None:
            return ConditionResult(key, "intersects", value, None, False, missing=True)
        inter = sorted(set(actual) & set(value))
        return ConditionResult(key, "intersects", value, inter, bool(inter))

    # 5. enum membership  (rule value is a list, profile value is scalar)
    if isinstance(value, list):
        actual = profile.get(key)
        if actual is None:
            return ConditionResult(key, "in", value, None, False, missing=True)
        return ConditionResult(key, "in", value, actual, actual in value)

    # 6. boolean truthiness  (value is True)
    if isinstance(value, bool):
        actual = profile.get(key)
        if actual is None:
            return ConditionResult(key, "==", value, None, False, missing=True)
        return ConditionResult(key, "==", value, actual, bool(actual) == value)

    # 7. scalar equality  (gst_scheme == "qrmp")
    actual = profile.get(key)
    if actual is None:
        return ConditionResult(key, "==", value, None, False, missing=True)
    return ConditionResult(key, "==", value, actual, actual == value)


# ---------------------------------------------------------------------------
# Confidence model — derived from the condition results + template status.
# ---------------------------------------------------------------------------
def score_confidence(conds: list[ConditionResult], template_verified: bool) -> float:
    if not conds:
        conf = CONF_HARD
    else:
        per = []
        for c in conds:
            if c.missing:
                per.append(CONF_MISSING)
            elif c.near_boundary:
                per.append(CONF_BOUNDARY)
            elif c.key == "all" or c.key in HARD_FIELDS or c.key.replace("_min", "").replace("_cr", "") in {"asset_size", "turnover"} or c.key in MIN_ALIASES or c.key in STATE_KEYS:
                per.append(CONF_HARD)
            else:
                per.append(CONF_SOFT_PRESENT)
        conf = min(per)
    if not template_verified:
        conf = min(conf, CONF_UNVERIFIED_CAP)
    return round(conf, 2)


# ---------------------------------------------------------------------------
# Rationale — deterministic, template-based, auditable plain language.
# (An LLM may rephrase this for tone, but the facts come from here.)
# ---------------------------------------------------------------------------
def build_rationale(decision: Decision, conds: list[ConditionResult]) -> str:
    if not conds or (len(conds) == 1 and conds[0].key == "all"):
        return "Applies to all NBFCs / companies (universal obligation)."
    parts = []
    for c in conds:
        if c.missing:
            parts.append(f"'{c.key}' not yet answered")
            continue
        if c.predicate == "intersects":
            parts.append(f"operates in {c.actual or 'no matching state'} (state-scoped)")
        elif c.predicate == ">=":
            parts.append(f"{c.key.replace('_min_cr','').replace('_min','')} = {c.actual} {'>=' if c.passed else '<'} {c.expected}")
        elif c.predicate == "in":
            parts.append(f"{c.key} = '{c.actual}' {'is' if c.passed else 'is not'} in {c.expected}")
        else:
            parts.append(f"{c.key} = {c.actual} (required {c.expected})")
    joined = "; ".join(parts)
    if decision == Decision.APPLICABLE:
        return f"Included because: {joined}."
    if decision == Decision.NEEDS_REVIEW:
        return f"Needs confirmation: {joined}."
    return f"Excluded because: {joined}."


# ---------------------------------------------------------------------------
# Evaluate a single template against the profile.
# Implicit AND across all conditions in the rule.
# ---------------------------------------------------------------------------
def evaluate_template(tpl: dict, profile: dict) -> list[ObligationResult]:
    rule = tpl.get("applicability_rule", {}) or {"all": True}
    conds = [eval_condition(k, v, profile) for k, v in rule.items()]
    missing = [c.key for c in conds if c.missing]
    template_verified = tpl.get("verification_status") == "VERIFIED"

    # Decision logic:
    #   any hard failure (failed & not missing)        -> NOT_APPLICABLE
    #   else any missing field                         -> NEEDS_REVIEW
    #   else all passed                                -> APPLICABLE
    hard_fail = any((not c.passed) and (not c.missing) for c in conds)
    if hard_fail:
        decision = Decision.NOT_APPLICABLE
    elif missing:
        decision = Decision.NEEDS_REVIEW
    else:
        decision = Decision.APPLICABLE

    conf = score_confidence(conds, template_verified)
    rationale = build_rationale(decision, conds)

    base = ObligationResult(
        template_id=tpl["template_id"], title=tpl["title"], category=tpl["category"],
        decision=decision.value, confidence=conf, rationale=rationale,
        conditions=[asdict(c) for c in conds], missing_fields=missing,
        template_verified=template_verified,
    )

    # State expansion: only for APPLICABLE state-scoped obligations.
    state_keys_present = [k for k in rule if k in STATE_KEYS]
    is_per_state = bool(state_keys_present) or tpl["template_id"] in PER_STATE_TEMPLATE_IDS
    if decision == Decision.APPLICABLE and is_per_state:
        if state_keys_present:
            allowed = set(rule[state_keys_present[0]])
            states = sorted(set(profile.get("operating_states", []) or []) & allowed)
        else:
            states = sorted(profile.get("operating_states", []) or [])
        out = []
        for st in states:
            r = ObligationResult(**{**asdict(base)})
            r.template_id = f'{base.template_id}__{st}'
            r.state = st
            r.title = f'{base.title} [{st}]'
            r.conditions = base.conditions
            out.append(r)
        return out or [base]
    return [base]


# ---------------------------------------------------------------------------
# Evaluate the whole library against a profile -> generation result.
# ---------------------------------------------------------------------------
def generate_compliance_universe(library: dict, profile: dict) -> dict:
    results: list[ObligationResult] = []
    for tpl in library["obligation_templates"]:
        results.extend(evaluate_template(tpl, profile))

    applicable = [r for r in results if r.decision == Decision.APPLICABLE.value]
    review = [r for r in results if r.decision == Decision.NEEDS_REVIEW.value]
    not_app = [r for r in results if r.decision == Decision.NOT_APPLICABLE.value]

    laws_touched = {
        tpl["law_id"]
        for tpl in library["obligation_templates"]
        for r in applicable
        if r.template_id.split("__")[0] == tpl["template_id"]
    }
    provisional = any(not r.template_verified for r in applicable + review)

    return {
        "summary": {
            "applicable": len(applicable),
            "needs_review": len(review),
            "not_applicable": len(not_app),
            "laws_touched": len(laws_touched),
            "library_provisional": provisional,
        },
        "applicable": [asdict_clean(r) for r in applicable],
        "needs_review": [asdict_clean(r) for r in review],
        "not_applicable": [asdict_clean(r) for r in not_app],
    }


def asdict_clean(r: ObligationResult) -> dict:
    d = asdict(r)
    d.pop("conditions", None)  # keep top-level output compact; full trace available on demand
    return d


# ---------------------------------------------------------------------------
# Re-evaluation diff: compare a fresh run against the previously stored set.
# Returns added / removed / unchanged for the PRD "regenerate with diff" view.
# ---------------------------------------------------------------------------
def diff_universe(old_ids: set[str], new_result: dict) -> dict:
    new_ids = {r["template_id"] for r in new_result["applicable"]}
    return {
        "added": sorted(new_ids - old_ids),
        "removed": sorted(old_ids - new_ids),   # deactivate (is_active=False), never delete
        "unchanged": sorted(new_ids & old_ids),
    }
