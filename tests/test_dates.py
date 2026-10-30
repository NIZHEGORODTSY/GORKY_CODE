from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from app.core.dates import Period, calendar_lines, parse_time, period_bounds, resolve_day

MSK = ZoneInfo("Europe/Moscow")
NOW = datetime(2026, 10, 30, 14, 0, tzinfo=MSK)  # пятница


def test_today_bounds():
    start, end = period_bounds(Period.TODAY, NOW)
    assert (start, end) == (datetime(2026, 10, 30, tzinfo=MSK), datetime(2026, 10, 31, tzinfo=MSK))


def test_this_week_is_monday_to_monday():
    start, end = period_bounds(Period.THIS_WEEK, NOW)
    assert start.date() == date(2026, 10, 26) and end.date() == date(2026, 11, 2)


def test_next_week():
    start, end = period_bounds(Period.NEXT_WEEK, NOW)
    assert start.date() == date(2026, 11, 2) and end.date() == date(2026, 11, 9)


def test_custom_range_is_inclusive():
    start, end = period_bounds(Period.CUSTOM, NOW, date(2026, 11, 5), date(2026, 11, 6))
    assert start.date() == date(2026, 11, 5) and end.date() == date(2026, 11, 7)


@pytest.mark.parametrize("raw,expected", [("15:00", time(15)), ("9", time(9)), ("9.30", time(9, 30))])
def test_parse_time(raw, expected):
    assert parse_time(raw) == expected


def test_calendar_marks_today_and_weekdays():
    lines = calendar_lines(NOW.date(), days=3).splitlines()
    assert lines[0] == "2026-10-30 — пятница (сегодня)"
    assert lines[1] == "2026-10-31 — суббота (завтра)"


@pytest.mark.parametrize("token,expected", [
    ("today", date(2026, 10, 30)),
    ("tomorrow", date(2026, 10, 31)),
    ("thursday", date(2026, 11, 5)),
    ("friday", date(2026, 11, 6)),  # сегодня пятница -> следующая
    ("end_of_week", date(2026, 11, 1)),
    ("next_week", date(2026, 11, 2)),
])
def test_resolve_day(token, expected):
    assert resolve_day(token, NOW.date()) == expected
