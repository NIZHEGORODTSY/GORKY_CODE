import logging
from datetime import date, datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from aiogram.utils.chat_action import ChatActionSender

from app.assistant.actions import ActionResult
from app.assistant.service import Assistant
from app.bot.keyboards import (
    BTN_EXPORT,
    BTN_HELP,
    BTN_SETTINGS,
    BTN_TASKS,
    BTN_TODAY,
    BTN_TOMORROW,
    BTN_WEEK,
    TZ_LABEL,
    event_actions,
    export_actions,
    list_actions,
    main_menu,
    settings_actions,
    timezone_actions,
)
from app.core.dates import WEEKDAYS
from app.core.formatting import MONTHS_GEN, plain
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
    "🔁 «Каждый понедельник в 10 планёрка»\n\n"
    "<b>Посмотреть и найти</b>\n"
    "📅 «Что у меня сегодня?» · «Планы на неделю»\n"
    "🔎 «Найди задачу про договор»\n\n"
    "<b>Изменить</b>\n"
    "↪️ «Перенеси её на пятницу» · ✏️ «Переименуй в …» · ✅ «Я купил билеты» · 🗑 «Встреча отменилась»\n\n"
    "<b>Настроить</b>\n"
    "🌍 «Я в Новосибирске» · ☀️ «Присылай план по утрам в 8»\n\n"
    "Напоминания пришлю сам, о встречах предупрежу за 15 минут. "
    "Планы можно добавить в календарь телефона — кнопка «📆 В календарь»."
)


# --- справка, списки, задачи ---------------------------------------------------

@router.message(CommandStart())
@router.message(Command("help"))
@router.message(F.text == BTN_HELP)
async def on_help(message: Message, webapp_url: str) -> None:
    await message.answer(HELP, reply_markup=main_menu(webapp_url))


@router.message(Command("today"))
@router.message(F.text == BTN_TODAY)
async def on_today(message: Message, assistant: Assistant) -> None:
    today = await _local_today(assistant, message.from_user.id)
    text, markup = await _render_view(assistant, message.from_user.id, "d", today)
    await message.answer(text, reply_markup=markup)


@router.message(Command("tomorrow"))
@router.message(F.text == BTN_TOMORROW)
async def on_tomorrow(message: Message, assistant: Assistant) -> None:
    today = await _local_today(assistant, message.from_user.id)
    text, markup = await _render_view(assistant, message.from_user.id, "d", today + timedelta(days=1))
    await message.answer(text, reply_markup=markup)


@router.message(Command("week"))
@router.message(F.text == BTN_WEEK)
async def on_week(message: Message, assistant: Assistant) -> None:
    today = await _local_today(assistant, message.from_user.id)
    text, markup = await _render_view(assistant, message.from_user.id, "w", today)
    await message.answer(text, reply_markup=markup)


@router.message(Command("tasks"))
@router.message(F.text == BTN_TASKS)
async def on_tasks(message: Message, assistant: Assistant) -> None:
    text, markup = await _render_view(assistant, message.from_user.id, "t", date.today())
    await message.answer(text, reply_markup=markup)


# --- календарь телефона и настройки ------------------------------------------------

@router.message(Command("calendar"))
@router.message(F.text == BTN_EXPORT)
async def on_export(message: Message, assistant: Assistant, public_base: str) -> None:
    ics, token = await assistant.export_ics(message.from_user.id)
    feed = f"{public_base}/ics/{token}.ics" if public_base else ""
    lines = ["📆 <b>Планы в календаре телефона</b>", ""]
    if feed:
        lines += [
            "Ссылка-подписка — календарь будет обновляться сам:",
            f"<code>{feed}</code>",
            "",
            "• <b>Android / Google:</b> кнопка ниже → «Добавить»",
            "• <b>iPhone:</b> Настройки → Календарь → Учётные записи → Добавить → Другое → "
            "Подписной календарь → вставь ссылку",
            "• <b>Яндекс Календарь:</b> Добавить календарь → Подписаться → вставь ссылку",
            "",
            "А ещё прикрепляю файл — открой его, чтобы добавить планы разово.",
        ]
    else:
        lines += [
            "Открой файл ниже — iPhone и Android предложат добавить записи в календарь.",
            "Ссылка-подписка с автообновлением появится, когда бот будет работать на сервере.",
        ]
    await message.answer("\n".join(lines), reply_markup=export_actions(feed), disable_web_page_preview=True)
    await message.answer_document(BufferedInputFile(ics.encode(), filename="gorky-plans.ics"))


@router.message(Command("settings"))
@router.message(F.text == BTN_SETTINGS)
async def on_settings(message: Message, assistant: Assistant) -> None:
    s = await assistant.settings(message.from_user.id)
    await message.answer(_settings_text(s), reply_markup=settings_actions(s))


# --- свободный текст и голос ---------------------------------------------------

@router.message(F.text)
async def on_text(message: Message, bot: Bot, assistant: Assistant) -> None:
    async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
        result = await assistant.handle(message.from_user.id, message.text)
    await message.answer(result.text, reply_markup=event_actions(result.events, result.undo))


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

    await message.answer(
        f"🎙 <i>{escape(text)}</i>\n\n{result.text}", reply_markup=event_actions(result.events, result.undo)
    )
    if not (await assistant.settings(message.from_user.id)).voice_replies:
        return
    try:
        async with ChatActionSender.record_voice(bot=bot, chat_id=message.chat.id):
            voice = await tts.synthesize(result.text)
        await message.answer_voice(BufferedInputFile(voice, filename="reply.mp3"))
    except Exception:
        # Текстовый ответ уже отправлен — без голоса пользователь ничего не теряет
        log.exception("TTS failed")


