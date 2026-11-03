from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _as_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    extension_shared_key: str
    model: str
    reasoning_effort: str
    max_output_tokens: int
    openai_base_url: str
    vector_store_id: str
    search_max_results: int
    search_min_score: float
    max_request_bytes: int
    max_question_chars: int
    max_web_context_chars: int
    connect_timeout_seconds: int
    read_timeout_seconds: int
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_use_tls: bool
    sales_notification_to: str
    sales_notification_from: str

    @property
    def openai_enabled(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def retrieval_enabled(self) -> bool:
        return self.openai_enabled and bool(self.vector_store_id)

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host and self.sales_notification_from)


def _vector_store_from_manifest(backend_root: Path) -> str:
    configured = os.getenv("DOCUMENT_MANIFEST_PATH", "vector_store_manifest.json")
    manifest_path = Path(configured)
    if not manifest_path.is_absolute():
        manifest_path = backend_root / manifest_path
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return ""
    return str(payload.get("vector_store_id") or "").strip()


def load_settings(backend_root: Path | None = None) -> Settings:
    root = backend_root or Path(__file__).resolve().parents[1]
    vector_store_id = os.getenv("OPENAI_VECTOR_STORE_ID", "").strip()
    if not vector_store_id:
        vector_store_id = _vector_store_from_manifest(root)
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        extension_shared_key=os.getenv("SMA_EXTENSION_SHARED_KEY", "").strip(),
        model=os.getenv("OPENAI_MODEL", "gpt-6-luna").strip() or "gpt-6-luna",
        reasoning_effort=os.getenv("OPENAI_REASONING_EFFORT", "none").strip() or "none",
        max_output_tokens=max(1000, min(_as_int("OPENAI_MAX_OUTPUT_TOKENS", 4000), 16000)),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        vector_store_id=vector_store_id,
        search_max_results=max(1, min(_as_int("DOCUMENT_SEARCH_MAX_RESULTS", 6), 12)),
        search_min_score=max(0.0, min(_as_float("DOCUMENT_SEARCH_MIN_SCORE", 0.30), 1.0)),
        max_request_bytes=max(64_000, _as_int("MAX_REQUEST_BYTES", 2_097_152)),
        max_question_chars=max(100, _as_int("MAX_QUESTION_CHARS", 4_000)),
        max_web_context_chars=max(5_000, _as_int("MAX_WEB_CONTEXT_CHARS", 80_000)),
        connect_timeout_seconds=max(1, _as_int("OPENAI_CONNECT_TIMEOUT_SECONDS", 10)),
        read_timeout_seconds=max(10, _as_int("OPENAI_READ_TIMEOUT_SECONDS", 150)),
        smtp_host=os.getenv("SMTP_HOST", "").strip(),
        smtp_port=_as_int("SMTP_PORT", 587),
        smtp_username=os.getenv("SMTP_USERNAME", "").strip(),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        smtp_use_tls=_as_bool(os.getenv("SMTP_USE_TLS"), True),
        sales_notification_to=os.getenv("SALES_NOTIFICATION_TO", "sales@jormall.com").strip(),
        sales_notification_from=os.getenv("SALES_NOTIFICATION_FROM", "").strip(),
    )
