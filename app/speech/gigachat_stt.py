"""Распознавание речи через GigaChat: аудио загружается в хранилище и расшифровывается моделью.

SaluteSpeech для физлиц закрыт с 15.07.2026, а GigaChat (3-Pro, 2-Pro) понимает аудио
в ogg/opus — голосовые Telegram отправляем как есть.
"""

import logging

from gigachat import GigaChat
from gigachat.models import Chat, Messages

from app.tls import sber_ssl_context

log = logging.getLogger(__name__)

PROMPT = (
    "Распознай русскую речь в аудио и выведи только дословный текст, без пояснений и кавычек. "
    "Если речи нет или она неразборчива — выведи пустую строку."
)


class GigaChatSTT:
    def __init__(self, credentials: str, scope: str, model: str, ca_bundle: str = ""):
        self._g = GigaChat(
            credentials=credentials,
            scope=scope,
            model=model,
            ssl_context=sber_ssl_context(ca_bundle),
            timeout=60,
        )

    async def recognize(self, audio: bytes, filename: str, mime: str) -> str:
        uploaded = await self._g.aupload_file((filename, audio, mime), purpose="general")
        try:
            resp = await self._g.achat(
                Chat(
                    temperature=0.0,
                    messages=[Messages(role="user", content=PROMPT, attachments=[uploaded.id_])],
                )
            )
            return (resp.choices[0].message.content or "").strip().strip("«»\"")
        finally:
            try:
                await self._g.adelete_file(uploaded.id_)
            except Exception:
                log.warning("failed to delete uploaded audio %s", uploaded.id_)

    async def close(self) -> None:
        await self._g.aclose()
