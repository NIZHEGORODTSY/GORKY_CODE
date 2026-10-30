from sqlalchemy.ext.asyncio import async_sessionmaker

from app.storage.repository import UserRepository


class Assistant:
    """Точка входа бизнес-логики: принимает текст пользователя, возвращает ответ.

    Сейчас заглушка: регистрирует пользователя и повторяет сообщение.
    Разбор запроса через LLM подключается в модуле llm/.
    """

    def __init__(self, session_factory: async_sessionmaker, default_timezone: str):
        self._session_factory = session_factory
        self._default_timezone = default_timezone

    async def handle(self, user_id: int, text: str) -> str:
        async with self._session_factory() as session, session.begin():
            await UserRepository(session).ensure(user_id, self._default_timezone)
        return f"Принял: «{text}». Понимание запросов пока не подключено."
