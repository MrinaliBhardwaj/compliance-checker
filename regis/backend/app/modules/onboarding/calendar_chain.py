"""
Pure orchestration of the core chain (Milestone M4, deterministic part):

    profile  --applicability-->  universe  --build-->  company_obligations
             --instance gen-->  obligation_instances

These are pure functions over dicts so they are unit-testable with no DB and are
reused verbatim by the DB-backed onboarding service. The service's only extra job
is to persist what these return and write audit rows.
"""

from __future__ import annotations

from datetime import date

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
        cobs.append(
            {
                "company_obligation_id": f'co_{r["template_id"]}',
                "template_id": r["template_id"],
                "due_rule": t["due_rule"],
                "owner_role": t["default_owner_role"],
                "risk_level": t["risk_level"],
                "state": r.get("state"),
            }
        )
    return cobs


NEXT_FY_LEAD_DAYS = 60


def fy_windows(today: date) -> list[tuple[date, date]]:
    """Indian FY (Apr-Mar) windows to generate for a calendar created `today`.

    The current FY, plus the next one in the FY's last 60 days so a late-year
    calendar isn't nearly empty. Separate windows rather than one long one: the
    generator walks at most 15 months of periods from window_start.
    """
    y = today.year if today.month >= 4 else today.year - 1
    windows = [(date(y, 4, 1), date(y + 1, 3, 31))]
    if (windows[0][1] - today).days < NEXT_FY_LEAD_DAYS:
        windows.append((date(y + 1, 4, 1), date(y + 2, 3, 31)))
    return windows


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
