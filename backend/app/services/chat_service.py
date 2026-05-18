from __future__ import annotations

from pathlib import Path
import re

from openai import OpenAI

from app.core.config import settings
from app.services.fallback_service import get_fallback_response

client = OpenAI(
    api_key=settings.OPENAI_API_KEY,
    timeout=settings.OPENAI_TIMEOUT_SECONDS,
    max_retries=1,
) if settings.OPENAI_API_KEY else None

BASE_DIR = Path(__file__).resolve().parents[3]
SYSTEM_PROMPT_PATH = BASE_DIR / "backend" / "app" / "prompts" / "system_prompt.txt"


def _load_system_prompt() -> str:
    if SYSTEM_PROMPT_PATH.exists():
        return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")

    return "Jesteś Erion, krótkim i naturalnym asystentem głosowym Querionu."


def _clean_answer(answer: str) -> str:
    cleaned = re.sub(r"\s+", " ", answer or "").strip()
    cleaned = cleaned.replace("**", "").replace("#", "")
    return cleaned[:520]


def _fallback_from_context(context: str) -> str:
    for line in context.splitlines():
        stripped = line.strip()

        if not stripped:
            continue

        if stripped.startswith("Źródło:") or stripped.startswith("Sekcja:") or stripped.startswith("Temat:"):
            continue

        if stripped.startswith("#") or stripped.startswith("-"):
            continue

        return _clean_answer(stripped[:420])

    return get_fallback_response()


def generate_answer(user_text: str, context: str = "", category: str = "general") -> str:
    """
    Generuje krótką odpowiedź głosową.

    Logika:
    - project: pytania o Querion / wystawę / fakty projektowe idą przez RAG,
    - lifestyle: model może odpowiedzieć normalnie nawet bez RAG,
    - ai: model może odpowiedzieć normalnie nawet bez RAG,
    - general: poza zakresem, obsługiwane fallbackiem w voice.py.
    """
    context = (context or "").strip()
    category = (category or "general").strip().lower()

    if not client:
        if context:
            return _fallback_from_context(context)
        return get_fallback_response()

    system_prompt = _load_system_prompt()

    if context:
        context_block = f"Kontekst z RAG:\n{context}"
    else:
        context_block = "Kontekst z RAG: brak dopasowanego fragmentu."

    user_prompt = f"""
Pytanie użytkownika:
{user_text}

Rozpoznany tryb:
{category}

{context_block}

Zasady odpowiedzi:
- odpowiedz po polsku,
- odpowiedź ma być gotowa do odczytania głosem,
- maksymalnie 1-2 krótkie zdania,
- bez markdown, bez list, bez nazw plików i bez informacji o źródłach,
- jeśli tryb to project, Querion, Erion, Quera, wystawa, stanowisko albo fakty organizacyjne: trzymaj się kontekstu RAG i nie wymyślaj brakujących faktów,
- jeśli tryb to lifestyle, wellbeing, sen, stres, odpoczynek, koncentracja, motywacja, kreatywność, nauka, organizacja dnia, ruch, jedzenie, telefon, ekrany albo codzienne nawyki: możesz odpowiedzieć z ogólnej wiedzy modelu nawet bez RAG,
- jeśli pytanie dotyczy AI lub technologii: wyjaśnij prosto, krótko i ciekawie,
- jeśli pytanie jest poza rolą Eriona, odpowiedz dokładnie: „Przykro mi, nie jestem biegły w tym temacie, więc nie odpowiem ci na to pytanie.”,
- nie diagnozuj,
- nie zalecaj leczenia, leków, terapii ani suplementów,
- nie udzielaj porad prawnych ani finansowych,
- nie wymyślaj cen, godzin, lokalizacji, partnerów, klientów ani faktów o Querionie, jeśli nie ma ich w kontekście.
""".strip()

    try:
        response = client.chat.completions.create(
            model=settings.OPENAI_CHAT_MODEL,
            temperature=settings.OPENAI_CHAT_TEMPERATURE,
            max_tokens=settings.OPENAI_CHAT_MAX_TOKENS,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        answer = response.choices[0].message.content or ""
        answer = _clean_answer(answer)

        if answer:
            return answer

        if context:
            return _fallback_from_context(context)

        return get_fallback_response()

    except Exception as error:
        print("CHAT ERROR:", repr(error))

        if context:
            return _fallback_from_context(context)

        return get_fallback_response()