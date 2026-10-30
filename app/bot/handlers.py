import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from aiogram.utils.chat_action import ChatActionSender

from app.assistant.service import Assistant
from app.bot.keyboards import BTN_HELP, BTN_TODAY, BTN_WEEK, event_actions, main_menu
from app.llm.base import ToolCall
from app.speech.base import SpeechToText, TextToSpeech

log = logging.getLogger(__name__)
router = Router()

HELP = (
    "👋 <b>Я голосовой планировщик.</b>\n"
    "Пиши или отправляй голосовые — как другу, без команд.\n\n"
    "<b>Создать</b>\n"
    "⏰ «Напомни завтра в 10 позвонить Ивану»\n"
    "👥 «В четверг в 11 встреча с дизайнером»\n"
    "📝 «До конца недели купить билеты»\n\n"
    "<b>Посмотреть и найти</b>\n"
    "📅 «Что у меня сегодня?» · «Планы на неделю»\n"
    "🔎 «Найди задачу про договор»\n\n"
    "<b>Изменить</b>\n"
    "↪️ «Перенеси её на пятницу» · ✅ «Я купил билеты» · 🗑 «Встреча отменилась»\n\n"
    "Напоминания пришлю сам, о встречах предупрежу за 15 минут."
)


@router.message(CommandStart())
@router.message(Command("help"))
@router.message(F.text == BTN_HELP)
async def on_help(message: Message, webapp_url: str) -> None:
    await message.answer(HELP, reply_markup=main_menu(webapp_url))


@router.message(Command("today"))
@router.message(F.text == BTN_TODAY)
async def on_today(message: Message, assistant: Assistant) -> None:
    result = await assistant.run_action(message.from_user.id, ToolCall("list_events", {"period": "today"}))
    await message.answer(result.text)


@router.message(Command("week"))
@router.message(F.text == BTN_WEEK)
async def on_week(message: Message, assistant: Assistant) -> None:
    result = await assistant.run_action(message.from_user.id, ToolCall("list_events", {"period": "this_week"}))
    await message.answer(result.text)


@router.message(F.text)
async def on_text(message: Message, bot: Bot, assistant: Assistant) -> None:
    async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
        result = await assistant.handle(message.from_user.id, message.text)
    await message.answer(result.text, reply_markup=event_actions(result.events))


@router.message(F.voice)
async def on_voice(
    message: Message, bot: Bot, assistant: Assistant, stt: SpeechToText, tts: TextToSpeech
) -> None:
    async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
        audio = await bot.download(message.voice)
        try:
            text = await stt.recognize(audio.read(), "voice.ogg", message.voice.mime_type or "audio/ogg")
        except Exception:
            log.exception("STT failed")
            await message.answer("😕 Не получилось распознать голосовое — попробуй ещё раз или напиши текстом.")
            return
        if not text:
            await message.answer("🙉 Не расслышал. Повтори, пожалуйста.")
            return
        result = await assistant.handle(message.from_user.id, text)

    await message.answer(f"🎙 <i>{escape(text)}</i>\n\n{result.text}", reply_markup=event_actions(result.events))
    try:
        async with ChatActionSender.record_voice(bot=bot, chat_id=message.chat.id):
            voice = await tts.synthesize(result.text)
        await message.answer_voice(BufferedInputFile(voice, filename="reply.mp3"))
    except Exception:
        # Текстовый ответ уже отправлен — без голоса пользователь ничего не теряет
        log.exception("TTS failed")


@router.callback_query(F.data.startswith("ev:"))
async def on_event_button(callback: CallbackQuery, assistant: Assistant) -> None:
    parts = callback.data.split(":")
    action, event_id = parts[1], int(parts[2])
    calls = {
        "done": ToolCall("complete_event", {"event_id": event_id}),
        "del": ToolCall("delete_event", {"event_id": event_id}),
        "snooze": ToolCall("update_event", {"event_id": event_id, "in_minutes": int(parts[-1])}),
    }
    if action not in calls:
        await callback.answer()
        return
    result = await assistant.run_action(callback.from_user.id, calls[action])
    await callback.answer()
    # Дописываем итог к исходному сообщению и убираем кнопки — так история чата остаётся понятной
    await callback.message.edit_text(f"{callback.message.html_text}\n\n{result.text}", reply_markup=None)
