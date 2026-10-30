"""Поиск по смыслу без эмбеддингов: LLM выбирает подходящие записи из списка кандидатов.

Используется, когда полнотекстовый поиск ничего не нашёл («Ваня» vs «Иван»,
«слайды» vs «презентация»). У личного планировщика записей немного, список влезает в промпт.
"""

import logging

from app.core.models import Event
from app.llm.base import ChatMessage, LLMClient, ToolSpec

log = logging.getLogger(__name__)

SELECT_EVENTS = ToolSpec(
    name="select_events",
    description="Вернуть номера записей, подходящих под запрос пользователя.",
    parameters={
        "type": "object",
        "properties": {
            "ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Номера подходящих записей, от самой подходящей. Пустой список, если подходящих нет.",
            }
        },
        "required": ["ids"],
    },
)

PROMPT = (
    "Ты ищешь записи пользователя по смыслу. Учитывай синонимы, уменьшительные имена "
    "(Ваня = Иван), однокоренные и близкие по смыслу слова (слайды ≈ презентация). "
    "Выбирай запись, только если она действительно про то же самое, что запрос. "
    "Если ни одна не подходит — верни пустой список: это нормальный и частый результат, "
    "лучше ничего не найти, чем показать нерелевантное. Ответь вызовом select_events."
)


class LLMEventMatcher:
    def __init__(self, llm: LLMClient, max_results: int = 5):
        self._llm = llm
        self._max_results = max_results

    async def match(self, query: str, candidates: list[Event]) -> list[Event]:
        if not candidates:
            return []
        by_id = {e.id: e for e in candidates}
        listing = "\n".join(f"{e.id}: {e.title}" for e in candidates)
        messages = [
            ChatMessage("system", PROMPT),
            ChatMessage("user", f"Запрос: {query}\n\nЗаписи:\n{listing}"),
        ]
        try:
            reply = await self._llm.complete(messages, [SELECT_EVENTS])
        except Exception:
            log.exception("LLM matcher failed")
            return []
        if not reply.tool_call:
            return []
        ids = reply.tool_call.arguments.get("ids") or []
        return [by_id[i] for i in ids if isinstance(i, int) and i in by_id][: self._max_results]
