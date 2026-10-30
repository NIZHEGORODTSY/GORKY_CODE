"""SaluteSpeech (Сбер): синхронное распознавание и синтез через REST API."""

import asyncio
import time
import uuid

import httpx

from app.tls import sber_ssl_context

AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
API_URL = "https://smartspeech.sber.ru/rest/v1"
VOICE = "May_24000"
MAX_TTS_CHARS = 1000


class SaluteSpeechClient:
    def __init__(self, credentials: str, scope: str, ca_bundle: str = ""):
        self._credentials = credentials
        self._scope = scope
        self._http = httpx.AsyncClient(verify=sber_ssl_context(ca_bundle), timeout=30)
        self._token = ""
        self._token_expires = 0.0
        self._lock = asyncio.Lock()

    async def _auth_header(self) -> dict[str, str]:
        async with self._lock:
            # Токен живёт 30 минут, обновляем с запасом
            if time.time() > self._token_expires - 60:
                resp = await self._http.post(
                    AUTH_URL,
                    headers={"Authorization": f"Basic {self._credentials}", "RqUID": str(uuid.uuid4())},
                    data={"scope": self._scope},
                )
                resp.raise_for_status()
                body = resp.json()
                self._token = body["access_token"]
                self._token_expires = body["expires_at"] / 1000
        return {"Authorization": f"Bearer {self._token}"}

    async def recognize(self, ogg_opus: bytes) -> str:
        resp = await self._http.post(
            f"{API_URL}/speech:recognize",
            headers={**await self._auth_header(), "Content-Type": "audio/ogg;codecs=opus"},
            content=ogg_opus,
        )
        resp.raise_for_status()
        return " ".join(resp.json().get("result", [])).strip()

    async def synthesize(self, text: str) -> bytes:
        resp = await self._http.post(
            f"{API_URL}/text:synthesize",
            params={"format": "opus", "voice": VOICE},
            headers={**await self._auth_header(), "Content-Type": "application/text"},
            content=_for_speech(text).encode(),
        )
        resp.raise_for_status()
        return resp.content

    async def close(self) -> None:
        await self._http.aclose()


def _for_speech(text: str) -> str:
    """Убираем то, что плохо звучит: маркеры списков, лишние переносы."""
    lines = [line.strip().lstrip("•").strip() for line in text.splitlines() if line.strip()]
    spoken = ". ".join(line.rstrip(".:") for line in lines) + "."
    return spoken[:MAX_TTS_CHARS]
