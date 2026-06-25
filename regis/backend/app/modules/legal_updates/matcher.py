"""
Legal-update applicability matcher — deterministic, and deliberately built on the
SAME predicate engine as obligation applicability. An update's `affects_filter`
uses the identical rule DSL (rbi_layer membership, *_min_cr, boolean flags, state
intersection), so there is ONE rule language and one tested evaluator in the system.

Three-state, same safety property as the obligation engine:
  - all conditions pass on known fields  -> AFFECTS (applicable)
  - some referenced field unknown         -> MAY_AFFECT (review manually)  [never dropped]
  - a condition fails on a known value    -> NOT_APPLICABLE (filtered out)
Empty filter -> affects everyone.
"""
from __future__ import annotations

from app.engines.applicability import Decision, eval_condition


def match_update(affects_filter: dict | None, profile: dict) -> dict:
    if not affects_filter:
        return {"decision": Decision.APPLICABLE.value, "missing_fields": [], "matched": ["all"]}

    conds = [eval_condition(k, v, profile) for k, v in affects_filter.items()]
    missing = [c.key for c in conds if c.missing]
    hard_fail = any((not c.passed) and (not c.missing) for c in conds)
    if hard_fail:
        decision = Decision.NOT_APPLICABLE
    elif missing:
        decision = Decision.NEEDS_REVIEW
    else:
        decision = Decision.APPLICABLE
    matched = [c.key for c in conds if c.passed]
    return {"decision": decision.value, "missing_fields": missing, "matched": matched}


# Precedence when an org has multiple entity profiles: surface the strongest signal.
_RANK = {Decision.APPLICABLE.value: 2, Decision.NEEDS_REVIEW.value: 1,
         Decision.NOT_APPLICABLE.value: 0}


def match_org(affects_filter: dict | None, profiles: list[dict]) -> dict:
    """An update affects the org if it affects ANY entity profile (strongest wins)."""
    if not profiles:
        # no profile yet -> can't decide -> surface for manual review, never drop
        return {"decision": Decision.NEEDS_REVIEW.value, "missing_fields": ["profile"],
                "matched": []}
    best = None
    for p in profiles:
        m = match_update(affects_filter, p)
        if best is None or _RANK[m["decision"]] > _RANK[best["decision"]]:
            best = m
    return best
