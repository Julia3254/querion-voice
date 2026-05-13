from __future__ import annotations

from pathlib import Path
import re

from openai import OpenAI

from app.core.config import settings

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

    return "Jesteś krótkim, naturalnym asystentem głosowym w tematyce lifestyle i AI."


def _clean_answer(answer: str) -> str:
    cleaned = re.sub(r"\s+", " ", answer or "").strip()
    cleaned = cleaned.replace("**", "").replace("#", "")
    return cleaned[:420]


def _fallback_from_context(context: str) -> str:
    for line in context.splitlines():
        stripped = line.strip()

        if not stripped:
            continue
        if stripped.startswith("Źródło:") or stripped.startswith("Sekcja:"):
            continue
        if stripped.startswith("#") or stripped.startswith("-"):
            continue

        return _clean_answer(stripped[:420])

    return "Mogę odpowiedzieć krótko w tematyce lifestyle, wellbeing albo ciekawostek o AI."


def generate_answer(user_text: str, context: str) -> str:
    if not context.strip():
        return "Przykro mi, nie jestem biegły w tym temacie, więc nie odpowiem ci na to pytanie."

    if not client:
        return _fallback_from_context(context)

    system_prompt = _load_system_prompt()
    user_prompt = f"""
Pytanie użytkownika:
{user_text}

Kontekst z RAG. Najpierw internetowy cache lifestyle, potem lokalne raw jako uzupełnienie:
{context}

Zasady odpowiedzi:
- odpowiedz po polsku,
- główny zakres to lifestyle, wellbeing, codzienne nawyki, odpoczynek, sen, ruch, koncentracja, stres, energia, kreatywność i cyfrowy wellbeing,
- AI traktuj jako dodatek: ciekawostki, inspiracje i wpływ technologii na codzienne życie,
- odpowiadaj szeroko na podstawie kontekstu z internetowego RAG, jeśli pytanie da się obsłużyć bezpiecznie i ogólnie,
- blokuj tylko tematy wykluczone, ryzykowne lub poza bezpiecznym zakresem,
- jeśli pytanie dotyczy wystawy lub firmy Querion, odpowiedz tylko na podstawie kontekstu,
- nie diagnozuj, nie zalecaj leczenia, leków, terapii ani suplementów,
- nie udzielaj porad prawnych ani finansowych,
- odpowiedź ma być gotowa do odczytania głosem,
- maksymalnie 1-2 krótkie zdania,
- bez markdown, bez list, bez nazw plików i bez informacji o źródłach.
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
        return answer or _fallback_from_context(context)
    except Exception as error:
        print("CHAT ERROR:", repr(error))
        return _fallback_from_context(context)