from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentChunk
from app.services.embedding_service import create_embeddings


DEFAULT_TOP_K = 5
DEFAULT_CLIENT_SLUG = "jormall"
MAX_VECTOR_CANDIDATES = 40

TABLE_QUERY_TERMS = {
    "active",
    "address",
    "affordability",
    "applicant",
    "applicants",
    "application",
    "amount",
    "certificate",
    "collected",
    "bundle",
    "bundles",
    "column",
    "compare",
    "count",
    "credit",
    "document",
    "documents",
    "fee",
    "fees",
    "highest",
    "incomplete",
    "installment",
    "installments",
    "instalment",
    "instalments",
    "list",
    "lowest",
    "menu",
    "monthly",
    "number",
    "package",
    "packages",
    "performs",
    "plans",
    "position",
    "positioned",
    "positioning",
    "price",
    "prices",
    "pricing",
    "processed",
    "proof",
    "provider",
    "purpose",
    "prize",
    "prizes",
    "quantity",
    "rate",
    "required",
    "requirement",
    "requirements",
    "repayment",
    "repayments",
    "review",
    "reward",
    "rewards",
    "row",
    "salary",
    "table",
    "tier",
    "total",
    "value",
}


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    chunk_id: UUID
    document_id: UUID
    document_title: str
    original_filename: str
    language: str
    section_title: str | None
    source_reference: str | None
    content: str
    similarity: float
    metadata: dict[str, Any]
    client_slug: str


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    question: str
    embedding_model: str
    prompt_tokens: int
    total_tokens: int
    results: list[RetrievedChunk]


def is_metadata_only_chunk(content: str) -> bool:
    lines = [
        line.strip()
        for line in content.splitlines()
        if line.strip()
    ]

    if not lines:
        return True

    metadata_prefixes = (
        "source type:",
        "source url:",
        "base url:",
        "page url:",
        "scraped at:",
        "pages scraped:",
        "images saved:",
        "screenshots saved:",
        "videos found:",
        "local static url:",
    )

    non_metadata_lines = [
        line
        for line in lines
        if not line.lower().startswith(metadata_prefixes)
    ]

    if not non_metadata_lines:
        return True

    if len(non_metadata_lines) == 1 and non_metadata_lines[0].lower() in {
        "headings",
        "visible page text",
        "links and buttons",
        "website image evidence",
        "website screenshot evidence",
        "website video evidence",
    }:
        return True

    return False


def has_media_or_evidence_metadata(chunk: RetrievedChunk) -> bool:
    metadata = chunk.metadata or {}

    return bool(
        metadata.get("local_static_url")
        or metadata.get("video_url")
        or "Video URL:" in chunk.content
        or "[[image:" in chunk.content
        or "[[video:" in chunk.content
    )


def compact_numeric(value: str) -> str:
    return re.sub(r"[,\s]+", "", value.lower())


def table_lexical_tokens(value: Any) -> set[str]:
    text = str(value or "")
    lowered = text.lower()
    tokens = {
        compact_numeric(token)
        for token in re.findall(
            r"\d[\d,]*(?:\.\d+)?(?:\s*[kKmM]\b)?|[a-zA-Z][a-zA-Z0-9]*",
            lowered,
        )
        if compact_numeric(token)
    }

    for match in re.finditer(r"\b(\d[\d,\s]*)\s*(?:k|thousand)\b", lowered):
        number = compact_numeric(match.group(1))
        tokens.add(f"{number}k")
        try:
            tokens.add(str(int(number) * 1000))
        except ValueError:
            pass

    for match in re.finditer(r"\b(\d[\d,\s]*)\s*(?:m|million)\b", lowered):
        number = compact_numeric(match.group(1))
        tokens.add(f"{number}m")
        try:
            tokens.add(str(int(number) * 1000000))
        except ValueError:
            pass

    return tokens


def is_table_chunk(chunk: RetrievedChunk) -> bool:
    metadata = chunk.metadata or {}
    content = chunk.content.lower()

    return bool(
        metadata.get("block_kind") == "table"
        or metadata.get("chunk_category") == "table"
        or metadata.get("table_headers")
        or "table columns:" in content
        or re.search(r"\brow\s+\d+:\s+\w+:", content)
    )


