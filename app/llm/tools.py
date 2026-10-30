"""Функции, которые может вызвать LLM. Описания — часть промпта, формулируем точно."""

from app.core.dates import DAY_TOKENS, WEEKDAY_TOKENS
from app.llm.base import ToolSpec

CREATE_EVENT = ToolSpec(
    name="create_event",
    description="Создать задачу, напоминание или встречу.",
    parameters={
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": ["task", "reminder", "meeting"],
                "description": (
                    "reminder — просят напомнить о чём-то в конкретный момент; "
                    "meeting — встреча, созвон, совещание с кем-то; "
                    "task — дело, которое нужно сделать (к сроку или без срока)."
                ),
            },
            "title": {
                "type": "string",
                "description": (
                    "Суть записи с заглавной буквы, без даты, времени и служебных слов "
                    "(«напомни», «поставь задачу», «у меня»). Примеры: «Позвонить Ивану», "
                    "«Встреча с дизайнером», «Купить билеты»."
                ),
            },
            "day": {
                "type": "string",
                "enum": DAY_TOKENS,
                "description": (
                    "День, если он назван словами: today, tomorrow, day_after_tomorrow, день недели "
                    "(«в четверг» — thursday), end_of_week («до конца недели»), next_week («на следующей неделе»)."
                ),
            },
            "date": {
                "type": "string",
                "description": "Только если названо конкретное число («5 ноября», «15.11») — дата YYYY-MM-DD.",
            },
            "time": {
                "type": "string",
                "description": (
                    "Время HH:MM (24 часа): «в 9 утра» — 09:00, «в 3 дня» — 15:00, «в 22:00» — 22:00. "
                    "Не заполняй и не придумывай, если время не названо."
                ),
            },
            "in_minutes": {
                "type": "integer",
                "description": "Только для «через N минут/часов»: через сколько минут от текущего момента.",
            },
            "duration_minutes": {
                "type": "integer",
                "description": "Длительность встречи в минутах, только если названа.",
            },
            "repeat": {
                "type": "string",
                "enum": ["daily", "weekdays", "weekly", "monthly"],
                "description": (
                    "Только если сказано про повтор (время при этом — в поле time): «каждый день» — daily, «по будням» — weekdays, "
                    "«каждый понедельник», «по средам и пятницам» — weekly (+ repeat_days), «каждый месяц» — monthly."
                ),
            },
            "repeat_days": {
                "type": "array",
                "items": {"type": "string", "enum": WEEKDAY_TOKENS},
                "description": "Дни недели для repeat=weekly.",
            },
        },
        "required": ["kind", "title"],
    },
)

LIST_EVENTS = ToolSpec(
    name="list_events",
    description="Показать задачи, напоминания и встречи за период: «что у меня сегодня», «планы на неделю».",
    parameters={
        "type": "object",
        "properties": {
            "period": {
                "type": "string",
                "enum": ["today", "tomorrow", "day_after_tomorrow", "this_week", "next_week", "custom"],
                "description": "custom — конкретная дата или диапазон, тогда заполни date_from и date_to.",
            },
            "date_from": {"type": "string", "description": "YYYY-MM-DD, только для custom."},
            "date_to": {"type": "string", "description": "YYYY-MM-DD включительно, только для custom."},
            "kind": {
                "type": "string",
                "enum": ["meeting", "task"],
                "description": "Только если спрашивают именно о встречах (meeting) или о задачах (task).",
            },
        },
        "required": ["period"],
    },
)

SEARCH_EVENTS = ToolSpec(
    name="search_events",
    description=(
        "Найти ранее созданные записи по смыслу, включая прошедшие и выполненные: "
        "«найди задачу про договор», «когда была встреча с Иваном». "
        "Не используй перед переносом, выполнением или удалением — те функции сами находят запись по query."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Ключевые слова о сути записи, 1–4 слова, например «договор» или «Иван встреча».",
            },
            "kind": {
                "type": "string",
                "enum": ["meeting", "task"],
                "description": "meeting — если ищут встречу, созвон, демо; task — если ищут задачу или напоминание.",
            },
            "time_scope": {
                "type": "string",
                "enum": ["past", "future"],
                "description": "past — если спрашивают о прошедшем («когда была», «ставил»), future — о предстоящем («когда будет»).",
            },
        },
        "required": ["query"],
    },
)

_TARGET = {
    "event_id": {
        "type": "integer",
        "description": "Номер записи из списка «Записи из последних ответов», если речь о ней («её», «эту», «первую»).",
    },
    "query": {
        "type": "string",
        "description": "Если записи нет в контексте — ключевые слова, по которым её найти.",
    },
}

UPDATE_EVENT = ToolSpec(
    name="update_event",
    description=(
        "Изменить запись: перенести («перенеси её на завтра», «сдвинь созвон на 17:00»), "
        "переименовать («переименуй встречу в …»), изменить длительность встречи."
    ),
    parameters={
        "type": "object",
        "properties": {
            **_TARGET,
            "day": CREATE_EVENT.parameters["properties"]["day"],
            "date": CREATE_EVENT.parameters["properties"]["date"],
            "time": CREATE_EVENT.parameters["properties"]["time"],
            "in_minutes": CREATE_EVENT.parameters["properties"]["in_minutes"],
            "title": {"type": "string", "description": "Новое название, только если просят переименовать."},
            "duration_minutes": CREATE_EVENT.parameters["properties"]["duration_minutes"],
        },
    },
)

COMPLETE_EVENT = ToolSpec(
    name="complete_event",
    description="Отметить задачу выполненной: «я позвонил Ивану», «готово», «отметь отчёт сделанным».",
    parameters={"type": "object", "properties": _TARGET},
)

DELETE_EVENT = ToolSpec(
    name="delete_event",
    description="Удалить или отменить запись: «удали задачу про билеты», «встреча отменилась».",
    parameters={"type": "object", "properties": _TARGET},
)

UPDATE_SETTINGS = ToolSpec(
    name="update_settings",
    description=(
        "Изменить настройки: часовой пояс («я в Новосибирске», «у меня время +4 к Москве»), "
        "утреннюю сводку («присылай план по утрам в 8», «не присылай сводку»), "
        "голосовые ответы («отвечай без голоса»)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "timezone": {"type": "string", "description": "Часовой пояс IANA, например Asia/Novosibirsk, Europe/Moscow."},
            "digest_time": {"type": "string", "description": "Время утренней сводки HH:MM или off — выключить."},
            "voice_replies": {"type": "boolean", "description": "Отвечать ли голосом на голосовые."},
        },
    },
)

TOOLS = [CREATE_EVENT, LIST_EVENTS, SEARCH_EVENTS, UPDATE_EVENT, COMPLETE_EVENT, DELETE_EVENT, UPDATE_SETTINGS]
