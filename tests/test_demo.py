from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.demo import classify, load_demo_events
from app.core.models import EventKind, EventStatus

MSK = ZoneInfo("Europe/Moscow")
NOW = datetime(2026, 10, 30, 14, 0, tzinfo=MSK)


def test_classify():
    assert classify("Созвон с Альфой по CRM") == EventKind.MEETING
    assert classify("Провести планёрку по бюджету") == EventKind.MEETING
    assert classify("Напомнить Анной про CRM") == EventKind.REMINDER
    assert classify("Подготовить отчёт") == EventKind.TASK


def test_load_demo_csv():
    events = load_demo_events(1, MSK, NOW)
    assert len(events) == 1000
    kinds = Counter(e.kind for e in events)
    assert kinds[EventKind.MEETING] > 100 and kinds[EventKind.REMINDER] > 50
    past_tasks = [e for e in events if e.starts_at < NOW and e.kind != EventKind.MEETING]
    assert all(e.status == EventStatus.DONE for e in past_tasks)
    assert all(e.status == EventStatus.OPEN for e in events if e.starts_at >= NOW)
