"""
NBFC Document Intelligence — Phase 1 (ported verbatim from the verified
reference `document_intelligence.py`).

Implements the parts that must be exact and testable:
  - canonical document-type taxonomy + mapping of required_evidence -> type
  - extraction schema (fields per type)
  - validation engine (extracted entities vs the target obligation instance)
  - duplicate detection (exact hash + key-tuple)
  - evidence-completeness checker (library required_evidence vs linked docs)
  - confidence model + routing thresholds

Classification + entity extraction themselves are OCR/LLM calls; they are
behind a clean interface (classify_and_extract) which delegates to app.ai.
The AI layer SUGGESTS; the human confirms (Maker-Checker is unchanged).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum


# ---------------------------------------------------------------------------
# 1. Canonical document-type taxonomy
# ---------------------------------------------------------------------------
class DocType(str, Enum):
    FILING_ACK = "FILING_ACK"                 # proof a return/form was filed
    PAYMENT_CHALLAN = "PAYMENT_CHALLAN"       # tax/contribution payment proof
    STATUTORY_CERTIFICATE = "STATUTORY_CERTIFICATE"
    BOARD_SECRETARIAL = "BOARD_SECRETARIAL"   # minutes/notices/resolutions/forms
    POLICY_DOC = "POLICY_DOC"
    REGISTER_MIS_LOG = "REGISTER_MIS_LOG"
    COMPUTATION_RECON = "COMPUTATION_RECON"
    AUDITED_REPORT = "AUDITED_REPORT"
    LICENSE_REGISTRATION = "LICENSE_REGISTRATION"
    RETURN_STATEMENT_FILE = "RETURN_STATEMENT_FILE"
    INTERNAL_NOTE = "INTERNAL_NOTE"
    OTHER = "OTHER"


# ordered (specific -> general) keyword rules mapping evidence text -> DocType
TYPE_RULES = [
    (DocType.PAYMENT_CHALLAN, ["challan", "trrn", "payment proof", "payment confirmation", "itns"]),
    (DocType.LICENSE_REGISTRATION, ["s&e certificate", "cersai registration", "ckyc upload",
                                    "appointment", "ic constitution", "gro/io", "cco appointment",
                                    "rbi approval letter", "public notice", "registration id"]),
    (DocType.STATUTORY_CERTIFICATE, ["sac", "firc", "form 16", "form 3cd", "form 3ceb", "form 15cb",
                                     "15cb", "mr-3", "asset cover certificate", "valuation certificate",
                                     "rating letter", "auditor certificate", "auditor consent",
                                     "limited review report", "actuarial valuation", "certificate"]),
    (DocType.AUDITED_REPORT, ["audited financials", "audit report", "rbia report", "is audit",
                              "bcp/dr", "audit working papers", "board fraud review", "auditor's report",
                              "board & auditor reports", "audited accounts", "committee report"]),
    (DocType.COMPUTATION_RECON, ["computation", "working", "reconciliation", "2b vs books",
                                 "50-50 test", "tp study", "projection", "bucketing", "cap computation",
                                 "itc reconciliation", "trial balance", "ageing", "gstr-9c"]),
    (DocType.BOARD_SECRETARIAL, ["minutes", "notice", "resolution", "mbp-1", "dir-8", "dir-2",
                                 "dir-11", "attendance", "board report", "ben-1", "list of allottees",
                                 "shareholding details", "board approvals", "board/agm"]),
    (DocType.POLICY_DOC, ["policy", "code of conduct", "fpc", "kfs template", "kfs templates"]),
    (DocType.REGISTER_MIS_LOG, ["register", "mis", " log", "logs", "ledger", "schedule",
                                "communication log", "trading window", "sdd", "re-kyc records",
                                "kyc records"]),
    (DocType.RETURN_STATEMENT_FILE, ["statement", "fvu file", "crilc-sma file", "transaction extract",
                                     "contribution statement", "filed results", "return working file",
                                     "custody statement", "self-invoices", "sample loan disclosures",
                                     "concentration report", "exposure computation", "data audit"]),
    (DocType.INTERNAL_NOTE, ["internal suspicion note", "declaration", "disclosure", "due-diligence",
                             "down-load log", "traces download log", "reject-and-rectify"]),
    (DocType.FILING_ACK, ["acknowledgment", "acknowledgement", " ack", "srn", "itr-v", "receipt",
                          "arn", "rrn", "token", "exchange certificate", "intimation copy",
                          "record date intimation", "lc disclosure filing", "annual report filing proof",
                          "spend proof", "transfer documents", "charge instrument",
                          "no-dues / satisfaction letter", "incident report", "filing", "form d ack"]),
]


def map_evidence_to_type(evidence: str) -> DocType:
    e = evidence.lower()
    for dtype, kws in TYPE_RULES:
        if any(k in e for k in kws):
            return dtype
    return DocType.OTHER


# ---------------------------------------------------------------------------
# 2. Extraction schema — fields expected per canonical type.
# Common fields apply to all; type-specific fields layered on top.
# ---------------------------------------------------------------------------
COMMON_FIELDS = ["document_date", "period", "reference_number", "authority", "entity_identifier"]
TYPE_FIELDS = {
    DocType.PAYMENT_CHALLAN: ["challan_number", "bsr_code", "payment_date", "amount",
                              "assessment_year", "tan_or_pan"],
    DocType.FILING_ACK: ["srn_or_ack_no", "form_number", "filing_date", "cin_or_gstin"],
    DocType.RETURN_STATEMENT_FILE: ["return_type", "return_period", "gstin_or_tan", "token_number"],
    DocType.STATUTORY_CERTIFICATE: ["issuer", "issue_date", "valid_until", "subject"],
    DocType.LICENSE_REGISTRATION: ["license_number", "issuing_authority", "valid_from", "valid_until"],
    DocType.BOARD_SECRETARIAL: ["meeting_date", "resolution_type", "form_number"],
    DocType.AUDITED_REPORT: ["report_period", "auditor_name", "sign_date"],
    DocType.COMPUTATION_RECON: ["period", "computed_value"],
    DocType.POLICY_DOC: ["approval_date", "next_review_date", "version"],
    DocType.REGISTER_MIS_LOG: ["period", "record_count"],
    DocType.INTERNAL_NOTE: ["note_date", "author_role"],
    DocType.OTHER: [],
}


# ---------------------------------------------------------------------------
# 3. Confidence model + routing
# ---------------------------------------------------------------------------
HIGH, MED = 0.85, 0.60   # >=HIGH auto-suggest (pre-checked); >=MED suggest; else manual


def route(confidence: float) -> str:
    if confidence >= HIGH:
        return "AUTO_SUGGEST"      # pre-checked link, user confirms
    if confidence >= MED:
        return "SUGGEST_REVIEW"    # surfaced, user must confirm type+link
    return "MANUAL"                # user classifies/links manually


# ---------------------------------------------------------------------------
# 4. Validation engine — extracted entities vs the target instance.
# Returns checks with pass/warn/fail; never auto-completes.
# ---------------------------------------------------------------------------
@dataclass
class Check:
    name: str
    result: str          # pass | warn | fail
    detail: str


def validate(extracted: dict, instance: dict, template: dict, org: dict) -> list[Check]:
    checks: list[Check] = []

    # 4.1 period match
    ext_period = (extracted.get("period") or extracted.get("return_period")
                  or extracted.get("assessment_year") or "")
    inst_period = instance.get("period_label", "")
    if ext_period:
        ok = _periods_align(ext_period, inst_period)
        checks.append(Check("period_match", "pass" if ok else "warn",
                            f"doc period '{ext_period}' vs instance '{inst_period}'"))
    else:
        checks.append(Check("period_match", "warn", "no period extracted"))

    # 4.2 filing/payment date within window (period_start .. due_date + grace)
    ddate = _parse_date(extracted.get("filing_date") or extracted.get("payment_date")
                        or extracted.get("document_date"))
    due = _parse_date(instance.get("due_date"))
    if ddate and due:
        within = ddate <= due + timedelta(days=3)
        checks.append(Check("date_in_window", "pass" if within else "fail",
                            f"doc date {ddate} vs due {due}"))
    else:
        checks.append(Check("date_in_window", "warn", "missing date(s)"))

    # 4.3 form match against template.form_reference
    form_ref = (template.get("form_reference") or "").strip().lower()
    ext_form = (extracted.get("form_number") or extracted.get("return_type") or "").strip().lower()
    if form_ref and ext_form:
        ok = form_ref in ext_form or ext_form in form_ref
        checks.append(Check("form_match", "pass" if ok else "warn",
                            f"template '{form_ref}' vs doc '{ext_form}'"))

    # 4.4 entity identifier match (GSTIN/TAN/PAN/CIN vs org master)
    ext_id = (extracted.get("cin_or_gstin") or extracted.get("gstin_or_tan")
              or extracted.get("tan_or_pan") or extracted.get("entity_identifier") or "")
    known = {v for v in [org.get("cin"), org.get("pan"), org.get("gstin"), org.get("tan")] if v}
    if ext_id:
        ok = any(ext_id.replace(" ", "").upper() == k.replace(" ", "").upper() for k in known)
        checks.append(Check("entity_match", "pass" if ok else "fail",
                            f"doc id '{ext_id}' {'matches' if ok else 'NOT in'} org master"))

    # 4.5 amount sanity
    amt = extracted.get("amount")
    if amt is not None:
        checks.append(Check("amount_sanity", "pass" if amt > 0 else "fail", f"amount={amt}"))

    # 4.6 licence expiry capture -> renewal trigger
    valid_until = _parse_date(extracted.get("valid_until"))
    if valid_until:
        checks.append(Check("expiry_capture", "pass",
                            f"valid_until {valid_until} -> schedule renewal"))
    return checks


def _periods_align(a: str, b: str) -> bool:
    norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
    na, nb = norm(a), norm(b)
    if na in nb or nb in na:
        return True
    # quarter/month token overlap
    toks_a = set(re.findall(r"q[1-4]|20\d\d|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec", a.lower()))
    toks_b = set(re.findall(r"q[1-4]|20\d\d|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec", b.lower()))
    return bool(toks_a & toks_b)


def _parse_date(s):
    if isinstance(s, date):
        return s
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            from datetime import datetime
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# 5. Duplicate detection
# ---------------------------------------------------------------------------
def file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def dedupe(new_doc: dict, existing: list[dict]) -> dict:
    # 5.1 exact byte duplicate
    for e in existing:
        if e.get("sha256") and e["sha256"] == new_doc.get("sha256"):
            return {"verdict": "EXACT_DUPLICATE", "of": e["id"], "action": "block"}
    # 5.2 key-tuple near-duplicate: same entity + form + period + reference
    key = lambda d: (d.get("entity_id"), (d.get("ai_extracted") or {}).get("form_number"),
                     (d.get("ai_extracted") or {}).get("period"),
                     (d.get("ai_extracted") or {}).get("reference_number"))
    nk = key(new_doc)
    if all(nk):  # only when the tuple is fully populated
        for e in existing:
            if key(e) == nk:
                return {"verdict": "NEAR_DUPLICATE", "of": e["id"], "action": "warn"}
    return {"verdict": "UNIQUE", "action": "accept"}


# ---------------------------------------------------------------------------
# 6. Evidence-completeness checker
# Maps a template's required_evidence -> canonical types, then checks coverage
# against the doc types linked to the instance.
# ---------------------------------------------------------------------------
def completeness(template: dict, linked_doc_types: list[str]) -> dict:
    required = template.get("required_evidence", [])
    required_types = []
    for ev in required:
        required_types.append((ev, map_evidence_to_type(ev).value))
    have = set(linked_doc_types)
    covered = [(ev, t) for (ev, t) in required_types if t in have]
    missing = [(ev, t) for (ev, t) in required_types if t not in have]
    # primary evidence = the first required item (usually the filing ack / challan)
    primary = required_types[0] if required_types else None
    primary_present = primary and primary[1] in have
    total = len(required_types) or 1
    return {
        "required": required_types,
        "covered": covered,
        "missing": missing,
        "pct": round(100 * len(covered) / total),
        "primary_present": bool(primary_present),
        # gate: a Checker may approve only if primary evidence present (configurable)
        "eligible_for_completion": bool(primary_present),
    }


# ---------------------------------------------------------------------------
# Interface to the AI layer (OCR + LLM).
# Delegates to app.ai.documents in production; raises if no provider wired.
# In production: OCR (if scanned) -> LLM structured extraction -> this schema.
# ---------------------------------------------------------------------------
def classify_and_extract(file_bytes: bytes, mime: str, hint: dict | None = None) -> dict:
    from app.ai.documents import classify_and_extract as _impl
    return _impl(file_bytes, mime, hint)
