"""Человекочитаемые ответы. Без markdown: текст может быть озвучен."""

from datetime import date
from itertools import groupby
from zoneinfo import ZoneInfo

from app.core.dates import WEEKDAYS
from app.core.models import Event, EventKind, EventStatus

MONTHS_GEN = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]
KIND_LABEL = {EventKind.TASK: "задача", EventKind.REMINDER: "напоминание", EventKind.MEETING: "встреча"}


def fmt_day(d: date, today: date) -> str:
    base = f"{d.day} {MONTHS_GEN[d.month - 1]}"
    if d.year != today.year:
        base += f" {d.year}"
    delta = (d - today).days
    if delta == 0:
        return f"сегодня, {base}"
    if delta == 1:
        return f"завтра, {base}"
    if delta == 2:
        return f"послезавтра, {base}"
    return f"{WEEKDAYS[d.weekday()]}, {base}"


def fmt_when(e: Event, tz: ZoneInfo, today: date) -> str:
    if e.starts_at is None:
        return "без срока"
    local = e.starts_at.astimezone(tz)
    day = fmt_day(local.date(), today)
    return day if e.all_day else f"{day} в {local:%H:%M}"


def fmt_created(e: Event, tz: ZoneInfo, today: date) -> str:
    label = KIND_LABEL[e.kind].capitalize()
    when = fmt_when(e, tz, today)
    if e.kind == EventKind.REMINDER:
        return f"Готово, напомню {when}: {e.title}."
    if e.starts_at is None:
        return f"{label} добавлена: {e.title}."
    return f"Готово. {label} «{e.title}» — {when}."


def _line(e: Event, tz: ZoneInfo) -> str:
    time_part = "весь день" if e.all_day or e.starts_at is None else f"{e.starts_at.astimezone(tz):%H:%M}"
    done = " (выполнено)" if e.status == EventStatus.DONE else ""
    return f"• {time_part} — {e.title} ({KIND_LABEL[e.kind]}){done}"


def fmt_list(events: list[Event], tz: ZoneInfo, today: date, empty: str) -> str:
    if not events:
        return empty
    parts = []
    by_day = groupby(events, key=lambda e: e.starts_at.astimezone(tz).date())
    for day, items in by_day:
        parts.append(fmt_day(day, today).capitalize() + ":")
        parts.extend(_line(e, tz) for e in items)
    return "\n".join(parts)


def fmt_found(events: list[Event], tz: ZoneInfo, today: date) -> str:
    lines = ["Нашёл:"] if len(events) > 1 else []
    for e in events:
        label = KIND_LABEL[e.kind]
        done = ", выполнено" if e.status == EventStatus.DONE else ""
        when = fmt_when(e, tz, today)
        if len(events) == 1:
            return f"Нашёл {label}: «{e.title}» — {when}{done}."
        lines.append(f"• {e.title} ({label}) — {when}{done}")
    return "\n".join(lines)
