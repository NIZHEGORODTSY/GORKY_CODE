from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.ics import build_calendar
from app.core.models import Event, EventKind

MSK = ZoneInfo("Europe/Moscow")


def test_calendar_contains_events_rrule_and_alarm():
    events = [
        Event(1, EventKind.MEETING, "Планёрка, команда", datetime(2026, 11, 2, 10, tzinfo=MSK),
              datetime(2026, 11, 2, 11, tzinfo=MSK), id=5, recurrence="weekly:0"),
        Event(1, EventKind.TASK, "Отчёт", datetime(2026, 11, 6, tzinfo=MSK), all_day=True, id=6),
    ]
    ics = build_calendar(events)
    assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n")
    assert "DTSTART:20261102T070000Z" in ics            # 10:00 МСК = 07:00 UTC
    assert "RRULE:FREQ=WEEKLY;BYDAY=MO" in ics
    assert r"SUMMARY:Планёрка\, команда" in ics          # экранирование запятой
    assert "TRIGGER:-PT15M" in ics
    assert "DTSTART;VALUE=DATE:20261106" in ics


def test_long_lines_are_folded():
    ics = build_calendar([Event(1, EventKind.TASK, "Очень " * 30, datetime(2026, 11, 6, 9, tzinfo=MSK), id=1)])
    assert all(len(line.encode()) <= 75 for line in ics.split("\r\n"))
