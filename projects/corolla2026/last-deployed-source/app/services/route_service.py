from __future__ import annotations

import re
from urllib.parse import urlencode

from app.constants import PUBLIC_BASE_PATH


CLIENT_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DEFAULT_PUBLIC_BASE_PATH = "/central-trade-auto-co-markazia-toyota-jordan"


def clean_base_path(path: str = PUBLIC_BASE_PATH) -> str:
    cleaned = "/" + str(path or "").strip().strip("/")
    return cleaned.rstrip("/") or DEFAULT_PUBLIC_BASE_PATH


def validate_public_client_slug(client_slug: str) -> str:
    slug = (client_slug or "").strip()
    if not CLIENT_SLUG_PATTERN.fullmatch(slug):
        raise ValueError("Invalid client slug.")
    return slug


def get_public_base_path() -> str:
    return clean_base_path()


def get_generator_path() -> str:
    return get_public_base_path()


def get_embed_loader_path() -> str:
    return f"{get_public_base_path()}/embed/jormall-chatbot.js"


EMBED_LOADER_PATH = get_embed_loader_path()


def get_public_chatbot_path(
    client_slug: str,
    *,
    query: dict[str, str] | None = None,
) -> str:
    validate_public_client_slug(client_slug)
    path = f"{get_public_base_path()}/"
    if query:
        clean_query = {
            str(key): str(value)
            for key, value in query.items()
            if value is not None and str(value) != ""
        }
        if clean_query:
            path = f"{path}?{urlencode(clean_query)}"
    return path


def get_public_embed_chatbot_path(client_slug: str) -> str:
    return get_public_chatbot_path(client_slug, query={"embed": "1"})


def build_public_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def append_original_query(path: str, query_string: str | None) -> str:
    query = (query_string or "").strip()
    if not query:
        return path
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}{query}"
