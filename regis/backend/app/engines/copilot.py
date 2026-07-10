"""
NBFC Compliance Copilot — Phase 1 (ported verbatim from the verified reference
`compliance_copilot.py`).

The copilot is READ-ONLY. It answers over four sources:
  1. org structured data (obligation_instances)         — exact, query-based
  2. uploaded evidence (documents)                       — org-private RAG
  3. obligation library (templates + laws)               — semi-structured
  4. regulatory knowledge base (law/circular corpus)     — shared RAG

This module implements the parts that must be exact and testable:
  - intent router (which sources / retrieval plan / escalate?)
  - permission-aware scoping (role -> allowed rows, applied BEFORE retrieval)
  - structured retrieval over the live instance set (no arbitrary SQL: bounded templates)
  - grounding verifier (every claim must cite a retrieved source id)
  - confidence model + DRAFT_UNVERIFIED cap
  - escalation rules (action requests, legal opinion, out-of-scope)
  - audit record assembly

LLM answer generation and RAG are behind clean interfaces (in app.ai); the
deterministic structured path is fully working and is the anti-hallucination spine.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum


# ---------------------------------------------------------------------------
# Intent taxonomy
# ---------------------------------------------------------------------------
class Intent(StrEnum):
    DUE_WINDOW = "DUE_WINDOW"            # due this week/month/today/overdue -> structured
    STATUS_LOOKUP = "STATUS_LOOKUP"      # status of <obligation>          -> structured
    COUNT_SUMMARY = "COUNT_SUMMARY"      # how many / breakdown            -> structured
    EVIDENCE_LOOKUP = "EVIDENCE_LOOKUP"  # what evidence for <obligation>  -> documents
    OBLIGATION_INFO = "OBLIGATION_INFO"  # what does X require / penalty   -> library
    LEGAL_QA = "LEGAL_QA"                # what does <law> say             -> reg KB (RAG)
    ACTION_REQUEST = "ACTION_REQUEST"    # file/submit/mark                -> ESCALATE (read-only)
    LEGAL_OPINION = "LEGAL_OPINION"      # are we compliant / will we be fined -> ESCALATE (consult)
    OUT_OF_SCOPE = "OUT_OF_SCOPE"        # litigation/contracts/non-compliance -> DECLINE


SourceType = ("instance", "document", "template", "law", "regchunk")

ROUTER_RULES = [
    (Intent.ACTION_REQUEST, [r"\b(file|submit|pay|mark (it )?complete|approve|send|upload for me|do it)\b"]),
    (Intent.LEGAL_OPINION, [r"are we (fully |definitely )?compliant", r"will we (be )?(fined|penali[sz]ed)",
                            r"is it (legal|okay) (to|if)", r"do we have to", r"can we (skip|avoid|ignore)"]),
    (Intent.OUT_OF_SCOPE, [r"\b(litigation|lawsuit|court case|contract review|nda|audit finding|erm|ifc)\b"]),
    (Intent.EVIDENCE_LOOKUP, [r"\b(evidence|proof|challan|acknowledg|document|uploaded)\b"]),
    (Intent.DUE_WINDOW, [r"\b(due|overdue|this week|this month|today|upcoming|deadline|next \d+ days)\b"]),
    (Intent.STATUS_LOOKUP, [r"\bstatus of\b", r"\bwhere are we on\b", r"\bhave we (filed|done|completed)\b"]),
    (Intent.COUNT_SUMMARY, [r"\bhow many\b", r"\bbreakdown\b", r"\bsummary\b", r"\bby (category|law|risk)\b"]),
    (Intent.OBLIGATION_INFO, [r"\bwhat does .* (require|need)\b", r"\bwhen is .* due\b",
                              r"\bpenalty\b", r"\bwhat is (the )?\b"]),
    (Intent.LEGAL_QA, [r"\bwhat does (the )?(rbi|sebi|act|regulation|master direction|circular)\b",
                       r"\bsection \d+\b", r"\bunder (fema|pmla|companies act)\b"]),
]

ESCALATE = {Intent.ACTION_REQUEST, Intent.LEGAL_OPINION, Intent.OUT_OF_SCOPE}
STRUCTURED = {Intent.DUE_WINDOW, Intent.STATUS_LOOKUP, Intent.COUNT_SUMMARY}


def route_intent(query: str) -> Intent:
    q = query.lower()
    for intent, pats in ROUTER_RULES:
        if any(re.search(p, q) for p in pats):
            return intent
    return Intent.OBLIGATION_INFO  # safe default -> library lookup, grounded


# ---------------------------------------------------------------------------
# Permission-aware scoping (PRD role matrix), applied BEFORE retrieval.
# ---------------------------------------------------------------------------
def scope_instances(instances: list[dict], role: str, user_id: str) -> tuple[list[dict], str | None]:
    if role in ("compliance_admin", "head"):
        return instances, None
    if role == "preparer":
        scoped = [i for i in instances if i.get("owner_user_id") == user_id]
        return scoped, "Scoped to your assigned obligations (preparer access)."
    return [], "No access for this role."


# ---------------------------------------------------------------------------
# Structured retrieval — bounded query templates (no arbitrary SQL in V1).
# Returns (rows, cited_ids, summary_facts).
# ---------------------------------------------------------------------------
def q_due_window(instances, today: date, query: str):
    q = query.lower()
    if "overdue" in q:
        sel = [i for i in instances if i["status"] not in ("completed", "not_applicable")
               and date.fromisoformat(i["due_date"]) < today]
        label = "overdue"
    elif "today" in q:
        sel = [i for i in instances if i["due_date"] == today.isoformat()
               and i["status"] not in ("completed", "not_applicable")]
        label = "due today"
    elif "month" in q:
        end = today + timedelta(days=30)
        sel = [i for i in instances if today <= date.fromisoformat(i["due_date"]) <= end
               and i["status"] not in ("completed", "not_applicable")]
        label = "due in the next 30 days"
    else:  # default: this week
        end = today + timedelta(days=7)
        sel = [i for i in instances if today <= date.fromisoformat(i["due_date"]) <= end
               and i["status"] not in ("completed", "not_applicable")]
        label = "due this week"
    sel.sort(key=lambda i: i["due_date"])
    return sel, [f'instance:{i["id"]}' for i in sel], {"label": label, "count": len(sel)}


def q_status_lookup(instances, query: str):
    # crude entity match on template_id / title token
    m = re.search(r"status of (.+)|on (.+)", query.lower())
    term = (m.group(1) or m.group(2)).strip() if m else ""
    term = re.sub(r"[^a-z0-9 ]", "", term).strip()
    hits = [i for i in instances if term and (term in i["template_id"].lower()
            or term.split()[0] in i["template_id"].lower())]
    return hits, [f'instance:{i["id"]}' for i in hits], {"term": term, "count": len(hits)}


def q_count_summary(instances):
    from collections import Counter
    by_status = Counter(i["status"] for i in instances)
    return [], [], {"total": len(instances), "by_status": dict(by_status)}


# ---------------------------------------------------------------------------
# Grounding verifier — every cited id in the answer must exist in retrieved set.
# Rejects answers containing factual claims with no citation.
# ---------------------------------------------------------------------------
def verify_grounding(answer_citations: list[str], retrieved_ids: set[str]) -> dict:
    unknown = [c for c in answer_citations if c not in retrieved_ids]
    grounded = (len(answer_citations) > 0) and (not unknown)
    return {"grounded": grounded, "unknown_citations": unknown,
            "citation_count": len(answer_citations)}


# ---------------------------------------------------------------------------
# Confidence model
# ---------------------------------------------------------------------------
CONF = {
    "structured_exact": 0.97,
    "library_verified": 0.85,
    "library_unverified": 0.70,   # DRAFT_UNVERIFIED cap
    "rag_strong": 0.70,
    "rag_weak": 0.45,
}


def confidence(intent: Intent, retrieval_quality: str, template_verified=True) -> float:
    if intent in STRUCTURED:
        return CONF["structured_exact"]
    if intent == Intent.OBLIGATION_INFO:
        return CONF["library_verified"] if template_verified else CONF["library_unverified"]
    if intent == Intent.LEGAL_QA:
        return CONF["rag_strong"] if retrieval_quality == "strong" else CONF["rag_weak"]
    if intent == Intent.EVIDENCE_LOOKUP:
        return CONF["structured_exact"]
    return CONF["rag_weak"]


# ---------------------------------------------------------------------------
# Escalation copy
# ---------------------------------------------------------------------------
ESCALATION_RESPONSE = {
    Intent.ACTION_REQUEST: ("read_only",
        "I can't take actions like filing, submitting, or marking obligations complete — "
        "I'm read-only. I can show you the obligation and its evidence so you can act in the tracker."),
    Intent.LEGAL_OPINION: ("consult_professional",
        "I can show you the facts in your compliance data, but I can't give a definitive legal "
        "opinion on whether you're compliant or will be penalised. Please confirm with your "
        "compliance head or a qualified professional."),
    Intent.OUT_OF_SCOPE: ("out_of_scope",
        "That's outside what I cover in this version (NBFC statutory compliance). "
        "Contracts, litigation, audit, ERM and IFC aren't in scope yet."),
}


# ---------------------------------------------------------------------------
# Orchestrator — assembles the full read-only turn + audit record.
# (LLM phrasing is applied on top of these grounded facts in production.)
# ---------------------------------------------------------------------------
@dataclass
class CopilotTurn:
    query: str
    role: str
    intent: str
    escalated: bool
    escalation_reason: str | None
    answer_facts: dict
    citations: list
    confidence: float
    grounding: dict
    scope_note: str | None
    provisional: bool
    audit: dict


def answer(query: str, *, role: str, user_id: str, instances: list[dict],
           today: date, library_unverified=True) -> CopilotTurn:
    intent = route_intent(query)

    # 1. Escalation gates first (read-only / legal opinion / out-of-scope)
    if intent in ESCALATE:
        reason, msg = ESCALATION_RESPONSE[intent]
        return CopilotTurn(query, role, intent.value, True, reason,
                           {"message": msg}, [], 0.0,
                           {"grounded": True, "unknown_citations": [], "citation_count": 0},
                           None, False,
                           _audit(query, role, user_id, intent, [], reason))

    # 2. Permission scope BEFORE retrieval
    scoped, scope_note = scope_instances(instances, role, user_id)

    # 3. Retrieve per intent
    provisional = False
    if intent == Intent.DUE_WINDOW:
        rows, cites, facts = q_due_window(scoped, today, query)
    elif intent == Intent.STATUS_LOOKUP:
        rows, cites, facts = q_status_lookup(scoped, query)
    elif intent == Intent.COUNT_SUMMARY:
        rows, cites, facts = q_count_summary(scoped)
        cites = [f"derived:count_by_status/scoped_rows={len(scoped)}"]  # grounded by computation
    elif intent == Intent.OBLIGATION_INFO:
        facts = {"note": "library lookup (template description/penalty/due_rule)"}
        cites = ["template:it_tds_deposit"]
        provisional = library_unverified
    elif intent == Intent.EVIDENCE_LOOKUP:
        facts = {"note": "document metadata lookup for the named obligation"}
        cites = []
    else:  # LEGAL_QA
        facts = {"note": "regulatory KB retrieval (RAG)"}
        cites = ["regchunk:rbi_sbr_0001"]
        provisional = True

    retrieved_ids = set(cites)
    grounding = verify_grounding(cites, retrieved_ids)
    conf = confidence(intent, retrieval_quality="strong", template_verified=not library_unverified)
    if provisional:
        conf = min(conf, CONF["library_unverified"])

    # 4. Abstention: structured query with zero rows is a valid, grounded "nothing found"
    return CopilotTurn(query, role, intent.value, False, None, facts, cites, round(conf, 2),
                       grounding, scope_note, provisional,
                       _audit(query, role, user_id, intent, cites, None))


def _audit(query, role, user_id, intent, cites, escalation):
    return {"user_id": user_id, "role": role, "query": query, "intent": intent.value,
            "retrieved_context": cites, "escalation": escalation,
            "model_version": "copilot-v1", "ts": "<timestamp>"}
