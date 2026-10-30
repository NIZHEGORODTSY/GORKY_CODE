from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.assistant.actions import Actions
from app.core.formatting import plain
from app.llm.base import ToolCall
from tests.fakes import FakeEventRepository, FakeUserRepository, meeting

MSK = ZoneInfo("Europe/Moscow")
NOW = datetime(2026, 10, 30, 14, 0, tzinfo=MSK)  # пятница
USER = 1


async def test_weekly_meeting_shows_every_week():
    repo = FakeEventRepository()
    actions = Actions(repo, USER, NOW)
    res = await actions.run(ToolCall("create_event", {
        "kind": "meeting", "title": "Планёрка", "time": "10:00", "repeat": "weekly", "repeat_days": ["monday"]}))
    assert repo.events[0].starts_at == datetime(2026, 11, 2, 10, tzinfo=MSK)
    assert "каждый пн" in plain(res.text)
    listed = await actions.run(ToolCall("list_events", {"period": "custom", "date_from": "2026-11-01", "date_to": "2026-11-16"}))
    assert plain(listed.text).count("Планёрка") == 3


async def test_complete_recurring_moves_to_next_and_undo_restores():
    repo = FakeEventRepository()
    actions = Actions(repo, USER, NOW)
    await actions.run(ToolCall("create_event", {"kind": "reminder", "title": "Таблетки", "time": "22:00", "repeat": "daily"}))
    res = await actions.run(ToolCall("complete_event", {"event_id": 1}))
    assert repo.events[0].starts_at == datetime(2026, 10, 31, 22, tzinfo=MSK)
    assert "Следующий раз" in plain(res.text) and res.undo
    event_id, ts = res.undo.split(":")
    await actions.run(ToolCall("restore_event", {"event_id": int(event_id), "starts_at": int(ts)}))
    assert repo.events[0].starts_at == datetime(2026, 10, 30, 22, tzinfo=MSK)


async def test_delete_then_undo():
    repo = FakeEventRepository()
    actions = Actions(repo, USER, NOW)
    await actions.run(ToolCall("create_event", {"kind": "task", "title": "Купить билеты", "day": "tomorrow"}))
    res = await actions.run(ToolCall("delete_event", {"event_id": 1}))
    assert repo.events[0].status.value == "cancelled"
    await actions.run(ToolCall("restore_event", {"event_id": int(res.undo)}))
    assert repo.events[0].status.value == "open"


async def test_rename_and_duration():
    repo = FakeEventRepository()
    actions = Actions(repo, USER, NOW)
    e = await repo.add(meeting(USER, "Созвон", datetime(2026, 10, 31, 15, tzinfo=MSK)))
    res = await actions.run(ToolCall("update_event", {"event_id": e.id, "title": "Созвон с заказчиком", "duration_minutes": 120}))
    moved = await repo.get(USER, e.id)
    assert moved.title == "Созвон с заказчиком"
    assert moved.ends_at == datetime(2026, 10, 31, 17, tzinfo=MSK)
    assert "Переименовал" in plain(res.text)


async def test_settings():
    users = FakeUserRepository()
    actions = Actions(FakeEventRepository(), USER, NOW, users=users)
    res = await actions.run(ToolCall("update_settings", {"timezone": "Asia/Novosibirsk", "digest_time": "8:00", "voice_replies": False}))
    assert users.values == {"timezone": "Asia/Novosibirsk", "digest_time": time(8), "voice_replies": False}
    assert "Новосиб" not in res.text and "08:00" in res.text
    bad = await actions.run(ToolCall("update_settings", {"timezone": "Mars/Olympus"}))
    assert "Не узнал" in bad.text


async def test_meeting_lead_setting():
    users = FakeUserRepository()
    actions = Actions(FakeEventRepository(), USER, NOW, users=users)
    res = await actions.run(ToolCall("update_settings", {"meeting_lead_minutes": 30}))
    assert users.values == {"meeting_lead_minutes": 30}
    assert "за 30 мин" in res.text
