"""Telegram-интерфейс.

Разделы (сегодня, неделя, задачи, настройки…) живут в одном сообщении-«панели»: навигация
перерисовывает его на месте, а не присылает новое. Команды и кнопка «🏠 Меню» удаляют
сообщение пользователя и переносят панель вниз чата. Свободный текст и голос — обычный диалог.
"""

import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from html import escape
from zoneinfo import ZoneInfo

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import BufferedInputFile, CallbackQuery, FSInputFile, Message
from aiogram.utils.chat_action import ChatActionSender

from app.assistant.actions import ActionResult
from app.assistant.service import Assistant
from app.bot.keyboards import (
    BTN_MENU,
    TZ_LABEL,
    back_only,
    demo_actions,
    demo_load_only,
    event_actions,
    export_actions,
    home_actions,
    list_actions,
    reply_menu,
    settings_actions,
    timezone_actions,
)
from app.core.dates import WEEKDAYS
from app.core.formatting import MONTHS_GEN, plain
from app.llm.base import ToolCall
from app.speech.base import SpeechToText, TextToSpeech

log = logging.getLogger(__name__)
router = Router()

# Последняя панель в каждом чате (в памяти процесса: после рестарта старая панель просто останется в истории)
_panels: dict[int, int] = {}

HELP = (
    "❓ <b>Что я умею</b>\n"
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
    "Напоминания пришлю сам, о встречах предупрежу за 15 минут."
)

WELCOME_IMAGE = Path(__file__).resolve().parents[2] / "assets" / "welcome.jpg"
_welcome_photo_id: str | None = None  # после первой отправки Telegram отдаёт file_id — дальше без загрузки файла

WELCOME = (
    "👋 <b>{hello}</b>\n\n"
    "Я Горький — помогаю держать в голове всё важное, чтобы ты не держал. "
    "Просто скажи или напиши, как другу, а я сам пойму, что это: задача, встреча или напоминание. "
    "И обязательно напомню вовремя.\n\n"
    "<b>Например:</b>\n"
    "🎙 «Напомни завтра в 10 позвонить маме»\n"
    "👥 «В четверг в 15:00 созвон с командой»\n"
    "📅 «Что у меня на неделе?»\n\n"
    "Попробуй прямо сейчас — голосом быстрее всего 😉\n\n"
    "<i>Проверяешь тестовое задание? В меню «📥 Демо-данные» — 1000 записей для поиска.</i>"
)


def _remember_welcome_photo(message: Message) -> None:
    global _welcome_photo_id
    if message.photo:
        _welcome_photo_id = message.photo[-1].file_id


COMMAND_VIEWS = {"menu": "home", "today": "d", "tomorrow": "d+1", "week": "w", "tasks": "t",
                 "calendar": "export", "settings": "settings", "help": "help", "demo": "demo"}

DEMO_TRY = (
    "Попробуй спросить:\n"
    "🔎 «Найди задачу про договор»\n"
    "🔎 «Когда у меня была встреча с Иваном?»\n"
    "🔎 «Когда будет созвон с Альфой?»\n"
    "📅 «Что у меня на этой неделе?» · «Что было 15 января 2024?»"
)


# --- вход в панель -------------------------------------------------------------

@router.message(CommandStart())
async def on_start(message: Message, bot: Bot, assistant: Assistant, webapp_url: str, public_base: str) -> None:
    name = escape(message.from_user.first_name or "")
    caption = WELCOME.format(hello=f"Привет, {name}!" if name else "Привет!")
    photo = _welcome_photo_id or FSInputFile(WELCOME_IMAGE)
    try:
        sent = await message.answer_photo(photo, caption=caption, reply_markup=reply_menu(webapp_url))
        _remember_welcome_photo(sent)
    except TelegramBadRequest:
        # Картинка недоступна — приветствие всё равно должно дойти
        await message.answer(caption, reply_markup=reply_menu(webapp_url))
    await _show_panel(bot, message.chat.id, *await _render(assistant, message.from_user.id, "home", None, public_base))


@router.message(F.text == BTN_MENU)
@router.message(Command(*COMMAND_VIEWS))
async def on_panel_command(message: Message, bot: Bot, assistant: Assistant, public_base: str) -> None:
    view = "home" if message.text == BTN_MENU else COMMAND_VIEWS[message.text.lstrip("/").split("@")[0]]
    await _delete(message)
    today = await _local_today(assistant, message.from_user.id)
    if view.startswith("d"):
        view, anchor = "d", today + timedelta(days=1 if view == "d+1" else 0)
    else:
        anchor = today
    await _show_panel(bot, message.chat.id, *await _render(assistant, message.from_user.id, view, anchor, public_base))


# --- навигация по панели (на месте) ---------------------------------------------

@router.callback_query(F.data.startswith("v:"))
async def on_view(callback: CallbackQuery, assistant: Assistant, public_base: str) -> None:
    _, view, *rest = callback.data.split(":")
    anchor = date.fromisoformat(rest[0]) if rest else None
    await callback.answer()
    await _edit_panel(callback, *await _render(assistant, callback.from_user.id, view, anchor, public_base))


