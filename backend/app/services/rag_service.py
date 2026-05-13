from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable

from app.core.config import settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = PROJECT_ROOT / "knowledge_base" / "raw"
INTERNET_DIR = PROJECT_ROOT / "knowledge_base" / "internet"
INTERNET_CACHE_DIR = INTERNET_DIR / "cache"

STOP_WORDS = {
    "co", "to", "jest", "kim", "kto", "ty", "czy", "jak", "dla", "kogo", "gdzie",
    "mnie", "mi", "o", "w", "we", "na", "i", "a", "z", "ze", "do", "się", "sie",
    "ten", "ta", "te", "tym", "jaki", "jaka", "jakie", "powiedz", "opowiedz", "daj",
    "mozesz", "możesz", "prosze", "proszę", "cos", "coś", "by", "byc", "być", "mam",
    "chce", "chcę", "chcialbym", "chciałbym", "albo", "oraz", "od", "po", "jestem",
    "mi", "moj", "mój", "moja", "moje", "mogę", "moge", "można", "mozna",
    "bardzo", "troche", "trochę", "dzis", "dziś",
}

LIFESTYLE_QUERY_HINTS = {
    "lifestyle", "wellbeing", "samopoczucie", "nawyk", "nawyki", "dzień", "dzien",
    "odpoczynek", "relaks", "sen", "spanie", "regeneracja", "energia", "zmęczenie", "zmeczenie",
    "ruch", "spacer", "aktywność", "aktywnosc", "przerwa", "woda", "nawodnienie",
    "stres", "spokój", "spokoj", "oddech", "koncentracja", "skupienie", "kreatywność",
    "kreatywnosc", "organizacja", "plan", "rutyna", "telefon", "ekran", "cyfrowy",
}

AI_QUERY_HINTS = {
    "ai", "sztuczna", "sztucznej", "inteligencja", "inteligencji", "model", "chatbot", "gpt",
    "głos", "glos", "rag", "baza", "wiedza", "ciekawostka", "ciekawostkę", "ciekawostke",
    "technologia", "robot", "algorytm", "automatyzacja",
}

PROJECT_QUERY_HINTS = {
    "querion", "quera", "erion", "wystawa", "ekspozycja", "firma", "atrakcja", "park", "avatar", "awatar",
    "stanowisko", "stacja", "ekran", "tutaj",
}

VOICE_QUERY_HINTS = {
    "rozmowa", "rozmawiać", "rozmawiac", "mowa", "głos", "glos", "głosowa", "glosowa",
    "mikrofon", "słucha", "slucha", "słuchasz", "sluchasz", "mówisz", "mowisz",
    "odpowiadasz", "odpowiedź", "odpowiedz", "telefon", "tv", "telewizor",
}

VOICE_QUERY_PHRASES = {
    "jak działa rozmowa", "jak dziala rozmowa", "jak działa mowa", "jak dziala mowa",
    "jak działa głos", "jak dziala glos", "jak działa mikrofon", "jak dziala mikrofon",
    "jak rozmawiać", "jak rozmawiac", "z tobą", "z toba", "co potrafisz",
    "kim jesteś", "kim jestes", "jak mam zacząć", "jak mam zaczac",
    "co mogę zrobić", "co moge zrobic", "co można robić", "co mozna robic",
    "co tu można robić", "co tu mozna robic", "co tutaj można robić", "co tutaj mozna robic",
    "co tu robić", "co tu robic", "co tutaj robić", "co tutaj robic",
}

TOPIC_HINTS: dict[str, set[str]] = {
    "sleep": {"sen", "spanie", "regeneracja", "wieczor", "wieczór", "zmęczenie", "zmeczenie", "energia"},
    "movement": {"ruch", "spacer", "aktywność", "aktywnosc", "ćwiczenia", "cwiczenia", "przerwa", "siedzenie"},
    "stress": {"stres", "napięcie", "napiecie", "oddech", "spokój", "spokoj", "relaks", "emocje"},
    "nutrition": {"jedzenie", "dieta", "posiłek", "posilek", "woda", "energia", "odżywianie", "odzywianie"},
    "small_changes": {"nawyk", "nawyki", "rutyna", "zmiana", "motywacja", "krok", "zacząć", "zaczac"},
    "lifestyle": LIFESTYLE_QUERY_HINTS,
    "digital_wellbeing": {"telefon", "ekran", "powiadomienia", "cyfrowy", "skupienie", "technologia"},
    "ai": AI_QUERY_HINTS,
}

