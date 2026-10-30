"""Ответы пользователю в Telegram-HTML. Пользовательский текст всегда экранируем.

Оформление: заголовок ответа, пустая строка, тело. Время — моноширинным (<code>), чтобы столбцы
ровнялись; записи дня — в цитате (<blockquote>), название — жирным, детали — отдельной строкой.
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
ALL_DAY = "весь день"

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
    """«завтра, 31 октября в 10:00» — для фраз вроде «Перенёс … на …»."""
    if e.starts_at is None:
        return "без срока"
    local = e.starts_at.astimezone(tz)
    day = fmt_day(local.date(), today)
    return day if e.all_day else f"{day} в {local:%H:%M}"


def _when_line(e: Event, tz: ZoneInfo, today: date) -> str:
    """«Завтра, 31 октября · 15:00–16:00» — строка с датой под названием записи."""
    if e.starts_at is None:
        return "без срока"
    local = e.starts_at.astimezone(tz)
    day = fmt_day(local.date(), today).capitalize()
    if e.all_day:
        return f"{day} · {ALL_DAY}"
    span = f"{local:%H:%M}"
    if e.ends_at:
        span += f"–{e.ends_at.astimezone(tz):%H:%M}"
    return f"{day} · {span}"


def _card(e: Event, tz: ZoneInfo, today: date) -> str:
    """Карточка записи: значок и название, ниже — когда и повтор."""
    lines = [f"{KIND_ICON[e.kind]} <b>{escape(e.title)}</b>", f"🗓 {_when_line(e, tz, today)}"]
    if e.recurrence:
        lines.append(f"🔁 {describe(e.recurrence)}")
    if e.status == EventStatus.DONE:
        lines.append("✔️ выполнено")
    return "\n".join(lines)


def fmt_created(e: Event, tz: ZoneInfo, today: date) -> str:
    heading = {
        EventKind.REMINDER: "⏰ <b>Напомню</b>",
        EventKind.MEETING: "✅ <b>Встреча добавлена</b>",
        EventKind.TASK: "✅ <b>Задача добавлена</b>",
    }[e.kind]
    return f"{heading}\n\n{_card(e, tz, today)}"


def _line(e: Event, tz: ZoneInfo) -> str:
    """Строка списка: «<code>10:00</code>  👥 Созвон с командой»."""
    time_part = ALL_DAY if e.all_day or e.starts_at is None else f"{e.starts_at.astimezone(tz):%H:%M}"
    title = escape(e.title)
    if e.status == EventStatus.DONE:
        title = f"<s>{title}</s>"
    repeat = " 🔁" if e.recurrence else ""
    return f"<code>{time_part}</code>  {KIND_ICON[e.kind]} {title}{repeat}"


def fmt_list(events: list[Event], tz: ZoneInfo, today: date, empty: str) -> str:
    if not events:
        return f"🌿 {empty}"
    blocks = []
    for day, items in groupby(events, key=lambda e: e.starts_at.astimezone(tz).date()):
        rows = "\n".join(_line(e, tz) for e in items)
        blocks.append(f"📅 <b>{fmt_day(day, today).capitalize()}</b>\n<blockquote>{rows}</blockquote>")
    return "\n\n".join(blocks)


def fmt_found(events: list[Event], tz: ZoneInfo, today: date) -> str:
    n = len(events)
    heading = "🔎 <b>Нашёл</b>" if n == 1 else f"🔎 <b>Нашёл {n} {_plural(n, 'запись', 'записи', 'записей')}</b>"
    return heading + "\n\n" + "\n\n".join(_card(e, tz, today) for e in events)


def _plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many
