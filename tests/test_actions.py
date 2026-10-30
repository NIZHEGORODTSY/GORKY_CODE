from datetime import datetime
from zoneinfo import ZoneInfo

from app.assistant.actions import Actions
from app.core.formatting import plain
from app.core.models import EventKind
from app.llm.base import ToolCall
from tests.fakes import FakeEventRepository, meeting

MSK = ZoneInfo("Europe/Moscow")
NOW = datetime(2026, 10, 30, 14, 0, tzinfo=MSK)  # пятница
USER = 1


def make():
    repo = FakeEventRepository()
    return repo, Actions(repo, USER, NOW)


async def test_create_meeting():
    repo, actions = make()
    res = await actions.run(ToolCall("create_event", {
        "kind": "meeting", "title": "Встреча с командой", "date": "2026-10-31", "time": "15:00"}))
    e = repo.events[0]
    assert e.kind == EventKind.MEETING
    assert e.starts_at == datetime(2026, 10, 31, 15, tzinfo=MSK)
    assert e.ends_at == datetime(2026, 10, 31, 16, tzinfo=MSK)
    assert "Завтра, 31 октября · 15:00–16:00" in plain(res.text)


async def test_meeting_without_time_asks():
    repo, actions = make()
    res = await actions.run(ToolCall("create_event", {"kind": "meeting", "title": "Встреча с Иваном", "date": "2026-10-31"}))
    assert not repo.events
    assert "время" in res.text


async def test_task_with_date_only_is_all_day():
    repo, actions = make()
    await actions.run(ToolCall("create_event", {"kind": "task", "title": "Отправить отчёт", "date": "2026-11-06"}))
    assert repo.events[0].all_day
    assert repo.events[0].starts_at == datetime(2026, 11, 6, tzinfo=MSK)


async def test_reminder_time_without_date_picks_nearest():
    repo, actions = make()
    await actions.run(ToolCall("create_event", {"kind": "reminder", "title": "Выпить таблетку", "time": "10:00"}))
    assert repo.events[0].starts_at == datetime(2026, 10, 31, 10, tzinfo=MSK)  # 10:00 сегодня уже прошло


async def test_past_time_asks():
    repo, actions = make()
    res = await actions.run(ToolCall("create_event", {
        "kind": "reminder", "title": "Позвонить", "date": "2026-10-30", "time": "09:00"}))
    assert not repo.events
    assert "прошло" in res.text


async def test_task_without_date():
    repo, actions = make()
    res = await actions.run(ToolCall("create_event", {"kind": "task", "title": "Починить велосипед"}))
    assert repo.events[0].starts_at is None
    assert "Починить велосипед" in res.text


async def test_list_today_filters_by_kind():
    repo, actions = make()
    repo.events.append(meeting(USER, "Созвон", datetime(2026, 10, 30, 16, tzinfo=MSK)))
    await repo.add(repo.events.pop())
    res = await actions.run(ToolCall("list_events", {"period": "today", "kind": "meeting"}))
    assert "16:00  👥 Созвон" in plain(res.text)
    res = await actions.run(ToolCall("list_events", {"period": "today", "kind": "task"}))
    assert plain(res.text) == "🌿 На сегодня задач нет."


async def test_search():
    repo, actions = make()
    await repo.add(meeting(USER, "Обсудить договор аренды", datetime(2026, 10, 20, 12, tzinfo=MSK)))
    res = await actions.run(ToolCall("search_events", {"query": "договор"}))
    assert "Обсудить договор аренды" in res.text
    res = await actions.run(ToolCall("search_events", {"query": "презентация"}))
    assert "Не нашёл" in res.text


class FakeMatcher:
    async def match(self, query, candidates):
        return [e for e in candidates if "Ивана" in e.title] if query == "Ваня" else []


async def test_search_falls_back_to_matcher():
    repo = FakeEventRepository()
    await repo.add(meeting(USER, "Обед у Ивана", datetime(2026, 10, 20, 12, tzinfo=MSK)))
    res = await Actions(repo, USER, NOW, FakeMatcher()).run(ToolCall("search_events", {"query": "Ваня"}))
    assert "Обед у Ивана" in res.text


async def test_conflicting_meeting_warns():
    repo, actions = make()
    await repo.add(meeting(USER, "Созвон с командой", datetime(2026, 10, 31, 15, tzinfo=MSK)))
    res = await actions.run(ToolCall("create_event", {
        "kind": "meeting", "title": "Встреча с Иваном", "day": "tomorrow", "time": "15:30"}))
    assert len(repo.events) == 2
    assert "Пересекается с «Созвон с командой» в 15:00" in plain(res.text)


async def test_reschedule_keeps_time_and_duration():
    repo, actions = make()
    e = await repo.add(meeting(USER, "Встреча с Иваном", datetime(2026, 10, 31, 15, tzinfo=MSK)))
    res = await actions.run(ToolCall("update_event", {"event_id": e.id, "day": "monday"}))
    moved = await repo.get(USER, e.id)
    assert moved.starts_at == datetime(2026, 11, 2, 15, tzinfo=MSK)
    assert moved.ends_at == datetime(2026, 11, 2, 16, tzinfo=MSK)
    assert "Перенёс «Встреча с Иваном»" in plain(res.text)


async def test_complete_and_delete_by_query():
    repo, actions = make()
    await actions.run(ToolCall("create_event", {"kind": "task", "title": "Купить билеты", "day": "end_of_week"}))
    await actions.run(ToolCall("create_event", {"kind": "task", "title": "Отправить отчёт", "day": "monday"}))
    await actions.run(ToolCall("complete_event", {"query": "билеты"}))
    await actions.run(ToolCall("delete_event", {"query": "отчёт"}))
    assert [e.status.value for e in repo.events] == ["done", "cancelled"]


async def test_ambiguous_target_asks_with_options():
    repo, actions = make()
    await repo.add(meeting(USER, "Встреча с Иваном", datetime(2026, 10, 31, 15, tzinfo=MSK)))
    await repo.add(meeting(USER, "Обед с Иваном", datetime(2026, 11, 2, 13, tzinfo=MSK)))
    res = await actions.run(ToolCall("delete_event", {"query": "Иван"}))
    assert "Нашёл несколько" in res.text and len(res.events) == 2


class ScriptedLLM:
    def __init__(self, *replies):
        self.replies = list(replies)

    async def complete(self, messages, tools):
        return self.replies.pop(0)


async def test_search_then_reschedule_follow_up():
    from app.assistant.service import run_tool_call
    from app.llm.base import LLMReply

    repo, actions = make()
    e = await repo.add(meeting(USER, "Встреча с Иваном", datetime(2026, 10, 31, 15, tzinfo=MSK)))
    llm = ScriptedLLM(LLMReply(tool_call=ToolCall("update_event", {"event_id": e.id, "time": "17:00"})))
    res = await run_tool_call(llm, [], ToolCall("search_events", {"query": "Иван"}), actions)
    assert (await repo.get(USER, e.id)).starts_at == datetime(2026, 10, 31, 17, tzinfo=MSK)
    assert "Перенёс" in res.text


def test_split_type_words():
    from app.assistant.actions import _split_type_words

    assert _split_type_words("задача договор") == ("договор", "task")
    assert _split_type_words("встреча с Иваном") == ("с Иваном", "meeting")
    assert _split_type_words("встреча") == ("встреча", "meeting")
    assert _split_type_words("презентация") == ("презентация", None)
