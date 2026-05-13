from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[3]
INTERNET_DIR = PROJECT_ROOT / "knowledge_base" / "internet"
SOURCES_PATH = INTERNET_DIR / "sources.json"
CACHE_DIR = INTERNET_DIR / "cache"
CACHE_PATH = CACHE_DIR / "internet_chunks.jsonl"

REQUEST_TIMEOUT_SECONDS = 14
MAX_CHUNK_CHARS = 1200
MIN_CHUNK_CHARS = 180
USER_AGENT = "Querion-RAG-Ingest/1.0 (+https://querion.local)"

TOPIC_SEARCH_TERMS_PL: dict[str, str] = {
    "lifestyle": "lifestyle codzienne nawyki wellbeing samopoczucie zdrowy tryb życia odpoczynek energia rutyna małe zmiany",
    "movement": "ruch spacer aktywność fizyczna ćwiczenia przerwa od siedzenia ciało energia zdrowe nawyki",
    "sleep": "sen spanie odpoczynek regeneracja wieczór zasypianie rytm dnia zmęczenie energia",
    "stress": "stres napięcie oddech spokój relaks wyciszenie emocje przerwa rozmowa wsparcie",
    "nutrition": "jedzenie dieta odżywianie posiłki warzywa owoce woda energia zdrowe wybory bez diety medycznej",
    "small_changes": "małe kroki nawyki zmiana rutyna motywacja zdrowe wybory wellbeing energia",
    "digital_wellbeing": "cyfrowy wellbeing telefon ekran powiadomienia technologia uwaga skupienie przerwa od ekranu",
    "ai": "sztuczna inteligencja AI technologia chatbot model językowy głosowe AI codzienne życie kreatywność",
}


@dataclass(frozen=True)
class InternetSource:
    name: str
    url: str
    topic: str
    language: str = "en"
    priority: int = 5


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _chunk_id(source_url: str, content: str) -> str:
    digest = hashlib.sha1(f"{source_url}\n{content}".encode("utf-8")).hexdigest()
    return digest[:24]


def _load_sources() -> list[InternetSource]:
    if not SOURCES_PATH.exists():
        raise FileNotFoundError(f"Missing sources file: {SOURCES_PATH}")

    data = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    raw_sources = data.get("sources", [])
    sources: list[InternetSource] = []

    for item in raw_sources:
        if not isinstance(item, dict):
            continue

        name = _normalize_whitespace(str(item.get("name", "")))
        url = _normalize_whitespace(str(item.get("url", "")))
        topic = _normalize_whitespace(str(item.get("topic", "lifestyle"))) or "lifestyle"
        language = _normalize_whitespace(str(item.get("language", "en"))) or "en"

        try:
            priority = int(item.get("priority", 5))
        except (TypeError, ValueError):
            priority = 5

        if name and url.startswith("http"):
            sources.append(
                InternetSource(
                    name=name,
                    url=url,
                    topic=topic,
                    language=language,
                    priority=priority,
                )
            )

    return sources


def _fetch_html(source: InternetSource) -> str:
    response = requests.get(
        source.url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.text


def _extract_text_blocks(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg", "canvas", "form", "nav", "footer", "header"]):
        tag.decompose()

    candidates: list[str] = []

    for tag in soup.find_all(["h1", "h2", "h3", "p", "li"]):
        text = _normalize_whitespace(tag.get_text(" ", strip=True))

        if not text:
            continue

        if len(text) < 45 and tag.name not in {"h1", "h2", "h3"}:
            continue

        if re.search(r"cookie|privacy policy|subscribe|newsletter|javascript", text, re.I):
            continue

        candidates.append(text)

    deduped: list[str] = []
    seen: set[str] = set()

    for text in candidates:
        key = text.lower()[:220]

        if key in seen:
            continue

        seen.add(key)
        deduped.append(text)

    return deduped


def _make_chunks(blocks: Iterable[str]) -> list[str]:
    chunks: list[str] = []
    current = ""

    for block in blocks:
        block = _normalize_whitespace(block)

        if not block:
            continue

        if len(block) > MAX_CHUNK_CHARS:
            sentences = re.split(r"(?<=[.!?])\s+", block)

            for sentence in sentences:
                if len(current) + len(sentence) + 1 > MAX_CHUNK_CHARS and current:
                    if len(current) >= MIN_CHUNK_CHARS:
                        chunks.append(current.strip())
                    current = ""

                current += sentence + " "

            continue

        if len(current) + len(block) + 2 > MAX_CHUNK_CHARS and current:
            if len(current) >= MIN_CHUNK_CHARS:
                chunks.append(current.strip())
            current = ""

        current += block + "\n"

    if len(current.strip()) >= MIN_CHUNK_CHARS:
        chunks.append(current.strip())

    return chunks


def _record_for_chunk(source: InternetSource, chunk: str, index: int) -> dict[str, Any]:
    search_text = " ".join(
        [
            source.topic,
            source.name,
            TOPIC_SEARCH_TERMS_PL.get(source.topic, ""),
            "lifestyle wellbeing zdrowe nawyki odpoczynek energia AI technologia",
        ]
    )

    return {
        "id": _chunk_id(source.url, chunk),
        "source_type": "internet",
        "source_name": source.name,
        "source_url": source.url,
        "topic": source.topic,
        "language": source.language,
        "priority": source.priority,
        "chunk_index": index,
        "search_text": _normalize_whitespace(search_text),
        "content": chunk,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }


def ingest_sources() -> dict[str, Any]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    sources = _load_sources()
    all_records: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for source in sources:
        try:
            html = _fetch_html(source)
            blocks = _extract_text_blocks(html)
            chunks = _make_chunks(blocks)

            for index, chunk in enumerate(chunks):
                all_records.append(_record_for_chunk(source, chunk, index))

        except Exception as error:
            errors.append(
                {
                    "source": source.name,
                    "url": source.url,
                    "error": repr(error),
                }
            )

    with CACHE_PATH.open("w", encoding="utf-8") as file:
        for record in all_records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

    report = {
        "sources_total": len(sources),
        "chunks_written": len(all_records),
        "cache_path": str(CACHE_PATH),
        "errors": errors,
    }

    (CACHE_DIR / "ingest_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return report


if __name__ == "__main__":
    print(json.dumps(ingest_sources(), ensure_ascii=False, indent=2))