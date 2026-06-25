"""
NBFC Instance Generator — Phase 1 reference implementation.

Converts applicable company_obligations into dated obligation_instances
over a rolling horizon, using each template's due_rule.

Covers the SCHEDULED families (recurring + governance cadence + data/dependency
anchored). EVENT-DRIVEN rules produce no scheduled instances here — they are
created on event triggers (see spec §6); this module exposes a stub for them.

Deterministic + idempotent: (company_obligation_id, period_label) is unique,
so re-running never duplicates.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta
from calendar import monthrange
from typing import Callable

# ---------------------------------------------------------------------------
# Calendar context
# ---------------------------------------------------------------------------
FY_START_MONTH = 4                      # India FY = 1 Apr – 31 Mar
QUARTER_ENDS = [(3, 31), (6, 30), (9, 30), (12, 31)]
TDS_QUARTER_ENDS = [(6, 30), (9, 30), (12, 31), (3, 31)]  # IT TDS quarters

# Minimal holiday set for working-day adjustment (extend via config table).
HOLIDAYS_2026_27 = {
    date(2026, 8, 15), date(2026, 10, 2), date(2026, 10, 20),
    date(2027, 1, 26), date(2027, 3, 25),
}

def is_working_day(d: date) -> bool:
    return d.weekday() < 5 and d not in HOLIDAYS_2026_27

def adjust(d: date, mode: str | None) -> tuple[date, bool]:
    if not mode:
        return d, False
    moved = False
    step = 1 if mode == "next" else -1
    while not is_working_day(d):
        d += timedelta(days=step); moved = True
    return d, moved

def month_end(y: int, m: int) -> date:
    return date(y, m, monthrange(y, m)[1])

def add_months(y: int, m: int, n: int) -> tuple[int, int]:
    idx = (m - 1) + n
    return y + idx // 12, idx % 12 + 1

def fy_of(d: date) -> int:
    return d.year if d.month >= FY_START_MONTH else d.year - 1


# ---------------------------------------------------------------------------
# Output record
# ---------------------------------------------------------------------------
@dataclass
class Instance:
    company_obligation_id: str
    template_id: str
    period_label: str
    due_date: str
    status: str = "pending"
    working_day_adjusted: bool = False
    generation_source: str = "scheduled"
    anchor: str | None = None           # dependency anchor description
    owner_role: str = "preparer"
    risk_level: str = "medium"


# ---------------------------------------------------------------------------
# Strategy registry: due_rule.type -> generator(due_rule, ctx) -> [(label,date,adj)]
# ctx provides: window_start, window_end, anchors (dependency dates), state
# ---------------------------------------------------------------------------
def _in_window(d: date, ctx) -> bool:
    return ctx["window_start"] <= d <= ctx["window_end"]

def gen_day_of_month(dr, ctx):
    out = []
    y, m = ctx["window_start"].year, ctx["window_start"].month
    for _ in range(15):  # walk months across the window
        py, pm = y, m                        # the period month
        ay, am = add_months(py, pm, dr.get("offset_month", 0))
        day = min(dr["day"], monthrange(ay, am)[1])
        due = date(ay, am, day)
        # March special (e.g., TDS deposited by 30 Apr for March)
        if dr.get("march_special") and pm == 3:
            ms = dr["march_special"]; due = date(ay, ms["month"], ms["day"])
        due, adj = adjust(due, dr.get("working_day_adjustment"))
        if _in_window(due, ctx):
            out.append((f"{py}-{pm:02d}", due, adj))
        y, m = add_months(y, m, 1)
    return out

def gen_days_after_month_end(dr, ctx):
    out = []
    y, m = ctx["window_start"].year, ctx["window_start"].month
    for _ in range(15):
        due = month_end(y, m) + timedelta(days=dr["days"])
        due, adj = adjust(due, dr.get("working_day_adjustment"))
        if _in_window(due, ctx):
            out.append((f"{y}-{m:02d}", due, adj))
        y, m = add_months(y, m, 1)
    return out

def gen_days_after_quarter_end(dr, ctx):
    out = []
    for y in range(ctx["window_start"].year, ctx["window_end"].year + 1):
        for (qm, qd) in QUARTER_ENDS:
            qend = date(y, qm, qd)
            days = dr["days"]
            # year-end quarter may carry a longer window (annual_days)
            if qm == 3 and "annual_days" in dr:
                days = dr["annual_days"]
            due = qend + timedelta(days=days)
            due, adj = adjust(due, dr.get("working_day_adjustment"))
            if _in_window(due, ctx):
                out.append((f"{y}Q{[3,6,9,12].index(qm)+1}", due, adj))
    return out

def gen_days_after_fortnight_end(dr, ctx):
    out, d = [], ctx["window_start"]
    while d <= ctx["window_end"]:
        end = date(d.year, d.month, 15) if d.day <= 15 else month_end(d.year, d.month)
        due = end + timedelta(days=dr["days"])
        due, adj = adjust(due, dr.get("working_day_adjustment"))
        if _in_window(due, ctx):
            out.append((f"{end.isoformat()}-FN", due, adj))
        d = end + timedelta(days=1)
    return [t for i, t in enumerate(out) if t not in out[:i]]

def gen_weekly(dr, ctx):
    out = []; d = ctx["window_start"]
    target = {"monday":0,"tuesday":1,"wednesday":2,"thursday":3,"friday":4}[dr["day_of_week"]]
    while d.weekday() != target:
        d += timedelta(days=1)
    while d <= ctx["window_end"]:
        due, adj = adjust(d, dr.get("working_day_adjustment"))
        out.append((f"WK-{d.isocalendar().week}-{d.year}", due, adj))
        d += timedelta(days=7)
    return out

def gen_fixed_date(dr, ctx):
    out = []
    for y in range(ctx["window_start"].year, ctx["window_end"].year + 1):
        due = date(y, dr["month"], dr["day"])
        due, adj = adjust(due, dr.get("working_day_adjustment"))
        if _in_window(due, ctx):
            out.append((f"FY{fy_of(due)}", due, adj))
    return out

def gen_days_after_fy_end(dr, ctx):
    out = []
    for y in range(ctx["window_start"].year - 1, ctx["window_end"].year + 1):
        due = date(y, 3, 31) + timedelta(days=dr["days"])
        due, adj = adjust(due, dr.get("working_day_adjustment"))
        if _in_window(due, ctx):
            out.append((f"FY{y-1}", due, adj))
    return out

def _date_list(dr, ctx, quarters=False):
    out = []
    for y in range(ctx["window_start"].year, ctx["window_end"].year + 1):
        for i, mmdd in enumerate(dr["dates"]):
            mm, dd = map(int, mmdd.split("-"))
            due = date(y, mm, dd)
            due, adj = adjust(due, dr.get("working_day_adjustment"))
            if _in_window(due, ctx):
                out.append((f"{y}-{mmdd}", due, adj))
    return out

def gen_advance_tax(dr, ctx): return _date_list(dr, ctx)
def gen_tds_return(dr, ctx): return _date_list(dr, ctx)
def gen_esi_return(dr, ctx): return _date_list(dr, ctx)
def gen_msme(dr, ctx): return _date_list(dr, ctx)

def gen_state_specific(dr, ctx):
    # half-yearly via common_dates, else monthly via default_day
    if "common_dates" in dr:
        return _date_list({"dates": dr["common_dates"],
                           "working_day_adjustment": dr.get("working_day_adjustment")}, ctx)
    return gen_day_of_month({"day": dr["default_day"], "offset_month": dr.get("offset_month", 1),
                             "working_day_adjustment": dr.get("working_day_adjustment")}, ctx)

def gen_max_gap(dr, ctx):
    # Board meetings: emit quarterly placeholders honoring the max-gap constraint
    out = []; d = ctx["window_start"]
    while d <= ctx["window_end"]:
        out.append((f"BM-{d.isoformat()}", d, False))
        d += timedelta(days=min(dr["days"], 90))
    return out

# Governance cadence anchored to FY
def gen_annual_fy(dr, ctx, month=3, day=31, label="REVIEW"):
    out = []
    for y in range(ctx["window_start"].year, ctx["window_end"].year + 1):
        due = month_end(y, 3) if (month == 3 and day == 31) else date(y, month, day)
        if _in_window(due, ctx):
            out.append((f"FY{fy_of(due)}-{label}", due, False))
    return out

def gen_first_bm(dr, ctx):
    # first board meeting of FY ~ first working day of April-ish; use 30 Apr placeholder
    out = []
    for y in range(ctx["window_start"].year, ctx["window_end"].year + 1):
        due = date(y, 4, 30)
        if _in_window(due, ctx):
            out.append((f"FY{fy_of(due)}-FIRSTBM", due, False))
    return out

# Dependency-anchored: due relative to an anchor obligation's ACTUAL date
def gen_days_after_anchor(dr, ctx, anchor_key, label):
    anchor = ctx["anchors"].get(anchor_key)
    if not anchor:
        return [(f"{label}-AWAIT", None, False)]   # parked until anchor known
    due = anchor + timedelta(days=dr["days"])
    due, adj = adjust(due, dr.get("working_day_adjustment"))
    return [(f"{label}-{anchor.isoformat()}", due, adj)] if _in_window(due, ctx) else []

# Data-anchored: license renewal lead_days before an expiry from a document
def gen_license_renewal(dr, ctx):
    expiry = ctx.get("license_expiry")
    if not expiry:
        return [("RENEWAL-AWAIT-EXPIRY", None, False)]
    due = expiry - timedelta(days=dr.get("lead_days", 30))
    return [(f"RENEWAL-{expiry.isoformat()}", due, False)] if _in_window(due, ctx) else []


SCHEDULED = {
    "day_of_month": gen_day_of_month,
    "days_after_month_end": gen_days_after_month_end,
    "days_after_quarter_end": gen_days_after_quarter_end,
    "days_after_fortnight_end": gen_days_after_fortnight_end,
    "weekly": gen_weekly,
    "fixed_date": gen_fixed_date,
    "days_after_fy_end": gen_days_after_fy_end,
    "advance_tax_dates": gen_advance_tax,
    "tds_return_dates": gen_tds_return,
    "esi_return_dates": gen_esi_return,
    "msme_dates": gen_msme,
    "state_specific": gen_state_specific,
    "max_gap_days": gen_max_gap,
    "first_board_meeting_of_fy": gen_first_bm,
    "license_renewal": gen_license_renewal,
}
# governance cadence types -> annual FY review instances
GOV_ANNUAL = {"annual_board_review", "annual_review", "before_board_report"}
GOV_QUARTERLY = {"audit_committee_cycle"}
# dependency-anchored types
ANCHORED = {
    "days_after_agm": ("agm_date", "FILING"),
    "days_after_tds_return": ("tds_return_date", "TDSCERT"),
}
# event-driven types -> NOT generated on a schedule (created on event)
EVENT_DRIVEN = {"days_after_event", "before_event", "hours_after_event",
                "around_due_date", "days_after_account_open",
                "per_loan_disbursal", "per_rate_reset", "risk_based_periodic"}
# continuous controls -> no dated instances (perpetual)
CONTINUOUS = {"continuous"}


def generate_instances(company_obligations: list[dict], ctx: dict) -> dict:
    instances: list[Instance] = []
    event_driven, continuous, parked = [], [], []

    for co in company_obligations:
        dr = co["due_rule"]; t = dr.get("type")
        meta = dict(company_obligation_id=co["company_obligation_id"],
                    template_id=co["template_id"], owner_role=co.get("owner_role", "preparer"),
                    risk_level=co.get("risk_level", "medium"))
        cctx = {**ctx, "state": co.get("state")}

        if t in EVENT_DRIVEN:
            event_driven.append(co["template_id"]); continue
        if t in CONTINUOUS:
            continuous.append(co["template_id"]); continue

        if t in SCHEDULED:
            rows = SCHEDULED[t](dr, cctx)
        elif t in GOV_ANNUAL:
            rows = gen_annual_fy(dr, cctx, label="REVIEW")
        elif t in GOV_QUARTERLY:
            rows = gen_days_after_quarter_end({"days": 30, "working_day_adjustment": "next"}, cctx)
        elif t in ANCHORED:
            akey, lbl = ANCHORED[t]; rows = gen_days_after_anchor(dr, cctx, akey, lbl)
        else:
            rows = []  # unknown -> log as gap

        for label, due, adj in rows:
            if due is None:
                parked.append((co["template_id"], label)); continue
            instances.append(Instance(due_date=due.isoformat(), period_label=label,
                                       working_day_adjusted=adj, anchor=cctx.get("state"),
                                       **meta))

    instances.sort(key=lambda i: i.due_date)
    return {"instances": instances, "event_driven": event_driven,
            "continuous": continuous, "parked": parked}


# ---------------------------------------------------------------------------
# Overdue sweep + reminder schedule (pure functions for the daily job)
# ---------------------------------------------------------------------------
def is_overdue(inst: Instance, today: date) -> bool:
    return (inst.status not in ("completed", "not_applicable")
            and date.fromisoformat(inst.due_date) < today)

def reminder_schedule(due: date, lead_days=(7, 3, 1), overdue_days=(1, 3, 7)) -> dict:
    return {
        "pre_due": [(due - timedelta(days=d)).isoformat() for d in lead_days],
        "overdue_escalation": [(due + timedelta(days=d)).isoformat() for d in overdue_days],
    }


if __name__ == "__main__":
    from applicability_engine import generate_compliance_universe
    lib = json.load(open("/mnt/user-data/outputs/nbfc_obligation_library_seed.json"))
    tpl_by_id = {t["template_id"]: t for t in lib["obligation_templates"]}

    # Reuse golden Profile B (middle-layer, multi-state) -> applicable set
    profile_B = {
        "rbi_registered": True, "nbfc_category": "nd_si", "rbi_layer": "middle",
        "deposit_taking": False, "is_listed": False, "has_listed_debt": True,
        "asset_size_cr": 3000, "turnover_cr": 450, "employee_count": 260,
        "branch_count": 22, "operating_states": ["MH", "KA", "TN", "DL"],
        "gst_registered": True, "gst_scheme": "regular", "is_isd": False,
        "esi_applicable": True, "has_foreign_investment": True,
        "has_nonresident_payments": True, "has_international_transactions": True,
        "has_reportable_accounts": True, "has_msme_dues": True, "csr_applicable": True,
        "has_sbo": True, "has_capital_changes": True, "has_ecb": True, "has_odi": False,
        "has_eligible_bonus_employees": False, "does_digital_lending": False,
        "has_dlg_arrangements": False, "has_floating_rate_retail": True,
        "is_secured_lender": True, "is_large_corporate": True, "has_borrowings": True,
    }
    uni = generate_compliance_universe(lib, profile_B)

    # Build company_obligations input (carry due_rule + meta from template)
    cobs = []
    for r in uni["applicable"]:
        base_id = r["template_id"].split("__")[0]
        t = tpl_by_id[base_id]
        cobs.append({
            "company_obligation_id": f'co_{r["template_id"]}',
            "template_id": r["template_id"],
            "due_rule": t["due_rule"], "owner_role": t["default_owner_role"],
            "risk_level": t["risk_level"], "state": r["state"],
        })

    ctx = {
        "window_start": date(2026, 4, 1), "window_end": date(2027, 3, 31),
        "anchors": {"agm_date": date(2026, 9, 25), "tds_return_date": date(2026, 7, 31)},
        "license_expiry": date(2026, 11, 30),
    }
    out = generate_instances(cobs, ctx)
    ins = out["instances"]
    print(f"Applicable company_obligations: {len(cobs)}")
    print(f"Dated instances generated (FY2026-27 window): {len(ins)}")
    print(f"Event-driven (created on trigger, not scheduled): {len(out['event_driven'])}")
    print(f"Continuous controls (no dated instance): {len(out['continuous'])}")
    print(f"Parked awaiting anchor/expiry: {len(out['parked'])}  e.g. {out['parked'][:3]}")
    from collections import Counter
    print("Instances by month:", dict(sorted(Counter(i.due_date[:7] for i in ins).items())))
    wda = sum(1 for i in ins if i.working_day_adjusted)
    print(f"Working-day-adjusted due dates: {wda}")
    print("\nSample April 2026 instances:")
    for i in [x for x in ins if x.due_date.startswith("2026-04")][:8]:
        print(f"  {i.due_date}  {i.template_id:28} {i.period_label:12} owner={i.owner_role}")
