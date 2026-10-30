"""Фоновая отправка напоминаний и предупреждений о встречах."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo

from aiogram import Bot
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bot.keyboards import reminder_actions
from app.core.dates import day_start
from app.core.formatting import KIND_ICON, fmt_day, fmt_list
from app.core.models import Event, EventKind
from app.core.recurrence import next_after
from app.storage.repository import EventRepository, UserRepository

log = logging.getLogger(__name__)

POLL_SECONDS = 30
MAX_AGE = timedelta(hours=6)
DIGEST_WINDOW = timedelta(hours=3)  # после простоя бота не шлём сводку поздно вечером


def notification_text(e: Event, now: datetime) -> str:
    if e.kind == EventKind.MEETING:
        minutes = max(0, round((e.starts_at - now).total_seconds() / 60))
        head = f"Через {minutes} мин встреча" if minutes else "Начинается встреча"
        return f"🤝 <b>{head}</b>\n{escape(e.title)}"
    return f"⏰ <b>Напоминаю</b>\n{escape(e.title)}"


async def run_notifier(bot: Bot, session_factory: async_sessionmaker) -> None:
    while True:
        try:
            await _tick(bot, session_factory)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("notifier tick failed")
        await asyncio.sleep(POLL_SECONDS)


async def _tick(bot: Bot, session_factory: async_sessionmaker) -> None:
    now = datetime.now(timezone.utc)
    async with session_factory() as session, session.begin():
        repo = EventRepository(session)
        for event in await repo.due_notifications(now, MAX_AGE):
            try:
                markup = reminder_actions(event.id) if event.kind == EventKind.REMINDER else None
                await bot.send_message(event.user_id, notification_text(event, now), reply_markup=markup)
            except Exception:
                # Пользователь заблокировал бота и т.п. — помечаем, чтобы не повторять бесконечно
                log.warning("failed to notify user %s about event %s", event.user_id, event.id)
            await repo.mark_notified(event.id, now)
        await _roll_recurring(repo, UserRepository(session), now)
    async with session_factory() as session, session.begin():
        await _send_digests(bot, EventRepository(session), UserRepository(session), now)


async def _roll_recurring(repo: EventRepository, users: UserRepository, now: datetime) -> None:
    """Прошедшее повторение -> следующее (напоминание по нему придёт заново)."""
    for e in await repo.recurring_passed(now):
        finished = e.starts_at + timedelta(days=1) if e.all_day else (e.ends_at or e.starts_at)
        if finished > now:
            continue
        settings = await users.get(e.user_id)
        current = e.starts_at.astimezone(ZoneInfo(settings.timezone))
        nxt = next_after(current, e.recurrence, now)
        ends = nxt + (e.ends_at - e.starts_at) if e.ends_at else None
        await repo.reschedule(e.user_id, e.id, nxt, ends, e.all_day)


async def _send_digests(bot: Bot, repo: EventRepository, users: UserRepository, now: datetime) -> None:
    for settings, last_sent in await users.digest_candidates():
        tz = ZoneInfo(settings.timezone)
        local = now.astimezone(tz)
        due = datetime.combine(local.date(), settings.digest_time, tzinfo=tz)
        if last_sent == local.date() or not (due <= local < due + DIGEST_WINDOW):
            continue
        try:
            await bot.send_message(settings.id, await digest_text(repo, settings.id, local))
        except Exception:
            log.warning("failed to send digest to %s", settings.id)
        await users.update(settings.id, last_digest_on=local.date())


async def digest_text(repo: EventRepository, user_id: int, local_now: datetime) -> str:
    tz = local_now.tzinfo
    today = local_now.date()
    start = day_start(today, tz)
    events = await repo.list_between(user_id, start, start + timedelta(days=1))
    parts = [f"☀️ <b>Доброе утро! {fmt_day(today, today).capitalize()}</b>", ""]
    parts.append(fmt_list(events, tz, today, "Сегодня ничего не запланировано — свободный день."))
    overdue = await repo.list_overdue(user_id, start)
    if overdue:
        parts += ["", "⚠️ <b>Не выполнено раньше</b>"]
        parts += [f"{KIND_ICON[e.kind]} {escape(e.title)} — {fmt_day(e.starts_at.astimezone(tz).date(), today)}" for e in overdue[:10]]
    return "\n".join(parts)
