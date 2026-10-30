"""Синтез речи через edge-tts (нейросетевые голоса Microsoft Edge, без ключа).

Неофициальный доступ: при сбое бот отвечает только текстом.
"""

import asyncio

import edge_tts

from app.speech.text import for_speech

TIMEOUT_SECONDS = 20


class EdgeTTS:
    mime = "audio/mpeg"

    def __init__(self, voice: str):
        self._voice = voice

    async def synthesize(self, text: str) -> bytes:
        return await asyncio.wait_for(self._synthesize(for_speech(text)), TIMEOUT_SECONDS)

    async def _synthesize(self, text: str) -> bytes:
        audio = bytearray()
        async for chunk in edge_tts.Communicate(text, self._voice).stream():
            if chunk["type"] == "audio":
                audio += chunk["data"]
        return bytes(audio)
