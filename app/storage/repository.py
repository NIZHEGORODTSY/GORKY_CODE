from datetime import datetime

from sqlalchemy import select
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
        kind: EventKind | None = None,
        include_closed: bool = False,
    ) -> list[Event]:
        """События с starts_at в полуинтервале [start, end), по возрастанию времени."""
        q = select(EventRow).where(
            EventRow.user_id == user_id,
            EventRow.starts_at >= start,
            EventRow.starts_at < end,
        )
        if kind is not None:
            q = q.where(EventRow.kind == kind.value)
        if not include_closed:
            q = q.where(EventRow.status == EventStatus.OPEN.value)
        rows = await self._s.scalars(q.order_by(EventRow.starts_at))
        return [r.to_domain() for r in rows]

    async def set_status(self, user_id: int, event_id: int, status: EventStatus) -> bool:
        row = await self._s.scalar(
            select(EventRow).where(EventRow.user_id == user_id, EventRow.id == event_id)
        )
        if row is None:
            return False
        row.status = status.value
        return True
