from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.recurrence import build_rule, describe, first_on_or_after, next_after, occurrences, to_rrule

MSK = ZoneInfo("Europe/Moscow")
FRI = datetime(2026, 10, 30, 10, tzinfo=MSK)  # пятница


def test_build_rule():
    assert build_rule("weekly", ["monday", "wednesday"], FRI.date()) == "weekly:0,2"
    assert build_rule("weekly", None, FRI.date()) == "weekly:4"
    assert build_rule("never", None, FRI.date()) is None


def test_weekdays_skip_weekend():
    assert next_after(FRI, "weekdays", FRI) == datetime(2026, 11, 2, 10, tzinfo=MSK)
    assert first_on_or_after(datetime(2026, 10, 31, 9, tzinfo=MSK), "weekdays").date() == date(2026, 11, 2)


def test_occurrences_in_week():
    start, end = datetime(2026, 11, 2, tzinfo=MSK), datetime(2026, 11, 9, tzinfo=MSK)
    days = [d.day for d in occurrences(FRI, "weekly:0,2", start, end)]
    assert days == [2, 4]


def test_monthly_clamps_to_last_day():
    jan31 = datetime(2027, 1, 31, 9, tzinfo=MSK)
    assert next_after(jan31, "monthly", jan31) == datetime(2027, 2, 28, 9, tzinfo=MSK)


def test_describe_and_rrule():
    assert describe("weekly:0,2") == "каждый пн и ср"
    assert describe("weekdays") == "по будням"
    assert to_rrule("weekly:0,2") == "FREQ=WEEKLY;BYDAY=MO,WE"
