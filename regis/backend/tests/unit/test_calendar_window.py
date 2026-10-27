"""Unit tests — the default generation window for a calendar created today."""

from datetime import date

from app.modules.onboarding.calendar_chain import fy_windows


def test_mid_year_is_the_current_fy():
    assert fy_windows(date(2026, 10, 27)) == [(date(2026, 4, 1), date(2027, 3, 31))]


def test_january_to_march_belongs_to_the_fy_that_started_last_april():
    assert fy_windows(date(2027, 1, 15))[0] == (date(2026, 4, 1), date(2027, 3, 31))


def test_april_first_starts_a_new_fy():
    assert fy_windows(date(2027, 4, 1)) == [(date(2027, 4, 1), date(2028, 3, 31))]


def test_last_60_days_of_the_fy_also_cover_the_next_one():
    assert fy_windows(date(2027, 2, 15)) == [
        (date(2026, 4, 1), date(2027, 3, 31)),
        (date(2027, 4, 1), date(2028, 3, 31)),
    ]
    assert len(fy_windows(date(2027, 1, 30))) == 1  # 60 days out is not yet "last 60"
