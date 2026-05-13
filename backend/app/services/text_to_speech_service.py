from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json
import re

import requests
from openai import OpenAI

from app.core.config import settings
from app.schemas.voice import VoiceTarget

openai_client = (
    OpenAI(
        api_key=settings.OPENAI_API_KEY,
        timeout=settings.OPENAI_TIMEOUT_SECONDS,
        max_retries=1,
    )
    if settings.OPENAI_API_KEY
    else None
)

OUTPUT_DIR = Path("app/temp/audio_responses")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech"


def _safe_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    return cleaned[:900]


def _target_voice_id(target: VoiceTarget) -> str:
    if target == "tv":
        return settings.ELEVENLABS_TV_VOICE_ID.strip()

    return settings.ELEVENLABS_PHONE_VOICE_ID.strip()


def _cache_filename(
    text: str,
    target: VoiceTarget,
    provider: str,
    voice_key: str,
    model_key: str,
) -> str:
    digest = sha256(
        json.dumps(
            {
                "text": _safe_text(text),
                "target": target,
                "provider": provider,
                "voice_key": voice_key,
                "model_key": model_key,
                "output_format": settings.ELEVENLABS_OUTPUT_FORMAT,
                "stability": settings.ELEVENLABS_STABILITY,
                "similarity_boost": settings.ELEVENLABS_SIMILARITY_BOOST,
                "style": settings.ELEVENLABS_STYLE,
                "use_speaker_boost": settings.ELEVENLABS_USE_SPEAKER_BOOST,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:32]

    return f"tts_{digest}.mp3"


def _instructions_for_target(target: VoiceTarget) -> str:
    if target == "tv":
        return (
            "Mów po polsku naturalnie, krótko i przyjaźnie. "
            "To głos Eriona na ekranie TV na wystawie. "
            "Brzmij ciekawie i zapraszająco, ale bez teatralności i bez długich pauz."
        )

    return (
        "Mów po polsku naturalnie, krótko i jasno. "
        "To głos Query na telefonie, więc odpowiedź ma brzmieć szybko, ciepło i pomocnie."
    )


def _elevenlabs_voice_settings() -> dict:
    return {
        "stability": settings.ELEVENLABS_STABILITY,
        "similarity_boost": settings.ELEVENLABS_SIMILARITY_BOOST,
        "style": settings.ELEVENLABS_STYLE,
        "use_speaker_boost": settings.ELEVENLABS_USE_SPEAKER_BOOST,
    }


def _generate_with_elevenlabs(
    text: str,
    target: VoiceTarget,
    output_path: Path,
) -> bool:
    voice_id = _target_voice_id(target)

    print(
        "ELEVENLABS DEBUG:",
        {
            "target": target,
            "voice_id": voice_id,
            "has_key": bool(settings.ELEVENLABS_API_KEY),
            "model": settings.ELEVENLABS_TTS_MODEL,
        },
    )

    if not settings.ELEVENLABS_API_KEY:
        print("ELEVENLABS SKIPPED: brak ELEVENLABS_API_KEY w .env")
        return False

    if not voice_id:
        print("ELEVENLABS SKIPPED: brak voice_id dla targetu:", target)
        return False

    url = f"{ELEVENLABS_API_URL}/{voice_id}"

    headers = {
        "xi-api-key": settings.ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }

    params = {
        "output_format": settings.ELEVENLABS_OUTPUT_FORMAT,
    }

    payload = {
        "text": text,
        "model_id": settings.ELEVENLABS_TTS_MODEL,
        "voice_settings": _elevenlabs_voice_settings(),
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            params=params,
            json=payload,
            timeout=settings.ELEVENLABS_TIMEOUT_SECONDS,
        )

        if response.status_code >= 400:
            print(
                "ELEVENLABS TTS ERROR:",
                response.status_code,
                response.text[:800],
            )
            output_path.unlink(missing_ok=True)
            return False

        output_path.write_bytes(response.content)

        if output_path.stat().st_size <= 0:
            print("ELEVENLABS TTS ERROR: plik audio jest pusty")
            output_path.unlink(missing_ok=True)
            return False

        print(
            "TTS PROVIDER: ELEVENLABS",
            {
                "target": target,
                "voice_id": voice_id,
                "file": output_path.name,
                "size": output_path.stat().st_size,
            },
        )

        return True

    except Exception as error:
        print("ELEVENLABS TTS ERROR:", repr(error))
        output_path.unlink(missing_ok=True)
        return False


def _generate_with_openai(
    text: str,
    target: VoiceTarget,
    output_path: Path,
) -> bool:
    if not openai_client:
        print("OPENAI TTS SKIPPED: brak OPENAI_API_KEY")
        return False

    try:
        with openai_client.audio.speech.with_streaming_response.create(
            model=settings.OPENAI_TTS_MODEL,
            voice=settings.OPENAI_TTS_VOICE,
            input=text,
            instructions=_instructions_for_target(target),
            response_format="mp3",
        ) as response:
            response.stream_to_file(output_path)

        if output_path.exists() and output_path.stat().st_size > 0:
            print(
                "TTS PROVIDER: OPENAI FALLBACK",
                {
                    "target": target,
                    "voice": settings.OPENAI_TTS_VOICE,
                    "file": output_path.name,
                    "size": output_path.stat().st_size,
                },
            )
            return True

        output_path.unlink(missing_ok=True)
        return False

    except Exception as error:
        print("OPENAI TTS FALLBACK ERROR:", repr(error))
        output_path.unlink(missing_ok=True)
        return False


def generate_speech(text: str, target: VoiceTarget = "phone") -> str | None:
    text = _safe_text(text)

    if not text:
        return None

    elevenlabs_voice_id = _target_voice_id(target)
    should_use_elevenlabs = bool(settings.ELEVENLABS_API_KEY and elevenlabs_voice_id)

    if should_use_elevenlabs:
        elevenlabs_filename = _cache_filename(
            text=text,
            target=target,
            provider="elevenlabs",
            voice_key=elevenlabs_voice_id,
            model_key=settings.ELEVENLABS_TTS_MODEL,
        )

        elevenlabs_output_path = OUTPUT_DIR / elevenlabs_filename

        if elevenlabs_output_path.exists() and elevenlabs_output_path.stat().st_size > 0:
            print(
                "TTS CACHE HIT: ELEVENLABS",
                {
                    "target": target,
                    "voice_id": elevenlabs_voice_id,
                    "file": elevenlabs_filename,
                },
            )
            return f"/audio/{elevenlabs_filename}"

        if _generate_with_elevenlabs(text, target, elevenlabs_output_path):
            return f"/audio/{elevenlabs_filename}"

        print("ElevenLabs nie wygenerował audio, próbuję fallback OpenAI TTS.")
    else:
        print(
            "ELEVENLABS SKIPPED:",
            {
                "target": target,
                "has_key": bool(settings.ELEVENLABS_API_KEY),
                "voice_id": elevenlabs_voice_id,
            },
        )

    openai_filename = _cache_filename(
        text=text,
        target=target,
        provider="openai",
        voice_key=settings.OPENAI_TTS_VOICE,
        model_key=settings.OPENAI_TTS_MODEL,
    )

    openai_output_path = OUTPUT_DIR / openai_filename

    if openai_output_path.exists() and openai_output_path.stat().st_size > 0:
        print(
            "TTS CACHE HIT: OPENAI FALLBACK",
            {
                "target": target,
                "voice": settings.OPENAI_TTS_VOICE,
                "file": openai_filename,
            },
        )
        return f"/audio/{openai_filename}"

    if _generate_with_openai(text, target, openai_output_path):
        return f"/audio/{openai_filename}"

    print("TTS ERROR: nie udało się wygenerować audio ani ElevenLabs, ani OpenAI")
    return None