FALLBACK_LIFESTYLE_QUERIES = {
    "co robic", "co robić", "jak zyc", "jak żyć", "co polecasz", "powiedz cos", "powiedz coś",
    "pogadaj", "porozmawiaj", "pomoz", "pomóż", "mam pytanie", "nie wiem",
}


@dataclass(frozen=True)
class RagSection:
    source_type: str
    source_name: str
    title: str
    content: str
    topic: str = "general"
    priority: int = 5
    search_text: str = ""
    source_url: str = ""

    @property
    def display_source(self) -> str:
        if self.source_type == "internet":
            return f"internet:{self.source_name}"
        return f"raw:{self.source_name}"


def _normalize(text: str) -> str:
    return (text or "").lower().strip()


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[a-zA-ZąćęłńóśźżĄĆĘŁŃÓŚŹŻ0-9]+", _normalize(text))
    return [word for word in words if word not in STOP_WORDS and len(word) > 1]


def _fuzzy_contains_any(text: str, hints: set[str]) -> bool:
    normalized = _normalize(text)
    tokens = _tokens(text)

    for hint in hints:
        hint_norm = _normalize(hint)

        if hint_norm in normalized:
            return True

        stem = hint_norm[:5]

        if len(stem) >= 4 and any(token.startswith(stem) or stem in token for token in tokens):
            return True

    return False


def _fuzzy_token_overlap(tokens: Iterable[str], hints: set[str]) -> bool:
    for token in tokens:
        token_norm = _normalize(token)

        for hint in hints:
            hint_norm = _normalize(hint)

            if token_norm == hint_norm:
                return True

            if len(token_norm) >= 5 and len(hint_norm) >= 5:
                if token_norm[:5] == hint_norm[:5]:
                    return True
                if token_norm.startswith(hint_norm[:5]) or hint_norm.startswith(token_norm[:5]):
                    return True

    return False


def _split_markdown_sections(filename: str, content: str) -> list[RagSection]:
    sections: list[RagSection] = []
    parts = re.split(r"\n(?=#{1,3} )", content)

    for index, part in enumerate(parts):
        cleaned = part.strip()

        if not cleaned:
            continue

        title_match = re.search(r"^#{1,3}\s+(.+)$", cleaned, flags=re.MULTILINE)
        title = title_match.group(1).strip() if title_match else filename

        if title.lower().startswith("krótkie pytania") or title.lower().startswith("krotkie pytania"):
            continue

        is_project_file = filename in {
            "firma.md",
            "ekspozycja.md",
            "faq.md",
            "rdzen_asystenta.md",
            "demo_qa_querion_erion_ai.md",
        }

        priority = 8 if is_project_file else 6
        topic = "project" if is_project_file else "general"

        if filename == "lifestyle.md":
            topic = "lifestyle"
            priority = 6

        if filename == "ai_ciekawostki.md":
            topic = "ai"
            priority = 6

        if len(cleaned) > 1800:
            paragraphs = [p.strip() for p in re.split(r"\n\s*\n", cleaned) if p.strip()]
            chunk = ""
            chunk_index = 0

            for paragraph in paragraphs:
                if len(chunk) + len(paragraph) > 1400 and chunk:
                    sections.append(
                        RagSection(
                            source_type="raw",
                            source_name=filename,
                            title=f"{title} {chunk_index}".strip(),
                            content=chunk.strip(),
                            topic=topic,
                            priority=priority,
                        )
                    )
                    chunk = ""
                    chunk_index += 1

                chunk += paragraph + "\n\n"

            if chunk.strip():
                sections.append(
                    RagSection(
                        source_type="raw",
                        source_name=filename,
                        title=f"{title} {chunk_index}".strip(),
                        content=chunk.strip(),
                        topic=topic,
                        priority=priority,
                    )
                )
        else:
            sections.append(
                RagSection(
                    source_type="raw",
                    source_name=filename,
                    title=title or f"{filename}:{index}",
                    content=cleaned,
                    topic=topic,
                    priority=priority,
                )
            )

    return sections


def _iter_jsonl_records(paths: Iterable[Path]) -> Iterable[dict[str, Any]]:
    for path in paths:
        if not path.exists():
            continue

        with path.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()

                if not line:
                    continue

                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if isinstance(record, dict):
                    yield record


@lru_cache(maxsize=1)
def _load_internet_cache_sections() -> tuple[RagSection, ...]:
    sections: list[RagSection] = []
    jsonl_paths = sorted(INTERNET_CACHE_DIR.glob("*.jsonl")) if INTERNET_CACHE_DIR.exists() else []

    for record in _iter_jsonl_records(jsonl_paths):
        content = str(record.get("content", "")).strip()

        if not content:
            continue

        sections.append(
            RagSection(
                source_type="internet",
                source_name=str(record.get("source_name", "internet")),
                title=str(record.get("title", record.get("source_name", "internet"))),
                content=content,
                topic=str(record.get("topic", "lifestyle")),
                priority=int(record.get("priority", 5) or 5),
                search_text=str(record.get("search_text", "")),
                source_url=str(record.get("source_url", "")),
            )
        )

    return tuple(sections)


