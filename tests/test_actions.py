from datetime import datetime
from zoneinfo import ZoneInfo

from app.assistant.actions import Actions
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
    assert "завтра" in res.text and "15:00" in res.text


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
    assert "16:00 — Созвон" in res.text
    res = await actions.run(ToolCall("list_events", {"period": "today", "kind": "task"}))
    assert res.text == "На сегодня задач нет."


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
