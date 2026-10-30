from dataclasses import replace
from datetime import datetime, timedelta, timezone

from app.core.models import Event, EventKind, EventStatus


class FakeEventRepository:
    """In-memory замена EventRepository для тестов бизнес-логики."""

    def __init__(self):
        self.events: list[Event] = []

    async def add(self, event: Event) -> Event:
        stored = replace(event, id=len(self.events) + 1, created_at=datetime.now(timezone.utc))
        self.events.append(stored)
        return stored

    async def list_between(self, user_id, start, end, kinds=None, include_closed=False):
        found = [
            e for e in self.events
            if e.user_id == user_id
            and e.starts_at is not None
            and start <= e.starts_at < end
            and (not kinds or e.kind in kinds)
            and (include_closed or e.status == EventStatus.OPEN)
        ]
        return sorted(found, key=lambda e: e.starts_at)

    async def get(self, user_id, event_id):
        return next((e for e in self.events if e.user_id == user_id and e.id == event_id), None)

    def _replace(self, event_id, **changes):
        self.events = [replace(e, **changes) if e.id == event_id else e for e in self.events]

    async def set_status(self, user_id, event_id, status):
        self._replace(event_id, status=status)
        return True

    async def reschedule(self, user_id, event_id, starts_at, ends_at, all_day):
        self._replace(event_id, starts_at=starts_at, ends_at=ends_at, all_day=all_day, notified_at=None)

    async def overlapping_meetings(self, user_id, start, end, exclude_id=None):
        return [
            e for e in self.events
            if e.user_id == user_id and e.kind == EventKind.MEETING and e.status == EventStatus.OPEN
            and e.id != exclude_id and e.starts_at < end and e.ends_at > start
        ]

    async def list_recent(self, user_id, kinds=None, limit=200):
        return [e for e in reversed(self.events) if e.user_id == user_id and (not kinds or e.kind in kinds)][:limit]

    async def search_text(self, user_id, query, kinds=None, limit=5):
        words = [w[:5] for w in query.lower().split()]
        return [
            e for e in self.events
            if e.user_id == user_id
            and any(w in e.title.lower() for w in words)
            and (not kinds or e.kind in kinds)
        ][:limit]


def meeting(user_id: int, title: str, starts_at: datetime) -> Event:
    return Event(
        user_id=user_id, kind=EventKind.MEETING, title=title,
        starts_at=starts_at, ends_at=starts_at + timedelta(hours=1),
    )