@lru_cache(maxsize=1)
def _load_internet_markdown_sections() -> tuple[RagSection, ...]:
    sections: list[RagSection] = []

    if not INTERNET_DIR.exists():
        return tuple(sections)

    for path in sorted(INTERNET_DIR.glob("*.md")):
        try:
            content = path.read_text(encoding="utf-8").strip()
        except UnicodeDecodeError:
            content = path.read_text(errors="ignore").strip()

        if not content:
            continue

        for section in _split_markdown_sections(path.name, content):
            sections.append(
                RagSection(
                    source_type="internet",
                    source_name=path.name,
                    title=section.title,
                    content=section.content,
                    topic="lifestyle" if "lifestyle" in path.name else "ai" if "ai" in path.name else "general",
                    priority=7,
                    search_text="lifestyle wellbeing codzienne nawyki AI technologia",
                )
            )

    return tuple(sections)


@lru_cache(maxsize=1)
def _load_raw_sections() -> tuple[RagSection, ...]:
    sections: list[RagSection] = []

    if not RAW_DIR.exists():
        return tuple(sections)

    for path in sorted(RAW_DIR.glob("*.md")):
        try:
            content = path.read_text(encoding="utf-8").strip()
        except UnicodeDecodeError:
            content = path.read_text(errors="ignore").strip()

        if content:
            sections.extend(_split_markdown_sections(path.name, content))

    return tuple(sections)


def _query_category(question: str) -> str:
    normalized = _normalize(question)
    tokens = set(_tokens(question))

    if (
        _fuzzy_token_overlap(tokens, PROJECT_QUERY_HINTS | VOICE_QUERY_HINTS)
        or _fuzzy_contains_any(normalized, PROJECT_QUERY_HINTS | VOICE_QUERY_HINTS)
        or any(phrase in normalized for phrase in VOICE_QUERY_PHRASES)
    ):
        return "project"

    if _fuzzy_token_overlap(tokens, AI_QUERY_HINTS) or _fuzzy_contains_any(normalized, AI_QUERY_HINTS):
        return "ai"

    if _fuzzy_token_overlap(tokens, LIFESTYLE_QUERY_HINTS) or _fuzzy_contains_any(normalized, LIFESTYLE_QUERY_HINTS):
        return "lifestyle"

    if any(term in normalized for term in FALLBACK_LIFESTYLE_QUERIES):
        return "lifestyle"

    return "general"


def _score_section(question: str, section: RagSection) -> int:
    normalized = _normalize(question)
    query_tokens = _tokens(question)

    if any(
        phrase in normalized
        for phrase in {
            "co mogę zrobić", "co moge zrobic", "co można robić", "co mozna robic",
            "co tu", "co tutaj", "na tym stanowisku",
        }
    ):
        query_tokens.extend(["robić", "robic", "zacząć", "zaczac", "rozmawiać", "rozmawiac"])

    searchable = _normalize(
        " ".join(
            [
                section.title,
                section.content,
                section.topic,
                section.search_text,
                section.source_name,
            ]
        )
    )
    category = _query_category(question)

    score = 0

    for token in query_tokens:
        if token in searchable:
            score += 5
        elif len(token) >= 6 and token[:5] in searchable:
            score += 3

        if token in _normalize(section.source_name):
            score += 2

    for i in range(len(query_tokens) - 1):
        phrase = f"{query_tokens[i]} {query_tokens[i + 1]}"

        if phrase in searchable:
            score += 7

    topic_hints = TOPIC_HINTS.get(section.topic, set())

    if _fuzzy_token_overlap(query_tokens, topic_hints):
        score += 28

    if category == "lifestyle":
        if section.source_type == "internet":
            score += 16

        if section.topic in {"lifestyle", "movement", "sleep", "stress", "nutrition", "small_changes", "digital_wellbeing"}:
            score += 22

        if section.source_name == "lifestyle.md":
            score += 8

    if category == "ai":
        if section.topic == "ai" or "ai" in _normalize(section.source_name) or "ciekawostki" in _normalize(section.source_name):
            score += 22

        if section.source_type == "internet":
            score += 8

    if category == "project":
        if section.source_name in {"firma.md", "ekspozycja.md", "faq.md", "rdzen_asystenta.md", "demo_qa_querion_erion_ai.md"}:
            score += 28

        if section.source_type == "internet" and section.topic not in {"ai", "digital_wellbeing"}:
            score -= 8

    if category == "general":
        if section.source_type == "internet" and section.topic in {"lifestyle", "small_changes", "digital_wellbeing"}:
            score += 10

        if any(term in normalized for term in FALLBACK_LIFESTYLE_QUERIES):
            score += 10

    score += max(0, min(section.priority, 10))
    return score


