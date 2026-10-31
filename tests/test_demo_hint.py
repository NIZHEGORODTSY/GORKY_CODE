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


def test_list_buttons_open_card_and_card_has_actions():
    from datetime import date, datetime
    from zoneinfo import ZoneInfo

    from app.bot.keyboards import item_actions, list_actions
    from tests.fakes import meeting

    msk = ZoneInfo("Europe/Moscow")
    e = meeting(1, "Созвон с Орбитой", datetime(2026, 10, 31, 15, 30, tzinfo=msk))
    e.id = 7
    rows = list_actions([e], "d", date(2026, 10, 31), msk).inline_keyboard
    assert rows[0][0].text == "🤝 15:30 · Созвон с Орбитой"
    assert rows[0][0].callback_data == "it:7:d:2026-10-31"
    card = [b.callback_data for row in item_actions(e, "d", date(2026, 10, 31)).inline_keyboard for b in row]
    assert card == ["ls:7:d:2026-10-31", "lx:7:d:2026-10-31", "v:d:2026-10-31", "v:home"]


def test_calendar_is_inline_web_app_not_reply_keyboard():
    from datetime import date

    from app.bot.keyboards import home_actions, reply_menu

    assert all(b.web_app is None for row in reply_menu().keyboard for b in row)
    buttons = [b for row in home_actions(date(2026, 11, 1), "https://gorky.po-bvi.ru/app/").inline_keyboard for b in row]
    assert any(b.web_app and b.web_app.url == "https://gorky.po-bvi.ru/app/" for b in buttons)
    assert not any(b.web_app for row in home_actions(date(2026, 11, 1)).inline_keyboard for b in row)