# --- кнопки под сообщениями ------------------------------------------------------

@router.callback_query(F.data.startswith("ev:"))
async def on_event_button(callback: CallbackQuery, assistant: Assistant) -> None:
    _, action, *rest = callback.data.split(":")
    event_id = int(rest[0])
    uid = callback.from_user.id
    if action == "ics":
        ics, _ = await assistant.export_ics(uid, event_id)
        await callback.answer("Открой файл — запись добавится в календарь")
        await callback.message.answer_document(BufferedInputFile(ics.encode(), filename=f"event-{event_id}.ics"))
        return
    calls = {
        "done": ToolCall("complete_event", {"event_id": event_id}),
        "del": ToolCall("delete_event", {"event_id": event_id}),
        "snooze": ToolCall("update_event", {"event_id": event_id, "in_minutes": int(rest[-1])}),
        "undo": ToolCall("restore_event", {"event_id": event_id, "starts_at": rest[1] if len(rest) > 1 else None}),
    }
    if action not in calls:
        await callback.answer()
        return
    result = await assistant.run_action(uid, calls[action])
    await callback.answer()
    # Итог дописываем к исходному сообщению — так история чата остаётся понятной
    await callback.message.edit_text(
        f"{callback.message.html_text}\n\n{result.text}", reply_markup=event_actions([], result.undo)
    )


@router.callback_query(F.data.startswith("ls:"))
async def on_list_done(callback: CallbackQuery, assistant: Assistant) -> None:
    _, event_id, view, anchor = callback.data.split(":")
    result = await assistant.run_action(callback.from_user.id, ToolCall("complete_event", {"event_id": int(event_id)}))
    await callback.answer(_plain_head(result))
    text, markup = await _render_view(assistant, callback.from_user.id, view, date.fromisoformat(anchor))
    await _edit(callback, text, markup)


@router.callback_query(F.data.startswith("nav:"))
async def on_nav(callback: CallbackQuery, assistant: Assistant) -> None:
    _, view, anchor = callback.data.split(":")
    text, markup = await _render_view(assistant, callback.from_user.id, view, date.fromisoformat(anchor))
    await callback.answer()
    await _edit(callback, text, markup)


@router.callback_query(F.data.startswith("set:"))
async def on_settings_button(callback: CallbackQuery, assistant: Assistant) -> None:
    _, key, *value = callback.data.split(":", 2)
    if key == "tzmenu":
        await callback.answer()
        await callback.message.edit_reply_markup(reply_markup=timezone_actions())
        return
    args = {
        "voice": lambda v: {"voice_replies": v == "1"},
        "digest": lambda v: {"digest_time": v},
        "tz": lambda v: {"timezone": v},
    }[key](value[0])
    result = await assistant.run_action(callback.from_user.id, ToolCall("update_settings", args))
    await callback.answer(_plain_head(result))
    s = await assistant.settings(callback.from_user.id)
    await _edit(callback, _settings_text(s), settings_actions(s))


# --- вспомогательное -------------------------------------------------------------

async def _render_view(assistant: Assistant, user_id: int, view: str, anchor: date):
    """Список дня (d), недели (w) или всех задач (t) + кнопки к нему."""
    if view == "t":
        result = await assistant.tasks_overview(user_id)
    else:
        if view == "w":
            anchor = anchor - timedelta(days=anchor.weekday())
            span = {"date_from": anchor.isoformat(), "date_to": (anchor + timedelta(days=6)).isoformat()}
        else:
            span = {"date_from": anchor.isoformat(), "date_to": anchor.isoformat()}
        result = await assistant.run_action(user_id, ToolCall("list_events", {"period": "custom", **span}))
    return _with_title(result, view, anchor), list_actions(result.events, view, anchor)


def _with_title(result: ActionResult, view: str, anchor: date) -> str:
    if view == "w":
        end = anchor + timedelta(days=6)
        return f"🗓 <b>Неделя {anchor:%d.%m} — {end:%d.%m}</b>\n\n{result.text}"
    if view == "d" and not result.events:
        day = f"{WEEKDAYS[anchor.weekday()].capitalize()}, {anchor.day} {MONTHS_GEN[anchor.month - 1]}"
        return f"<b>{day}</b>\n\n🌿 Ничего не запланировано."
    return result.text


def _settings_text(s) -> str:
    digest = f"каждый день в {s.digest_time:%H:%M}" if s.digest_time else "выключена"
    now = datetime.now(ZoneInfo(s.timezone))
    return (
        "⚙️ <b>Настройки</b>\n\n"
        f"🌍 Часовой пояс: {escape(TZ_LABEL.get(s.timezone, s.timezone))} (сейчас {now:%H:%M})\n"
        f"☀️ Утренняя сводка: {digest}\n"
        f"🔊 Голосовые ответы: {'включены' if s.voice_replies else 'выключены'}\n\n"
        "Меняй кнопками ниже или голосом: «я в Новосибирске», «присылай план в 8»."
    )


async def _local_today(assistant: Assistant, user_id: int) -> date:
    s = await assistant.settings(user_id)
    return datetime.now(ZoneInfo(s.timezone)).date()


def _plain_head(result: ActionResult) -> str:
    return plain(result.text).split("\n")[0][:200]


async def _edit(callback: CallbackQuery, text: str, markup) -> None:
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        # «message is not modified» — содержимое не поменялось, это нормально
        log.debug("edit skipped", exc_info=True)
