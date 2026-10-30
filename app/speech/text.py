MAX_TTS_CHARS = 1000


def for_speech(text: str) -> str:
    """Убираем то, что плохо звучит: маркеры списков, лишние переносы."""
    lines = [line.strip().lstrip("•").strip() for line in text.splitlines() if line.strip()]
    spoken = ". ".join(line.rstrip(".:") for line in lines) + "."
    return spoken[:MAX_TTS_CHARS]
