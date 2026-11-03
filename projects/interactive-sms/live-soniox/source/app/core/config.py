from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str

    openai_api_key: SecretStr | None = None
    openai_chat_model: str = "gpt-5.6-luna"
    openai_embedding_model: str = "text-embedding-3-large"
    openai_transcription_model: str = "gpt-transcribe"
    openai_live_transcription_model: str = "gpt-live-transcribe"
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "marin"
    openai_audio_request_timeout_seconds: int = Field(default=45, ge=5, le=120)
    openai_chat_input_cost_per_million_usd: float = Field(default=0.0, ge=0.0)
    openai_chat_output_cost_per_million_usd: float = Field(default=0.0, ge=0.0)
    openai_embedding_cost_per_million_usd: float = Field(default=0.0, ge=0.0)

    deepgram_api_key: SecretStr | None = None
    deepgram_stt_model: str = "nova-3"
    deepgram_request_timeout_seconds: int = Field(default=30, ge=5, le=90)
    deepgram_english_tts_model: str = "flux-kit-en"
    deepgram_english_tts_speed: float = Field(default=1.05, ge=0.85, le=1.15)

    deepgram_arabic_tts_model: str = "sonic-3.6"
    deepgram_arabic_tts_voice_id: str = "b068aef8-2c18-4a1d-bafb-e8f6d2239d60"
    deepgram_arabic_tts_speed: float = Field(default=1.08, ge=0.7, le=1.5)

    soniox_api_key: SecretStr | None = None
    soniox_stt_model: str = "stt-rt-v5"
    soniox_stt_fallback_model: str = "stt-async-v5"
    soniox_stt_workflow: Literal["async", "realtime"] = "async"
    soniox_stt_min_confidence: float = Field(default=0.985, ge=0.0, le=1.0)
    soniox_tts_model: str = "tts-rt-v2"
    soniox_tts_voice: str = "Kayla"
    soniox_tts_english_speed: float = Field(default=1.02, ge=0.7, le=1.3)
    soniox_tts_arabic_speed: float = Field(default=1.06, ge=0.7, le=1.3)
    soniox_tts_reduce_silence: bool = True
    soniox_request_timeout_seconds: int = Field(default=45, ge=5, le=90)
    voice_stt_provider: Literal["soniox", "openai"] = "soniox"
    voice_tts_provider: Literal["soniox", "openai"] = "soniox"
    voice_max_upload_mb: int = Field(default=8, ge=1, le=25)
    voice_max_recording_seconds: int = Field(default=45, ge=5, le=120)
    voice_tts_max_characters: int = Field(default=1400, ge=100, le=2000)
    voice_speech_summary_max_characters: int = Field(default=360, ge=160, le=700)
    voice_usage_sync_enabled: bool = False
    voice_usage_sync_interval_seconds: int = Field(default=900, ge=60, le=86400)
    voice_usage_sync_lookback_days: int = Field(default=30, ge=1, le=31)
    voice_usage_sync_max_pages: int = Field(default=20, ge=1, le=100)
    voice_daily_budget_usd: float = Field(default=0.0, ge=0.0, le=1000000.0)
    voice_monthly_budget_usd: float = Field(default=0.0, ge=0.0, le=10000000.0)

    voice_enabled: bool = True
    voice_generation_timeout_seconds: int = Field(default=90, ge=5, le=180)
    voice_browser_fallback_enabled: bool = False
    google_cloud_project: str = ""
    google_cloud_region: str = "global"
    gemini_tts_model: str = "gemini-2.5-flash-tts"
    gemini_tts_voice_en: str = "Kore"
    gemini_tts_voice_ar: str = "Achernar"
    gemini_tts_language_en: str = "en-US"
    gemini_tts_language_ar: str = "ar-EG"
    gemini_tts_cache_ttl_seconds: int = Field(default=900, ge=0, le=86400)

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
        default=2000,
        ge=100,
        le=2000,
    )

    chat_reasoning_effort: str = "low"
    chat_verbosity: str = "medium"
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
    app_base_path: str = "/interactive-sms"
    enable_api_docs: bool = False
    callback_dashboard_password: SecretStr | None = None
    client_chatgpt_monthly_token_limit: int = Field(default=30_000_000, ge=1, le=10_000_000_000)
    client_voice_input_monthly_minutes: int = Field(default=300, ge=1, le=1_000_000)
    client_voice_output_monthly_minutes: int = Field(default=300, ge=1, le=1_000_000)
    chat_history_enabled: bool = True
    admin_session_timeout: int = Field(default=8 * 60 * 60, ge=300, le=7 * 24 * 60 * 60)
    chat_export_max_rows: int = Field(default=5000, ge=1, le=50000)
    app_timezone: str = "Asia/Amman"
    chatbot_setup_price_jod: int = Field(default=150, ge=1, le=100000)
    chatbot_hosting_1_month_jod: int = Field(default=30, ge=1, le=100000)
    chatbot_hosting_3_months_jod: int = Field(default=75, ge=1, le=100000)
    chatbot_hosting_6_months_jod: int = Field(default=140, ge=1, le=100000)
    chatbot_hosting_12_months_jod: int = Field(default=200, ge=1, le=100000)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
