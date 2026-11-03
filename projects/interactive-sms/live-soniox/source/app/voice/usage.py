from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import SessionLocal
from app.models.voice_usage import VoiceApiRequest


log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VoiceUsageHandle:
    id: UUID
    client_reference_id: str


def _fingerprint(session_id: str) -> str:
    if not session_id:
        return ""
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()


def _safe_error_type(error: BaseException | str) -> str:
    value = error if isinstance(error, str) else type(error).__name__
    return str(value).strip()[:100]


def begin_voice_request(
    *,
    client_slug: str,
    operation: str,
    model: str,
    language: str,
    voice: str = "",
    session_id: str = "",
    input_audio_bytes: int = 0,
    input_text_characters: int = 0,
    provider: str = "soniox",
) -> VoiceUsageHandle | None:
    request_id = uuid4()
    reference = f"jm:{client_slug}:{operation}:{request_id}"
    try:
        with SessionLocal.begin() as db:
            db.add(
                VoiceApiRequest(
                    id=request_id,
                    client_slug=client_slug,
                    provider=provider,
                    operation=operation,
                    model=model,
                    voice=voice,
                    language=language,
                    status="started",
                    client_reference_id=reference,
                    session_fingerprint=_fingerprint(session_id),
                    input_audio_bytes=max(0, input_audio_bytes),
                    input_text_characters=max(0, input_text_characters),
                    started_at=datetime.now(UTC),
                )
            )
        return VoiceUsageHandle(id=request_id, client_reference_id=reference)
    except SQLAlchemyError as error:
        log.warning("voice_usage_ledger_begin_failed type=%s", type(error).__name__)
        return None


def update_voice_request(handle: VoiceUsageHandle | None, **values: Any) -> None:
    if handle is None:
        return
    permitted = {
        "language", "status", "provider_request_id", "provider_request_scope",
        "cache_hit", "output_audio_bytes", "input_audio_duration_ms",
        "output_audio_duration_ms", "request_duration_ms", "first_audio_ms",
        "first_audio_at", "finished_at", "error_type",
        "input_text_tokens", "input_audio_tokens", "output_text_tokens",
        "output_audio_tokens", "estimated_cost_usd", "confirmed_cost_usd",
    }
    clean = {key: value for key, value in values.items() if key in permitted}
    if "error_type" in clean:
        clean["error_type"] = _safe_error_type(clean["error_type"])
    if not clean:
        return
    try:
        with SessionLocal.begin() as db:
            row = db.execute(
                select(VoiceApiRequest).where(VoiceApiRequest.id == handle.id)
            ).scalar_one_or_none()
            if row is None:
                return
            for key, value in clean.items():
                setattr(row, key, value)
    except SQLAlchemyError as error:
        log.warning("voice_usage_ledger_update_failed type=%s", type(error).__name__)


def complete_voice_request(handle: VoiceUsageHandle | None, **values: Any) -> None:
    update_voice_request(
        handle,
        **values,
        status="completed",
        finished_at=datetime.now(UTC),
        error_type="",
    )


def fail_voice_request(handle: VoiceUsageHandle | None, error: BaseException | str, **values: Any) -> None:
    update_voice_request(
        handle,
        **values,
        status="failed",
        finished_at=datetime.now(UTC),
        error_type=_safe_error_type(error),
    )


def cancel_voice_request(handle: VoiceUsageHandle | None, **values: Any) -> None:
    update_voice_request(
        handle,
        **values,
        status="cancelled",
        finished_at=datetime.now(UTC),
        error_type="client_cancelled",
    )
