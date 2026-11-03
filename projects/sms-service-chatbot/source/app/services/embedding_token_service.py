from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import settings

try:  # pragma: no cover - exercised when the optional package is installed.
    import tiktoken
except ImportError:  # pragma: no cover - conservative fallback for local tools.
    tiktoken = None


EMBEDDING_MODEL_TOKEN_LIMITS = {
    "text-embedding-3-large": 8191,
    "text-embedding-3-small": 8191,
    "text-embedding-ada-002": 8191,
}
EMBEDDING_TOKEN_SAFETY_MARGIN = 256


@dataclass(frozen=True, slots=True)
class TextPart:
    text: str
    token_count: int


def embedding_model_token_limit(model: str | None = None) -> int:
    model_name = model or settings.openai_embedding_model
    return EMBEDDING_MODEL_TOKEN_LIMITS.get(model_name, 8191)


def safe_embedding_token_limit(model: str | None = None) -> int:
    return max(1, embedding_model_token_limit(model) - EMBEDDING_TOKEN_SAFETY_MARGIN)


def _encoding():
    if tiktoken is None:
        return None

    try:
        return tiktoken.encoding_for_model(settings.openai_embedding_model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def count_embedding_tokens(text: str) -> int:
    cleaned = str(text or "")
    encoding = _encoding()

    if encoding is None:
        return max(1, (len(cleaned) + 2) // 3)

    return max(1, len(encoding.encode(cleaned)))


def normalize_embedding_text(text: str) -> str:
    return re.sub(r"[ \t\r\f\v]+", " ", str(text or "")).strip()


def _split_by_token_window(text: str, max_tokens: int) -> list[str]:
    encoding = _encoding()

    if encoding is None:
        max_chars = max(100, max_tokens * 3)
        return [
            text[index:index + max_chars].strip()
            for index in range(0, len(text), max_chars)
            if text[index:index + max_chars].strip()
        ]

    tokens = encoding.encode(text)
    return [
        encoding.decode(tokens[index:index + max_tokens]).strip()
        for index in range(0, len(tokens), max_tokens)
        if encoding.decode(tokens[index:index + max_tokens]).strip()
    ]


def _candidate_blocks(text: str, max_tokens: int) -> list[str]:
    blocks: list[str] = []

    for paragraph in re.split(r"\n\s*\n+", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue

        if count_embedding_tokens(paragraph) <= max_tokens:
            blocks.append(paragraph)
            continue

        sentences = re.split(r"(?<=[.!?\u061f\u3002])\s+", paragraph)
        if len(sentences) > 1:
            blocks.extend(sentence.strip() for sentence in sentences if sentence.strip())
        else:
            blocks.append(paragraph)

    return blocks


def split_text_for_embedding(
    text: str,
    max_tokens: int | None = None,
) -> list[TextPart]:
    limit = max_tokens or safe_embedding_token_limit()
    cleaned = normalize_embedding_text(text)

    if not cleaned:
        return []

    if count_embedding_tokens(cleaned) <= limit:
        return [TextPart(text=cleaned, token_count=count_embedding_tokens(cleaned))]

    parts: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for block in _candidate_blocks(cleaned, limit):
        block_tokens = count_embedding_tokens(block)

        if block_tokens > limit:
            if current:
                parts.append("\n\n".join(current).strip())
                current = []
                current_tokens = 0

            parts.extend(_split_by_token_window(block, limit))
            continue

        if current and current_tokens + block_tokens > limit:
            parts.append("\n\n".join(current).strip())
            current = []
            current_tokens = 0

        current.append(block)
        current_tokens += block_tokens

    if current:
        parts.append("\n\n".join(current).strip())

    return [
        TextPart(text=part, token_count=count_embedding_tokens(part))
        for part in parts
        if part.strip()
    ]
