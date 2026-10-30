import re
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]


class Period(StrEnum):
    TODAY = "today"
    TOMORROW = "tomorrow"
    DAY_AFTER_TOMORROW = "day_after_tomorrow"
    THIS_WEEK = "this_week"
    NEXT_WEEK = "next_week"
    CUSTOM = "custom"


def calendar_lines(today: date, days: int = 14) -> str:
    """Таблица ближайших дней для промпта: модели не нужно самой считать дни недели."""
    marks = {0: " (сегодня)", 1: " (завтра)", 2: " (послезавтра)"}
    lines = []
    for i in range(days):
        d = today + timedelta(days=i)
        lines.append(f"{d.isoformat()} — {WEEKDAYS[d.weekday()]}{marks.get(i, '')}")
    return "\n".join(lines)


WEEKDAY_TOKENS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DAY_TOKENS = ["today", "tomorrow", "day_after_tomorrow", *WEEKDAY_TOKENS, "end_of_week", "next_week"]


def resolve_day(token: str, today: date) -> date:
    """Словесный день -> дата. Считаем в коде: LLM ошибается в арифметике дней недели.

    День недели — ближайший следующий (в пятницу «в пятницу» = через неделю).
    """
    if token == "today":
        return today
    if token == "tomorrow":
        return today + timedelta(days=1)
    if token == "day_after_tomorrow":
        return today + timedelta(days=2)
    if token == "end_of_week":
        return today + timedelta(days=6 - today.weekday())
    if token == "next_week":
        return today + timedelta(days=7 - today.weekday())
    if token in WEEKDAY_TOKENS:
        ahead = (WEEKDAY_TOKENS.index(token) - today.weekday()) % 7 or 7
        return today + timedelta(days=ahead)
    raise ValueError(f"unknown day token: {token!r}")


def day_start(d: date, tz: ZoneInfo) -> datetime:
    return datetime.combine(d, time.min, tzinfo=tz)


def period_bounds(
    period: Period,
    now: datetime,
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[datetime, datetime]:
    """Полуинтервал [start, end) в часовом поясе `now`."""
    tz = now.tzinfo
    today = now.date()
    if period == Period.TODAY:
        start = today
        end = today + timedelta(days=1)
    elif period == Period.TOMORROW:
        start = today + timedelta(days=1)
        end = start + timedelta(days=1)
    elif period == Period.DAY_AFTER_TOMORROW:
        start = today + timedelta(days=2)
        end = start + timedelta(days=1)
    elif period == Period.THIS_WEEK:
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=7)
    elif period == Period.NEXT_WEEK:
        start = today - timedelta(days=today.weekday()) + timedelta(days=7)
        end = start + timedelta(days=7)
    else:
        if date_from is None:
            raise ValueError("custom period requires date_from")
        start = date_from
        end = (date_to or date_from) + timedelta(days=1)
    return day_start(start, tz), day_start(end, tz)


def parse_date(value: str) -> date:
    return date.fromisoformat(value.strip()[:10])


_TIME_RE = re.compile(r"^\s*(\d{1,2})(?:[:.](\d{2}))?\s*$")


def parse_time(value: str) -> time:
    m = _TIME_RE.match(value)
    if not m:
        raise ValueError(f"bad time: {value!r}")
    hour, minute = int(m.group(1)), int(m.group(2) or 0)
    return time(hour % 24, minute)
