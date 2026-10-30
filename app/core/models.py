from dataclasses import dataclass
from datetime import datetime, time
from enum import StrEnum


class EventKind(StrEnum):
    TASK = "task"
    REMINDER = "reminder"
    MEETING = "meeting"


class EventStatus(StrEnum):
    OPEN = "open"
    DONE = "done"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class Event:
    """Задача, напоминание или встреча. Все datetime — timezone-aware."""

    user_id: int
    kind: EventKind
    title: str
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    all_day: bool = False
    status: EventStatus = EventStatus.OPEN
    id: int | None = None
    created_at: datetime | None = None
    notified_at: datetime | None = None
    recurrence: str | None = None  # см. app/core/recurrence.py: daily | weekdays | weekly:0,2 | monthly


@dataclass(slots=True)
class UserSettings:
    id: int
    timezone: str
    voice_replies: bool = True
    digest_time: time | None = None  # утренняя сводка; None — выключена
    ics_token: str | None = None
