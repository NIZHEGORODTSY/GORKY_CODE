from aiohttp.test_utils import TestClient, TestServer

from app.assistant.actions import ActionResult
from app.webapp.dev import sign_init_data
from app.webapp.server import create_app

TOKEN = "123456:TEST-TOKEN"


class FakeAssistant:
    def __init__(self):
        self.calls = []

    async def run_action(self, user_id, call):
        self.calls.append((user_id, call.name, call.arguments))
        return ActionResult("✅ <b>Выполнено:</b> «Купить билеты»")


async def make_client(assistant):
    client = TestClient(TestServer(create_app(TOKEN, assistant, session_factory=None, default_tz="Europe/Moscow")))
    await client.start_server()
    return client


async def test_api_rejects_unsigned_requests():
    client = await make_client(FakeAssistant())
    try:
        assert (await client.post("/api/events/1/done")).status == 401
        bad = sign_init_data("999:OTHER", 42)
        assert (await client.post("/api/events/1/done", headers={"Authorization": f"tma {bad}"})).status == 401
    finally:
        await client.close()


async def test_action_runs_for_signed_user():
    assistant = FakeAssistant()
    client = await make_client(assistant)
    try:
        resp = await client.post("/api/events/7/done", headers={"Authorization": f"tma {sign_init_data(TOKEN, 42)}"})
        assert resp.status == 200
        assert (await resp.json())["message"] == "✅ Выполнено: «Купить билеты»"
        assert assistant.calls == [(42, "complete_event", {"event_id": 7})]
    finally:
        await client.close()


async def test_index_is_public():
    client = await make_client(FakeAssistant())
    try:
        resp = await client.get("/app/")
        assert resp.status == 200 and "telegram-web-app.js" in await resp.text()
    finally:
        await client.close()