@router.callback_query(F.data.startswith("ls:"))
async def on_list_done(callback: CallbackQuery, assistant: Assistant, public_base: str) -> None:
    _, event_id, view, anchor = callback.data.split(":")
    result = await assistant.run_action(callback.from_user.id, ToolCall("complete_event", {"event_id": int(event_id)}))
    await callback.answer(_head(result))
    await _edit_panel(callback, *await _render(assistant, callback.from_user.id, view, date.fromisoformat(anchor), public_base))


@router.callback_query(F.data.startswith("set:"))
async def on_settings_button(callback: CallbackQuery, assistant: Assistant, public_base: str) -> None:
    _, key, value = callback.data.split(":", 2)
    args = {"voice": {"voice_replies": value == "1"}, "digest": {"digest_time": value}, "tz": {"timezone": value}}[key]
    result = await assistant.run_action(callback.from_user.id, ToolCall("update_settings", args))
    await callback.answer(_head(result))
    await _edit_panel(callback, *await _render(assistant, callback.from_user.id, "settings", None, public_base))


@router.callback_query(F.data.startswith("demo:"))
async def on_demo(callback: CallbackQuery, assistant: Assistant, public_base: str) -> None:
    uid = callback.from_user.id
    if callback.data == "demo:load":
        # Сразу показываем, что работа идёт; итог — всплывающим окном, которое нельзя не заметить
        await _edit_panel(callback, "⏳ <b>Загружаю 1000 записей из задания…</b>", None)
        try:
            count = await assistant.load_demo(uid)
        except Exception:
            log.exception("demo import failed")
            await callback.answer("😕 Не получилось загрузить демо-данные. Попробуй ещё раз чуть позже.", show_alert=True)
            await _edit_panel(callback, *await _render(assistant, uid, "demo", None, public_base))
            return
        total = await assistant.demo_count(uid)
        popup = f"✅ Готово! Загружено {count} записей." if count else f"✅ Демо-данные уже загружены ({total} записей)."
        await callback.answer(popup + " Попробуй спросить: «Когда у меня была встреча с Иваном?»", show_alert=True)
    else:
        count = await assistant.clear_demo(uid)
        await callback.answer(f"🧹 Убрал {count} демо-записей. Твои собственные записи не тронуты.", show_alert=True)
    await _edit_panel(callback, *await _render(assistant, uid, "demo", None, public_base))


@router.callback_query(F.data == "m:open")
async def on_open_menu(callback: CallbackQuery, bot: Bot, assistant: Assistant, public_base: str) -> None:
    """«Меню» под ответом бота: ответ остаётся, панель открывается внизу чата."""
    await callback.answer()
    home = await _render(assistant, callback.from_user.id, "home", None, public_base)
    await _show_panel(bot, callback.message.chat.id, *home)


# --- свободный текст и голос ---------------------------------------------------

@router.message(F.text)
async def on_text(message: Message, bot: Bot, assistant: Assistant) -> None:
    async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
        result = await assistant.handle(message.from_user.id, message.text)
    text, markup = await _with_demo_hint(assistant, message.from_user.id, result)
    await message.answer(text, reply_markup=markup)


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

    reply, markup = await _with_demo_hint(assistant, message.from_user.id, result)
    await message.answer(f"🎙 <i>{escape(text)}</i>\n\n{reply}", reply_markup=markup)
    if not (await assistant.settings(message.from_user.id)).voice_replies:
        return
    try:
        async with ChatActionSender.record_voice(bot=bot, chat_id=message.chat.id):
            voice = await tts.synthesize(result.text)
        await message.answer_voice(BufferedInputFile(voice, filename="reply.mp3"))
    except Exception:
        # Текстовый ответ уже отправлен — без голоса пользователь ничего не теряет
        log.exception("TTS failed")


# --- кнопки под ответами диалога ---------------------------------------------------

@router.callback_query(F.data.startswith("ev:"))
async def on_event_button(callback: CallbackQuery, assistant: Assistant) -> None:
    _, action, *rest = callback.data.split(":")
    event_id = int(rest[0])
    uid = callback.from_user.id
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


# --- разделы панели --------------------------------------------------------------

