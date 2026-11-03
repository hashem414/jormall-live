from __future__ import annotations

import time
from decimal import Decimal

from app.core.config import settings
from app.voice.usage import VoiceUsageHandle, complete_voice_request, fail_voice_request


def _int(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def response_usage(response) -> tuple[int, int]:
    usage = getattr(response, "usage", None)
    return (
        _int(getattr(usage, "input_tokens", getattr(usage, "prompt_tokens", 0))),
        _int(getattr(usage, "output_tokens", getattr(usage, "completion_tokens", 0))),
    )


def estimated_cost(*, operation: str, input_tokens: int, output_tokens: int) -> Decimal:
    if operation == "embedding":
        value = input_tokens * settings.openai_embedding_cost_per_million_usd / 1_000_000
    else:
        value = (
            input_tokens * settings.openai_chat_input_cost_per_million_usd
            + output_tokens * settings.openai_chat_output_cost_per_million_usd
        ) / 1_000_000
    return Decimal(str(value))


def complete_openai_request(handle: VoiceUsageHandle | None, response, *, operation: str, started: float) -> None:
    input_tokens, output_tokens = response_usage(response)
    complete_voice_request(
        handle,
        provider_request_id=str(getattr(response, "id", "") or getattr(response, "_request_id", "")) or None,
        input_text_tokens=input_tokens,
        output_text_tokens=output_tokens,
        estimated_cost_usd=estimated_cost(operation=operation, input_tokens=input_tokens, output_tokens=output_tokens),
        request_duration_ms=int((time.perf_counter() - started) * 1000),
    )


def fail_openai_request(handle: VoiceUsageHandle | None, error: BaseException, *, started: float) -> None:
    fail_voice_request(handle, error, request_duration_ms=int((time.perf_counter() - started) * 1000))