def table_lexical_score(*, question: str, chunk: RetrievedChunk) -> float:
    question_tokens = table_lexical_tokens(question)
    if not question_tokens:
        return 0.0

    chunk_tokens = table_lexical_tokens(
        " ".join(
            [
                chunk.document_title,
                chunk.section_title or "",
                chunk.content,
                " ".join(
                    str(value)
                    for value in (chunk.metadata or {}).values()
                    if isinstance(value, str)
                ),
            ]
        )
    )
    overlap = question_tokens & chunk_tokens

    if not overlap:
        return 0.0

    score = min(0.20, len(overlap) * 0.035)
    exact_alphanumeric_overlap = {
        token
        for token in overlap
        if re.search(r"\d", token) and re.search(r"[a-z]", token)
    }
    exact_numeric_overlap = {
        token
        for token in overlap
        if re.fullmatch(r"\d+(?:\.\d+)?", token)
    }

    if exact_alphanumeric_overlap:
        score += 0.15
    elif exact_numeric_overlap:
        score += 0.08

    if is_table_chunk(chunk):
        score += 0.08

    if question_tokens & TABLE_QUERY_TERMS and is_table_chunk(chunk):
        score += 0.06

    return score


def final_ranked_chunks(
    *,
    chunks: list[RetrievedChunk],
    question: str,
    top_k: int,
    include_metadata_only: bool,
) -> list[RetrievedChunk]:
    if include_metadata_only:
        candidates = chunks
    else:
        useful_chunks = [
            chunk
            for chunk in chunks
            if not is_metadata_only_chunk(chunk.content)
            or has_media_or_evidence_metadata(chunk)
        ]

        candidates = useful_chunks or chunks

    if question and any(term in question.lower() for term in TABLE_QUERY_TERMS):
        return sorted(
            candidates,
            key=lambda chunk: (
                chunk.similarity + table_lexical_score(question=question, chunk=chunk),
                chunk.similarity,
            ),
            reverse=True,
        )[:top_k]

    return candidates[:top_k]


def retrieve_client_chunks(
    *,
    question: str,
    db: Session,
    top_k: int = DEFAULT_TOP_K,
    client_slug: str = DEFAULT_CLIENT_SLUG,
    include_metadata_only: bool = False,
) -> RetrievalResult:
    cleaned_question = question.strip()

    if not cleaned_question:
        raise ValueError("Question cannot be empty.")

    if top_k < 1 or top_k > 10:
        raise ValueError("top_k must be between 1 and 10.")

    embedding_result = create_embeddings([cleaned_question])
    question_embedding = embedding_result.embeddings[0]

    cosine_distance = DocumentChunk.embedding.cosine_distance(
        question_embedding
    ).label("cosine_distance")

    statement = (
        select(
            DocumentChunk,
            Document,
            cosine_distance,
        )
        .join(
            Document,
            Document.id == DocumentChunk.document_id,
        )
        .where(
            DocumentChunk.embedding.is_not(None),
            DocumentChunk.client_slug == client_slug,
            Document.client_slug == client_slug,
            Document.status == "active",
            Document.visibility == "client",
        )
        .order_by(cosine_distance.asc())
        .limit(max(top_k, min(MAX_VECTOR_CANDIDATES, top_k * 4)))
    )

    rows = db.execute(statement).all()

    retrieved_chunks: list[RetrievedChunk] = []

    for chunk, document, distance in rows:
        if distance is None:
            continue

        similarity = max(
            -1.0,
            min(1.0, 1.0 - float(distance)),
        )

        retrieved_chunks.append(
            RetrievedChunk(
                chunk_id=chunk.id,
                document_id=document.id,
                document_title=document.title,
                original_filename=document.original_filename,
                language=document.language,
                section_title=chunk.section_title,
                source_reference=chunk.source_reference,
                content=chunk.content,
                similarity=similarity,
                metadata=chunk.chunk_metadata,
                client_slug=chunk.client_slug,
            )
        )

    return RetrievalResult(
        question=cleaned_question,
        embedding_model=embedding_result.model,
        prompt_tokens=embedding_result.prompt_tokens,
        total_tokens=embedding_result.total_tokens,
        results=final_ranked_chunks(
            chunks=retrieved_chunks,
            question=cleaned_question,
            top_k=top_k,
            include_metadata_only=include_metadata_only,
        ),
    )
