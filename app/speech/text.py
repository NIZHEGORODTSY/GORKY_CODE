import unicodedata

from app.core.formatting import plain

MAX_TTS_CHARS = 1000
INVISIBLE = {"️", "‍"}  # вариационный селектор и склейка эмодзи


def for_speech(text: str) -> str:
    """Убираем то, что плохо звучит: HTML, эмодзи, маркеры списков, лишние переносы."""
    text = "".join(ch for ch in plain(text) if unicodedata.category(ch) != "So" and ch not in INVISIBLE)
    lines = [line.strip().lstrip("•").strip() for line in text.splitlines() if line.strip()]
    spoken = ". ".join(line.rstrip(".:") for line in lines) + "."
    return spoken[:MAX_TTS_CHARS]
