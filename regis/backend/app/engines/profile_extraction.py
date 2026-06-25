"""
NBFC Onboarding Profile Extraction — Phase 1 (ported verbatim from the verified
reference `profile_extraction.py`).

Turns raw onboarding input (questionnaire answers, entity-master fields, free
text, document-extracted identifiers) into the EXACT structured profile the
applicability engine consumes — with per-field provenance, confidence,
validation, derivation, consistency checks, and a review list.

Deterministic core implemented here: normalization, format validation,
derivation rules (SBR layer, regulatory category, ESI/CSR/GST), consistency
engine, confidence + provenance, completeness/gap detection.

The LLM layer (free-text -> field values, one targeted follow-up question per
gap, derivation explanations) sits ABOVE this and is in app.ai (stubbed).
Unresolved fields are intentionally left None — the applicability engine already
routes those to NEEDS_REVIEW, so the two components compose without guessing.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from enum import Enum

from .applicability import HARD_FIELDS


# ---------------------------------------------------------------------------
# Provenance + confidence
# ---------------------------------------------------------------------------
class Source(str, Enum):
    ASKED = "ASKED"               # answered directly in the questionnaire
    EXTRACTED = "EXTRACTED"       # parsed from an uploaded document
    DERIVED = "DERIVED"           # inferred from other fields (confirm)
    DEFAULT_UNKNOWN = "DEFAULT_UNKNOWN"  # not provided -> review downstream


CONF = {Source.ASKED: 0.97, Source.EXTRACTED: 0.90,
        Source.DERIVED: 0.85, Source.DEFAULT_UNKNOWN: 0.0}


@dataclass
class Field:
    value: object
    source: Source
    confidence: float
    note: str = ""


# ---------------------------------------------------------------------------
# Normalizers
# ---------------------------------------------------------------------------
STATE_MAP = {
    "maharashtra": "MH", "karnataka": "KA", "tamil nadu": "TN", "tamilnadu": "TN",
    "delhi": "DL", "west bengal": "WB", "gujarat": "GJ", "andhra pradesh": "AP",
    "telangana": "TS", "madhya pradesh": "MP", "haryana": "HR", "rajasthan": "RJ",
    "uttar pradesh": "UP", "kerala": "KL", "punjab": "PB",
}
STATE_CODES = set(STATE_MAP.values())


def normalize_states(raw) -> Field:
    if raw is None:
        return Field(None, Source.DEFAULT_UNKNOWN, 0.0, "states not provided")
    items = raw if isinstance(raw, list) else re.split(r"[,;/]| and ", str(raw))
    out, unknown = [], []
    for it in items:
        t = it.strip().lower()
        if not t:
            continue
        if t.upper() in STATE_CODES:
            out.append(t.upper())
        elif t in STATE_MAP:
            out.append(STATE_MAP[t])
        else:
            unknown.append(it.strip())
    out = sorted(set(out))
    note = f"unrecognized: {unknown}" if unknown else ""
    src = Source.ASKED if out and not unknown else (Source.ASKED if out else Source.DEFAULT_UNKNOWN)
    return Field(out, src, CONF[Source.ASKED] if out else 0.0, note)


def parse_amount_cr(raw) -> Field:
    """Parse asset size / turnover to a number in Rs. crore; keep band awareness."""
    if raw is None:
        return Field(None, Source.DEFAULT_UNKNOWN, 0.0, "amount not provided")
    if isinstance(raw, (int, float)):
        return Field(float(raw), Source.ASKED, CONF[Source.ASKED])
    s = str(raw).lower().replace(",", "").replace("₹", "").replace("rs", "")
    s = s.replace("crore", "").replace("cr", "").strip()
    # word numbers (light touch)
    s = s.replace("thousand", "000").replace("around", "").replace("approx", "").strip()
    # band like "500-1000" or ">5000" or "5000+"
    band = re.findall(r"\d+\.?\d*", s)
    if not band:
        return Field(None, Source.DEFAULT_UNKNOWN, 0.0, f"unparseable amount '{raw}'")
    nums = [float(x) for x in band]
    if len(nums) >= 2:  # a band -> use midpoint, flag near-boundary
        val = sum(nums[:2]) / 2
        return Field(val, Source.ASKED, 0.80, f"band {nums[:2]} -> midpoint {val}")
    return Field(nums[0], Source.ASKED, CONF[Source.ASKED])


def normalize_bool(raw) -> Field:
    if raw is None:
        return Field(None, Source.DEFAULT_UNKNOWN, 0.0)
    if isinstance(raw, bool):
        return Field(raw, Source.ASKED, CONF[Source.ASKED])
    t = str(raw).strip().lower()
    if t in ("yes", "y", "true", "1"):
        return Field(True, Source.ASKED, CONF[Source.ASKED])
    if t in ("no", "n", "false", "0"):
        return Field(False, Source.ASKED, CONF[Source.ASKED])
    if t in ("n/a", "na", "not applicable", "don't know", "unknown"):
        return Field(None, Source.DEFAULT_UNKNOWN, 0.0, "answered unknown/NA")
    return Field(None, Source.DEFAULT_UNKNOWN, 0.0, f"unparseable bool '{raw}'")


NBFC_BUSINESS = {
    "investment and credit": "icc", "investment & credit": "icc", "icc": "icc",
    "infrastructure": "ifc", "ifc": "ifc", "microfinance": "mfi", "mfi": "mfi",
    "factor": "factor", "housing finance": "hfc",
}


def normalize_business(raw) -> Field:
    if raw is None:
        return Field(None, Source.DEFAULT_UNKNOWN, 0.0)
    t = str(raw).strip().lower()
    for k, v in NBFC_BUSINESS.items():
        if k in t:
            return Field(v, Source.ASKED, CONF[Source.ASKED])
    return Field("other", Source.ASKED, 0.6, f"business type '{raw}' -> other")


# ---------------------------------------------------------------------------
# Format validators (identifiers)
# ---------------------------------------------------------------------------
VALIDATORS = {
    "cin": r"^[LUu]\d{5}[A-Za-z]{2}\d{4}[A-Za-z]{3}\d{6}$",
    "pan": r"^[A-Za-z]{5}\d{4}[A-Za-z]$",
    "gstin": r"^\d{2}[A-Za-z]{5}\d{4}[A-Za-z]\d[A-Za-z\d]{2}$",
    "tan": r"^[A-Za-z]{4}\d{5}[A-Za-z]$",
}


def validate_identifier(kind: str, value: str) -> tuple[bool, str]:
    if not value:
        return False, f"{kind} missing"
    ok = bool(re.match(VALIDATORS[kind], value.strip()))
    return ok, "" if ok else f"{kind} '{value}' fails format check"


# ---------------------------------------------------------------------------
# Derivation rules (SBR + statutory thresholds). All flagged DERIVED -> confirm.
# Verify thresholds against current RBI/statute during content pass.
# ---------------------------------------------------------------------------
def derive_regulatory_category(asset_cr, deposit) -> Field:
    if deposit is True:
        return Field("deposit_taking", Source.DERIVED, 0.85, "deposit-taking NBFC")
    if asset_cr is None:
        return Field(None, Source.DEFAULT_UNKNOWN, 0.0, "asset size unknown")
    if asset_cr >= 500:
        return Field("nd_si", Source.DERIVED, 0.85, "non-deposit, asset >= Rs.500cr")
    return Field("icc", Source.DERIVED, 0.85, "non-deposit, asset < Rs.500cr")


def derive_rbi_layer(asset_cr, deposit, rbi_designated_upper=False) -> Field:
    if rbi_designated_upper:
        return Field("upper", Source.ASKED, CONF[Source.ASKED], "RBI-designated Upper Layer")
    if deposit is True:
        return Field("middle", Source.DERIVED, 0.85, "deposit-taking -> Middle Layer (SBR)")
    if asset_cr is None:
        return Field(None, Source.DEFAULT_UNKNOWN, 0.0, "asset size unknown")
    if asset_cr >= 1000:
        return Field("middle", Source.DERIVED, 0.85, "asset >= Rs.1000cr -> Middle Layer")
    return Field("base", Source.DERIVED, 0.80,
                 "asset < Rs.1000cr -> Base Layer (RBI may place higher; confirm)")


def derive_esi(employee_count) -> Field:
    if employee_count is None:
        return Field(None, Source.DEFAULT_UNKNOWN, 0.0)
    return Field(employee_count >= 10, Source.DERIVED, 0.80,
                 "ESI threshold ~10 employees (state-varying; confirm)")


def derive_gst_scheme(turnover_cr) -> Field:
    if turnover_cr is None:
        return Field(None, Source.DEFAULT_UNKNOWN, 0.0)
    scheme = "qrmp" if turnover_cr <= 5 else "regular"
    return Field(scheme, Source.DERIVED, 0.70,
                 "QRMP is an election (<= Rs.5cr eligible); confirm choice")


def derive_csr(turnover_cr) -> Field:
    if turnover_cr is None:
        return Field(None, Source.DEFAULT_UNKNOWN, 0.0,
                     "needs net worth / net profit to confirm s.135")
    if turnover_cr >= 1000:
        return Field(True, Source.DERIVED, 0.80, "turnover >= Rs.1000cr (s.135)")
    return Field(None, Source.DEFAULT_UNKNOWN, 0.0,
                 "below turnover trigger; check net worth/profit")


# ---------------------------------------------------------------------------
# Consistency engine
# ---------------------------------------------------------------------------
@dataclass
class Issue:
    field: str
    severity: str   # contradiction | warning
    detail: str


def consistency_checks(p: dict, asserted: dict) -> list[Issue]:
    issues = []
    asset = p["asset_size_cr"].value
    # user-asserted layer vs derived expectation
    a_layer = asserted.get("rbi_layer")
    if a_layer == "base" and asset is not None and asset >= 1000:
        issues.append(Issue("rbi_layer", "contradiction",
            f"answered Base but asset Rs.{asset}cr implies Middle Layer (>=1000)"))
    if p["deposit_taking"].value is True and a_layer == "base":
        issues.append(Issue("rbi_layer", "contradiction",
            "deposit-taking NBFCs are Middle Layer under SBR, not Base"))
    # states vs branches
    if p["branch_count"].value and not p["operating_states"].value:
        issues.append(Issue("operating_states", "warning",
            f"{p['branch_count'].value} branches but no operating states provided"))
    # listed debt vs is_listed coherence
    if p["has_listed_debt"].value and p["is_listed"].value is None:
        issues.append(Issue("is_listed", "warning",
            "has listed debt securities; confirm equity-listing status"))
    # near-boundary asset size
    if asset is not None and 900 <= asset <= 1100:
        issues.append(Issue("asset_size_cr", "warning",
            f"asset Rs.{asset}cr is near the Rs.1000cr layer boundary; confirm exact figure"))
    return issues


# ---------------------------------------------------------------------------
# Extraction orchestrator
# ---------------------------------------------------------------------------
# soft operational flags not in the core questionnaire -> left None (review downstream)
SOFT_FLAGS = ["has_foreign_investment", "has_nonresident_payments",
              "has_international_transactions", "has_reportable_accounts",
              "has_msme_dues", "has_sbo", "has_capital_changes", "has_ecb", "has_odi",
              "has_eligible_bonus_employees", "does_digital_lending",
              "has_dlg_arrangements", "has_floating_rate_retail", "is_secured_lender",
              "is_large_corporate", "has_borrowings", "is_isd"]

# Targeted one-line follow-ups for gap fields (LLM may rephrase conversationally).
FOLLOWUP_TEXT = {
    "turnover_cr": "What was your turnover last financial year?",
    "employee_count": "How many employees do you have?",
    "operating_states": "Which states do you operate in?",
    "gst_registered": "Is the company registered under GST?",
    "has_foreign_investment": "Do you have any foreign investment (FDI)?",
    "has_nonresident_payments": "Do you make payments to non-residents (foreign vendors/lenders)?",
    "has_international_transactions": "Any transactions with overseas associated enterprises?",
    "has_reportable_accounts": "Do you hold accounts for foreign tax residents (FATCA/CRS)?",
    "has_msme_dues": "Do you have outstanding dues to MSME suppliers?",
    "has_sbo": "Any significant beneficial owners (SBO) to declare?",
    "has_capital_changes": "Have you issued or transferred shares this year?",
    "has_ecb": "Any External Commercial Borrowings (ECB)?",
    "has_odi": "Any overseas direct investments (JV/WOS)?",
    "csr_applicable": "What is your net worth / net profit? (to confirm CSR applicability)",
    "has_floating_rate_retail": "Do you offer floating-rate retail loans?",
    "does_digital_lending": "Do you lend through digital channels / apps?",
}


def field_yield(library: dict) -> dict:
    """How many obligations each profile field gates -> drives gap ranking."""
    from collections import Counter
    raw = Counter()
    for o in library["obligation_templates"]:
        for k in o["applicability_rule"]:
            base = k.replace("_min_cr", "").replace("_min", "")
            raw[base] += 1
    alias = {"asset_size": "asset_size_cr", "turnover": "turnover_cr",
             "has_employees": "employee_count", "has_branches": "branch_count",
             "pt_states": "operating_states", "lwf_states": "operating_states"}
    out = Counter()
    for k, c in raw.items():
        out[alias.get(k, k)] += c
    return dict(out)


def gap_questions(F: dict, library: dict) -> list[dict]:
    """Only ask for fields that (a) are unknown and (b) change applicability.
    Ranked by yield (obligations affected); hard fields prioritized at ties."""
    yields = field_yield(library)
    gaps = []
    for fname, fval in F.items():
        if fval.value is not None:
            continue
        if fname not in FOLLOWUP_TEXT:
            continue   # no targeted question -> silently flows to NEEDS_REVIEW
        gaps.append({"field": fname, "question": FOLLOWUP_TEXT[fname],
                     "yield": yields.get(fname, 0), "hard": fname in HARD_FIELDS})
    gaps.sort(key=lambda x: (x["hard"], x["yield"]), reverse=True)
    return gaps


def extract_profile(raw: dict, library: dict | None = None) -> dict:
    F: dict[str, Field] = {}

    # entity-master identifiers (validated)
    id_issues = []
    for kind in ("cin", "pan"):
        v = raw.get(kind)
        ok, msg = validate_identifier(kind, v) if v else (False, f"{kind} missing")
        if v and not ok:
            id_issues.append(Issue(kind, "warning", msg))

    # always-known: they hold a CoR -> registered
    F["rbi_registered"] = Field(True, Source.EXTRACTED, 0.95, "from RBI CoR on file")

    # asked-directly fields
    F["asset_size_cr"] = parse_amount_cr(raw.get("asset_size"))
    F["turnover_cr"] = parse_amount_cr(raw.get("turnover"))
    F["deposit_taking"] = normalize_bool(raw.get("deposit_taking"))
    F["is_listed"] = normalize_bool(raw.get("is_listed"))
    F["has_listed_debt"] = normalize_bool(raw.get("has_listed_debt"))
    F["operating_states"] = normalize_states(raw.get("operating_states"))
    F["branch_count"] = (Field(int(raw["branch_count"]), Source.ASKED, CONF[Source.ASKED])
                         if raw.get("branch_count") is not None
                         else Field(None, Source.DEFAULT_UNKNOWN, 0.0))
    F["employee_count"] = (Field(int(raw["employee_count"]), Source.ASKED, CONF[Source.ASKED])
                           if raw.get("employee_count") is not None
                           else Field(None, Source.DEFAULT_UNKNOWN, 0.0))
    F["gst_registered"] = normalize_bool(raw.get("gst_registered"))
    business = normalize_business(raw.get("nbfc_type"))   # descriptive, not engine-consumed

    # derived fields (suggested, confirm)
    F["nbfc_category"] = derive_regulatory_category(F["asset_size_cr"].value,
                                                    F["deposit_taking"].value)
    F["rbi_layer"] = derive_rbi_layer(F["asset_size_cr"].value, F["deposit_taking"].value,
                                      str(raw.get("rbi_layer", "")).lower() == "upper")
    F["esi_applicable"] = derive_esi(F["employee_count"].value)
    F["gst_scheme"] = (derive_gst_scheme(F["turnover_cr"].value)
                       if F["gst_registered"].value else
                       Field(None, Source.DEFAULT_UNKNOWN, 0.0, "not GST-registered"))
    F["csr_applicable"] = derive_csr(F["turnover_cr"].value)

    # soft flags: take if explicitly provided, else leave unknown for review
    for flag in SOFT_FLAGS:
        if flag in raw:
            F[flag] = normalize_bool(raw.get(flag))
        else:
            F[flag] = Field(None, Source.DEFAULT_UNKNOWN, 0.0, "ask or confirm")

    # consistency
    asserted = {"rbi_layer": str(raw.get("rbi_layer", "")).lower() or None}
    issues = id_issues + consistency_checks(F, asserted)

    # assemble engine profile (value-only) + provenance + review list
    profile = {k: v.value for k, v in F.items()}
    review_fields = [k for k, v in F.items()
                     if v.source == Source.DEFAULT_UNKNOWN or v.confidence < 0.85]
    derived_to_confirm = [k for k, v in F.items() if v.source == Source.DERIVED]
    known = sum(1 for v in F.values() if v.value is not None)

    return {
        "profile": profile,
        "business_classification": business.value,
        "provenance": {k: {"source": v.source.value, "confidence": round(v.confidence, 2),
                           "note": v.note} for k, v in F.items()},
        "issues": [asdict(i) for i in issues],
        "review_fields": review_fields,
        "derived_to_confirm": derived_to_confirm,
        "gap_questions": gap_questions(F, library) if library else [],
        "completeness": {"known": known, "total": len(F),
                         "pct": round(100 * known / len(F))},
    }
