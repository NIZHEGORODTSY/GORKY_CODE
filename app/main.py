import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.assistant.service import Assistant
from app.bot.handlers import router
from app.config import get_settings
from app.llm.gigachat_client import GigaChatClient
from app.storage.db import make_engine, make_session_factory


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    engine = make_engine(settings.database_url)
    llm = GigaChatClient(
        credentials=settings.gigachat_credentials,
        scope=settings.gigachat_scope,
        model=settings.gigachat_model,
        ca_bundle=settings.sber_ca_bundle,
        embeddings_model=settings.gigachat_embeddings_model,
    )
    assistant = Assistant(make_session_factory(engine), llm, settings.default_timezone)

    bot = Bot(settings.bot_token)
    dp = Dispatcher(assistant=assistant)
    dp.include_router(router)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await llm.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
