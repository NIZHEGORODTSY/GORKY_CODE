import logging
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.assistant.actions import Actions
from app.assistant.prompt import build_system_prompt
from app.llm.base import ChatMessage, LLMClient
from app.llm.tools import TOOLS
from app.storage.repository import EventRepository, UserRepository

log = logging.getLogger(__name__)

HISTORY_SIZE = 10  # сообщений (пар вопрос/ответ — вдвое меньше)
LLM_ERROR = "Не получилось обработать запрос — попробуй ещё раз чуть позже."


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
        self._default_timezone = default_timezone
        self._clock = clock
        # История в памяти процесса: для прототипа достаточно, теряется при рестарте
        self._history: dict[int, deque[ChatMessage]] = defaultdict(lambda: deque(maxlen=HISTORY_SIZE))

    async def handle(self, user_id: int, text: str) -> str:
        async with self._session_factory() as session, session.begin():
            tz_name = await UserRepository(session).ensure(user_id, self._default_timezone)
        tz = ZoneInfo(tz_name)
        now = self._clock(tz)

        history = self._history[user_id]
        user_msg = ChatMessage("user", text)
        messages = [ChatMessage("system", build_system_prompt(now, tz_name)), *history, user_msg]

        try:
            reply = await self._llm.complete(messages, TOOLS)
        except Exception:
            log.exception("LLM call failed")
            return LLM_ERROR

        if reply.tool_call:
            log.info("tool call %s %s", reply.tool_call.name, reply.tool_call.arguments)
            async with self._session_factory() as session, session.begin():
                result = await Actions(EventRepository(session), user_id, now).run(reply.tool_call)
            answer = result.text
        else:
            answer = reply.text.strip() or "Не понял запрос. Попробуй сформулировать иначе."

        history.extend([user_msg, ChatMessage("assistant", answer)])
        return answer
