"""Проверочный набор фраз: живая модель + наш код должны дать правильный итог.

Для создания проверяется сохранённая запись (тип, дата/время) или уточняющий вопрос,
для списков и поиска — выбранная функция и период.

Запуск:  python -m scripts.eval_phrases [модель ...]
Без аргументов — модель из GIGACHAT_MODEL. Нужен .env с GIGACHAT_CREDENTIALS.
"""

import asyncio
import json
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from app.assistant.actions import Actions
from app.assistant.prompt import build_system_prompt
from app.config import get_settings
from app.llm.base import ChatMessage, LLMReply
from app.llm.gigachat_client import GigaChatClient
from app.llm.tools import TOOLS
from tests.fakes import FakeEventRepository

TZ = "Europe/Moscow"
NOW = datetime(2026, 10, 30, 14, 0, tzinfo=ZoneInfo(TZ))  # пятница

# at: "YYYY-MM-DD HH:MM" или "YYYY-MM-DD" (весь день); clarify: должен переспросить, а не создать
CASES = [
    ("Напомни мне завтра в 10 утра позвонить Ивану", "create_event", {"kind": "reminder", "at": "2026-10-31 10:00"}),
    ("В пятницу нужно отправить отчет", "create_event", {"kind": "task", "at": "2026-11-06"}),
    ("Поставь задачу купить билеты до конца недели", "create_event", {"kind": "task", "at": "2026-11-01"}),
    ("Напомни через два часа выключить духовку", "create_event", {"kind": "reminder", "at": "2026-10-30 16:00"}),
    ("Послезавтра вечером забрать посылку", "create_event", {"at": "2026-11-01 19:00"}),
    ("Напомни 5 ноября оплатить интернет в 12", "create_event", {"kind": "reminder", "at": "2026-11-05 12:00"}),
    ("Добавь встречу с командой завтра в 15:00", "create_event", {"kind": "meeting", "at": "2026-10-31 15:00"}),
    ("В четверг в 11 у меня встреча с дизайнером", "create_event", {"kind": "meeting", "at": "2026-11-05 11:00"}),
    ("Созвон с заказчиком во вторник в 3 дня", "create_event", {"kind": "meeting", "at": "2026-11-03 15:00"}),
    ("Поставь встречу с Иваном завтра", "create_event", {"kind": "meeting", "clarify": True}),
    ("Что у меня сегодня?", "list_events", {"period": "today"}),
    ("Какие планы на сегодня?", "list_events", {"period": "today"}),
    ("Покажи мои встречи на сегодня", "list_events", {"period": "today", "kind": "meeting"}),
    ("Есть ли у меня встречи сегодня?", "list_events", {"period": "today", "kind": "meeting"}),
    ("Какие задачи у меня на завтра?", "list_events", {"period": "tomorrow", "kind": "task"}),
    ("Что запланировано на эту неделю?", "list_events", {"period": "this_week"}),
    ("Что у меня на следующей неделе?", "list_events", {"period": "next_week"}),
    ("Найди задачу про презентацию", "search_events", {}),
    ("Когда у меня была встреча с Иваном?", "search_events", {}),
    ("Я когда-то ставил задачу по договору, найди ее", "search_events", {}),
]


async def check(reply: LLMReply, tool: str, expected: dict) -> str | None:
    """None — ок, иначе описание ошибки."""
    if not reply.tool_call:
        return f"ответил текстом: {reply.text[:60]!r}"
    if reply.tool_call.name != tool:
        return f"функция {reply.tool_call.name}"
    args = reply.tool_call.arguments
    if tool != "create_event":
        for key, value in expected.items():
            if args.get(key) != value:
                return f"{key}={args.get(key)} (ждали {value})"
        return None

    repo = FakeEventRepository()
    await Actions(repo, 1, NOW).run(reply.tool_call)
    if expected.get("clarify"):
        return "создал запись вместо вопроса" if repo.events else None
    if not repo.events:
        return "не создал запись"
    e = repo.events[0]
    if "kind" in expected and e.kind != expected["kind"]:
        return f"kind={e.kind}"
    local = e.starts_at.astimezone(NOW.tzinfo) if e.starts_at else None
    at = "" if local is None else (f"{local:%Y-%m-%d}" if e.all_day else f"{local:%Y-%m-%d %H:%M}")
    return None if at == expected["at"] else f"at={at or '—'} (ждали {expected['at']})"


async def run(model: str) -> int:
    s = get_settings()
    llm = GigaChatClient(s.gigachat_credentials, s.gigachat_scope, model, s.sber_ca_bundle)
    system = ChatMessage("system", build_system_prompt(NOW, TZ))
    ok = 0
    started = time.monotonic()
    try:
        for phrase, tool, expected in CASES:
            reply = await llm.complete([system, ChatMessage("user", phrase)], TOOLS)
            error = await check(reply, tool, expected)
            ok += error is None
            args = json.dumps(reply.tool_call.arguments, ensure_ascii=False) if reply.tool_call else ""
            print(f"{'OK ' if error is None else 'ERR'} {phrase:<50} {error or ''}  {args if error else ''}")
    finally:
        await llm.close()
    print(f"== {model}: {ok}/{len(CASES)}, {time.monotonic() - started:.0f} с")
    return ok


async def main() -> None:
    models = sys.argv[1:] or [get_settings().gigachat_model]
    for model in models:
        await run(model)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
