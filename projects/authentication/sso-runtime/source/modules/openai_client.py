"""Shared OpenAI client construction for web-worker-safe HTTP behavior."""

import os

import httpx
from openai import OpenAI


def create_openai_client(api_key):
    """Create a client without consulting OS proxy settings unless explicitly enabled."""
    trust_env = os.getenv("OPENAI_HTTP_TRUST_ENV", "false").strip().lower() in {
        "1", "true", "yes", "on"
    }
    return OpenAI(
        api_key=api_key,
        http_client=httpx.Client(trust_env=trust_env),
    )
