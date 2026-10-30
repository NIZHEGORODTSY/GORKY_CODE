"""Telegram Mini App: календарь записей. Отдаёт страницу и JSON API.

Пользователь определяется по initData, подписанным Telegram (заголовок `Authorization: tma <initData>`),
поэтому чужие записи получить нельзя. Изменения идут через Assistant.run_action — та же логика, что у бота.
"""

import logging
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from aiogram.utils.web_app import safe_parse_webapp_init_data
from aiohttp import web
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.assistant.service import Assistant
from app.core.formatting import plain
from app.core.models import Event
from app.core.recurrence import describe
from app.llm.base import ToolCall
from app.storage.repository import EventRepository, UserRepository

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
MAX_RANGE_DAYS = 62
ACTIONS = {"done": "complete_event", "delete": "delete_event"}

USER_ID = web.RequestKey("user_id", int)
CTX = web.AppKey("ctx", dict)


def create_app(bot_token: str, assistant: Assistant, session_factory: async_sessionmaker, default_tz: str) -> web.Application:
    app = web.Application(middlewares=[_auth(bot_token)])
    app[CTX] = {"assistant": assistant, "sessions": session_factory, "default_tz": default_tz}
    app.router.add_get("/", _root)
    app.router.add_get("/app/", _index)
    app.router.add_get("/health", _health)
    app.router.add_get("/api/events", _list_events)
    app.router.add_post("/api/events/{event_id:\\d+}/{action}", _event_action)
    app.router.add_get("/ics/{token}.ics", _ics_feed)
    return app


def _auth(bot_token: str):
    @web.middleware
    async def middleware(request: web.Request, handler):
        if not request.path.startswith("/api/"):
            return await handler(request)
        scheme, _, init_data = request.headers.get("Authorization", "").partition(" ")
        try:
            if scheme != "tma":
                raise ValueError("no tma auth")
            data = safe_parse_webapp_init_data(bot_token, init_data)
        except ValueError:
            raise web.HTTPUnauthorized(text="invalid init data")
        if data.user is None:
            raise web.HTTPUnauthorized(text="no user")
        request[USER_ID] = data.user.id
        return await handler(request)

    return middleware


async def _root(_: web.Request) -> web.Response:
    raise web.HTTPFound("/app/")


async def _health(_: web.Request) -> web.Response:
    return web.json_response({"ok": True})


async def _index(_: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


async def _list_events(request: web.Request) -> web.Response:
    ctx = request.app[CTX]
    user_id = request[USER_ID]
    try:
        start = date.fromisoformat(request.query["from"])
        end = date.fromisoformat(request.query["to"])
    except (KeyError, ValueError):
        raise web.HTTPBadRequest(text="from/to required, YYYY-MM-DD")
    if not 0 <= (end - start).days <= MAX_RANGE_DAYS:
        raise web.HTTPBadRequest(text="bad range")

    async with ctx["sessions"]() as session, session.begin():
        tz = ZoneInfo(await UserRepository(session).ensure(user_id, ctx["default_tz"]))
        repo = EventRepository(session)
        events = await repo.list_between(
            user_id,
            datetime.combine(start, time.min, tzinfo=tz),
            datetime.combine(end + timedelta(days=1), time.min, tzinfo=tz),
            include_closed=True,
        )
        undated = await repo.list_undated(user_id)
    return web.json_response({
        "timezone": str(tz),
        "today": datetime.now(tz).date().isoformat(),
        "events": [_to_json(e, tz) for e in events if e.status.value != "cancelled"],
        "undated": [_to_json(e, tz) for e in undated],
    })


async def _event_action(request: web.Request) -> web.Response:
    action = ACTIONS.get(request.match_info["action"])
    if action is None:
        raise web.HTTPNotFound()
    event_id = int(request.match_info["event_id"])
    result = await request.app[CTX]["assistant"].run_action(request[USER_ID], ToolCall(action, {"event_id": event_id}))
    return web.json_response({"message": plain(result.text)})


async def _ics_feed(request: web.Request) -> web.Response:
    """Подписка на календарь: токен в ссылке секретный, знает только владелец."""
    ctx = request.app[CTX]
    async with ctx["sessions"]() as session, session.begin():
        user = await UserRepository(session).by_ics_token(request.match_info["token"])
    if user is None:
        raise web.HTTPNotFound()
    ics, _ = await ctx["assistant"].export_ics(user.id)
    return web.Response(
        text=ics,
        content_type="text/calendar",
        charset="utf-8",
        headers={"Content-Disposition": 'inline; filename="gorky.ics"', "Cache-Control": "no-cache"},
    )


def _to_json(e: Event, tz: ZoneInfo) -> dict:
    local = e.starts_at.astimezone(tz) if e.starts_at else None
    return {
        "id": e.id,
        "kind": e.kind.value,
        "title": e.title,
        "date": local.date().isoformat() if local else None,
        "time": None if local is None or e.all_day else f"{local:%H:%M}",
        "end_time": f"{e.ends_at.astimezone(tz):%H:%M}" if e.ends_at else None,
        "status": e.status.value,
        "repeat": describe(e.recurrence) if e.recurrence else None,
    }


async def start_webapp(app: web.Application, host: str, port: int) -> web.AppRunner:
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    log.info("webapp listening on %s:%s", host, port)
    return runner
