from __future__ import annotations

import re
from urllib.parse import urlencode

from app.core.config import settings


CLIENT_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def get_app_base_path() -> str:
    configured = (settings.app_base_path or "").strip().strip("/")
    return f"/{configured}" if configured else ""


def with_app_base_path(path: str) -> str:
    base_path = get_app_base_path()
    clean_path = "/" + str(path or "").strip().lstrip("/")
    if clean_path == "/":
        return f"{base_path}/" if base_path else "/"
    return f"{base_path}{clean_path}"


def strip_app_base_path(path: str) -> str:
    base_path = get_app_base_path()
    if not base_path:
        return path
    if path == base_path:
        return "/"
    if path.startswith(f"{base_path}/"):
        return path[len(base_path):] or "/"
    return path


def validate_public_client_slug(client_slug: str) -> str:
    slug = (client_slug or "").strip()
    if not CLIENT_SLUG_PATTERN.fullmatch(slug):
        raise ValueError("Invalid client slug.")
    return slug


def get_public_chatbot_path(
    client_slug: str,
    *,
    query: dict[str, str] | None = None,
) -> str:
    validate_public_client_slug(client_slug)
    path = with_app_base_path("/")
    if query:
        clean_query = {
            str(key): str(value)
            for key, value in query.items()
            if value is not None and str(value) != ""
        }
        if clean_query:
            path = f"{path}?{urlencode(clean_query)}"
    return path

def build_public_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def append_original_query(path: str, query_string: str | None) -> str:
    query = (query_string or "").strip()
    if not query:
        return path
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}{query}"
