"""
PRD 14.2 — mid-period onboarding.

An NBFC signing up in August has already filed its April-to-July returns; it
just did not file them here. Generating those instances keeps the financial-year
record complete, but presenting them as OVERDUE tells a new customer the product
believes they are 135 filings behind. That is the first screen a design partner
sees, and it reads as the product being confidently wrong about them.

Found by running the app, not by a unit test: the dashboard opened on "135
overdue, Health 61%" for an account created seconds earlier.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.modules.onboarding.calendar_chain import default_window, fy_end, fy_start
from app.modules.onboarding.service import generate_calendar
from app.modules.reports.service import build_compliance_report

AUGUST = date(2026, 8, 25)

PROFILE = {
    "rbi_registered": True, "nbfc_category": "nd_si", "rbi_layer": "middle",
    "deposit_taking": False, "is_listed": False, "has_listed_debt": True,
    "asset_size_cr": 3000, "turnover_cr": 450, "employee_count": 260,
    "branch_count": 22, "operating_states": ["MH"], "gst_registered": True,
}


def _generate(db, seeded_org, on: date):
    return generate_calendar(
        db, organization_id=seeded_org["org_id"], entity_id=seeded_org["entity_id"],
        profile=PROFILE, onboarded_on=on)


# ---------------------------------------------------------------------------
# The window itself
# ---------------------------------------------------------------------------

def test_window_follows_the_financial_year_of_the_signup_date():
    """It was hardcoded to FY2026-27 regardless of when anyone signed up."""
    assert default_window(date(2026, 8, 25)) == {
        "window_start": date(2026, 4, 1), "window_end": date(2027, 3, 31)}
    # A March signup belongs to the FY that is ending, not the one starting.
    assert default_window(date(2026, 3, 15)) == {
        "window_start": date(2025, 4, 1), "window_end": date(2026, 3, 31)}


def test_fy_boundaries_are_april_to_march():
    assert fy_start(date(2026, 4, 1)) == date(2026, 4, 1)
    assert fy_start(date(2026, 3, 31)) == date(2025, 4, 1)
    assert fy_end(date(2026, 8, 25)) == date(2027, 3, 31)


def test_months_parameter_is_honoured():
    """It used to compute a date and discard it, so `months` did nothing."""
    w = default_window(date(2026, 8, 25), months=6)
    assert w["window_start"] == date(2026, 8, 25)
    assert w["window_end"] == date(2027, 1, 31)


# ---------------------------------------------------------------------------
# The behaviour that matters
# ---------------------------------------------------------------------------

def test_a_mid_year_signup_is_not_told_it_is_overdue(db, seeded_org):
    res = _generate(db, seeded_org, AUGUST)
    db.flush()

    assert res.historical > 0, "an August signup must have April-July backfill"

    report = build_compliance_report(
        db, organization_id=seeded_org["org_id"], today=AUGUST)

    assert report["tiles"]["overdue"] == 0, (
        "nothing due before onboarding may be presented as overdue — "
        f"got {report['tiles']['overdue']}"
    )
    assert report["tiles"]["historical"] == res.historical


def test_the_backfill_is_visible_not_hidden(db, seeded_org):
    """Silently dropping the period would leave a hole in the FY record."""
    res = _generate(db, seeded_org, AUGUST)
    db.flush()
    report = build_compliance_report(
        db, organization_id=seeded_org["org_id"], today=AUGUST)

    assert report["tiles"]["historical"] > 0
    assert report["totals"]["by_status"]["historical"] == res.historical


def test_health_is_not_diluted_by_work_that_predates_the_customer(db, seeded_org):
    _generate(db, seeded_org, AUGUST)
    db.flush()
    report = build_compliance_report(
        db, organization_id=seeded_org["org_id"], today=AUGUST)

    # Nothing is overdue and nothing was missed, so a fresh account is healthy.
    assert report["health_score"] == 100


def test_obligations_after_onboarding_stay_trackable(db, seeded_org):
    """The fix must not sweep future work into the backfill."""
    _generate(db, seeded_org, AUGUST)
    db.flush()
    report = build_compliance_report(
        db, organization_id=seeded_org["org_id"], today=AUGUST)

    future = [i for i in report.get("due_this_week", [])]
    tracked = report["totals"]["instances"] - report["totals"]["by_status"]["historical"]
    assert tracked > 0, "everything cannot be historical"
    assert all(i["status"] != "historical" for i in future)


def test_an_explicit_window_marks_nothing_historical(db, seeded_org):
    """
    Naming a window means "this is my tracking period". Deliberate backfills and
    fixtures must not be silently reclassified.
    """
    res = generate_calendar(
        db, organization_id=seeded_org["org_id"], entity_id=seeded_org["entity_id"],
        profile=PROFILE,
        ctx={"window_start": date(2026, 4, 1), "window_end": date(2027, 3, 31),
             "anchors": {"agm_date": date(2026, 9, 25),
                         "tds_return_date": date(2026, 7, 31)},
             "license_expiry": date(2026, 11, 30)})
    assert res.historical == 0


def test_a_signup_on_the_first_day_of_the_year_has_no_backfill(db, seeded_org):
    res = _generate(db, seeded_org, date(2026, 4, 1))
    db.flush()
    assert res.historical == 0, "nothing precedes the first day of the FY"


def test_historical_instances_are_terminal_but_an_admin_can_reopen(db, seeded_org):
    """If a filing genuinely was missed, the org must be able to track it."""
    from app.modules.obligations.lifecycle import LifecycleError, plan_transition

    for action in ("start", "submit", "approve"):
        try:
            plan_transition(action, "historical", "compliance_admin")
            raise AssertionError(f"'{action}' should be refused on historical")
        except LifecycleError:
            pass

    assert plan_transition("reopen", "historical", "compliance_admin") == "in_progress"


def test_reminders_never_fire_for_backfill(db, seeded_org):
    """The escalation ladder must not chase a customer about a prior period."""
    from app.modules.notify.service import run_reminders

    _generate(db, seeded_org, AUGUST)
    db.flush()
    out = run_reminders(db, seeded_org["org_id"], AUGUST + timedelta(days=1))
    assert isinstance(out["notifications"], int)

    report = build_compliance_report(
        db, organization_id=seeded_org["org_id"], today=AUGUST)
    assert report["tiles"]["overdue"] == 0
