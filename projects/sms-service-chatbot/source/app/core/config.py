from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str

    openai_api_key: SecretStr | None = None
    openai_chat_model: str = "gpt-5.5"
    openai_embedding_model: str = "text-embedding-3-large"
    openai_vision_model: str = ""

    embedding_dimensions: int = 3072
    embedding_batch_size: int = Field(
        default=16,
        ge=1,
        le=256,
    )

    retrieval_top_k: int = Field(
        default=5,
        ge=1,
        le=10,
    )

    min_retrieval_similarity: float = Field(
        default=0.50,
        ge=0.0,
        le=1.0,
    )

    cross_language_min_retrieval_similarity: float = Field(
        default=0.35,
        ge=0.0,
        le=1.0,
    )

    chat_max_output_tokens: int = Field(
        default=220,
        ge=100,
        le=2000,
    )

    chat_reasoning_effort: str = "low"
    chat_verbosity: str = "low"
    max_concurrent_scrapes: int = Field(
        default=1,
        ge=1,
        le=4,
    )
    max_upload_files: int = Field(
        default=20,
        ge=1,
        le=100,
    )
    max_upload_file_mb: int = Field(
        default=25,
        ge=1,
        le=200,
    )
    max_upload_total_mb: int = Field(
        default=250,
        ge=1,
        le=2000,
    )
    public_chatbot_base_url: str = ""
    app_base_path: str = ""
    callback_admin_token: SecretStr | None = None
    callback_dashboard_password: SecretStr | None = None
    dashboard_username: str = ""
    dashboard_password: SecretStr | None = None
    session_secret: SecretStr | None = None
    csrf_secret: SecretStr | None = None
    cookie_secure: bool = True
    sales_callback_dashboard_enabled: bool = True
    chat_history_dashboard_enabled: bool = True
    media_retrieval_enabled_default: bool = False
    media_max_images_per_collection: int = Field(default=50, ge=1, le=500)
    media_max_file_size_mb: int = Field(default=8, ge=1, le=50)
    media_max_total_collection_mb: int = Field(default=120, ge=1, le=1000)
    media_max_pixel_dimension: int = Field(default=4096, ge=512, le=12000)
    media_max_results_per_answer: int = Field(default=4, ge=1, le=8)
    media_min_similarity: float = Field(default=0.35, ge=0.0, le=1.0)
    media_direct_match_boost: float = Field(default=0.18, ge=0.0, le=1.0)
    media_context_boost: float = Field(default=0.10, ge=0.0, le=1.0)
    media_vision_confidence_threshold: float = Field(default=0.72, ge=0.0, le=1.0)
    media_analysis_concurrency: int = Field(default=2, ge=1, le=6)
    media_stale_processing_minutes: int = Field(default=15, ge=1, le=1440)
    media_public_cache_seconds: int = Field(default=3600, ge=0, le=31536000)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
