import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode

from app.assistant.service import Assistant
from app.bot.handlers import router
from app.bot.notifier import run_notifier
from app.bot.profile import setup_menu_button
from app.config import get_settings
from app.llm.gigachat_client import GigaChatClient
from app.speech.edge import EdgeTTS
from app.speech.gigachat_stt import GigaChatSTT
from app.webapp.server import create_app, start_webapp
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

    stt = GigaChatSTT(
        settings.gigachat_credentials, settings.gigachat_scope, settings.gigachat_model, settings.sber_ca_bundle
    )
    tts = EdgeTTS(settings.tts_voice)

    session = AiohttpSession(proxy=settings.telegram_proxy) if settings.telegram_proxy else None
    bot = Bot(settings.bot_token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(
        assistant=assistant,
        stt=stt,
        tts=tts,
        webapp_url=settings.public_webapp_url,
        public_base=settings.public_webapp_url.removesuffix("/app/"),
    )
    dp.include_router(router)
    await setup_menu_button(bot, settings.public_webapp_url)
    notifier = asyncio.create_task(run_notifier(bot, session_factory))
    webapp = await start_webapp(
        create_app(settings.bot_token, assistant, session_factory, settings.default_timezone),
        settings.webapp_host,
        settings.webapp_port,
    )
    try:
        await dp.start_polling(bot)
    finally:
        notifier.cancel()
        await webapp.cleanup()
        await bot.session.close()
        await llm.close()
        await stt.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
