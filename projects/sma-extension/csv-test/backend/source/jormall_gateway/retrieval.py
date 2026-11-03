from __future__ import annotations

import re
from typing import Any

from .config import Settings
from .openai_http import OpenAIHTTPClient, OpenAIUpstreamError, RetrievedChunk


ARABIC_RE = re.compile(r"[\u0600-\u06ff]")
ARTICLE_EN_RE = re.compile(r"\bArticle\s+([1-8])\b", re.IGNORECASE)
ARTICLE_AR_RE = re.compile(r"المادة\s*([1-8])")
ARTICLE_AR_ORDINALS = {
    "الأولى": "1", "الاولى": "1", "الثانية": "2", "الثالثة": "3",
    "الرابعة": "4", "الخامسة": "5", "السادسة": "6", "السابعة": "7",
    "الثامنة": "8",
}
ARTICLE_HEADING_EN_RE = re.compile(r"(?im)^[ \t]*Article\s+([1-8])\b[^\n]*")
ARTICLE_HEADING_AR_RE = re.compile(r"(?im)^[ \t]*المادة\s*\(?([1-8])\)?[^\n]*")
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
MANUAL_HEADING_RE = re.compile(
    r"(?im)^[ \t]*(" + "|".join(re.escape(section) for section in MANUAL_SECTIONS) + r")[ \t]*$"
)
TRC_RESPONSIBILITY_ARTICLES = {"3", "4", "5", "7"}


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
    if any(term in lowered for term in (
        "upload number from notepad", "upload numbers from notepad", "save contact",
        "notepad file", "click on the import", "mobile numbers must be written with country code",
    )):
        return "Address book"
    if any(term in lowered for term in ("add new category", "contacts categories", "category list")):
        return "Category Management"
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


def _section_segments(filename: str, text: str) -> list[tuple[str, str]]:
    if _is_trc(filename):
        pattern = ARTICLE_HEADING_AR_RE if "_AR." in filename else ARTICLE_HEADING_EN_RE
        matches = list(pattern.finditer(text))
        segments = [
            (
                text[
                    match.start() : matches[index + 1].start() if index + 1 < len(matches) else len(text)
                ].strip(),
                f"Article {match.group(1)}",
            )
            for index, match in enumerate(matches)
        ] if matches else []
    else:
        matches = list(MANUAL_HEADING_RE.finditer(text))
        segments = [
            (
                text[
                    match.start() : matches[index + 1].start() if index + 1 < len(matches) else len(text)
                ].strip(),
                match.group(1),
            )
            for index, match in enumerate(matches)
        ] if matches else []
    useful = [(segment, section) for segment, section in segments if len(segment) >= 40]
    return useful or [(text, "")]


def _manual_sections_for_question(question: str) -> set[str]:
    lowered = (question or "").lower()
    if any(term in lowered for term in ("address book", "contact", "notepad", "upload numbers")):
        return {"Address book", "Category Management"}
    if "category management" in lowered or "contact categor" in lowered:
        return {"Category Management"}
    if any(term in lowered for term in ("request new sender", "request a new sender", "new sender")):
        return {"Request New Sender"}
    if "schedule" in lowered:
        return {"Schedule Message", "Generate Message"}
    if "template" in lowered:
        return {"Template Message", "Generate Message"}
    return set()


def is_trc_responsibility_question(question: str) -> bool:
    lowered = (question or "").lower()
    responsibility_terms = ("responsibil", "duties", "obligation", "التزامات", "مسؤوليات", "واجبات")
    role_terms = ("operator", "bulk message", "message source", "trc", "مشغل", "رسائل الجملة", "مصدر")
    return any(term in lowered for term in responsibility_terms) and any(
        term in lowered for term in role_terms
    )


def _is_trc_question(question: str, requested_article: str) -> bool:
    if requested_article or is_trc_responsibility_question(question):
        return True
    lowered = (question or "").lower()
    return any(term in lowered for term in (
        "trc", "bulk message", "advertising sms", "advertising message", "commission",
        "regulation", "prohibited", "رسائل الجملة", "الرسائل الدعائية", "الهيئة", "التعليمات",
    ))


def _supplemental_queries(question: str) -> list[str]:
    manual_sections = _manual_sections_for_question(question)
    queries: list[str] = []
    if "Address book" in manual_sections:
        queries.append(
            "Address book adding group contacts upload numbers from notepad select data fields "
            "select category Browse text file Import country code one contact per line comma"
        )
    if is_trc_responsibility_question(question):
        queries.extend((
            "Article 4 Regulatory Provisions for the Operator responsibilities",
            "Article 5 Regulatory Provisions for the Bulk Message Source responsibilities",
            "Article 7 shared Operator and Bulk Message Source general provisions",
        ))
    return queries


