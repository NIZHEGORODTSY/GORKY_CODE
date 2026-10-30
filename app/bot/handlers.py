import logging

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.types import BufferedInputFile, Message

from app.assistant.service import Assistant
from app.speech.base import SpeechToText, TextToSpeech

log = logging.getLogger(__name__)
router = Router()

GREETING = (
    "Привет! Я помогу с задачами, напоминаниями и встречами.\n"
    "Пиши или отправляй голосовые, например:\n"
    "• «Напомни завтра в 10 позвонить Ивану»\n"
    "• «В четверг в 11 встреча с дизайнером»\n"
    "• «Что у меня сегодня?»\n"
    "• «Найди задачу про договор»"
)


@router.message(CommandStart())
async def on_start(message: Message) -> None:
    await message.answer(GREETING)


@router.message(F.text)
async def on_text(message: Message, assistant: Assistant) -> None:
    reply = await assistant.handle(message.from_user.id, message.text)
    await message.answer(reply)


@router.message(F.voice)
async def on_voice(
    message: Message, bot: Bot, assistant: Assistant, stt: SpeechToText, tts: TextToSpeech
) -> None:
    audio = await bot.download(message.voice)
    try:
        text = await stt.recognize(audio.read(), "voice.ogg", message.voice.mime_type or "audio/ogg")
    except Exception:
        log.exception("STT failed")
        await message.answer("Не получилось распознать голосовое — попробуй ещё раз или напиши текстом.")
        return
    if not text:
        await message.answer("Не расслышал. Повтори, пожалуйста.")
        return

    reply = await assistant.handle(message.from_user.id, text)
    await message.answer(f"🎙 «{text}»\n\n{reply}")
    try:
        voice = await tts.synthesize(reply)
        await message.answer_voice(BufferedInputFile(voice, filename="reply.mp3"))
    except Exception:
        # Текстовый ответ уже отправлен — без голоса пользователь ничего не теряет
        log.exception("TTS failed")
