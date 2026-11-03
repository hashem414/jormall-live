from __future__ import annotations

import re
from typing import Any

from .config import Settings
from .openai_http import OpenAIHTTPClient, RetrievedChunk


ARABIC_RE = re.compile(r"[\u0600-\u06ff]")
ARTICLE_EN_RE = re.compile(r"\bArticle\s+([1-8])\b", re.IGNORECASE)
ARTICLE_AR_RE = re.compile(r"المادة\s*([1-8])")
ARTICLE_AR_ORDINALS = {
    "الأولى": "1", "الاولى": "1", "الثانية": "2", "الثالثة": "3",
    "الرابعة": "4", "الخامسة": "5", "السادسة": "6", "السابعة": "7",
    "الثامنة": "8",
}
MANUAL_SECTIONS = (
    "Platform Types",
    "Accessing Platforms",
    "Platform Main Menu",
    "Generate Message",
    "Category Management",
    "Address book",
    "Advanced Search",
    "Advanced Services Search",
    "Schedule Message",
    "Birthday Template",
    "Birthday Search",
    "Template Message",
    "Request New Sender",
    "Settings Management",
    "Important note",
)


def question_language(question: str) -> str:
    return "ar" if ARABIC_RE.search(question or "") else "en"


def _article_number(text: str) -> str:
    match = ARTICLE_AR_RE.search(text or "") or ARTICLE_EN_RE.search(text or "")
    if match:
        return match.group(1)
    lowered = (text or "").lower()
    return next((number for word, number in ARTICLE_AR_ORDINALS.items() if word in lowered), "")


def _article_numbers(text: str) -> list[str]:
    numbers = ARTICLE_AR_RE.findall(text or "") + ARTICLE_EN_RE.findall(text or "")
    return list(dict.fromkeys(numbers))


def infer_section(
    filename: str, text: str, attributes: dict[str, Any], question: str = ""
) -> str:
    configured = str(attributes.get("section") or "").strip()
    if configured:
        return configured
    if "TRC_SMS_Regulations" in filename:
        article_numbers = _article_numbers(text)
        requested_article = _article_number(question)
        if requested_article and requested_article in article_numbers:
            return f"Article {requested_article}"
        if len(article_numbers) == 1:
            return f"Article {article_numbers[0]}"
        if article_numbers:
            return f"Articles {', '.join(article_numbers)}"
        return "Regulations"
    lowered = text.lower()
    found = [(lowered.find(section.lower()), section) for section in MANUAL_SECTIONS]
    found = [(position, section) for position, section in found if position >= 0]
    return min(found)[1] if found else "Platform User Manual"


def _chunk_text(item: dict[str, Any]) -> str:
    return "\n".join(
        str(part.get("text") or "").strip()
        for part in (item.get("content") or [])
        if isinstance(part, dict) and part.get("type") == "text" and str(part.get("text") or "").strip()
    ).strip()


def _is_trc(filename: str) -> bool:
    return filename.startswith("TRC_SMS_Regulations")


def _file_language(filename: str, attributes: dict[str, Any]) -> str:
    configured = str(attributes.get("language") or "").lower()
    if configured in {"ar", "en"}:
        return configured
    return "ar" if "_AR." in filename else "en"


def select_retrieval_results(
    raw_results: list[dict[str, Any]], question: str, settings: Settings
) -> list[RetrievedChunk]:
    preferred_language = question_language(question)
    requested_article = _article_number(question)
    effective_min_score = (
        min(settings.search_min_score, 0.20)
        if preferred_language == "ar"
        else settings.search_min_score
    )
    normalized: list[tuple[dict[str, Any], str, str, dict[str, Any], float]] = []
    for item in raw_results:
        score = float(item.get("score") or 0)
        text = _chunk_text(item)
        filename = str(item.get("filename") or "Document")
        attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
        if score < effective_min_score or not text:
            continue
        normalized.append((item, filename, text, attrs, score))

    preferred_trc_exists = any(
        _is_trc(filename) and _file_language(filename, attrs) == preferred_language
        for _, filename, _, attrs, _ in normalized
    )
    selected: list[RetrievedChunk] = []
    seen: set[tuple[str, str]] = set()

    def sort_key(row: tuple[dict[str, Any], str, str, dict[str, Any], float]) -> tuple[int, float]:
        _item, filename, text, _attrs, score = row
        article_match = bool(
            requested_article and _is_trc(filename) and requested_article in _article_numbers(text)
        )
        return (1 if article_match else 0, score)

    for item, filename, text, attrs, score in sorted(normalized, key=sort_key, reverse=True):
        language = _file_language(filename, attrs)
        if requested_article and _is_trc(filename) and requested_article not in _article_numbers(text):
            continue
        if _is_trc(filename) and preferred_trc_exists and language != preferred_language:
            continue
        section = infer_section(filename, text, attrs, question)
        group = "trc" if _is_trc(filename) else filename.lower()
        dedupe_key = (group, section.lower())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        selected.append(
            RetrievedChunk(
                index=len(selected) + 1,
                file_id=str(item.get("file_id") or ""),
                filename=filename,
                score=score,
                text=text[:5000],
                attributes=attrs,
                section=section,
            )
        )
        if len(selected) >= settings.search_max_results:
            break
    return selected


def retrieve_documents(
    client: OpenAIHTTPClient, question: str, settings: Settings
) -> tuple[str, list[RetrievedChunk]]:
    if not settings.retrieval_enabled:
        return "unavailable", []
    raw = client.search_vector_store(question)
    return "available", select_retrieval_results(raw, question, settings)
