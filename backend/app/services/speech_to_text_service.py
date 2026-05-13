from __future__ import annotations

from openai import OpenAI

from app.core.config import settings

client = OpenAI(
    api_key=settings.OPENAI_API_KEY,
    timeout=settings.OPENAI_TIMEOUT_SECONDS,
    max_retries=1,
) if settings.OPENAI_API_KEY else None


def transcribe_audio(file_path: str) -> str:
    if not client:
        return ""

    with open(file_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model=settings.OPENAI_STT_MODEL,
            file=audio_file,
            language="pl",
        )

    return transcript.text