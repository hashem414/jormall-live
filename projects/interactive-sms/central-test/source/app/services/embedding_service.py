from __future__ import annotations

import time
from dataclasses import dataclass

from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)

from app.core.config import settings
from app.services.openai_client import get_openai_client


@dataclass(frozen=True, slots=True)
class EmbeddingBatch:
    model: str
    embeddings: list[list[float]]
    prompt_tokens: int
    total_tokens: int
    retry_count: int = 0


class EmbeddingPermanentError(RuntimeError):
    """Raised when OpenAI rejects an embedding request that should not retry."""


class EmbeddingTransientError(RuntimeError):
    """Raised when retries were exhausted for a transient embedding failure."""


def is_transient_embedding_error(error: Exception) -> bool:
    if isinstance(error, (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)):
        return True

    if isinstance(error, APIStatusError):
        return error.status_code == 429 or error.status_code >= 500

    return isinstance(error, APIError) and not isinstance(error, BadRequestError)


def create_embeddings(
    inputs: list[str],
    *,
    max_retries: int = 3,
    base_backoff_seconds: float = 1.0,
) -> EmbeddingBatch:
    if not inputs:
        raise ValueError("At least one text input is required.")

    cleaned_inputs = [text.strip() for text in inputs]

    if any(not text for text in cleaned_inputs):
        raise ValueError("Embedding inputs cannot be empty.")

    attempt = 0
    while True:
        try:
            response = get_openai_client().embeddings.create(
                model=settings.openai_embedding_model,
                input=cleaned_inputs,
                dimensions=settings.embedding_dimensions,
                encoding_format="float",
            )
            break
        except BadRequestError as error:
            raise EmbeddingPermanentError(str(error)) from error
        except APIError as error:
            if not is_transient_embedding_error(error) or attempt >= max_retries:
                raise EmbeddingTransientError(
                    "OpenAI could not create embeddings after retrying. "
                    "Check API availability, billing, and model access."
                ) from error

            time.sleep(base_backoff_seconds * (2 ** attempt))
            attempt += 1

    ordered_items = sorted(response.data, key=lambda item: item.index)
    embeddings = [item.embedding for item in ordered_items]

    if len(embeddings) != len(cleaned_inputs):
        raise RuntimeError("OpenAI returned an unexpected number of embeddings.")

    for embedding in embeddings:
        if len(embedding) != settings.embedding_dimensions:
            raise RuntimeError(
                "Embedding dimension mismatch. "
                f"Expected {settings.embedding_dimensions}, got {len(embedding)}."
            )

    return EmbeddingBatch(
        model=settings.openai_embedding_model,
        embeddings=embeddings,
        prompt_tokens=response.usage.prompt_tokens,
        total_tokens=response.usage.total_tokens,
        retry_count=attempt,
    )
