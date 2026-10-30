"""Выполнение функций, выбранных LLM: валидация аргументов, работа с хранилищем, ответ."""

import re
from html import escape
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from typing import Any

from app.core.dates import Period, day_start, parse_date, parse_time, period_bounds, resolve_day
from app.core.formatting import KIND_LABEL, fmt_created, fmt_day, fmt_found, fmt_list, fmt_when, q
from app.core.models import Event, EventKind, EventStatus
from app.llm.base import ToolCall

KIND_FILTER = {
    "meeting": {EventKind.MEETING},
    "task": {EventKind.TASK, EventKind.REMINDER},
}
PERIOD_LABEL = {
    Period.TODAY: "сегодня",
    Period.TOMORROW: "завтра",
    Period.DAY_AFTER_TOMORROW: "послезавтра",
    Period.THIS_WEEK: "этой неделе",
    Period.NEXT_WEEK: "следующей неделе",
}
DEFAULT_MEETING_MINUTES = 60


class Clarification(Exception):
    """Данных не хватает — текст задаётся пользователю как вопрос.

    `events` — варианты, о которых спрашиваем: попадут в контекст, чтобы
    ответ «первую» или «ту, что в четверг» можно было сопоставить с записью.
    """

    def __init__(self, question: str, events: list[Event] | None = None):
        super().__init__(question)
        self.events = events or []


@dataclass(slots=True)
class ActionResult:
    text: str
    events: list[Event] = field(default_factory=list)  # о чём шла речь — контекст следующего шага


