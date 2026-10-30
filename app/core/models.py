from dataclasses import dataclass
from datetime import datetime
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
