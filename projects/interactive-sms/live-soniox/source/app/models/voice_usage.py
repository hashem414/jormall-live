from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class VoiceApiRequest(Base):
    __tablename__ = "voice_api_requests"
    __table_args__ = (
        UniqueConstraint("client_reference_id", name="uq_voice_api_requests_client_reference"),
        UniqueConstraint("provider_request_id", name="uq_voice_api_requests_provider_request"),
        Index("ix_voice_api_requests_client_started", "client_slug", "started_at"),
        Index("ix_voice_api_requests_operation_started", "operation", "started_at"),
        Index("ix_voice_api_requests_status_started", "status", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    client_slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="soniox")
    operation: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    voice: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    language: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="started")
    client_reference_id: Mapped[str] = mapped_column(String(256), nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    provider_request_scope: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    session_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    input_audio_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    output_audio_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    input_text_characters: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_audio_duration_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    output_audio_duration_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    request_duration_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    first_audio_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    input_text_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    input_audio_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    output_text_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    output_audio_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    estimated_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 10), nullable=False, default=Decimal("0"))
    confirmed_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 10), nullable=False, default=Decimal("0"))
    confirmed_input_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 10), nullable=False, default=Decimal("0"))
    confirmed_output_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 10), nullable=False, default=Decimal("0"))
    error_type: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    first_audio_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class VoiceUsageSyncState(Base):
    __tablename__ = "voice_usage_sync_states"

    provider: Mapped[str] = mapped_column(String(40), primary_key=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_imported_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_imported_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
