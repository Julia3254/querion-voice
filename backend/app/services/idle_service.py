from __future__ import annotations

import json
import random
from functools import lru_cache
from pathlib import Path

from app.schemas.voice import VoiceTarget

BASE_DIR = Path(__file__).resolve().parents[3]
IDLE_PHRASES_PATH = BASE_DIR / "knowledge_base" / "idle" / "idle_phrases.json"

DEFAULT_TV_PHRASES = [
    "Ej, podejdziesz do mnie?",
    "Chcesz porozmawiać?",
    "Mam dla Ciebie krótką inspirację na teraz.",
]


@lru_cache(maxsize=1)
def load_idle_phrases() -> dict[str, list[str]]:
    if not IDLE_PHRASES_PATH.exists():
        return {"tv": DEFAULT_TV_PHRASES, "phone": []}

    try:
        data = json.loads(IDLE_PHRASES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"tv": DEFAULT_TV_PHRASES, "phone": []}

    normalized: dict[str, list[str]] = {"tv": [], "phone": []}

    for target in ("tv", "phone"):
        values = data.get(target, [])

        if isinstance(values, list):
            normalized[target] = [
                str(item).strip()
                for item in values
                if str(item).strip()
            ]

    if not normalized["tv"]:
        normalized["tv"] = DEFAULT_TV_PHRASES

    return normalized


def choose_idle_phrase(target: VoiceTarget = "tv") -> str:
    phrases = (
        load_idle_phrases().get(target)
        or load_idle_phrases().get("tv")
        or DEFAULT_TV_PHRASES
    )

    return random.choice(phrases)