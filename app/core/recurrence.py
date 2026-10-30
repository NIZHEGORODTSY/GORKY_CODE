"""Повторяющиеся записи. Правило — строка:

    daily        каждый день
    weekdays     по будням
    weekly:0,2   по дням недели (0 = понедельник)
    monthly      каждый месяц в тот же день (если дня нет — в последний день месяца)

В базе хранится одна запись: starts_at — ближайшее повторение. Когда повторение выполнено или
напоминание по нему отправлено, starts_at сдвигается на следующее. Для списков и календаря
повторения за период вычисляются на лету.
"""

import calendar
from datetime import date, datetime, timedelta

from app.core.dates import WEEKDAY_TOKENS

WEEKDAY_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
ICS_DAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
MAX_SCAN_DAYS = 400


def build_rule(repeat: str, days: list[str] | None, first_day: date) -> str | None:
    """Аргументы LLM -> правило. None — повтора нет или он не распознан."""
    if repeat == "daily":
        return "daily"
    if repeat == "weekdays":
        return "weekdays"
    if repeat == "monthly":
        return "monthly"
    if repeat == "weekly":
        indices = sorted({WEEKDAY_TOKENS.index(d) for d in days or [] if d in WEEKDAY_TOKENS})
        if not indices:
            indices = [first_day.weekday()]
        return "weekly:" + ",".join(map(str, indices))
    return None


def _matches(rule: str, d: date, anchor: date) -> bool:
    if rule == "daily":
        return True
    if rule == "weekdays":
        return d.weekday() < 5
    if rule.startswith("weekly:"):
        return d.weekday() in {int(x) for x in rule[7:].split(",")}
    if rule == "monthly":
        last = calendar.monthrange(d.year, d.month)[1]
        return d.day == min(anchor.day, last)
    raise ValueError(f"unknown rule {rule!r}")


def first_on_or_after(start: datetime, rule: str) -> datetime:
    """Первое повторение не раньше start (то же время суток)."""
    d = start.date()
    for _ in range(MAX_SCAN_DAYS):
        if _matches(rule, d, start.date()):
            return start.replace(year=d.year, month=d.month, day=d.day)
        d += timedelta(days=1)
    raise ValueError("no occurrence")


def next_after(current: datetime, rule: str, after: datetime) -> datetime:
    """Следующее повторение строго позже after. current — текущее повторение (в поясе пользователя)."""
    anchor = current.date()
    d = max(current.date(), after.astimezone(current.tzinfo).date())
    for _ in range(MAX_SCAN_DAYS):
        candidate = current.replace(year=d.year, month=d.month, day=d.day)
        if candidate > after and _matches(rule, d, anchor):
            return candidate
        d += timedelta(days=1)
    raise ValueError("no next occurrence")


def occurrences(current: datetime, rule: str, start: datetime, end: datetime) -> list[datetime]:
    """Повторения в полуинтервале [start, end), начиная с current."""
    result = []
    anchor = current.date()
    d = max(current.date(), start.astimezone(current.tzinfo).date())
    while True:
        candidate = current.replace(year=d.year, month=d.month, day=d.day)
        if candidate >= end:
            return result
        if candidate >= start and candidate >= current and _matches(rule, d, anchor):
            result.append(candidate)
        d += timedelta(days=1)


def describe(rule: str) -> str:
    if rule == "daily":
        return "каждый день"
    if rule == "weekdays":
        return "по будням"
    if rule == "monthly":
        return "каждый месяц"
    days = [WEEKDAY_SHORT[int(x)] for x in rule[7:].split(",")]
    return "каждый " + " и ".join(days) if len(days) <= 2 else "по " + ", ".join(days)


def to_rrule(rule: str) -> str:
    if rule == "daily":
        return "FREQ=DAILY"
    if rule == "weekdays":
        return "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"
    if rule == "monthly":
        return "FREQ=MONTHLY"
    return "FREQ=WEEKLY;BYDAY=" + ",".join(ICS_DAYS[int(x)] for x in rule[7:].split(","))
