from pathlib import Path
import uuid

from openai import OpenAI
from app.core.config import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)

OUTPUT_DIR = Path("app/temp/audio_responses")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def generate_speech(text: str) -> str | None:
    if not text or not text.strip():
        return None

    filename = f"{uuid.uuid4()}.mp3"
    output_path = OUTPUT_DIR / filename

    with client.audio.speech.with_streaming_response.create(
        model=settings.OPENAI_TTS_MODEL,
        voice=settings.OPENAI_TTS_VOICE,
        input=text,
        instructions="Mów po polsku, naturalnie, ciepło i spokojnie. Tempo umiarkowane. To odpowiedź avatara głosowego.",
        response_format="mp3",
    ) as response:
        response.stream_to_file(output_path)

    return f"/audio/{filename}"
