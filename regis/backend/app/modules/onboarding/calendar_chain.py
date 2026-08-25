"""
Pure orchestration of the core chain (Milestone M4, deterministic part):

    profile  --applicability-->  universe  --build-->  company_obligations
             --instance gen-->  obligation_instances

These are pure functions over dicts so they are unit-testable with no DB and are
reused verbatim by the DB-backed onboarding service. The service's only extra job
is to persist what these return and write audit rows.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.engines.applicability import generate_compliance_universe
from app.engines.instance_generator import generate_instances


def build_company_obligations(universe: dict, library: dict) -> list[dict]:
    """
    Turn the applicability engine's APPLICABLE results into the company_obligations
    input the instance generator consumes. Carries due_rule + owner + risk + state
    from the (base) template, preserving the per-state expansion ids.
    """
    tpl_by_id = {t["template_id"]: t for t in library["obligation_templates"]}
    cobs: list[dict] = []
    for r in universe["applicable"]:
        base_id = r["template_id"].split("__")[0]
        t = tpl_by_id[base_id]
        cobs.append({
            "company_obligation_id": f'co_{r["template_id"]}',
            "template_id": r["template_id"],
            "due_rule": t["due_rule"],
            "owner_role": t["default_owner_role"],
            "risk_level": t["risk_level"],
            "state": r.get("state"),
        })
    return cobs


def fy_start(on: date) -> date:
    """Indian financial year containing `on` — 1 April to 31 March."""
    return date(on.year if on.month >= 4 else on.year - 1, 4, 1)


def fy_end(on: date) -> date:
    return date(fy_start(on).year + 1, 3, 31)


def default_window(start: date | None = None, months: int = 12) -> dict:
    """The financial year containing `start`, so the FY audit trail is complete.

    Instances dated before the org actually onboarded are marked `historical` at
    persistence time rather than excluded here — see PRD 14.2. Generating them
    and labelling them is what keeps the FY record whole without accusing a new
    customer of missing filings they made before they had this product.

    `months` is honoured for a non-FY horizon; it previously computed a date and
    threw it away, so the parameter did nothing and the end was always hardcoded.
    """
    start = start or date.today()
    if months == 12:
        return {"window_start": fy_start(start), "window_end": fy_end(start)}
    end_year, end_month = divmod((start.month - 1) + months, 12)
    return {"window_start": start,
            "window_end": date(start.year + end_year, end_month + 1, 1) - timedelta(days=1)}


def run_chain(library: dict, profile: dict, ctx: dict | None = None) -> dict:
    """
    Full deterministic chain. Returns the universe, the company_obligations, and
    the generator output (dated instances + event-driven/continuous/parked sets).
    `ctx` provides the generation window, dependency anchors, license expiry, and
    (optionally) a DB-backed holiday set.
    """
    universe = generate_compliance_universe(library, profile)
    cobs = build_company_obligations(universe, library)
    ctx = ctx or {
        "window_start": date(2026, 4, 1),
        "window_end": date(2027, 3, 31),
        "anchors": {"agm_date": date(2026, 9, 25), "tds_return_date": date(2026, 7, 31)},
        "license_expiry": date(2026, 11, 30),
    }
    gen = generate_instances(cobs, ctx)
    return {"universe": universe, "company_obligations": cobs, "generation": gen}
