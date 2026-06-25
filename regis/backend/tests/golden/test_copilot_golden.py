"""
Golden regression — Copilot (the 10-query reference transcript).

Locked behaviours:
  - admin "due this week" = 18; preparer = 13 (scoped at retrieval, not prose)
  - overdue (admin) = 10; status dnbs02 = 4
  - structured conf 0.97; library/legal answers 0.70 + provisional
  - the three escalations produce no substantive answer
  - grounding verifier rejects invented ids
"""
from datetime import date, timedelta

import pytest

from app.engines.copilot import Intent, answer, route_intent, verify_grounding
from app.modules.onboarding.calendar_chain import run_chain

pytestmark = pytest.mark.golden

TODAY = date(2026, 7, 15)


@pytest.fixture(scope="module")
def org_rows(library, profile_b):
    """Materialize the generated instances into the dict rows the copilot queries,
    using the exact statuses/owners from the verified reference run."""
    gen = run_chain(library, profile_b)["generation"]["instances"]
    rows = []
    for n, ins in enumerate(gen):
        owner = "user_prep1" if ins.owner_role == "preparer" else "user_admin"
        d = date.fromisoformat(ins.due_date)
        status = "completed" if d < TODAY - timedelta(days=10) else "pending"
        rows.append({
            "id": f"i{n:03d}", "template_id": ins.template_id, "due_date": ins.due_date,
            "status": status, "owner_user_id": owner, "owner_role": ins.owner_role,
            "period_label": ins.period_label,
        })
    return rows


def test_due_this_week_admin_vs_preparer(org_rows):
    admin = answer("What's due this week?", role="compliance_admin",
                   user_id="user_admin", instances=org_rows, today=TODAY)
    prep = answer("What's due this week?", role="preparer",
                  user_id="user_prep1", instances=org_rows, today=TODAY)
    assert admin.answer_facts["count"] == 18
    assert prep.answer_facts["count"] == 13
    assert prep.scope_note and "preparer" in prep.scope_note.lower()
    assert admin.confidence == 0.97


def test_overdue_admin(org_rows):
    t = answer("What's overdue?", role="compliance_admin",
               user_id="user_admin", instances=org_rows, today=TODAY)
    assert t.answer_facts["count"] == 10
    assert t.intent == Intent.DUE_WINDOW.value


def test_status_dnbs02(org_rows):
    t = answer("What's the status of dnbs02?", role="compliance_admin",
               user_id="user_admin", instances=org_rows, today=TODAY)
    assert t.answer_facts["count"] == 4


def test_action_request_escalates(org_rows):
    t = answer("File my GST return for me", role="compliance_admin",
               user_id="user_admin", instances=org_rows, today=TODAY)
    assert t.escalated and t.escalation_reason == "read_only"
    assert "message" in t.answer_facts and "count" not in t.answer_facts


def test_legal_opinion_escalates(org_rows):
    t = answer("Are we definitely compliant with RBI?", role="compliance_admin",
               user_id="user_admin", instances=org_rows, today=TODAY)
    assert t.escalated and t.escalation_reason == "consult_professional"


def test_out_of_scope_declines(org_rows):
    t = answer("Help me with our litigation case", role="compliance_admin",
               user_id="user_admin", instances=org_rows, today=TODAY)
    assert t.escalated and t.escalation_reason == "out_of_scope"


def test_obligation_info_provisional(org_rows):
    t = answer("What does dnbs02 require?", role="compliance_admin",
               user_id="user_admin", instances=org_rows, today=TODAY)
    assert t.confidence == 0.70
    assert t.provisional is True


def test_legal_qa_provisional(org_rows):
    t = answer("What does the RBI master direction say under SBR?", role="head",
               user_id="user_head", instances=org_rows, today=TODAY)
    assert t.intent == Intent.LEGAL_QA.value
    assert t.confidence == 0.70
    assert t.provisional is True


def test_grounding_rejects_invented_id():
    g = verify_grounding(["instance:i999"], retrieved_ids={"instance:i001"})
    assert g["grounded"] is False
    assert g["unknown_citations"] == ["instance:i999"]


def test_router_classifies_escalations():
    assert route_intent("File my GST return for me") == Intent.ACTION_REQUEST
    assert route_intent("Are we definitely compliant?") == Intent.LEGAL_OPINION
    assert route_intent("help with litigation") == Intent.OUT_OF_SCOPE
