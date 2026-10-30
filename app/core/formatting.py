"""Ответы пользователю в Telegram-HTML. Пользовательский текст всегда экранируем.

Для истории диалога и озвучки HTML снимается функцией plain().
"""

import re
from datetime import date
from html import escape
from itertools import groupby
from zoneinfo import ZoneInfo

from app.core.dates import WEEKDAYS
from app.core.models import Event, EventKind, EventStatus
from app.core.recurrence import describe

MONTHS_GEN = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]
KIND_LABEL = {EventKind.TASK: "задача", EventKind.REMINDER: "напоминание", EventKind.MEETING: "встреча"}
KIND_ICON = {EventKind.TASK: "📝", EventKind.REMINDER: "⏰", EventKind.MEETING: "👥"}

_TAG_RE = re.compile(r"<[^>]+>")


def plain(html_text: str) -> str:
    """HTML -> обычный текст (для истории LLM и озвучки)."""
    return (
        _TAG_RE.sub("", html_text)
        .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#x27;", "'").replace("&amp;", "&")
    )


def q(title: str) -> str:
    """Название записи в кавычках, экранированное."""
    return f"«{escape(title)}»"


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
    text = _created(e, tz, today)
    if e.recurrence:
        text += f"\n🔁 {describe(e.recurrence)}"
    return text


def _created(e: Event, tz: ZoneInfo, today: date) -> str:
    icon = KIND_ICON[e.kind]
    title = escape(e.title)
    when = fmt_when(e, tz, today)
    if e.kind == EventKind.REMINDER:
        return f"{icon} <b>Напомню {when}</b>\n{title}"
    if e.kind == EventKind.MEETING:
        return f"{icon} <b>Встреча добавлена</b>\n{title}\n🕒 {when}"
    if e.starts_at is None:
        return f"{icon} <b>Задача добавлена</b>\n{title}"
    return f"{icon} <b>Задача добавлена</b>\n{title}\n📅 {when}"


def _line(e: Event, tz: ZoneInfo) -> str:
    time_part = "весь день" if e.all_day or e.starts_at is None else f"{e.starts_at.astimezone(tz):%H:%M}"
    title = escape(e.title)
    if e.status == EventStatus.DONE:
        title = f"<s>{title}</s>"
    repeat = " 🔁" if e.recurrence else ""
    return f"{KIND_ICON[e.kind]} {time_part} — {title}{repeat}"


def fmt_list(events: list[Event], tz: ZoneInfo, today: date, empty: str) -> str:
    if not events:
        return f"🌿 {empty}"
    parts = []
    by_day = groupby(events, key=lambda e: e.starts_at.astimezone(tz).date())
    for day, items in by_day:
        if parts:
            parts.append("")
        parts.append(f"<b>{fmt_day(day, today).capitalize()}</b>")
        parts.extend(_line(e, tz) for e in items)
    return "\n".join(parts)


def fmt_found(events: list[Event], tz: ZoneInfo, today: date) -> str:
    def row(e: Event) -> str:
        done = " ✔️" if e.status == EventStatus.DONE else ""
        repeat = f" · 🔁 {describe(e.recurrence)}" if e.recurrence else ""
        return f"{KIND_ICON[e.kind]} {escape(e.title)} — {fmt_when(e, tz, today)}{repeat}{done}"

    if len(events) == 1:
        return f"🔎 <b>Нашёл {KIND_LABEL[events[0].kind]}</b>\n{row(events[0])}"
    return "🔎 <b>Нашёл:</b>\n" + "\n".join(row(e) for e in events)
