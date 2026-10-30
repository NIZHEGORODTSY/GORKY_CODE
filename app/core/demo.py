"""Демо-данные из тестового задания: assets/voice_assistant_events_1000.csv (id, date, time, text).

Тип записи в файле не указан — определяем по первому слову. Даты оставляем как в файле
(2024–2027): часть записей в прошлом, часть впереди. Прошедшие задачи и напоминания
считаем выполненными, чтобы не было тысячи «просроченных».
"""

import csv
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.core.models import Event, EventKind, EventStatus

DEMO_CSV = Path(__file__).resolve().parents[2] / "assets" / "voice_assistant_events_1000.csv"
DEMO_SOURCE = "demo"
MEETING_MINUTES = 60

MEETING_WORDS = {"встреча", "созвон", "демо", "обсудить", "провести"}
REMINDER_WORDS = {"напомнить", "позвонить"}


def classify(text: str) -> EventKind:
    first = text.split(maxsplit=1)[0].lower() if text.strip() else ""
    if first in MEETING_WORDS:
        return EventKind.MEETING
    if first in REMINDER_WORDS:
        return EventKind.REMINDER
    return EventKind.TASK


def load_demo_events(user_id: int, tz: ZoneInfo, now: datetime, path: Path = DEMO_CSV) -> list[Event]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    events = []
    for row in rows:
        title = row["text"].strip()
        if not title:
            continue
        kind = classify(title)
        starts_at = datetime.combine(date.fromisoformat(row["date"]), time.fromisoformat(row["time"]), tzinfo=tz)
        past = starts_at < now
        events.append(Event(
            user_id=user_id,
            kind=kind,
            title=title,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=MEETING_MINUTES) if kind == EventKind.MEETING else None,
            status=EventStatus.DONE if past and kind != EventKind.MEETING else EventStatus.OPEN,
        ))
    return events