class Actions:
    def __init__(self, repo, user_id: int, now: datetime, matcher=None, recent: list[Event] | None = None):
        """`now` — aware datetime в часовом поясе пользователя; `matcher` — поиск по смыслу;
        `recent` — записи из последнего ответа (контекст диалога)."""
        self._repo = repo
        self._recent = recent or []
        self._matcher = matcher
        self._user_id = user_id
        self._now = now
        self._tz = now.tzinfo
        self._today = now.date()

    async def run(self, call: ToolCall) -> ActionResult:
        handlers = {
            "create_event": self._create,
            "list_events": self._list,
            "search_events": self._search,
            "update_event": self._update,
            "complete_event": self._complete,
            "delete_event": self._delete,
        }
        handler = handlers.get(call.name)
        if handler is None:
            return ActionResult("Не понял, что нужно сделать. Попробуй сформулировать иначе.")
        try:
            return await handler(call.arguments)
        except Clarification as c:
            return ActionResult(str(c), c.events)

    def remember(self, events: list[Event]) -> None:
        """Обновить контекст: следующий вызов может ссылаться на эти записи."""
        self._recent = events

    # --- создание ---------------------------------------------------------

    async def _create(self, args: dict[str, Any]) -> ActionResult:
        try:
            kind = EventKind(args.get("kind", "task"))
        except ValueError:
            kind = EventKind.TASK
        title = (args.get("title") or "").strip()
        if not title:
            raise Clarification("Что именно записать?")
        d, t = self._resolve_when(args)

        if kind == EventKind.MEETING and d is None:
            raise Clarification(f"📅 На какой день поставить встречу {q(title)}?")
        if kind == EventKind.MEETING and t is None:
            raise Clarification(f"🕒 На какое время поставить встречу {q(title)} ({fmt_day(d, self._today)})?")
        if kind == EventKind.REMINDER and t is None:
            raise Clarification(f"🕒 Во сколько напомнить: {escape(title)}?")

        starts_at, all_day = self._schedule(d, t)
        ends_at = None
        if kind == EventKind.MEETING:
            minutes = int(args.get("duration_minutes") or DEFAULT_MEETING_MINUTES)
            ends_at = starts_at + timedelta(minutes=minutes)

        conflicts = await self._conflicts(kind, starts_at, ends_at)
        event = await self._repo.add(
            Event(
                user_id=self._user_id,
                kind=kind,
                title=title,
                starts_at=starts_at,
                ends_at=ends_at,
                all_day=all_day,
            )
        )
        return ActionResult(fmt_created(event, self._tz, self._today) + conflicts, [event])

    # --- просмотр и поиск -------------------------------------------------

    async def _list(self, args: dict[str, Any]) -> ActionResult:
        try:
            period = Period(args.get("period", "today"))
        except ValueError:
            period = Period.TODAY
        date_from = _opt(parse_date, args.get("date_from"))
        date_to = _opt(parse_date, args.get("date_to"))
        if period == Period.CUSTOM and date_from is None:
            raise Clarification("За какой период показать?")
        start, end = period_bounds(period, self._now, date_from, date_to)

        events = await self._repo.list_between(
            self._user_id, start, end, kinds=KIND_FILTER.get(args.get("kind"))
        )
        what = {"meeting": "встреч", "task": "задач"}.get(args.get("kind"))
        if period not in PERIOD_LABEL:
            empty = "За этот период ничего не запланировано."
        elif what:
            empty = f"На {PERIOD_LABEL[period]} {what} нет."
        else:
            empty = f"На {PERIOD_LABEL[period]} ничего не запланировано."
        return ActionResult(fmt_list(events, self._tz, self._today, empty), events)

    async def _search(self, args: dict[str, Any]) -> ActionResult:
        query = (args.get("query") or "").strip()
        if not query:
            raise Clarification("Что поискать?")
        events = await self._find(query, KIND_FILTER.get(args.get("kind")))
        if not events:
            return ActionResult(f"🤷 Не нашёл записей про {q(query)}.")
        return ActionResult(fmt_found(events, self._tz, self._today), events)

    # --- изменение --------------------------------------------------------

    async def _update(self, args: dict[str, Any]) -> ActionResult:
        event = await self._target(args, "перенести")
        title_label = q(event.title)
        d, t = self._resolve_when(args)
        if d is None and t is None:
            raise Clarification(f"🕒 На когда перенести {title_label}?", [event])

        old_local = event.starts_at.astimezone(self._tz) if event.starts_at else None
        if d is None:
            d = old_local.date() if old_local else None
        if t is None and old_local and not event.all_day:
            t = old_local.time()
        starts_at, all_day = self._schedule(d, t)

        ends_at = None
        if event.kind == EventKind.MEETING:
            duration = (event.ends_at - event.starts_at) if event.ends_at and event.starts_at else None
            ends_at = starts_at + (duration or timedelta(minutes=DEFAULT_MEETING_MINUTES))

        conflicts = await self._conflicts(event.kind, starts_at, ends_at, exclude_id=event.id)
        await self._repo.reschedule(self._user_id, event.id, starts_at, ends_at, all_day)
        moved = replace(event, starts_at=starts_at, ends_at=ends_at, all_day=all_day)
        return ActionResult(f"↪️ <b>Перенёс</b> {title_label} на {fmt_when(moved, self._tz, self._today)}." + conflicts, [moved])

    async def _complete(self, args: dict[str, Any]) -> ActionResult:
        event = await self._target(args, "отметить выполненной")
        await self._repo.set_status(self._user_id, event.id, EventStatus.DONE)
        return ActionResult(f"✅ <b>Выполнено:</b> {q(event.title)}", [event])

    async def _delete(self, args: dict[str, Any]) -> ActionResult:
        event = await self._target(args, "удалить")
        await self._repo.set_status(self._user_id, event.id, EventStatus.CANCELLED)
        return ActionResult(f"🗑 <b>Удалил</b> {KIND_LABEL[event.kind]} {q(event.title)}.", [event])

    # --- вспомогательное --------------------------------------------------

    async def _target(self, args: dict[str, Any], verb: str) -> Event:
        """Запись, о которой речь: по id из контекста диалога или по описанию."""
        event_id = args.get("event_id")
        if event_id:
            event = await self._repo.get(self._user_id, int(event_id))
            if event and event.status != EventStatus.CANCELLED:
                return event
        query = (args.get("query") or "").strip()
        if not query:
            if len(self._recent) == 1:
                return self._recent[0]
            raise Clarification(f"Какую запись {verb}?")
        # Модель могла описать запись из контекста словами вместо event_id
        stems = [w[:5] for w in re.findall(r"\w+", query.lower()) if len(w) > 2]
        in_context = [e for e in self._recent if any(s in e.title.lower() for s in stems)]
        if len(in_context) == 1:
            return in_context[0]
        found = [e for e in await self._find(query, None) if e.status == EventStatus.OPEN]
        if not found:
            raise Clarification(f"🤷 Не нашёл открытых записей про {q(query)}.")
        if len(found) > 1:
            options = "\n".join(f"• {escape(e.title)} — {fmt_when(e, self._tz, self._today)}" for e in found)
            raise Clarification(f"🤔 Нашёл несколько, какую {verb}?\n{options}", found)
        return found[0]

    async def _find(self, query: str, kinds) -> list[Event]:
        events = await self._repo.search_text(self._user_id, query, kinds=kinds)
        if not events and self._matcher is not None:
            candidates = await self._repo.list_recent(self._user_id, kinds=kinds)
            events = await self._matcher.match(query, candidates)
        return events

    async def _conflicts(self, kind, starts_at, ends_at, exclude_id=None) -> str:
        if kind != EventKind.MEETING:
            return ""
        overlap = await self._repo.overlapping_meetings(self._user_id, starts_at, ends_at, exclude_id)
        if not overlap:
            return ""
        names = ", ".join(f"{q(e.title)} в {e.starts_at.astimezone(self._tz):%H:%M}" for e in overlap)
        return f"\n\n⚠️ <b>Пересекается</b> с {names}."

    def _resolve_when(self, args: dict[str, Any]) -> tuple[date | None, time | None]:
        minutes = args.get("in_minutes")
        if minutes:
            at = (self._now + timedelta(minutes=int(minutes))).replace(second=0, microsecond=0)
            return at.date(), at.time()
        d = _opt(parse_date, args.get("date"))
        if d is None and args.get("day"):
            d = _opt(lambda v: resolve_day(v, self._today), args["day"])
        return d, _opt(parse_time, args.get("time"))

    def _schedule(self, d: date | None, t: time | None) -> tuple[datetime | None, bool]:
        """Дата/время -> (starts_at, all_day) с проверкой на прошедшее время."""
        if t is not None and d is None:
            # «Напомни в 18:00» — ближайшее такое время
            today_at = datetime.combine(self._today, t, tzinfo=self._tz)
            d = self._today if today_at > self._now else self._today + timedelta(days=1)
        if t is None:
            return (day_start(d, self._tz) if d else None), d is not None
        starts_at = datetime.combine(d, t, tzinfo=self._tz)
        if starts_at < self._now - timedelta(minutes=1):
            raise Clarification(f"⌛ {fmt_day(d, self._today).capitalize()} в {t:%H:%M} уже прошло. На когда поставить?")
        return starts_at, False


def _opt(parser, value):
    if not value:
        return None
    try:
        return parser(str(value))
    except ValueError:
        return None
