"""Тексты профиля бота и меню команд."""

from aiogram import Bot
from aiogram.types import BotCommand, MenuButtonCommands, MenuButtonWebApp, WebAppInfo

NAME = "Горький · голосовой планировщик"

SHORT_DESCRIPTION = "Задачи, напоминания и встречи — просто скажи или напиши. Голосом или текстом."

DESCRIPTION = (
    "Привет! Я голосовой планировщик.\n\n"
    "🎙 Отправь голосовое или напиши как другу:\n"
    "• «Напомни завтра в 10 позвонить Ивану»\n"
    "• «В четверг в 11 встреча с дизайнером»\n"
    "• «Что у меня на неделе?»\n"
    "• «Найди задачу про договор»\n\n"
    "Сам пришлю напоминание вовремя и предупрежу, если встречи пересекаются."
)

COMMANDS = [
    BotCommand(command="menu", description="🏠 Меню"),
    BotCommand(command="today", description="📅 Что у меня сегодня"),
    BotCommand(command="tomorrow", description="➡️ Планы на завтра"),
    BotCommand(command="week", description="🗓 План на неделю"),
    BotCommand(command="tasks", description="📝 Все открытые задачи"),
    BotCommand(command="calendar", description="📆 Добавить планы в календарь телефона"),
    BotCommand(command="settings", description="⚙️ Часовой пояс, сводка, голос"),
    BotCommand(command="help", description="❓ Что я умею"),
]


async def setup_menu_button(bot: Bot, webapp_url: str) -> None:
    """Меню команд и кнопка слева от поля ввода: календарь, если Mini App доступен по HTTPS."""
    await bot.set_my_commands(COMMANDS)
    if webapp_url:
        button = MenuButtonWebApp(text="Календарь", web_app=WebAppInfo(url=webapp_url))
    else:
        button = MenuButtonCommands()
    await bot.set_chat_menu_button(menu_button=button)
