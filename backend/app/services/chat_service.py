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

    return "Jesteś głosowym asystentem Querionu. Twoja persona zależy od trybu: TV to Erion, telefon to Quera."


def _persona_for_target(target: str | None) -> dict[str, str]:
    target = (target or "phone").strip().lower()

    if target == "tv":
        return {
            "name": "Erion",
            "role": "cyfrowy avatar i głosowy asystent Querionu na ekranie TV",
            "intro": (
                "Jestem Erion, cyfrowy avatar i głosowy asystent Querionu na ekranie TV. "
                "Możesz zadawać mi pytania głosowo przez telefon połączony z ekranem."
            ),
        }

    return {
        "name": "Quera",
        "role": "mobilna głosowa asystentka Querionu na telefonie",
        "intro": (
            "Jestem Quera, mobilna głosowa asystentka Querionu. "
            "Możesz zabrać mnie ze sobą na telefonie i zadawać mi pytania głosowo."
        ),
    }


def _clean_answer(answer: str) -> str:
    cleaned = re.sub(r"\s+", " ", answer or "").strip()
    cleaned = cleaned.replace("**", "").replace("#", "")
    return cleaned[:620]


def _normalize_for_rules(text: str) -> str:
    text = (text or "").lower()

    replacements = {
        "ą": "a",
        "ć": "c",
        "ę": "e",
        "ł": "l",
        "ń": "n",
        "ó": "o",
        "ś": "s",
        "ź": "z",
        "ż": "z",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    aliases = {
        "kwerion": "querion",
        "klerion": "querion",
        "qwerion": "querion",
        "quarion": "querion",
        "kweryon": "querion",
        "keryon": "querion",
        "kerion": "querion",
        "querjon": "querion",
        "kwerjon": "querion",
        "querium": "querion",
        "kwerium": "querion",
        "queryon": "querion",
        "kwirion": "querion",
        "klirion": "querion",
        "kwera": "quera",
        "qera": "quera",
        "klera": "quera",
        "eryon": "erion",
        "erjon": "erion",
    }

    words = text.split()
    words = [aliases.get(word, word) for word in words]

    return " ".join(words)


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


def _answer_persona_question(user_text: str, target: str | None) -> str | None:
    normalized = _normalize_for_rules(user_text)
    persona = _persona_for_target(target)

    asks_about_self = any(
        phrase in normalized
        for phrase in [
            "kim jestes",
            "kim ty jestes",
            "kto ty jestes",
            "przedstaw sie",
            "jak masz na imie",
            "co potrafisz",
        ]
    )

    asks_about_quera = "quera" in normalized
    asks_about_erion = "erion" in normalized

    if asks_about_self:
        return persona["intro"]

    if asks_about_quera:
        return (
            "Quera to mobilna głosowa asystentka Querionu na telefonie. "
            "Możesz zabrać ją ze sobą i zadawać jej pytania głosowo."
        )

    if asks_about_erion:
        return (
            "Erion to cyfrowy avatar i głosowy asystent Querionu na ekranie TV. "
            "Można z nim rozmawiać przez telefon połączony z ekranem."
        )

    return None


def _answer_basic_project_question(user_text: str, context: str, target: str | None) -> str | None:
    normalized = _normalize_for_rules(user_text)
    context_normalized = _normalize_for_rules(context)

    persona_answer = _answer_persona_question(user_text, target)

    if persona_answer:
        return persona_answer

    if "querion" in normalized and any(
        phrase in normalized
        for phrase in [
            "co to",
            "czym jest",
            "czym sa",
            "opowiedz",
            "co to jest",
            "czym jest querion",
            "co to querion",
        ]
    ):
        if "querion" in context_normalized:
            return (
                "Querion to interaktywna przestrzeń, która łączy nowoczesną technologię, "
                "sztuczną inteligencję, multimedia i rozrywkę. To miejsce, w którym można "
                "doświadczać atrakcji opartych na obrazie, dźwięku, ruchu i interakcji."
            )

    return None


def _is_fallback_answer(answer: str) -> bool:
    normalized = _normalize_for_rules(answer)
    fallback = _normalize_for_rules(get_fallback_response())

    return fallback in normalized or "nie jestem biegly w tym temacie" in normalized


def generate_answer(
    user_text: str,
    context: str = "",
    category: str = "general",
    target: str | None = "phone",
) -> str:
    """
    Generuje krótką odpowiedź głosową.

    Persona:
    - target="tv" -> Erion
    - target="phone" -> Quera

    Logika:
    - project: fakty o Querionie idą przez RAG i nie wolno ich zmyślać,
    - jeżeli RAG znalazł kontekst projektu, model ma odpowiedzieć z kontekstu,
    - wszystko inne normalne: model OpenAI odpowiada jak ogólny asystent,
    - tematy wykluczone są blokowane wcześniej przez exclusion_service.
    """
    context = (context or "").strip()
    category = (category or "general").strip().lower()
    persona = _persona_for_target(target)

    persona_answer = _answer_persona_question(user_text, target)

    if persona_answer:
        return persona_answer

    if category == "project" and context:
        direct_project_answer = _answer_basic_project_question(user_text, context, target)

        if direct_project_answer:
            return direct_project_answer

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

Tryb urządzenia:
{target}

Aktualna persona:
{persona["name"]}

Rola persony:
{persona["role"]}

{context_block}

Zasady persony:
- jeśli target to tv, jesteś Erionem,
- jeśli target to phone, jesteś Querą,
- jeśli użytkownik pyta „kim jesteś”, „jak masz na imię” albo „przedstaw się”, odpowiedz jako aktualna persona,
- nie mów, że jesteś Erionem, gdy target to phone,
- nie mów, że jesteś Querą, gdy target to tv.

Zasady odpowiedzi:
- odpowiedz po polsku,
- odpowiedź ma być gotowa do odczytania głosem,
- maksymalnie 1-3 krótkie zdania,
- bez markdown, bez list, bez nazw plików i bez informacji o źródłach.

Zasady dla trybu project:
- jeśli tryb to project i kontekst z RAG istnieje, odpowiedz na podstawie kontekstu,
- jeśli pytanie dotyczy nazwy aktualnej persony, pierwszeństwo ma target urządzenia, a nie baza RAG,
- jeśli pytanie brzmi podobnie do „czym jest Querion”, „czym jest Kwerion”, „co to Querion”, odpowiedz definicją Querionu z kontekstu,
- jeśli pytanie dotyczy Querionu, Eriona, Query, wystawy, stanowiska, biletów, godzin, lokalizacji albo faktów organizacyjnych, trzymaj się kontekstu RAG i nie wymyślaj brakujących faktów,
- jeśli tryb to project, ale kontekst RAG nie zawiera odpowiedzi, odpowiedz dokładnie: „Przykro mi, nie jestem biegły w tym temacie, więc nie odpowiem ci na to pytanie.”.

Zasady dla pytań ogólnych:
- jeśli tryb nie jest project, odpowiedz normalnie z ogólnej wiedzy modelu, nawet jeśli RAG nie znalazł kontekstu,
- możesz odpowiadać na zwykłe pytania użytkownika o naukę, czas wolny, podróże, lokalne pomysły, technologię, AI, kreatywność, codzienne sprawy, nudę, organizację dnia, rozrywkę i ciekawostki,
- jeśli użytkownik pyta, jak zostałeś stworzony, odpowiedz ogólnie jako {persona["name"]}, że jesteś cyfrowym asystentem opartym o model językowy, rozpoznawanie mowy, syntezę głosu i bazę wiedzy Querionu.

Zasady bezpieczeństwa:
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

        if answer and not (category == "project" and context and _is_fallback_answer(answer)):
            return answer

        if category == "project" and context:
            direct_project_answer = _answer_basic_project_question(user_text, context, target)

            if direct_project_answer:
                return direct_project_answer

            return _fallback_from_context(context)

        if context:
            return _fallback_from_context(context)

        return get_fallback_response()

    except Exception as error:
        print("CHAT ERROR:", repr(error))

        if category == "project" and context:
            direct_project_answer = _answer_basic_project_question(user_text, context, target)

            if direct_project_answer:
                return direct_project_answer

            return _fallback_from_context(context)

        if context:
            return _fallback_from_context(context)

        return get_fallback_response()