"""Фоновая отправка напоминаний и предупреждений о встречах."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.models import Event, EventKind
from app.storage.repository import EventRepository

log = logging.getLogger(__name__)

POLL_SECONDS = 30
MEETING_LEAD = timedelta(minutes=15)
MAX_AGE = timedelta(hours=6)


def notification_text(e: Event, now: datetime) -> str:
    if e.kind == EventKind.MEETING:
        minutes = max(0, round((e.starts_at - now).total_seconds() / 60))
        return f"⏰ Через {minutes} мин встреча: {e.title}" if minutes else f"⏰ Начинается встреча: {e.title}"
    return f"⏰ Напоминаю: {e.title}"


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
        for event in await repo.due_notifications(now, MEETING_LEAD, MAX_AGE):
            try:
                await bot.send_message(event.user_id, notification_text(event, now))
            except Exception:
                # Пользователь заблокировал бота и т.п. — помечаем, чтобы не повторять бесконечно
                log.warning("failed to notify user %s about event %s", event.user_id, event.id)
            await repo.mark_notified(event.id, now)
