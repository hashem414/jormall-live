from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from config import (
    LLM_INTENT_ENABLED,
    OPENAI_CONFIGURED,
    OPENAI_INTENT_MODEL,
    OPENAI_INTENT_TIMEOUT_SECONDS,
)


class StructuredExplicitFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    cities: list[str]
    areas: list[str]
    gender: list[str]
    classes: list[str]
    age_min: Optional[int]
    age_max: Optional[int]


class StructuredCampaignIntent(BaseModel):
    """The only model-generated data accepted by the campaign pipeline."""

    model_config = ConfigDict(extra="forbid", strict=True)

    advertisers: list[str]
    brands: list[str]
    raw_product_phrases: list[str]
    normalized_product_concepts: list[str]
    open_product_terms: list[str]
    use_cases: list[str]
    audience_type: Literal["b2b", "b2c", "mixed", "unspecified"]
    target_entities: list[str]
    target_roles: list[str]
    target_industries: list[str]
    explicit_filters: StructuredExplicitFilters
    offer: str
    product_positioning: list[str]
    likely_class_affinity: list[
        Literal[
            "Upper:strong",
            "Upper:moderate",
            "Middle Plus:strong",
            "Middle Plus:moderate",
            "Middle:strong",
            "Middle:moderate",
            "Economy Plus:strong",
            "Economy Plus:moderate",
            "Economy:strong",
            "Economy:moderate",
        ]
    ]
    campaign_type: str
    clarification_needed: bool
    ambiguity_notes: list[str]
    confidence: float = Field(ge=0.0, le=1.0)


@dataclass(frozen=True)
class LLMIntentResult:
    payload: Dict[str, object] = field(default_factory=dict)
    call_count: int = 0
    provider: str = "local"
    used: bool = False
    latency_ms: int = 0
    error: str = ""


INSTRUCTIONS = """You extract campaign intent from one campaign prompt.
Return only the CampaignIntent structure requested by the schema.
Preserve specific brands and open-vocabulary product phrases. Normalize product concepts without replacing the original phrase.
Infer B2B, B2C, or mixed only from the prompt. Keep unknown values empty or unspecified; do not invent advertisers, filters, offers, or industries.
Set clarification_needed only when the product or audience is genuinely too ambiguous for local retrieval.
Do not recommend audience lists, candidates, companies, rankings, or tiers."""


def _safe_error(exc: Exception) -> str:
    name = type(exc).__name__
    if name == "APITimeoutError":
        return "timeout"
    if name == "AuthenticationError" or getattr(exc, "status_code", None) == 401:
        return "authentication_401"
    if name == "RateLimitError" or getattr(exc, "status_code", None) == 429:
        return "rate_limit_429"
    if name in {"APIConnectionError", "ConnectError", "NetworkError"}:
        return "unavailable"
    if name in {"ValidationError", "JSONDecodeError", "ValueError", "TypeError", "AttributeError"}:
        return "malformed_response"
    status = getattr(exc, "status_code", None)
    return f"api_error_{status}" if isinstance(status, int) else "unavailable"


def parse_optional_structured_intent(prompt: str, enabled: bool | None = None) -> LLMIntentResult:
    should_use = LLM_INTENT_ENABLED if enabled is None else bool(enabled)
    if not should_use:
        return LLMIntentResult()
    if not OPENAI_CONFIGURED:
        return LLMIntentResult(provider="local_fallback", error="not_configured")

    try:
        from openai import OpenAI
    except ImportError:
        return LLMIntentResult(provider="local_fallback", error="sdk_unavailable")

    started = time.perf_counter()
    try:
        client = OpenAI(max_retries=0, timeout=OPENAI_INTENT_TIMEOUT_SECONDS)
        response = client.responses.parse(
            model=OPENAI_INTENT_MODEL,
            instructions=INSTRUCTIONS,
            input=[{"role": "user", "content": prompt}],
            text_format=StructuredCampaignIntent,
            store=False,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise ValueError("structured intent was missing")
        payload = parsed.model_dump(mode="json")
        return LLMIntentResult(
            payload=payload,
            call_count=1,
            provider="openai",
            used=True,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
    except Exception as exc:
        return LLMIntentResult(
            call_count=1,
            provider="local_fallback",
            latency_ms=int((time.perf_counter() - started) * 1000),
            error=_safe_error(exc),
        )
