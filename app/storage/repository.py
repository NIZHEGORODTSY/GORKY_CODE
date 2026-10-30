import re
from datetime import datetime, timedelta

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Event, EventKind, EventStatus
from app.storage.tables import EventRow, UserRow


class UserRepository:
    def __init__(self, session: AsyncSession):
        self._s = session

    async def ensure(self, user_id: int, default_timezone: str) -> str:
        """Создаёт пользователя при первом обращении, возвращает его таймзону."""
        await self._s.execute(
            insert(UserRow)
            .values(id=user_id, timezone=default_timezone)
            .on_conflict_do_nothing(index_elements=[UserRow.id])
        )
        return await self._s.scalar(select(UserRow.timezone).where(UserRow.id == user_id))


class EventRepository:
    def __init__(self, session: AsyncSession):
        self._s = session

    async def add(self, event: Event) -> Event:
        row = EventRow(
            user_id=event.user_id,
            kind=event.kind.value,
            title=event.title,
            starts_at=event.starts_at,
            ends_at=event.ends_at,
            all_day=event.all_day,
            status=event.status.value,
        )
        self._s.add(row)
        await self._s.flush()
        await self._s.refresh(row)
        return row.to_domain()

    async def get(self, user_id: int, event_id: int) -> Event | None:
        row = await self._s.scalar(
            select(EventRow).where(EventRow.user_id == user_id, EventRow.id == event_id)
        )
        return row.to_domain() if row else None

    async def list_between(
        self,
        user_id: int,
        start: datetime,
        end: datetime,
        kinds: set[EventKind] | None = None,
        include_closed: bool = False,
    ) -> list[Event]:
        """События с starts_at в полуинтервале [start, end), по возрастанию времени."""
        q = select(EventRow).where(
            EventRow.user_id == user_id,
            EventRow.starts_at >= start,
            EventRow.starts_at < end,
        )
        if kinds:
            q = q.where(EventRow.kind.in_([k.value for k in kinds]))
        if not include_closed:
            q = q.where(EventRow.status == EventStatus.OPEN.value)
        rows = await self._s.scalars(q.order_by(EventRow.starts_at))
        return [r.to_domain() for r in rows]

    async def search_text(
        self,
        user_id: int,
        query: str,
        kinds: set[EventKind] | None = None,
        limit: int = 5,
    ) -> list[Event]:
        """Полнотекстовый поиск по названию (русская морфология), слова через ИЛИ."""
        words = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 1]
        if not words:
            return []
        tsquery = func.to_tsquery("russian", " | ".join(f"{w}:*" for w in words))
        tsvector = func.to_tsvector("russian", EventRow.title)
        q = select(EventRow).where(EventRow.user_id == user_id, tsvector.op("@@")(tsquery))
        if kinds:
            q = q.where(EventRow.kind.in_([k.value for k in kinds]))
        q = q.order_by(func.ts_rank(tsvector, tsquery).desc(), EventRow.starts_at.desc().nulls_last())
        rows = await self._s.scalars(q.limit(limit))
        return [r.to_domain() for r in rows]

    async def list_recent(self, user_id: int, kinds: set[EventKind] | None = None, limit: int = 200) -> list[Event]:
        """Последние созданные записи — кандидаты для поиска по смыслу."""
        q = select(EventRow).where(EventRow.user_id == user_id)
        if kinds:
            q = q.where(EventRow.kind.in_([k.value for k in kinds]))
        rows = await self._s.scalars(q.order_by(EventRow.created_at.desc()).limit(limit))
        return [r.to_domain() for r in rows]

    async def due_notifications(
        self, now: datetime, meeting_lead: timedelta, max_age: timedelta
    ) -> list[Event]:
        """Напоминания, время которых наступило, и встречи, до которых осталось meeting_lead.

        Старше max_age не берём: после долгого простоя бот не должен засыпать пользователя.
        """
        is_reminder = and_(EventRow.kind == EventKind.REMINDER.value, EventRow.starts_at <= now)
        is_meeting = and_(EventRow.kind == EventKind.MEETING.value, EventRow.starts_at <= now + meeting_lead)
        rows = await self._s.scalars(
            select(EventRow)
            .where(
                EventRow.status == EventStatus.OPEN.value,
                EventRow.notified_at.is_(None),
                EventRow.starts_at > now - max_age,
                or_(is_reminder, is_meeting),
            )
            .order_by(EventRow.starts_at)
        )
        return [r.to_domain() for r in rows]

    async def mark_notified(self, event_id: int, at: datetime) -> None:
        await self._s.execute(update(EventRow).where(EventRow.id == event_id).values(notified_at=at))

    async def set_status(self, user_id: int, event_id: int, status: EventStatus) -> bool:
        row = await self._s.scalar(
            select(EventRow).where(EventRow.user_id == user_id, EventRow.id == event_id)
        )
        if row is None:
            return False
        row.status = status.value
        return True
