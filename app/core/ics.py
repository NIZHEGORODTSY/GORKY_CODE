"""Экспорт в iCalendar (RFC 5545): .ics понимают Google, Apple, Яндекс Календарь и Outlook."""

from datetime import datetime, timedelta, timezone

from app.core.formatting import KIND_LABEL
from app.core.models import Event, EventKind, EventStatus
from app.core.recurrence import to_rrule

PRODID = "-//GORKY//Voice planner//RU"
DEFAULT_DURATION = timedelta(minutes=30)
ALARM_BEFORE = {EventKind.REMINDER: "PT0M", EventKind.MEETING: "-PT15M"}


def build_calendar(events: list[Event], name: str = "Горький · планы") -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_text(name)}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT30M",
        "X-PUBLISHED-TTL:PT30M",
    ]
    stamp = _utc(datetime.now(timezone.utc))
    for e in events:
        if e.starts_at is None or e.status == EventStatus.CANCELLED:
            continue
        lines += _event(e, stamp)
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def _event(e: Event, stamp: str) -> list[str]:
    lines = ["BEGIN:VEVENT", f"UID:event-{e.id}@gorky", f"DTSTAMP:{stamp}", f"SUMMARY:{_text(e.title)}"]
    if e.all_day:
        day = e.starts_at.date()
        lines += [f"DTSTART;VALUE=DATE:{day:%Y%m%d}", f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}"]
    else:
        lines += [f"DTSTART:{_utc(e.starts_at)}", f"DTEND:{_utc(e.ends_at or e.starts_at + DEFAULT_DURATION)}"]
    lines.append(f"CATEGORIES:{_text(KIND_LABEL[e.kind])}")
    if e.recurrence:
        lines.append(f"RRULE:{to_rrule(e.recurrence)}")
    if e.status == EventStatus.DONE:
        lines.append("STATUS:CANCELLED" if e.kind == EventKind.MEETING else "DESCRIPTION:Выполнено")
    elif e.kind in ALARM_BEFORE and not e.all_day:
        lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_text(e.title)}",
                  f"TRIGGER:{ALARM_BEFORE[e.kind]}", "END:VALARM"]
    lines.append("END:VEVENT")
    return lines


def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _text(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """Строки длиннее 75 байт переносятся (RFC 5545, 3.1), не разрывая UTF-8 символы."""
    out, current = [], ""
    for ch in line:
        if len((current + ch).encode()) > 75:
            out.append(current)
            current = " " + ch
        else:
            current += ch
    out.append(current)
    return "\r\n".join(out)
