from functools import lru_cache

from openai import OpenAI

from app.core.config import settings


@lru_cache
def get_openai_client() -> OpenAI:
    if settings.openai_api_key is None:
        raise RuntimeError(
            "OPENAI_API_KEY is missing. Add it to your local .env file."
        )

    api_key = settings.openai_api_key.get_secret_value().strip()

    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is empty. Add a valid key to your local .env file."
        )

    return OpenAI(api_key=api_key)
