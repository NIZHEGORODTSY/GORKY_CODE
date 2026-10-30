from typing import Protocol


class SpeechClient(Protocol):
    async def recognize(self, ogg_opus: bytes) -> str:
        """Голосовое сообщение Telegram (OGG/Opus) -> текст."""
        ...

    async def synthesize(self, text: str) -> bytes:
        """Текст -> OGG/Opus, пригодный для sendVoice."""
        ...

    async def close(self) -> None: ...
