"""Тексты профиля бота и меню команд."""

from aiogram import Bot
from aiogram.types import BotCommand, MenuButtonCommands, MenuButtonWebApp, WebAppInfo

NAME = "Горький · голосовой планировщик"

SHORT_DESCRIPTION = "Скажи — и я запомню. Задачи, встречи и напоминания голосом, без лишних кнопок."

DESCRIPTION = (
    "Горький — голосовой планировщик дел.\n\n"
    "Скажи или напиши, как другу: «Напомни завтра в 10 позвонить маме». "
    "Я сам пойму дату, запишу и напомню вовремя.\n\n"
    "— задачи и напоминания\n"
    "— встречи с проверкой пересечений\n"
    "— планы на день и неделю\n"
    "— поиск по старым записям\n"
    "— всё в календаре телефона\n\n"
    "Нажми «Старт» 👇"
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