def select_retrieval_results(
    raw_results: list[dict[str, Any]], question: str, settings: Settings
) -> list[RetrievedChunk]:
    preferred_language = question_language(question)
    manual_sections = _manual_sections_for_question(question)
    responsibility_question = is_trc_responsibility_question(question)
    # A role-comparison question may name one article as only part of the desired
    # answer (for example, "shared Article 7 duties"). Do not let that incidental
    # mention suppress the other role-bearing Articles 3, 4, and 5.
    requested_article = "" if responsibility_question else _article_number(question)
    trc_question = _is_trc_question(question, requested_article)
    effective_min_score = (
        min(settings.search_min_score, 0.20)
        if preferred_language == "ar"
        else settings.search_min_score
    )
    normalized: list[tuple[dict[str, Any], str, str, dict[str, Any], float, str]] = []
    for item in raw_results:
        score = float(item.get("score") or 0)
        text = _chunk_text(item)
        filename = str(item.get("filename") or "Document")
        attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
        if score < effective_min_score or not text:
            continue
        for segment, section_hint in _section_segments(filename, text):
            normalized.append((item, filename, segment, attrs, score, section_hint))

    preferred_trc_exists = any(
        _is_trc(filename) and _file_language(filename, attrs) == preferred_language
        for _, filename, _, attrs, _, _ in normalized
    )
    selected: list[RetrievedChunk] = []
    selected_positions: dict[tuple[str, str], int] = {}

    def sort_key(
        row: tuple[dict[str, Any], str, str, dict[str, Any], float, str]
    ) -> tuple[int, float]:
        _item, filename, text, _attrs, score, section_hint = row
        article_match = bool(
            requested_article
            and _is_trc(filename)
            and (section_hint == f"Article {requested_article}" or requested_article in _article_numbers(text))
        )
        return (1 if article_match else 0, score)

    for item, filename, text, attrs, score, section_hint in sorted(
        normalized, key=sort_key, reverse=True
    ):
        language = _file_language(filename, attrs)
        is_trc = _is_trc(filename)
        candidate_section = section_hint or infer_section(filename, text, attrs, question)
        if manual_sections and is_trc:
            continue
        if trc_question and not is_trc:
            continue
        if manual_sections and not is_trc and candidate_section not in manual_sections:
            continue
        if responsibility_question and candidate_section.startswith("Article "):
            if candidate_section.removeprefix("Article ") not in TRC_RESPONSIBILITY_ARTICLES:
                continue
        if requested_article and is_trc and (
            section_hint != f"Article {requested_article}"
            and requested_article not in _article_numbers(text)
        ):
            continue
        if is_trc and preferred_trc_exists and language != preferred_language:
            continue
        section = (
            f"Article {requested_article}"
            if requested_article and is_trc and requested_article in _article_numbers(text)
            else candidate_section
        )
        group = "trc" if is_trc else filename.lower()
        dedupe_key = (group, section.lower())
        if dedupe_key in selected_positions:
            position = selected_positions[dedupe_key]
            existing = selected[position]
            merged_text = existing.text
            if text not in merged_text:
                merged_text = f"{merged_text}\n\n{text}"[:5000]
            selected[position] = RetrievedChunk(
                index=existing.index,
                file_id=existing.file_id,
                filename=existing.filename,
                score=max(existing.score, score),
                text=merged_text,
                attributes=existing.attributes,
                section=existing.section,
            )
            continue
        if len(selected) >= settings.search_max_results:
            continue
        selected_positions[dedupe_key] = len(selected)
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
    return selected


def retrieve_documents(
    client: OpenAIHTTPClient, question: str, settings: Settings
) -> tuple[str, list[RetrievedChunk]]:
    if not settings.retrieval_enabled:
        return "unavailable", []
    raw: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    successful_searches = 0
    last_upstream_error: OpenAIUpstreamError | None = None
    for query in (question, *_supplemental_queries(question)):
        try:
            results = client.search_vector_store(query)
        except OpenAIUpstreamError as exc:
            # Supplemental searches improve coverage but must not erase useful
            # evidence already returned by earlier successful searches.
            last_upstream_error = exc
            continue
        successful_searches += 1
        for item in results:
            fingerprint = (str(item.get("file_id") or ""), _chunk_text(item))
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            raw.append(item)
    if successful_searches == 0 and last_upstream_error is not None:
        raise last_upstream_error
    return "available", select_retrieval_results(raw, question, settings)
