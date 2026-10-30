import json
import logging
from html import escape
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.assistant.actions import ActionResult, Actions
from app.assistant.prompt import build_system_prompt
from app.core.formatting import plain
from app.core.models import Event
from app.llm.base import ChatMessage, LLMClient, ToolCall
from app.llm.tools import TOOLS
from app.search.llm_matcher import LLMEventMatcher
from app.storage.repository import EventRepository, UserRepository

log = logging.getLogger(__name__)

HISTORY_SIZE = 10  # сообщений (пар вопрос/ответ — вдвое меньше)
RECENT_SIZE = 10
LLM_ERROR = "Не получилось обработать запрос — попробуй ещё раз чуть позже."


FOLLOW_UP_AFTER = {"search_events"}
TERMINAL_FOLLOW_UPS = {"update_event", "complete_event", "delete_event"}


async def run_tool_call(llm: LLMClient, messages: list[ChatMessage], call: ToolCall, actions: Actions) -> ActionResult:
    """Выполнить вызов; после поиска дать модели сделать второй шаг.

    «Сдвинь встречу с Иваном на 17:00» модель часто решает в два шага: найти, затем перенести.
    Если второго шага нет — пользователь получает результат поиска.
    """
    result = await actions.run(call)
    if call.name not in FOLLOW_UP_AFTER or not result.events:
        return result
    found = [{"event_id": e.id, "title": e.title} for e in result.events]
    follow_up = [
        *messages,
        ChatMessage("assistant", tool_call=call),
        ChatMessage("function", json.dumps({"found": found}, ensure_ascii=False), name=call.name),
    ]
    try:
        reply = await llm.complete(follow_up, TOOLS)
    except Exception:
        log.exception("follow-up LLM call failed")
        return result
    if reply.tool_call and reply.tool_call.name in TERMINAL_FOLLOW_UPS:
        log.info("follow-up tool call %s %s", reply.tool_call.name, reply.tool_call.arguments)
        actions.remember(result.events)
        return await actions.run(reply.tool_call)
    return result


class Assistant:
    """Оркестрация диалога: промпт + история -> LLM -> действие -> ответ пользователю."""

    def __init__(
        self,
        session_factory: async_sessionmaker,
        llm: LLMClient,
        default_timezone: str,
        clock: Callable[[ZoneInfo], datetime] = datetime.now,
    ):
        self._session_factory = session_factory
        self._llm = llm
        self._matcher = LLMEventMatcher(llm)
        self._default_timezone = default_timezone
        self._clock = clock
        # История в памяти процесса: для прототипа достаточно, теряется при рестарте
        self._history: dict[int, deque[ChatMessage]] = defaultdict(lambda: deque(maxlen=HISTORY_SIZE))
        # Записи из последнего ответа — для «перенеси её», «удали первую»
        self._recent: dict[int, list[Event]] = {}

    async def _now(self, user_id: int) -> tuple[datetime, str]:
        async with self._session_factory() as session, session.begin():
            tz_name = await UserRepository(session).ensure(user_id, self._default_timezone)
        return self._clock(ZoneInfo(tz_name)), tz_name

    async def handle(self, user_id: int, text: str) -> ActionResult:
        """Свободный текст пользователя -> ответ (Telegram-HTML) и записи, о которых он."""
        now, tz_name = await self._now(user_id)
        history = self._history[user_id]
        user_msg = ChatMessage("user", text)
        system = build_system_prompt(now, tz_name, self._recent.get(user_id))
        messages = [ChatMessage("system", system), *history, user_msg]

        try:
            reply = await self._llm.complete(messages, TOOLS)
        except Exception:
            log.exception("LLM call failed")
            return ActionResult(LLM_ERROR)

        if reply.tool_call:
            log.info("tool call %s %s", reply.tool_call.name, reply.tool_call.arguments)
            async with self._session_factory() as session, session.begin():
                actions = Actions(EventRepository(session), user_id, now, self._matcher, self._recent.get(user_id))
                result = await run_tool_call(self._llm, messages, reply.tool_call, actions)
            self._remember(user_id, result)
        else:
            result = ActionResult(escape(reply.text.strip()) or "Не понял запрос. Попробуй сформулировать иначе.")

        history.extend([user_msg, ChatMessage("assistant", plain(result.text))])
        return result

    async def run_action(self, user_id: int, call: ToolCall) -> ActionResult:
        """Действие без LLM — для команд меню и кнопок под сообщениями."""
        now, _ = await self._now(user_id)
        async with self._session_factory() as session, session.begin():
            result = await Actions(EventRepository(session), user_id, now, recent=self._recent.get(user_id)).run(call)
        self._remember(user_id, result)
        return result

    def _remember(self, user_id: int, result: ActionResult) -> None:
        if result.events:
            self._recent[user_id] = result.events[:RECENT_SIZE]
