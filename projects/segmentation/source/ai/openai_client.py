from __future__ import annotations

from typing import Any

from config import OPENAI_CONFIGURED


def create_openai_client(*, timeout: float, max_retries: int = 0) -> Any:
    if not OPENAI_CONFIGURED:
        raise RuntimeError("openai_not_configured")
    from openai import OpenAI

    return OpenAI(timeout=timeout, max_retries=max_retries)


def safe_openai_error(exc: Exception) -> str:
    name = type(exc).__name__
    status = getattr(exc, "status_code", None)
    if name == "APITimeoutError":
        return "timeout"
    if name == "AuthenticationError" or status == 401:
        return "authentication_401"
    if name == "RateLimitError" or status == 429:
        return "rate_limit_429"
    if name in {"ValidationError", "JSONDecodeError", "ValueError", "TypeError", "AttributeError"}:
        return "malformed_response"
    if name in {"APIConnectionError", "ConnectError", "NetworkError"}:
        return "unavailable"
    return f"api_error_{status}" if isinstance(status, int) else "unavailable"
