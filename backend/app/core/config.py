import os
from dotenv import load_dotenv

load_dotenv()


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if not value:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


class Settings:
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_CHAT_MODEL: str = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    OPENAI_STT_MODEL: str = os.getenv("OPENAI_STT_MODEL", "gpt-4o-mini-transcribe")
    OPENAI_TTS_MODEL: str = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
    OPENAI_TTS_VOICE: str = os.getenv("OPENAI_TTS_VOICE", "coral")
    OPENAI_CHAT_MAX_TOKENS: int = _int_env("OPENAI_CHAT_MAX_TOKENS", 70)
    VOICE_MAX_ANSWER_CHARS: int = _int_env("VOICE_MAX_ANSWER_CHARS", 160)
    OPENAI_CHAT_TEMPERATURE: float = _float_env("OPENAI_CHAT_TEMPERATURE", 0.15)
    OPENAI_TIMEOUT_SECONDS: float = _float_env("OPENAI_TIMEOUT_SECONDS", 12.0)

    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_TTS_MODEL: str = os.getenv("ELEVENLABS_TTS_MODEL", "eleven_multilingual_v2")
    ELEVENLABS_TV_VOICE_ID: str = os.getenv("ELEVENLABS_TV_VOICE_ID", "ZUdFQHf8lAj4o7hiHvbE")
    ELEVENLABS_PHONE_VOICE_ID: str = os.getenv("ELEVENLABS_PHONE_VOICE_ID", "yM93hbw8Qtvdma2wCnJG")
    ELEVENLABS_OUTPUT_FORMAT: str = os.getenv("ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128")
    ELEVENLABS_TIMEOUT_SECONDS: float = _float_env("ELEVENLABS_TIMEOUT_SECONDS", 18.0)
    ELEVENLABS_STABILITY: float = _float_env("ELEVENLABS_STABILITY", 0.45)
    ELEVENLABS_SIMILARITY_BOOST: float = _float_env("ELEVENLABS_SIMILARITY_BOOST", 0.85)
    ELEVENLABS_STYLE: float = _float_env("ELEVENLABS_STYLE", 0.20)
    ELEVENLABS_USE_SPEAKER_BOOST: bool = _bool_env("ELEVENLABS_USE_SPEAKER_BOOST", True)

    RAG_MAX_CONTEXT_CHARS: int = _int_env("RAG_MAX_CONTEXT_CHARS", 7500)
    RAG_MAX_SECTIONS: int = _int_env("RAG_MAX_SECTIONS", 6)
    RAG_MIN_SCORE: int = _int_env("RAG_MIN_SCORE", 2)

    IDLE_TV_COOLDOWN_SECONDS: int = _int_env("IDLE_TV_COOLDOWN_SECONDS", 25)


settings = Settings()