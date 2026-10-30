"""Профиль бота через Bot API: имя, описания, команды, аватар (BotFather не нужен).

Запуск:  python -m scripts.setup_bot_profile [путь к .env]   (по умолчанию .env)
Выполнять один раз на каждого бота: у set_my_name и аватара жёсткие лимиты Telegram.
"""

import asyncio
import sys
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile, InputProfilePhotoStatic
from dotenv import dotenv_values

from app.bot.profile import COMMANDS, DESCRIPTION, NAME, SHORT_DESCRIPTION

AVATAR = Path(__file__).resolve().parent.parent / "assets" / "avatar.jpg"


async def main(env_path: str) -> None:
    token = dotenv_values(env_path)["BOT_TOKEN"]
    async with Bot(token) as bot:
        me = await bot.get_me()
        print("bot:", me.username)
        await bot.set_my_name(NAME)
        await bot.set_my_short_description(SHORT_DESCRIPTION)
        await bot.set_my_description(DESCRIPTION)
        await bot.set_my_commands(COMMANDS)
        await bot.set_my_profile_photo(InputProfilePhotoStatic(photo=FSInputFile(AVATAR)))
        print("profile updated")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else ".env"))
