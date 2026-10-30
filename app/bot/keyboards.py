"""Клавиатуры бота. callback_data: ev:<действие>:<id>[:<минуты>]."""

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from app.core.models import Event, EventKind, EventStatus

BTN_TODAY = "📅 Сегодня"
BTN_WEEK = "🗓 Неделя"
BTN_HELP = "❓ Помощь"
BTN_CALENDAR = "🗂 Календарь"


def main_menu(webapp_url: str = "") -> ReplyKeyboardMarkup:
    second_row = [KeyboardButton(text=BTN_HELP)]
    if webapp_url:
        second_row.insert(0, KeyboardButton(text=BTN_CALENDAR, web_app=WebAppInfo(url=webapp_url)))
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_TODAY), KeyboardButton(text=BTN_WEEK)], second_row],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Скажи или напиши, что запланировать…",
    )


def event_actions(events: list[Event]) -> InlineKeyboardMarkup | None:
    """Кнопки под ответом, если речь об одной открытой записи."""
    if len(events) != 1 or events[0].status != EventStatus.OPEN or events[0].id is None:
        return None
    e = events[0]
    done_label = "✅ Выполнено" if e.kind != EventKind.MEETING else "✅ Прошла"
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=done_label, callback_data=f"ev:done:{e.id}"),
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"ev:del:{e.id}"),
    ]])


def reminder_actions(event_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⏰ +10 мин", callback_data=f"ev:snooze:{event_id}:10"),
        InlineKeyboardButton(text="⏰ +1 час", callback_data=f"ev:snooze:{event_id}:60"),
        InlineKeyboardButton(text="✅ Готово", callback_data=f"ev:done:{event_id}"),
    ]])
