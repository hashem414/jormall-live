from __future__ import annotations

import os
from dataclasses import dataclass
from sqlalchemy.engine import URL


class _SecretValue:
    def __init__(self, value: str):
        self._value = value

    def get_secret_value(self) -> str:
        return self._value


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    return int(value) if value else default


def env_float(name: str, default: float) -> float:
    value = os.getenv(name, "").strip()
    return float(value) if value else default


def secret(name: str) -> _SecretValue | None:
    value = os.getenv(name, "").strip()
    return _SecretValue(value) if value else None


def build_database_url(
    *,
    username: str,
    password: str,
    host: str,
    port: int,
    database: str,
) -> str:
    url = URL.create(
        drivername="postgresql+psycopg",
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
    )
    return url.render_as_string(hide_password=False)


@dataclass(frozen=True)
class Settings:
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str
    postgres_port: int
    database_url: str
    openai_api_key: _SecretValue | None = None
    openai_chat_model: str = ""
    openai_embedding_model: str = ""
    embedding_dimensions: int = 3072
    embedding_batch_size: int = 16
    retrieval_top_k: int = 5
    min_retrieval_similarity: float = 0.50
    cross_language_min_retrieval_similarity: float = 0.35
    chat_max_output_tokens: int = 220
    chat_reasoning_effort: str = "low"
    chat_verbosity: str = "low"
    max_concurrent_scrapes: int = 1
    max_upload_files: int = 20
    max_upload_file_mb: int = 25
    max_upload_total_mb: int = 250
    openai_vision_model: str = ""
    media_retrieval_enabled_default: bool = False
    media_max_images_per_collection: int = 50
    media_max_file_size_mb: int = 8
    media_max_total_collection_mb: int = 120
    media_max_pixel_dimension: int = 4096
    media_max_results_per_answer: int = 4
    media_min_similarity: float = 0.35
    media_direct_match_boost: float = 0.18
    media_context_boost: float = 0.10
    media_vision_confidence_threshold: float = 0.72
    media_analysis_concurrency: int = 2
    media_stale_processing_minutes: int = 15
    media_public_cache_seconds: int = 3600
    public_chatbot_base_url: str = ""
    app_base_path: str = ""
    callback_admin_token: _SecretValue | None = None
    callback_dashboard_password: _SecretValue | None = None
    dashboard_username: str = ""
    dashboard_password: _SecretValue | None = None
    session_secret: _SecretValue | None = None
    csrf_secret: _SecretValue | None = None
    cookie_secure: bool = False
    sales_callback_dashboard_enabled: bool = True
    chat_history_dashboard_enabled: bool = True


def get_settings() -> Settings:
    postgres_user = os.getenv("POSTGRES_USER", "chatbot").strip() or "chatbot"
    postgres_password = os.getenv("POSTGRES_PASSWORD", "").strip()
    postgres_db = os.getenv("POSTGRES_DB", "chatbot").strip() or "chatbot"
    postgres_host = os.getenv("POSTGRES_HOST", "postgres").strip() or "postgres"
    postgres_port = env_int("POSTGRES_PORT", 5432)
    database_url = build_database_url(
        username=postgres_user,
        password=postgres_password,
        host=postgres_host,
        port=postgres_port,
        database=postgres_db,
    )
    return Settings(
        postgres_user=postgres_user,
        postgres_password=postgres_password,
        postgres_db=postgres_db,
        postgres_host=postgres_host,
        postgres_port=postgres_port,
        database_url=database_url,
        openai_api_key=secret("OPENAI_API_KEY"),
        openai_chat_model=os.getenv("OPENAI_CHAT_MODEL", "").strip(),
        openai_embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "").strip(),
        embedding_dimensions=env_int("OPENAI_EMBEDDING_DIMENSIONS", env_int("EMBEDDING_DIMENSIONS", 3072)),
        embedding_batch_size=env_int("EMBEDDING_BATCH_SIZE", 16),
        retrieval_top_k=env_int("RETRIEVAL_TOP_K", 5),
        min_retrieval_similarity=env_float("MIN_RETRIEVAL_SIMILARITY", 0.50),
        cross_language_min_retrieval_similarity=env_float("CROSS_LANGUAGE_MIN_RETRIEVAL_SIMILARITY", 0.35),
        chat_max_output_tokens=env_int("CHAT_MAX_OUTPUT_TOKENS", 220),
        chat_reasoning_effort=os.getenv("CHAT_REASONING_EFFORT", "low").strip() or "low",
        chat_verbosity=os.getenv("CHAT_VERBOSITY", "low").strip() or "low",
        openai_vision_model=os.getenv("OPENAI_VISION_MODEL", "").strip(),
        public_chatbot_base_url=os.getenv("PUBLIC_CHATBOT_BASE_URL", "").strip(),
        app_base_path=os.getenv("APP_BASE_PATH", "").strip(),
        callback_admin_token=secret("CALLBACK_ADMIN_TOKEN"),
        callback_dashboard_password=secret("CALLBACK_DASHBOARD_PASSWORD"),
        dashboard_username=os.getenv("DASHBOARD_USERNAME", "").strip(),
        dashboard_password=secret("DASHBOARD_PASSWORD"),
        session_secret=secret("SESSION_SECRET"),
        csrf_secret=secret("CSRF_SECRET"),
        cookie_secure=env_bool("COOKIE_SECURE", False),
        sales_callback_dashboard_enabled=env_bool("SALES_CALLBACK_DASHBOARD_ENABLED", True),
        chat_history_dashboard_enabled=env_bool("CHAT_HISTORY_DASHBOARD_ENABLED", True),
    )


settings = get_settings()
