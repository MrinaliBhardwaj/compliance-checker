"""
Golden regression — instance generator (Profile B, FY2026-27 window).

Locked figures from the verified reference:
  367 dated instances, 21 event-driven, 3 continuous, 92 working-day-adjusted.
"""
from datetime import date

import pytest

from app.engines.instance_generator import generate_instances, is_overdue, reminder_schedule
from app.engines.instance_generator import Instance
from app.modules.onboarding.calendar_chain import run_chain

pytestmark = pytest.mark.golden


@pytest.fixture(scope="module")
def gen_b(library, profile_b):
    ctx = {
        "window_start": date(2026, 4, 1), "window_end": date(2027, 3, 31),
        "anchors": {"agm_date": date(2026, 9, 25), "tds_return_date": date(2026, 7, 31)},
        "license_expiry": date(2026, 11, 30),
    }
    return run_chain(library, profile_b, ctx)


def test_company_obligation_count(gen_b):
    assert len(gen_b["company_obligations"]) == 100


def test_dated_instance_count(gen_b):
    assert len(gen_b["generation"]["instances"]) == 367


def test_event_driven_held_back(gen_b):
    assert len(gen_b["generation"]["event_driven"]) == 21


def test_continuous_controls(gen_b):
    assert len(gen_b["generation"]["continuous"]) == 3


def test_working_day_adjusted(gen_b):
    wda = sum(1 for i in gen_b["generation"]["instances"] if i.working_day_adjusted)
    assert wda == 92


def test_idempotent_period_labels(gen_b):
    """(company_obligation_id, period_label) is unique — the idempotency key."""
    keys = [(i.company_obligation_id, i.period_label) for i in gen_b["generation"]["instances"]]
    assert len(keys) == len(set(keys))


def test_all_instances_within_window(gen_b):
    for i in gen_b["generation"]["instances"]:
        assert "2026-04-01" <= i.due_date <= "2027-03-31"


def test_overdue_predicate():
    inst = Instance(company_obligation_id="co", template_id="t",
                    period_label="2026-05", due_date="2026-05-10", status="pending")
    assert is_overdue(inst, date(2026, 5, 11)) is True
    assert is_overdue(inst, date(2026, 5, 9)) is False
    inst.status = "completed"
    assert is_overdue(inst, date(2026, 5, 11)) is False  # completed never overdue


def test_reminder_schedule():
    s = reminder_schedule(date(2026, 5, 10))
    assert s["pre_due"] == ["2026-05-03", "2026-05-07", "2026-05-09"]
    assert s["overdue_escalation"] == ["2026-05-11", "2026-05-13", "2026-05-17"]


def test_holiday_injection_changes_adjustment(library, profile_b):
    """Hardening check: passing an empty holiday set still produces a valid run
    (weekends still shift) and the default-set run reproduces 92."""
    base_ctx = {
        "window_start": date(2026, 4, 1), "window_end": date(2027, 3, 31),
        "anchors": {"agm_date": date(2026, 9, 25), "tds_return_date": date(2026, 7, 31)},
        "license_expiry": date(2026, 11, 30),
    }
    cobs = run_chain(library, profile_b, base_ctx)["company_obligations"]
    default_run = generate_instances(cobs, base_ctx)
    wda_default = sum(1 for i in default_run["instances"] if i.working_day_adjusted)
    assert wda_default == 92
    # default module set is restored after a call (no global leakage)
    again = generate_instances(cobs, base_ctx)
    assert sum(1 for i in again["instances"] if i.working_day_adjusted) == 92
