from pathlib import Path

from openai import OpenAI

from app.core.config import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None
BASE_DIR = Path(__file__).resolve().parents[3]
SYSTEM_PROMPT_PATH = BASE_DIR / "backend" / "app" / "prompts" / "system_prompt.txt"


def _load_system_prompt() -> str:
    if SYSTEM_PROMPT_PATH.exists():
        return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    return (
        "Jesteś pomocnym asystentem głosowym dla interaktywnej ekspozycji. "
        "Odpowiadasz wyłącznie na podstawie zatwierdzonej bazy wiedzy."
    )


def _fallback_from_context(context: str) -> str:
    for line in context.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("Źródło:") or stripped.startswith("Sekcja:"):
            continue
        if stripped.startswith("#") or stripped.startswith("-"):
            continue
        return stripped[:420]
    return "Mogę odpowiadać tylko na podstawie przygotowanej bazy wiedzy."


def generate_answer(user_text: str, context: str) -> str:
    if not context.strip():
        return "Przykro mi, nie jestem biegły w tym temacie, więc nie odpowiem ci na to pytanie."

    if not client:
        return _fallback_from_context(context)

    system_prompt = _load_system_prompt()
    user_prompt = f"""
Pytanie użytkownika:
{user_text}

Baza wiedzy, na której wolno się opierać:
{context}

Zasady odpowiedzi:
- odpowiedz wyłącznie na podstawie powyższej bazy wiedzy,
- nie dodawaj informacji spoza bazy,
- jeśli baza nie wystarcza, odpowiedz fallbackiem,
- odpowiedź ma być naturalna do odsłuchania głosem,
- maksymalnie 2-3 krótkie zdania,
- nie wymieniaj nazw plików źródłowych użytkownikowi.
""".strip()

    try:
        response = client.chat.completions.create(
            model=settings.OPENAI_CHAT_MODEL,
            temperature=0.2,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        answer = response.choices[0].message.content or ""
        answer = answer.strip()
        return answer or _fallback_from_context(context)
    except Exception:
        return _fallback_from_context(context)
