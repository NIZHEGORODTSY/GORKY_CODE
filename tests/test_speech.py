from app.speech.text import for_speech


def test_for_speech_flattens_list():
    text = "Сегодня, 30 октября:\n• 10:00 — Созвон (встреча)\n• 15:00 — Отчёт (задача)"
    assert for_speech(text) == "Сегодня, 30 октября. 10:00 — Созвон (встреча). 15:00 — Отчёт (задача)."


def test_meeting_notification_text():
    from datetime import datetime, timedelta, timezone

    from app.bot.notifier import notification_text
    from tests.fakes import meeting

    now = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
    assert notification_text(meeting(1, "Созвон", now + timedelta(minutes=15)), now) == "🤝 <b>Через 15 мин встреча</b>\nСозвон"


def test_for_speech_strips_html_and_emoji():
    assert for_speech("⏰ <b>Напомню завтра</b>\nПозвонить &amp; написать") == "Напомню завтра. Позвонить & написать."
