from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.assistant.service import Assistant

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
async def on_voice(message: Message) -> None:
    # TODO(speech): STT через SaluteSpeech -> assistant.handle -> текст + TTS-ответ
    await message.answer("Голосовые пока не поддерживаются — напиши текстом.")
