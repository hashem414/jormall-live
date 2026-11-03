"""إعدادات التطبيق — تُقرأ من .env مرة وحدة وتُستخدم بكل الطبقات."""

from __future__ import annotations

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # OpenAI
    openai_api_key: str
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    chat_model: str = "gpt-4o"
    utility_model: str = "gpt-4o-mini"

    # الصوت (OpenAI audio API)
    voice_enabled: bool = True
    stt_model: str = "gpt-4o-transcribe"      # كلام → نص
    tts_model: str = "gpt-4o-mini-tts"        # نص → كلام
    tts_voice: str = "shimmer"                # صوت أنثوي هادئ يناسب نبرة العيادة
    tts_format: str = "mp3"
    voice_max_upload_mb: float = 20.0         # حد حجم الملف المرفوع
    tts_max_chars: int = 1200                 # سقف طول النص المحوّل لصوت

    # PostgreSQL
    database_url: str = "postgresql://karmalite:REDACTED_CONFIGURE_LOCALLY@localhost:5432/karmalite"

    # Chunking
    chunk_max_chars: int = 900
    chunk_min_chars: int = 180
    chunk_overlap_chars: int = 120

    # Retrieval
    retrieve_candidates: int = 30      # كم مرشح من كل طريقة بحث قبل الدمج
    retrieve_top_k: int = 8            # كم شانك بينحط بالبرومبت
    min_relevance_score: float = 0.15  # عتبة تشابه cosine لاعتبار النتيجة ذات صلة
    rerank_enabled: bool = False
    history_turns: int = 8

    # App
    clinic_name: str = "Karmalite"
    clinic_phone: str = "(06) 586 8024"      # الأرضي الرئيسي — الحجز والاستفسارات اليومية
    emergency_phone: str = "07 7586 8024"    # الموبايل الرئيسي — يُستخدم أيضاً للتواصل العاجل
    log_level: str = "INFO"

    # موقع العيادة — تُملأ من .env. لو فاضية، البوت بيحوّل للاستقبال بدل ما يخترع عنوان.
    clinic_area: str = ""          # المنطقة، مثل: عبدون / الصويفية
    clinic_street: str = ""        # اسم الشارع
    clinic_building: str = ""      # اسم أو رقم المبنى
    clinic_floor: str = ""         # رقم الطابق
    clinic_landmark: str = ""      # علامة مميزة قريبة (اختياري)
    clinic_address_ar: str = ""    # العنوان بالعربي بسطر واحد (يتجاوز التركيب التلقائي)
    clinic_address_en: str = ""    # العنوان بالإنجليزي بسطر واحد
    clinic_maps_url: str = ""      # رابط الموقع على خرائط جوجل

    # لوحة الأدمن — لازم تحطها بـ .env وإلا صفحة الأدمن بترفض كل الطلبات
    admin_token: str = ""

    # ── التحقق بالبريد الإلكتروني قبل تثبيت الموعد ──
    # التحقق بينشّط لحاله لما smtp_host ينتعبّى. بدونه الحجز بيضل شغّال زي قبل
    # (مع تحذير بالسجل) بدل ما ينكسر على عيادة شغّالة.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_starttls: bool = True
    smtp_timeout_seconds: float = 20.0
    mail_from: str = ""                    # فاضي = بنستخدم smtp_user
    mail_from_name: str = "Karmalite Clinic"
    email_code_ttl_minutes: int = 15
    email_code_max_attempts: int = 5       # محاولات إدخال خاطئة قبل إبطال الرمز
    email_codes_per_hour: int = 5          # حدّ إرسال الرموز لنفس الإيميل

    # ── سقوف ضد الحجز العشوائي ──
    max_active_appointments_per_phone: int = 3
    max_bookings_per_hour_per_phone: int = 5

    # JorMall / JOSMS Service SMS
    sms_enabled: bool = False
    josms_api_url: str = (
        "https://www.josms.net/SMSServices/Clients/Prof/SingleSMS/"
        "SMSService.asmx/SendSMS"
    )
    josms_sender_id: str = ""
    josms_accname: str = ""
    josms_accpass: SecretStr = SecretStr("")
    josms_timeout_seconds: float = 30.0
    josms_max_attempts: int = 4
    josms_retry_minutes: int = 5
    # Exact comma-separated provider success responses. Until JorMall supplies
    # the official response map, successful HTTP requests stay unverified.
    josms_success_responses: str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
