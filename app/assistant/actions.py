"""Выполнение функций, выбранных LLM: валидация аргументов, работа с хранилищем, ответ."""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

from app.core.dates import Period, day_start, parse_date, parse_time, period_bounds, resolve_day
from app.core.formatting import fmt_created, fmt_day, fmt_found, fmt_list
from app.core.models import Event, EventKind
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
    """Данных не хватает — текст исключения задаётся пользователю как вопрос."""


@dataclass(slots=True)
class ActionResult:
    text: str
    event_ids: list[int] = field(default_factory=list)


class Actions:
    def __init__(self, repo, user_id: int, now: datetime, matcher=None):
        """`now` — aware datetime в часовом поясе пользователя; `matcher` — поиск по смыслу."""
        self._repo = repo
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
        }
        handler = handlers.get(call.name)
        if handler is None:
            return ActionResult("Не понял, что нужно сделать. Попробуй сформулировать иначе.")
        try:
            return await handler(call.arguments)
        except Clarification as c:
            return ActionResult(str(c))

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
            raise Clarification(f"На какой день поставить встречу «{title}»?")
        if kind == EventKind.MEETING and t is None:
            raise Clarification(f"На какое время поставить встречу «{title}» ({fmt_day(d, self._today)})?")
        if kind == EventKind.REMINDER and t is None:
            raise Clarification(f"Во сколько напомнить: {title}?")

        if t is not None and d is None:
            # «Напомни в 18:00» — ближайшее такое время
            d = self._today if datetime.combine(self._today, t, self._tz) > self._now else self._today + timedelta(days=1)

        if t is not None:
            starts_at = datetime.combine(d, t, tzinfo=self._tz)
            if starts_at < self._now - timedelta(minutes=1):
                raise Clarification(
                    f"{fmt_day(d, self._today).capitalize()} в {t:%H:%M} уже прошло. На когда поставить?"
                )
        else:
            starts_at = day_start(d, self._tz) if d else None

        ends_at = None
        if kind == EventKind.MEETING:
            minutes = int(args.get("duration_minutes") or DEFAULT_MEETING_MINUTES)
            ends_at = starts_at + timedelta(minutes=minutes)

        event = await self._repo.add(
            Event(
                user_id=self._user_id,
                kind=kind,
                title=title,
                starts_at=starts_at,
                ends_at=ends_at,
                all_day=d is not None and t is None,
            )
        )
        return ActionResult(fmt_created(event, self._tz, self._today), [event.id])

    def _resolve_when(self, args: dict[str, Any]) -> tuple[date | None, time | None]:
        minutes = args.get("in_minutes")
        if minutes:
            at = (self._now + timedelta(minutes=int(minutes))).replace(second=0, microsecond=0)
            return at.date(), at.time()
        d = _opt(parse_date, args.get("date"))
        if d is None and args.get("day"):
            d = _opt(lambda v: resolve_day(v, self._today), args["day"])
        return d, _opt(parse_time, args.get("time"))

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
        what = {"meeting": "встреч", "task": "задач"}.get(args.get("kind"), "ничего")
        if period in PERIOD_LABEL:
            empty = f"На {PERIOD_LABEL[period]} {what} нет." if what != "ничего" else f"На {PERIOD_LABEL[period]} ничего не запланировано."
        else:
            empty = "За этот период ничего не запланировано."
        return ActionResult(fmt_list(events, self._tz, self._today, empty), [e.id for e in events])

    async def _search(self, args: dict[str, Any]) -> ActionResult:
        query = (args.get("query") or "").strip()
        if not query:
            raise Clarification("Что поискать?")
        kinds = KIND_FILTER.get(args.get("kind"))
        events = await self._repo.search_text(self._user_id, query, kinds=kinds)
        if not events and self._matcher is not None:
            candidates = await self._repo.list_recent(self._user_id, kinds=kinds)
            events = await self._matcher.match(query, candidates)
        if not events:
            return ActionResult(f"Не нашёл записей про «{query}».")
        return ActionResult(fmt_found(events, self._tz, self._today), [e.id for e in events])


def _opt(parser, value):
    if not value:
        return None
    try:
        return parser(str(value))
    except ValueError:
        return None
