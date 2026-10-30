from app.assistant.actions import ActionResult
from app.bot.handlers import _with_demo_hint


class FakeAssistant:
    def __init__(self, demo):
        self.demo = demo

    async def demo_count(self, user_id):
        return self.demo


async def test_hint_when_nothing_found_and_no_demo():
    text, markup = await _with_demo_hint(FakeAssistant(0), 1, ActionResult("🤷 Не нашёл записей про «Иван»."))
    assert "ещё не загружены" in text
    assert markup.inline_keyboard[0][0].callback_data == "demo:load"


async def test_no_hint_when_demo_loaded():
    text, markup = await _with_demo_hint(FakeAssistant(1000), 1, ActionResult("🤷 Не нашёл записей про «Иван»."))
    assert "ещё не загружены" not in text
    assert markup.inline_keyboard[-1][0].callback_data == "m:open"
