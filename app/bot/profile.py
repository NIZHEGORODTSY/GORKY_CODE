"""Тексты профиля бота и меню команд."""

from aiogram import Bot
from aiogram.types import BotCommand, MenuButtonCommands, MenuButtonWebApp, WebAppInfo

NAME = "Горький · голосовой планировщик"

SHORT_DESCRIPTION = "Скажи — и я запомню. Задачи, встречи и напоминания голосом, без лишних кнопок."

DESCRIPTION = (
    "Привет! Я Горький — твой голосовой планировщик 🎙\n\n"
    "Говори как с другом — я сам пойму, что записать и когда напомнить:\n\n"
    "⏰ «Напомни завтра в 10 позвонить маме»\n"
    "👥 «В четверг в 15:00 созвон с командой»\n"
    "🔁 «Каждый понедельник планёрка в 10»\n"
    "🔎 «Найди задачу про договор»\n\n"
    "Пришлю напоминание вовремя, предупрежу о пересечениях и покажу планы в календаре телефона.\n\n"
    "Нажми «Старт» — и начнём 👇"
)

COMMANDS = [
    BotCommand(command="menu", description="🏠 Меню"),
    BotCommand(command="today", description="📅 Что у меня сегодня"),
    BotCommand(command="tomorrow", description="➡️ Планы на завтра"),
    BotCommand(command="week", description="🗓 План на неделю"),
    BotCommand(command="tasks", description="📝 Все открытые задачи"),
    BotCommand(command="calendar", description="📆 Добавить планы в календарь телефона"),
    BotCommand(command="settings", description="⚙️ Часовой пояс, сводка, голос"),
    BotCommand(command="demo", description="📥 Демо-данные из тестового задания"),
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
