"""عميل OpenAI مشترك (singleton) لكل التطبيق."""

from __future__ import annotations

from functools import lru_cache

from openai import OpenAI

from .config import get_settings


@lru_cache(maxsize=1)
def get_openai() -> OpenAI:
    settings = get_settings()
    return OpenAI(api_key=settings.openai_api_key, timeout=60.0, max_retries=3)
