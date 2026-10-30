import re
import secrets
from dataclasses import replace
from datetime import date, datetime, timedelta

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Event, EventKind, EventStatus, UserSettings
from app.core.recurrence import occurrences
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

    async def get(self, user_id: int) -> UserSettings | None:
        row = await self._s.get(UserRow, user_id)
        return _settings(row) if row else None

    async def update(self, user_id: int, **values) -> None:
        await self._s.execute(update(UserRow).where(UserRow.id == user_id).values(**values))

    async def ics_token(self, user_id: int) -> str:
        """Секретный токен ссылки на календарь; создаётся при первом запросе."""
        row = await self._s.get(UserRow, user_id)
        if row.ics_token is None:
            row.ics_token = secrets.token_urlsafe(24)
        return row.ics_token

    async def by_ics_token(self, token: str) -> UserSettings | None:
        row = await self._s.scalar(select(UserRow).where(UserRow.ics_token == token))
        return _settings(row) if row else None

    async def digest_candidates(self) -> list[tuple[UserSettings, date | None]]:
        """Пользователи с включённой сводкой и дата последней отправки."""
        rows = await self._s.scalars(select(UserRow).where(UserRow.digest_time.is_not(None)))
        return [(_settings(r), r.last_digest_on) for r in rows]


def _settings(row: UserRow) -> UserSettings:
    return UserSettings(
        id=row.id,
        timezone=row.timezone,
        voice_replies=row.voice_replies,
        digest_time=row.digest_time,
        ics_token=row.ics_token,
        meeting_lead_minutes=row.meeting_lead_minutes,
    )


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
            recurrence=event.recurrence,
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
        """События с starts_at в полуинтервале [start, end), по возрастанию времени.

        Повторяющиеся записи разворачиваются в отдельные вхождения (тот же id, своё время).
        """
        in_range = and_(EventRow.starts_at >= start, EventRow.starts_at < end)
        recurring = and_(EventRow.recurrence.is_not(None), EventRow.starts_at < end)
        q = select(EventRow).where(EventRow.user_id == user_id, or_(in_range, recurring))
        if kinds:
            q = q.where(EventRow.kind.in_([k.value for k in kinds]))
        if not include_closed:
            q = q.where(EventRow.status == EventStatus.OPEN.value)
        rows = await self._s.scalars(q.order_by(EventRow.starts_at))
        return expand_recurring([r.to_domain() for r in rows], start, end)

    async def list_undated(self, user_id: int) -> list[Event]:
        """Открытые задачи без срока."""
        rows = await self._s.scalars(
            select(EventRow)
            .where(
                EventRow.user_id == user_id,
                EventRow.starts_at.is_(None),
                EventRow.status == EventStatus.OPEN.value,
            )
            .order_by(EventRow.created_at)
        )
        return [r.to_domain() for r in rows]

    async def search_text(
        self,
        user_id: int,
        query: str,
        kinds: set[EventKind] | None = None,
        limit: int = 5,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> list[Event]:
        """Полнотекстовый поиск по названию (русская морфология), слова через ИЛИ.

        Сначала самые релевантные, при равенстве — ближайшие к текущему моменту.
        before/after — только записи раньше / не раньше этого момента («когда была встреча…»).
        """
        words = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 1]
        if not words:
            return []
        tsvector = func.to_tsvector("russian", EventRow.title)
        distance = func.abs(func.extract("epoch", EventRow.starts_at - func.now()))
        # Сначала записи со всеми словами («созвон с Альфой» — только с Альфой), затем хотя бы с одним
        for operator in (" & ", " | "):
            tsquery = func.to_tsquery("russian", operator.join(f"{w}:*" for w in words))
            q = select(EventRow).where(
                EventRow.user_id == user_id, EventRow.status != EventStatus.CANCELLED.value, tsvector.op("@@")(tsquery)
            )
            if kinds:
                q = q.where(EventRow.kind.in_([k.value for k in kinds]))
            if before is not None:
                q = q.where(EventRow.starts_at < before)
            if after is not None:
                q = q.where(EventRow.starts_at >= after)
            q = q.order_by(func.ts_rank(tsvector, tsquery).desc(), distance.asc().nulls_last())
            rows = list(await self._s.scalars(q.limit(limit)))
            if rows:
                return [r.to_domain() for r in rows]
        return []

    async def list_recent(self, user_id: int, kinds: set[EventKind] | None = None, limit: int = 200) -> list[Event]:
        """Последние созданные записи — кандидаты для поиска по смыслу."""
        q = select(EventRow).where(EventRow.user_id == user_id, EventRow.status != EventStatus.CANCELLED.value)
        if kinds:
            q = q.where(EventRow.kind.in_([k.value for k in kinds]))
        rows = await self._s.scalars(q.order_by(EventRow.created_at.desc()).limit(limit))
        return [r.to_domain() for r in rows]

    async def due_notifications(self, now: datetime, max_age: timedelta) -> list[Event]:
        """Напоминания, время которых наступило, и встречи, до которых осталось столько минут,
        сколько выбрал пользователь (users.meeting_lead_minutes).

        Старше max_age не берём: после долгого простоя бот не должен засыпать пользователя.
        """
        lead = func.make_interval(0, 0, 0, 0, 0, UserRow.meeting_lead_minutes)
        is_reminder = and_(EventRow.kind == EventKind.REMINDER.value, EventRow.starts_at <= now)
        is_meeting = and_(EventRow.kind == EventKind.MEETING.value, EventRow.starts_at <= now + lead)
        rows = await self._s.scalars(
            select(EventRow)
            .join(UserRow, UserRow.id == EventRow.user_id)
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

    async def reschedule(
        self, user_id: int, event_id: int, starts_at: datetime | None, ends_at: datetime | None, all_day: bool
    ) -> None:
        await self._s.execute(
            update(EventRow)
            .where(EventRow.user_id == user_id, EventRow.id == event_id)
            # Новое время — напоминание нужно отправить заново
            .values(starts_at=starts_at, ends_at=ends_at, all_day=all_day, notified_at=None)
        )

    async def overlapping_meetings(
        self, user_id: int, start: datetime, end: datetime, exclude_id: int | None = None
    ) -> list[Event]:
        q = select(EventRow).where(
            EventRow.user_id == user_id,
            EventRow.kind == EventKind.MEETING.value,
            EventRow.status == EventStatus.OPEN.value,
            EventRow.starts_at < end,
            EventRow.ends_at > start,
        )
        if exclude_id is not None:
            q = q.where(EventRow.id != exclude_id)
        rows = await self._s.scalars(q.order_by(EventRow.starts_at))
        return [r.to_domain() for r in rows]

    async def update(self, user_id: int, event_id: int, **values) -> None:
        """Точечное изменение полей записи (название, время, правило повтора...)."""
        await self._s.execute(
            update(EventRow).where(EventRow.user_id == user_id, EventRow.id == event_id).values(**values)
        )

    async def list_all(self, user_id: int, since: datetime) -> list[Event]:
        """Открытые и выполненные записи начиная с since (повторяющиеся — целиком) — для экспорта."""
        rows = await self._s.scalars(
            select(EventRow)
            .where(
                EventRow.user_id == user_id,
                EventRow.status != EventStatus.CANCELLED.value,
                EventRow.starts_at.is_not(None),
                or_(EventRow.starts_at >= since, EventRow.recurrence.is_not(None)),
            )
            .order_by(EventRow.starts_at)
        )
        return [r.to_domain() for r in rows]


    async def recurring_passed(self, now: datetime) -> list[Event]:
        """Открытые повторяющиеся записи, текущее повторение которых уже наступило."""
        rows = await self._s.scalars(
            select(EventRow).where(
                EventRow.recurrence.is_not(None),
                EventRow.status == EventStatus.OPEN.value,
                EventRow.starts_at <= now,
            )
        )
        return [r.to_domain() for r in rows]

    async def list_overdue(self, user_id: int, before: datetime) -> list[Event]:
        """Открытые разовые задачи и напоминания со сроком раньше before."""
        rows = await self._s.scalars(
            select(EventRow)
            .where(
                EventRow.user_id == user_id,
                EventRow.status == EventStatus.OPEN.value,
                EventRow.recurrence.is_(None),
                EventRow.kind != EventKind.MEETING.value,
                EventRow.starts_at < before,
            )
            .order_by(EventRow.starts_at)
        )
        return [r.to_domain() for r in rows]

    async def import_events(self, events: list[Event], source: str, notified_at: datetime) -> int:
        """Массовая загрузка (демо-данные). notified_at проставлен — бот не шлёт по ним напоминаний."""
        rows = [
            EventRow(
                user_id=e.user_id, kind=e.kind.value, title=e.title, starts_at=e.starts_at, ends_at=e.ends_at,
                all_day=e.all_day, status=e.status.value, recurrence=e.recurrence, source=source,
                notified_at=notified_at,
            )
            for e in events
        ]
        self._s.add_all(rows)
        await self._s.flush()
        return len(rows)

    async def count_source(self, user_id: int, source: str) -> int:
        return await self._s.scalar(
            select(func.count()).select_from(EventRow).where(EventRow.user_id == user_id, EventRow.source == source)
        )

    async def delete_source(self, user_id: int, source: str) -> int:
        result = await self._s.execute(
            delete(EventRow).where(EventRow.user_id == user_id, EventRow.source == source)
        )
        return result.rowcount

def expand_recurring(events: list[Event], start: datetime, end: datetime) -> list[Event]:
    """Повторяющиеся записи -> вхождения в [start, end) в поясе start; остальные как есть."""
    result = []
    for e in events:
        if not e.recurrence or e.starts_at is None:
            result.append(e)
            continue
        current = e.starts_at.astimezone(start.tzinfo)
        duration = (e.ends_at - e.starts_at) if e.ends_at else None
        for at in occurrences(current, e.recurrence, start, end):
            result.append(replace(e, starts_at=at, ends_at=at + duration if duration else None))
    return sorted(result, key=lambda e: e.starts_at)
