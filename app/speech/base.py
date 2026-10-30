from typing import Protocol


class SpeechToText(Protocol):
    async def recognize(self, audio: bytes, filename: str, mime: str) -> str: ...

    async def close(self) -> None: ...


class TextToSpeech(Protocol):
    mime: str  # формат результата, например audio/mpeg

    async def synthesize(self, text: str) -> bytes: ...
