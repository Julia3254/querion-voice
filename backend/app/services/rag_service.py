from pathlib import Path
import re
from typing import Dict, List, Tuple


STOP_WORDS = {
    "co",
    "to",
    "jest",
    "kim",
    "kto",
    "ty",
    "czy",
    "jak",
    "dla",
    "kogo",
    "gdzie",
    "mnie",
    "mi",
    "o",
    "w",
    "na",
    "i",
    "a",
    "z",
    "ze",
    "do",
    "się",
    "sie",
    "ten",
    "ta",
    "te",
    "tym",
    "tym",
    "jaki",
    "jaka",
    "jakie",
    "powiedz",
    "opowiedz",
    "daj",
}


IMPORTANT_KEYWORDS = {
    "ai",
    "sztuczna",
    "sztucznej",
    "inteligencja",
    "inteligencji",
    "querion",
    "quera",
    "query",
    "erion",
    "avatar",
    "awatar",
    "głos",
    "glos",
    "głosowa",
    "glosowa",
    "mikrofon",
    "technologia",
    "technologii",
    "ciekawostka",
    "ciekawostkę",
    "ciekawostke",
    "lifestyle",
    "podróż",
    "podroz",
    "nauka",
    "kreatywność",
    "kreatywnosc",
}


def _normalize(text: str) -> str:
    return text.lower().strip()


def _tokens(text: str) -> List[str]:
    normalized = _normalize(text)
    words = re.findall(r"[a-zA-ZąćęłńóśźżĄĆĘŁŃÓŚŹŻ0-9]+", normalized)
    return [word for word in words if word not in STOP_WORDS and len(word) > 1]


def _project_root() -> Path:
    # backend/app/services/rag_service.py -> project root
    return Path(__file__).resolve().parents[3]


def _knowledge_dirs() -> List[Path]:
    project_root = _project_root()
    backend_root = Path(__file__).resolve().parents[2]

    candidates = [
        project_root / "knowledge_base" / "raw",
        backend_root / "knowledge_base" / "raw",
        Path.cwd() / "knowledge_base" / "raw",
        Path.cwd().parent / "knowledge_base" / "raw",
    ]

    unique: List[Path] = []
    for path in candidates:
        if path not in unique:
            unique.append(path)

    return unique


def _load_markdown_files() -> List[Tuple[str, str]]:
    files: List[Tuple[str, str]] = []

    for directory in _knowledge_dirs():
        if not directory.exists():
            continue

        for path in sorted(directory.glob("*.md")):
            try:
                content = path.read_text(encoding="utf-8").strip()
            except UnicodeDecodeError:
                content = path.read_text(errors="ignore").strip()

            if content:
                files.append((path.name, content))

    return files


def _split_into_sections(filename: str, content: str) -> List[Tuple[str, str]]:
    sections: List[Tuple[str, str]] = []

    parts = re.split(r"\n(?=# )", content)

    for part in parts:
        cleaned = part.strip()
        if not cleaned:
            continue

        sections.append((filename, cleaned))

    return sections


def _score_section(question: str, filename: str, section: str) -> int:
    question_normalized = _normalize(question)
    section_normalized = _normalize(section)
    filename_normalized = _normalize(filename)

    score = 0
    question_tokens = _tokens(question)

    for token in question_tokens:
        if token in section_normalized:
            score += 3

        if token in filename_normalized:
            score += 2

    for keyword in IMPORTANT_KEYWORDS:
        if keyword in question_normalized and keyword in section_normalized:
            score += 6

        if keyword in question_normalized and keyword in filename_normalized:
            score += 4

    # Krótkie pytania typu "Co to jest AI?" mają mało słów,
    # więc wzmacniamy konkretne intencje.
    if "ai" in question_normalized:
        if "ai" in section_normalized or "sztuczn" in section_normalized:
            score += 12

    if "sztuczna" in question_normalized or "inteligencj" in question_normalized:
        if "sztuczn" in section_normalized or "inteligencj" in section_normalized:
            score += 12

    if "kim jeste" in question_normalized or "kto ty" in question_normalized:
        if "kim jeste" in section_normalized or "erion" in section_normalized or "quera" in section_normalized:
            score += 12

    if "co to jest" in question_normalized:
        if "co to jest" in section_normalized or "querion" in section_normalized or "doświadczenie" in section_normalized:
            score += 8

    if "gdzie jeste" in question_normalized:
        if "gdzie jeste" in section_normalized or "karkonosz" in section_normalized:
            score += 10

    if "ciekaw" in question_normalized:
        if "ciekaw" in section_normalized or "ai" in section_normalized:
            score += 10

    if "dla kogo" in question_normalized:
        if "dla kogo" in section_normalized or "dzieci" in section_normalized or "dorosłych" in section_normalized:
            score += 10

    return score


def _find_core_context(files: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    core_names = {
        "rdzen_asystenta.md",
        "krotkie_pytania_demo.md",
        "ai_ciekawostki.md",
        "faq.md",
    }

    core: List[Tuple[str, str]] = []

    for filename, content in files:
        if filename in core_names:
            core.append((filename, content))

    return core


def get_context_for_question(question: str) -> Dict[str, object]:
    files = _load_markdown_files()

    if not files:
        return {
            "has_context": False,
            "context": "",
            "sources": [],
        }

    core_files = _find_core_context(files)

    sections: List[Tuple[str, str]] = []
    for filename, content in files:
        sections.extend(_split_into_sections(filename, content))

    scored_sections: List[Tuple[int, str, str]] = []

    for filename, section in sections:
        score = _score_section(question, filename, section)

        if score > 0:
            scored_sections.append((score, filename, section))

    scored_sections.sort(key=lambda item: item[0], reverse=True)

    context_parts: List[str] = []
    sources: List[str] = []

    # 1. ZAWSZE dajemy rdzeń, jeśli istnieje.
    # To naprawia krótkie pytania typu: "Co to jest?", "Kim jesteś?", "Co to jest AI?"
    for filename, content in core_files:
        context_parts.append(f"Źródło: {filename}\n{content}")
        sources.append(filename)

    # 2. Dokładamy najlepiej dopasowane sekcje.
    for score, filename, section in scored_sections[:8]:
        context_parts.append(f"Źródło: {filename}\n{section}")

        if filename not in sources:
            sources.append(filename)

    # 3. Jeśli z jakiegoś powodu nie było rdzenia i nie było trafień,
    # dajemy pierwsze pliki, żeby model nadal miał jakikolwiek kontekst demo.
    if not context_parts:
        for filename, content in files[:4]:
            context_parts.append(f"Źródło: {filename}\n{content}")
            sources.append(filename)

    context = "\n\n---\n\n".join(context_parts)




    max_chars = 14000
    if len(context) > max_chars:
        context = context[:max_chars]

    return {
        "has_context": True,
        "context": context,
        "sources": sources,
    }