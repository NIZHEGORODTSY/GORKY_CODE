"""Клавиатуры бота.

callback_data (≤ 64 байт):
    ev:<done|del|ics>:<id>          действие с записью
    ev:snooze:<id>:<минуты>         отложить напоминание
    ev:undo:<id>[:<epoch>]          вернуть удалённое / выполненное
    ls:<id>:<d|w>:<YYYY-MM-DD>      выполнить пункт списка и перерисовать список
    nav:<d|w>:<YYYY-MM-DD>          листать день / неделю
    set:<voice|digest|tz|tzmenu>[:<значение>]
"""

from datetime import date, timedelta
from urllib.parse import quote

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from app.core.formatting import KIND_ICON, MONTHS_GEN
from app.core.models import Event, EventKind, EventStatus, UserSettings

BTN_TODAY = "📅 Сегодня"
BTN_TOMORROW = "➡️ Завтра"
BTN_WEEK = "🗓 Неделя"
BTN_TASKS = "📝 Задачи"
BTN_EXPORT = "📆 В календарь"
BTN_SETTINGS = "⚙️ Настройки"
BTN_HELP = "❓ Помощь"
BTN_CALENDAR = "🗂 Календарь"

MAX_LIST_BUTTONS = 8
DIGEST_OPTIONS = ["07:00", "08:00", "09:00", "10:00"]
# Часовые пояса России — самые частые варианты; остальные можно назвать голосом
TIMEZONES = [
    ("Калининград", "Europe/Kaliningrad"), ("Москва", "Europe/Moscow"), ("Самара", "Europe/Samara"),
    ("Екатеринбург", "Asia/Yekaterinburg"), ("Омск", "Asia/Omsk"), ("Новосибирск", "Asia/Novosibirsk"),
    ("Красноярск", "Asia/Krasnoyarsk"), ("Иркутск", "Asia/Irkutsk"), ("Якутск", "Asia/Yakutsk"),
    ("Владивосток", "Asia/Vladivostok"), ("Магадан", "Asia/Magadan"), ("Камчатка", "Asia/Kamchatka"),
]
TZ_LABEL = {tz: city for city, tz in TIMEZONES}


def btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def main_menu(webapp_url: str = "") -> ReplyKeyboardMarkup:
    last_row = [KeyboardButton(text=BTN_HELP)]
    if webapp_url:
        last_row.insert(0, KeyboardButton(text=BTN_CALENDAR, web_app=WebAppInfo(url=webapp_url)))
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_TODAY), KeyboardButton(text=BTN_TOMORROW), KeyboardButton(text=BTN_WEEK)],
            [KeyboardButton(text=BTN_TASKS), KeyboardButton(text=BTN_EXPORT), KeyboardButton(text=BTN_SETTINGS)],
            last_row,
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Скажи или напиши, что запланировать…",
    )


def event_actions(events: list[Event], undo: str | None = None) -> InlineKeyboardMarkup | None:
    """Под ответом об одной записи: выполнить / удалить / в календарь. После действия — «Вернуть»."""
    if undo:
        return InlineKeyboardMarkup(inline_keyboard=[[btn("↩️ Вернуть", f"ev:undo:{undo}")]])
    if len(events) != 1 or events[0].status != EventStatus.OPEN or events[0].id is None:
        return None
    e = events[0]
    done_label = "✅ Прошла" if e.kind == EventKind.MEETING else "✅ Выполнено"
    rows = [[btn(done_label, f"ev:done:{e.id}"), btn("🗑 Удалить", f"ev:del:{e.id}")]]
    if e.starts_at is not None:
        rows.append([btn("📥 В календарь телефона", f"ev:ics:{e.id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reminder_actions(event_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        btn("⏰ +10 мин", f"ev:snooze:{event_id}:10"),
        btn("⏰ +1 час", f"ev:snooze:{event_id}:60"),
        btn("✅ Готово", f"ev:done:{event_id}"),
    ]])


def list_actions(events: list[Event], view: str, anchor: date) -> InlineKeyboardMarkup:
    """Под списком: «выполнено» на каждый открытый пункт + листание (view: d — день, w — неделя, t — задачи)."""
    rows, seen = [], set()
    for e in events:
        if e.status != EventStatus.OPEN or e.id in seen or len(seen) >= MAX_LIST_BUTTONS:
            continue
        seen.add(e.id)
        title = e.title if len(e.title) <= 28 else e.title[:27] + "…"
        rows.append([btn(f"✓ {KIND_ICON[e.kind]} {title}", f"ls:{e.id}:{view}:{anchor.isoformat()}")])
    if view == "t":
        return InlineKeyboardMarkup(inline_keyboard=rows)
    step = timedelta(days=1 if view == "d" else 7)
    if view == "d":
        prev_label, next_label = f"◀️ {_short(anchor - step)}", f"{_short(anchor + step)} ▶️"
    else:
        prev_label, next_label = "◀️ Пред. неделя", "След. неделя ▶️"
    rows.append([btn(prev_label, f"nav:{view}:{(anchor - step).isoformat()}"),
                 btn(next_label, f"nav:{view}:{(anchor + step).isoformat()}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def export_actions(feed_url: str) -> InlineKeyboardMarkup | None:
    if not feed_url:
        return None
    webcal = "webcal://" + feed_url.removeprefix("https://")
    google = "https://calendar.google.com/calendar/render?cid=" + quote(webcal, safe="")
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Google Календарь", url=google)]])


def settings_actions(s: UserSettings) -> InlineKeyboardMarkup:
    voice = "🔊 Голосовые ответы: вкл" if s.voice_replies else "🔇 Голосовые ответы: выкл"
    rows = [[btn(voice, f"set:voice:{0 if s.voice_replies else 1}")]]
    current = f"{s.digest_time:%H:%M}" if s.digest_time else None
    rows.append([btn(("• " if opt == current else "") + opt, f"set:digest:{opt}") for opt in DIGEST_OPTIONS])
    rows.append([btn("🔕 Без утренней сводки" if current else "• Без утренней сводки", "set:digest:off")])
    rows.append([btn(f"🌍 Часовой пояс: {TZ_LABEL.get(s.timezone, s.timezone)}", "set:tzmenu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def timezone_actions() -> InlineKeyboardMarkup:
    rows = [[btn(city, f"set:tz:{tz}") for city, tz in TIMEZONES[i:i + 3]] for i in range(0, len(TIMEZONES), 3)]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _short(d: date) -> str:
    return f"{d.day} {MONTHS_GEN[d.month - 1][:3]}"
