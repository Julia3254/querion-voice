from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

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
    "moj", "mój", "moja", "moje", "mogę", "moge", "można", "mozna",
    "bardzo", "troche", "trochę", "dzis", "dziś",
}

BRAND_ALIASES = {
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
    "erionie": "erion",
}

PROJECT_SOURCE_NAMES = {
    "rdzen_asystenta.md",
    "firma.md",
    "faq.md",
    "ekspozycja.md",
    "demo_qa_querion_erion_ai.md",
}

PROJECT_QUERY_HINTS = {
    "querion", "kwerion", "klerion", "qwerion", "quarion",
    "kweryon", "keryon", "kerion", "querjon", "kwerjon",
    "querium", "kwerium", "queryon", "kwirion", "klirion",

    "quera", "kwera", "qera", "klera",
    "erion", "eryon", "erjon",

    "ai touch", "flying theater", "immersive experience", "cinema 5d",
    "explorer 270", "circulum 360", "racing",

    "wystawa", "ekspozycja", "stanowisko", "stacja",
    "avatar", "awatar",
    "bilet", "bilety", "cena", "ceny", "koszt", "kosztuje",
    "godziny", "otwarte", "otwarcie",
    "parking", "pies", "psem", "dostępność", "dostepnosc",
    "klient", "partner", "demo", "instalacja",
    "atrakcja", "atrakcje", "lokalizacja", "adres",
    "quera", "erion", "querion",
}

VOICE_QUERY_HINTS = {
    "rozmowa", "rozmawiać", "rozmawiac", "mowa", "głos", "glos", "głosowa", "glosowa",
    "mikrofon", "słucha", "slucha", "słuchasz", "sluchasz", "mówisz", "mowisz",
    "odpowiadasz", "odpowiedź", "odpowiedz", "tv", "telewizor",
}

VOICE_QUERY_PHRASES = {
    "jak działa rozmowa", "jak dziala rozmowa",
    "jak działa mowa", "jak dziala mowa",
    "jak działa głos", "jak dziala glos",
    "jak działa mikrofon", "jak dziala mikrofon",
    "jak rozmawiać", "jak rozmawiac",
    "z tobą", "z toba",
    "co potrafisz",
    "kim jesteś", "kim jestes",
    "jak mam zacząć", "jak mam zaczac",
}


@dataclass(frozen=True)
class RagSection:
    source_type: str
    source_name: str
    title: str
    content: str
    topic: str = "general"
    priority: int = 5
    source_url: str = ""

    @property
    def display_source(self) -> str:
        if self.source_url:
            return f"{self.source_type}:{self.source_name}:{self.source_url}"
        return f"{self.source_type}:{self.source_name}"


def _normalize(text: str) -> str:
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

    words = text.split()
    normalized_words = [BRAND_ALIASES.get(word, word) for word in words]

    return " ".join(normalized_words)


def _tokens(text: str) -> set[str]:
    normalized = _normalize(text)

    return {
        token
        for token in normalized.split()
        if len(token) >= 3 and token not in STOP_WORDS
    }


def _contains_any(normalized_text: str, hints: set[str]) -> bool:
    for hint in hints:
        normalized_hint = _normalize(hint)

        if not normalized_hint:
            continue

        if normalized_hint in normalized_text:
            return True

    return False


def _token_overlap(tokens: set[str], hints: set[str]) -> bool:
    normalized_hints = {_normalize(hint) for hint in hints}
    normalized_hints = {hint for hint in normalized_hints if hint}

    return bool(tokens & normalized_hints)


def _query_category(question: str) -> str:
    normalized = _normalize(question)
    query_tokens = _tokens(question)

    if _contains_any(normalized, PROJECT_QUERY_HINTS):
        return "project"

    if _contains_any(normalized, VOICE_QUERY_PHRASES):
        return "project"

    if _token_overlap(query_tokens, PROJECT_QUERY_HINTS | VOICE_QUERY_HINTS):
        return "project"

    return "general"


def _guess_topic(filename: str, title: str, content: str) -> str:
    text = _normalize(f"{filename} {title} {content[:500]}")

    if filename in PROJECT_SOURCE_NAMES:
        return "project"

    if _contains_any(text, PROJECT_QUERY_HINTS | VOICE_QUERY_HINTS):
        return "project"

    return "general"


def _split_markdown_sections(text: str, source_name: str, source_type: str) -> list[RagSection]:
    sections: list[RagSection] = []
    current_title = "Informacje"
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_title, current_lines

        content = "\n".join(current_lines).strip()

        if not content:
            return

        topic = _guess_topic(source_name, current_title, content)

        sections.append(
            RagSection(
                source_type=source_type,
                source_name=source_name,
                title=current_title,
                content=content,
                topic=topic,
                priority=8 if topic == "project" else 5,
            )
        )

    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            flush()
            current_title = line.lstrip("#").strip() or "Informacje"
            current_lines = []
        else:
            current_lines.append(line)

    flush()

    if not sections and text.strip():
        topic = _guess_topic(source_name, "Informacje", text)

        sections.append(
            RagSection(
                source_type=source_type,
                source_name=source_name,
                title="Informacje",
                content=text.strip(),
                topic=topic,
                priority=8 if topic == "project" else 5,
            )
        )

    return sections


@lru_cache(maxsize=1)
def _load_raw_sections() -> tuple[RagSection, ...]:
    sections: list[RagSection] = []

    if not RAW_DIR.exists():
        return tuple()

    for path in sorted(RAW_DIR.glob("*.md")):
        if path.name not in PROJECT_SOURCE_NAMES:
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except Exception as error:
            print("RAG RAW READ ERROR:", path, repr(error))
            continue

        sections.extend(_split_markdown_sections(text, path.name, "raw"))

    return tuple(sections)


