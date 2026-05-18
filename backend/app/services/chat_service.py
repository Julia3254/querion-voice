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
    return cleaned[:620]


def _fallback_from_context(context: str) -> str:
    for line in context.splitlines():
        stripped = line.strip()

        if not stripped:
            continue

        if stripped.startswith("Źródło:") or stripped.startswith("Sekcja:") or stripped.startswith("Temat:"):
            continue

        if stripped.startswith("#") or stripped.startswith("-"):
            continue

        return _clean_answer(stripped[:520])

    return get_fallback_response()


def generate_answer(user_text: str, context: str = "", category: str = "general") -> str:
    """
    Generuje krótką odpowiedź głosową.

    Logika:
    - project: fakty o Querionie idą przez RAG i nie wolno ich zmyślać,
    - wszystko inne normalne: model OpenAI odpowiada jak ogólny asystent,
    - tematy wykluczone są blokowane wcześniej przez exclusion_service.
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
- maksymalnie 1-3 krótkie zdania,
- bez markdown, bez list, bez nazw plików i bez informacji o źródłach,
- jeśli tryb to project, Querion, Erion, Quera, wystawa, stanowisko, bilety, godziny, lokalizacja albo fakty organizacyjne: trzymaj się kontekstu RAG i nie wymyślaj brakujących faktów,
- jeśli tryb nie jest project: odpowiedz normalnie z ogólnej wiedzy modelu, nawet jeśli RAG nie znalazł kontekstu,
- możesz odpowiadać na zwykłe pytania użytkownika o naukę, czas wolny, podróże, lokalne pomysły, technologię, AI, kreatywność, codzienne sprawy, nudę, organizację dnia, rozrywkę i ciekawostki,
- jeśli użytkownik pyta, jak zostałeś stworzony, odpowiedz ogólnie, że jesteś cyfrowym asystentem opartym o model językowy, rozpoznawanie mowy, syntezę głosu i bazę wiedzy Querionu,
- jeśli pytanie jest o Querion i brakuje danych w kontekście RAG, odpowiedz dokładnie: „Przykro mi, nie jestem biegły w tym temacie, więc nie odpowiem ci na to pytanie.”,
- jeśli pytanie dotyczy tematu wykluczonego albo niebezpiecznego, odpowiedz dokładnie: „Przykro mi, nie jestem biegły w tym temacie, więc nie odpowiem ci na to pytanie.”,
- nie diagnozuj,
- nie zalecaj leczenia, leków, terapii ani suplementów,
- nie udzielaj porad prawnych ani finansowych,
- nie odpowiadaj na treści seksualne, narkotyki, przemoc, instrukcje szkodliwe ani prośby o prywatne dane,
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