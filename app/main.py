import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.assistant.service import Assistant
from app.bot.handlers import router
from app.bot.notifier import run_notifier
from app.config import get_settings
from app.llm.gigachat_client import GigaChatClient
from app.speech.salute import SaluteSpeechClient
from app.storage.db import make_engine, make_session_factory


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    llm = GigaChatClient(
        credentials=settings.gigachat_credentials,
        scope=settings.gigachat_scope,
        model=settings.gigachat_model,
        ca_bundle=settings.sber_ca_bundle,
        embeddings_model=settings.gigachat_embeddings_model,
    )
    assistant = Assistant(session_factory, llm, settings.default_timezone)

    speech = None
    if settings.salute_speech_credentials:
        speech = SaluteSpeechClient(
            settings.salute_speech_credentials, settings.salute_speech_scope, settings.sber_ca_bundle
        )

    bot = Bot(settings.bot_token)
    dp = Dispatcher(assistant=assistant, speech=speech)
    dp.include_router(router)
    notifier = asyncio.create_task(run_notifier(bot, session_factory))
    try:
        await dp.start_polling(bot)
    finally:
        notifier.cancel()
        await bot.session.close()
        await llm.close()
        if speech:
            await speech.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