@lru_cache(maxsize=1)
def _load_internet_markdown_sections() -> tuple[RagSection, ...]:
    sections: list[RagSection] = []

    if not INTERNET_DIR.exists():
        return tuple()

    for path in sorted(INTERNET_DIR.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as error:
            print("RAG INTERNET MD READ ERROR:", path, repr(error))
            continue

        parsed_sections = _split_markdown_sections(text, path.name, "internet")
        sections.extend(
            section
            for section in parsed_sections
            if section.topic == "project"
        )

    return tuple(sections)


def _sections_from_cache_payload(payload: Any, source_name: str) -> list[RagSection]:
    sections: list[RagSection] = []

    if isinstance(payload, dict):
        possible_lists = []

        for key in ("sections", "results", "items", "documents", "pages"):
            value = payload.get(key)

            if isinstance(value, list):
                possible_lists.append(value)

        if not possible_lists:
            possible_lists.append([payload])

        for items in possible_lists:
            for item in items:
                if not isinstance(item, dict):
                    continue

                title = str(item.get("title") or item.get("name") or "Internet")
                content = str(
                    item.get("content")
                    or item.get("text")
                    or item.get("snippet")
                    or item.get("summary")
                    or ""
                ).strip()

                if not content:
                    continue

                source_url = str(item.get("url") or item.get("source_url") or "")
                topic = _guess_topic(source_name, title, content)

                if topic != "project":
                    continue

                sections.append(
                    RagSection(
                        source_type="internet",
                        source_name=source_name,
                        title=title,
                        content=content,
                        topic=topic,
                        priority=4,
                        source_url=source_url,
                    )
                )

    elif isinstance(payload, list):
        for item in payload:
            sections.extend(_sections_from_cache_payload(item, source_name))

    return sections


@lru_cache(maxsize=1)
def _load_internet_cache_sections() -> tuple[RagSection, ...]:
    sections: list[RagSection] = []

    if not INTERNET_CACHE_DIR.exists():
        return tuple()

    for path in sorted(INTERNET_CACHE_DIR.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as error:
            print("RAG INTERNET CACHE READ ERROR:", path, repr(error))
            continue

        sections.extend(_sections_from_cache_payload(payload, path.name))

    return tuple(sections)


def _score_section(question: str, section: RagSection) -> int:
    query_tokens = _tokens(question)

    searchable = _normalize(
        " ".join(
            [
                section.title,
                section.content,
                section.topic,
                section.source_name,
            ]
        )
    )
    searchable_tokens = _tokens(searchable)

    score = 0
    token_list = list(query_tokens)

    for token in token_list:
        if token in searchable_tokens:
            score += 8
        elif token in searchable:
            score += 4

    for i in range(len(token_list) - 1):
        phrase = f"{token_list[i]} {token_list[i + 1]}"

        if phrase in searchable:
            score += 8

    if section.source_name in PROJECT_SOURCE_NAMES:
        score += 8

    if section.topic == "project":
        score += 8

    score += max(0, min(section.priority, 10))

    return score


def _format_context(sections: list[RagSection]) -> str:
    parts: list[str] = []

    for section in sections:
        parts.append(
            f"Źródło: {section.display_source}\n"
            f"Temat: {section.topic}\n"
            f"{section.content}"
        )

    return "\n\n---\n\n".join(parts)


def _empty_context(category: str) -> Dict[str, object]:
    return {
        "has_context": False,
        "context": "",
        "sources": [],
        "category": category,
        "internet_cache_used": bool(_load_internet_cache_sections()),
    }


def get_context_for_question(question: str) -> Dict[str, object]:
    category = _query_category(question)

    if category != "project":
        return _empty_context(category)

    raw_sections = list(_load_raw_sections())
    internet_sections = list(_load_internet_cache_sections()) + list(_load_internet_markdown_sections())

    min_score = int(getattr(settings, "RAG_MIN_SCORE", 1) or 1)
    min_score = max(min_score, 12)

    max_sections = int(getattr(settings, "RAG_MAX_SECTIONS", 4) or 4)
    max_context_chars = int(getattr(settings, "RAG_MAX_CONTEXT_CHARS", 3500) or 3500)

    candidate_sections: list[RagSection] = [
        section
        for section in raw_sections + internet_sections
        if section.topic == "project" or section.source_name in PROJECT_SOURCE_NAMES
    ]

    scored: list[tuple[int, RagSection]] = []

    for section in candidate_sections:
        score = _score_section(question, section)

        if score >= min_score:
            scored.append((score, section))

    scored.sort(key=lambda item: item[0], reverse=True)

    selected: list[RagSection] = []
    seen_keys: set[str] = set()

    for _score, section in scored:
        if len(selected) >= max_sections:
            break

        key = f"{section.source_type}:{section.source_name}:{section.title}:{section.content[:120]}"

        if key in seen_keys:
            continue

        seen_keys.add(key)
        selected.append(section)

    if not selected:
        return _empty_context(category)

    context = _format_context(selected)

    if len(context) > max_context_chars:
        context = context[:max_context_chars]

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
        "internet_cache_used": bool(_load_internet_cache_sections()),
    }


def clear_rag_cache() -> None:
    _load_raw_sections.cache_clear()
    _load_internet_markdown_sections.cache_clear()
    _load_internet_cache_sections.cache_clear()