def _rank_sections(question: str, sections: list[RagSection], min_score: int) -> list[tuple[int, RagSection]]:
    scored: list[tuple[int, RagSection]] = []

    for section in sections:
        score = _score_section(question, section)

        if score >= min_score:
            scored.append((score, section))

    scored.sort(key=lambda item: item[0], reverse=True)
    return scored


def _select_unique(
    scored: list[tuple[int, RagSection]],
    limit: int,
    existing_keys: set[str] | None = None,
) -> list[RagSection]:
    selected: list[RagSection] = []
    seen = existing_keys or set()
    per_source: dict[str, int] = {}

    for _score, section in scored:
        if len(selected) >= limit:
            break

        key = f"{section.source_type}:{section.source_name}:{section.content[:160]}"

        if key in seen:
            continue

        if per_source.get(section.source_name, 0) >= 3:
            continue

        seen.add(key)
        per_source[section.source_name] = per_source.get(section.source_name, 0) + 1
        selected.append(section)

    return selected


def _format_context(sections: list[RagSection]) -> str:
    parts: list[str] = []

    for section in sections:
        source = section.display_source
        topic = section.topic
        parts.append(f"Źródło: {source}\nTemat: {topic}\n{section.content}")

    return "\n\n---\n\n".join(parts)


def get_context_for_question(question: str) -> Dict[str, object]:
    internet_cache_sections = list(_load_internet_cache_sections())
    internet_md_sections = list(_load_internet_markdown_sections())
    raw_sections = list(_load_raw_sections())

    internet_sections = internet_cache_sections + internet_md_sections
    selected: list[RagSection] = []
    seen_keys: set[str] = set()

    category = _query_category(question)
    min_score = max(1, settings.RAG_MIN_SCORE)

    if category == "project" and raw_sections:
        raw_scored = _rank_sections(question, raw_sections, min_score)
        selected.extend(_select_unique(raw_scored, 4, seen_keys))

    if internet_sections:
        internet_pool = internet_sections

        if category == "ai":
            ai_pool = [
                section
                for section in internet_sections
                if section.topic in {"ai", "digital_wellbeing"} or "ai" in _normalize(section.source_name)
            ]
            internet_pool = ai_pool or internet_sections

        elif category == "project":
            project_pool = [
                section
                for section in internet_sections
                if section.topic in {"ai", "digital_wellbeing"}
            ]
            internet_pool = project_pool or internet_sections

        internet_scored = _rank_sections(question, internet_pool, min_score)
        internet_limit = max(1, settings.RAG_MAX_SECTIONS - len(selected))
        selected.extend(_select_unique(internet_scored, internet_limit, seen_keys))

    should_add_raw = len(selected) < 3 or category in {"project", "ai"}

    if raw_sections and should_add_raw:
        raw_scored = _rank_sections(question, raw_sections, min_score)
        raw_limit = 4 if category == "project" else 2
        selected.extend(_select_unique(raw_scored, raw_limit, seen_keys))

    if not selected and internet_sections:
        general_lifestyle = [
            section
            for section in internet_sections
            if section.topic in {"lifestyle", "small_changes", "digital_wellbeing", "movement", "sleep", "stress"}
        ]
        selected.extend(general_lifestyle[: min(4, settings.RAG_MAX_SECTIONS)])

    if not selected and raw_sections:
        selected.extend(raw_sections[: min(4, settings.RAG_MAX_SECTIONS)])

    if not selected:
        return {"has_context": False, "context": "", "sources": []}

    context = _format_context(selected)

    if len(context) > settings.RAG_MAX_CONTEXT_CHARS:
        context = context[: settings.RAG_MAX_CONTEXT_CHARS]

    sources: list[str] = []

    for section in selected:
        source = section.display_source

        if source not in sources:
            sources.append(source)

    return {
        "has_context": True,
        "context": context,
        "sources": sources,
        "category": category,
        "internet_cache_used": bool(internet_cache_sections),
    }


def clear_rag_cache() -> None:
    _load_internet_cache_sections.cache_clear()
    _load_internet_markdown_sections.cache_clear()
    _load_raw_sections.cache_clear()