async def _render(assistant: Assistant, user_id: int, view: str, anchor: date | None, public_base: str):
    """(текст, клавиатура) раздела панели."""
    if view == "home":
        return await _home(assistant, user_id)
    if view == "help":
        return HELP, back_only()
    if view == "demo":
        count = await assistant.demo_count(user_id)
        if count:
            text = f"✅ <b>Демо-данные загружены: {count} записей</b>\nИз CSV тестового задания, 2024–2027 годы.\n\n{DEMO_TRY}"
        else:
            text = (
                "📥 <b>Демо-данные из задания</b>\n\n"
                "К тестовому заданию приложен файл с 1000 записей (задачи, напоминания и встречи "
                "за 2024–2027 годы). Загрузи их в свой аккаунт, чтобы попробовать поиск и списки. "
                "Убрать можно в любой момент — твои собственные записи не пострадают."
            )
        return text, demo_actions(bool(count))
    if view == "settings":
        s = await assistant.settings(user_id)
        return _settings_text(s), settings_actions(s)
    if view == "tz":
        return "🌍 <b>Часовой пояс</b>\n\nВыбери город или просто скажи: «я в Хабаровске».", timezone_actions()
    if view == "export":
        _, token = await assistant.export_ics(user_id)
        subscribe = f"{public_base}/calendar/{token}" if public_base else ""
        return _export_text(bool(subscribe)), export_actions(subscribe)
    if view == "t":
        result = await assistant.tasks_overview(user_id)
        return result.text, list_actions(result.events, "t", anchor or date.today())

    anchor = anchor or await _local_today(assistant, user_id)
    if view == "w":
        anchor -= timedelta(days=anchor.weekday())
        span = {"date_from": anchor.isoformat(), "date_to": (anchor + timedelta(days=6)).isoformat()}
    else:
        span = {"date_from": anchor.isoformat(), "date_to": anchor.isoformat()}
    result = await assistant.run_action(user_id, ToolCall("list_events", {"period": "custom", **span}))
    return _list_title(result, view, anchor), list_actions(result.events, view, anchor)


async def _home(assistant: Assistant, user_id: int):
    today = await _local_today(assistant, user_id)
    result = await assistant.run_action(
        user_id, ToolCall("list_events", {"period": "custom", "date_from": today.isoformat(), "date_to": today.isoformat()})
    )
    count = len(result.events)
    plans = f"на сегодня {count} {_plural(count, 'дело', 'дела', 'дел')}" if count else "на сегодня планов нет"
    text = (
        f"🏠 <b>{_day_title(today)}</b> — {plans}\n\n"
        "Напиши или скажи, что запланировать, или выбери раздел 👇"
    )
    return text, home_actions(today)


def _list_title(result: ActionResult, view: str, anchor: date) -> str:
    if view == "w":
        end = anchor + timedelta(days=6)
        return f"🗓 <b>Неделя {anchor:%d.%m} — {end:%d.%m}</b>\n\n{result.text}"
    if not result.events:
        return f"<b>{_day_title(anchor)}</b>\n\n🌿 Ничего не запланировано."
    return result.text


def _export_text(available: bool) -> str:
    if not available:
        return (
            "📆 <b>Календарь телефона</b>\n\n"
            "Подключение появится, когда бот работает на сервере с HTTPS."
        )
    return (
        "📆 <b>Календарь телефона</b>\n\n"
        "Подключи один раз — все задачи, напоминания и встречи будут появляться в обычном "
        "календаре телефона сами, вместе с повторами и оповещениями.\n\n"
        "• <b>iPhone</b> — откроется окно «Подписаться на календарь», нажми «Подписаться».\n"
        "• <b>Android</b> — откроется Google Календарь, нажми «Добавить».\n\n"
        "<i>iPhone обновляет календарь примерно раз в час, Google — реже.</i>"
    )


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


# --- вспомогательное ---------------------------------------------------------------

async def _show_panel(bot: Bot, chat_id: int, text: str, markup) -> None:
    """Новая панель внизу чата, старая удаляется."""
    old = _panels.pop(chat_id, None)
    if old is not None:
        try:
            await bot.delete_message(chat_id, old)
        except TelegramBadRequest:
            pass  # уже удалена или старше 48 часов
    sent = await bot.send_message(chat_id, text, reply_markup=markup, disable_web_page_preview=True)
    _panels[chat_id] = sent.message_id


async def _edit_panel(callback: CallbackQuery, text: str, markup) -> None:
    _panels[callback.message.chat.id] = callback.message.message_id
    try:
        await callback.message.edit_text(text, reply_markup=markup, disable_web_page_preview=True)
    except TelegramBadRequest:
        # «message is not modified» — содержимое не поменялось, это нормально
        log.debug("edit skipped", exc_info=True)


async def _delete(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        pass


async def _with_demo_hint(assistant: Assistant, user_id: int, result: ActionResult):
    """Поиск ничего не нашёл, а демо-данные не загружены — предлагаем загрузить (частый случай у проверяющих)."""
    if not result.events and result.text.startswith("🤷") and not await assistant.demo_count(user_id):
        hint = "\n\n💡 Демо-данные из задания (1000 записей) ещё не загружены — загрузи и спроси снова."
        return result.text + hint, demo_load_only()
    return result.text, event_actions(result.events, result.undo)


async def _local_today(assistant: Assistant, user_id: int) -> date:
    s = await assistant.settings(user_id)
    return datetime.now(ZoneInfo(s.timezone)).date()


def _day_title(d: date) -> str:
    return f"{WEEKDAYS[d.weekday()].capitalize()}, {d.day} {MONTHS_GEN[d.month - 1]}"


def _plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def _head(result: ActionResult) -> str:
    return plain(result.text).split("\n")[0][:200]
