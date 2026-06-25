"""Unit tests — pure reminder schedule (the deterministic notification core)."""
from datetime import date

from app.modules.notify.service import reminder_intents


def _inst(due, status="pending", risk="medium", owner="u1"):
    return {"id": "i1", "due_date": due, "status": status, "risk_level": risk,
            "owner_user_id": owner}


def test_pre_due_default_cadence():
    due = date(2026, 5, 10)
    for lead in (7, 3, 1):
        today = date(2026, 5, 10 - lead)
        kinds = [(x["kind"], x["lead"]) for x in reminder_intents([_inst(due.isoformat())], today)]
        assert ("pre_due", lead) in kinds


def test_high_risk_denser_cadence():
    due = date(2026, 5, 20)
    today = date(2026, 5, 5)  # 15 days before
    intents = reminder_intents([_inst(due.isoformat(), risk="high")], today)
    assert any(x["kind"] == "pre_due" and x["lead"] == 15 for x in intents)
    # medium risk has no 15-day lead
    assert not reminder_intents([_inst(due.isoformat(), risk="medium")], today)


def test_due_day():
    due = date(2026, 5, 10)
    intents = reminder_intents([_inst(due.isoformat())], due)
    assert any(x["kind"] == "due_day" for x in intents)


def test_overdue_escalation_ladder():
    due = date(2026, 5, 10)
    targets = {}
    for d, role in ((1, "owner"), (3, "compliance_admin"), (7, "head")):
        today = date(2026, 5, 10 + d)
        intents = reminder_intents([_inst(due.isoformat())], today)
        esc = [x for x in intents if x["kind"] == "overdue"]
        assert esc and esc[0]["target_role"] == role
        targets[role] = True
    assert targets == {"owner": True, "compliance_admin": True, "head": True}


def test_completed_and_na_get_no_reminders():
    due = date(2026, 5, 10)
    assert reminder_intents([_inst(due.isoformat(), status="completed")], date(2026, 5, 9)) == []
    assert reminder_intents([_inst(due.isoformat(), status="not_applicable")], date(2026, 5, 9)) == []


def test_no_due_date_skipped():
    assert reminder_intents([_inst(None)], date(2026, 5, 9)) == []
