import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[3]
EXCLUSIONS_PATH = BASE_DIR / "knowledge_base" / "exclusions" / "out_of_scope.json"
LEGACY_EXCLUSIONS_PATH = BASE_DIR / "knowledge_base" / "exclusuins" / "out_of_scope.json"


def load_exclusions() -> dict:
    path = EXCLUSIONS_PATH if EXCLUSIONS_PATH.exists() else LEGACY_EXCLUSIONS_PATH
    if not path.exists():
        return {
            "blocked_topics": [],
            "blocked_keywords": [],
            "blocked_patterns": [],
            "fallback_message": "Mogę odpowiadać tylko na pytania związane z ekspozycją i przygotowaną bazą wiedzy.",
        }

    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def check_exclusion(user_text: str) -> dict:
    data = load_exclusions()
    text = user_text.strip().lower()

    for keyword in data.get("blocked_keywords", []):
        if keyword.lower() in text:
            return {
                "blocked": True,
                "reason": f"blocked_keyword:{keyword}",
                "message": data.get("fallback_message", "To pytanie jest poza zakresem."),
            }

    for pattern in data.get("blocked_patterns", []):
        if pattern.lower() in text:
            return {
                "blocked": True,
                "reason": f"blocked_pattern:{pattern}",
                "message": data.get("fallback_message", "To pytanie jest poza zakresem."),
            }

    for topic in data.get("blocked_topics", []):
        if topic.lower() in text:
            return {
                "blocked": True,
                "reason": f"blocked_topic:{topic}",
                "message": data.get("fallback_message", "To pytanie jest poza zakresem."),
            }

    return {"blocked": False, "reason": None, "message": None}
