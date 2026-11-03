from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from sqlalchemy import or_, select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.voice_usage import VoiceApiRequest, VoiceUsageSyncState
from app.voice.providers.soniox import SonioxSpeechError, _json_request


log = logging.getLogger(__name__)


def _dt(value) -> datetime | None:
    if not value:
        return None
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.replace(tzinfo=UTC) if result.tzinfo is None else result
    except ValueError:
        return None


def _decimal(value) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _number(payload: dict, *keys: str) -> int:
    for key in keys:
        if key in payload and payload[key] is not None:
            try:
                return max(0, int(float(payload[key])))
            except (TypeError, ValueError):
                pass
    return 0


def _costs(item: dict) -> tuple[Decimal, Decimal, Decimal]:
    costs = item.get("costs") if isinstance(item.get("costs"), dict) else item
    input_cost = _decimal(costs.get("input_cost_usd") or costs.get("input_audio_cost_usd") or costs.get("input_cost"))
    output_cost = _decimal(costs.get("output_cost_usd") or costs.get("output_audio_cost_usd") or costs.get("output_cost"))
    total = _decimal(costs.get("total_cost_usd") or costs.get("total_cost") or item.get("cost_usd"))
    if not total:
        total = input_cost + output_cost
    return total, input_cost, output_cost


def apply_usage_log(db, item: dict, reconciled_at: datetime | None = None) -> bool:
    provider_id = str(item.get("uuid") or item.get("request_id") or item.get("id") or "").strip()
    reference = str(item.get("client_reference_id") or "").strip()
    if not provider_id and not reference:
        return False
    filters = []
    if reference:
        filters.append(VoiceApiRequest.client_reference_id == reference)
    if provider_id:
        filters.append(VoiceApiRequest.provider_request_id == provider_id)
    row = db.execute(select(VoiceApiRequest).where(or_(*filters))).scalar_one_or_none()
    model = str(item.get("model") or "unknown")[:80]
    operation = "tts" if model.startswith("tts-") else "stt" if model.startswith("stt-") else "other"
    started = _dt(item.get("start_time") or item.get("started_at")) or datetime.now(UTC)
    finished = _dt(item.get("end_time") or item.get("finished_at"))
    if row is None:
        row = VoiceApiRequest(
            client_slug="provider-unattributed",
            provider="soniox",
            operation=operation,
            model=model,
            status="completed",
            client_reference_id=reference or f"soniox:{provider_id}",
            provider_request_id=provider_id or None,
            started_at=started,
        )
        db.add(row)
    total_cost, input_cost, output_cost = _costs(item)
    row.provider_request_id = provider_id or row.provider_request_id
    row.provider_request_scope = str(item.get("request_scope") or "")[:80]
    row.model = model
    row.operation = operation if row.operation == "other" else row.operation
    row.status = "completed"
    row.provider_started_at = started
    row.provider_finished_at = finished
    row.input_text_tokens = _number(item, "input_text_tokens")
    row.input_audio_tokens = _number(item, "input_audio_tokens")
    row.output_text_tokens = _number(item, "output_text_tokens")
    row.output_audio_tokens = _number(item, "output_audio_tokens")
    row.input_audio_duration_ms = _number(item, "input_audio_duration_ms")
    row.output_audio_duration_ms = _number(item, "output_audio_duration_ms")
    if not row.request_duration_ms:
        row.request_duration_ms = _number(item, "duration_ms")
    row.confirmed_cost_usd = total_cost
    row.confirmed_input_cost_usd = input_cost
    row.confirmed_output_cost_usd = output_cost
    row.reconciled_at = reconciled_at or datetime.now(UTC)
    return True


def _items(payload: dict) -> list[dict]:
    for key in ("usage_logs", "logs", "items", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def sync_soniox_usage() -> dict[str, object]:
    now = datetime.now(UTC)
    with SessionLocal.begin() as db:
        state = db.get(VoiceUsageSyncState, "soniox")
        if state is None:
            state = VoiceUsageSyncState(provider="soniox")
            db.add(state)
        state.last_attempt_at = now
        start = (state.last_success_at - timedelta(hours=2)) if state.last_success_at else (now - timedelta(days=settings.voice_usage_sync_lookback_days))
        state.last_window_start = start
        state.last_window_end = now

    imported = 0
    cursor = ""
    try:
        for _ in range(settings.voice_usage_sync_max_pages):
            query = {
                "start_time": start.isoformat().replace("+00:00", "Z"),
                "end_time": now.isoformat().replace("+00:00", "Z"),
                "limit": "1000",
            }
            if cursor:
                query["cursor"] = cursor
            payload = _json_request(
                f"/usage-logs?{urlencode(query)}",
                user_error="Soniox usage synchronization failed.",
            )
            page = _items(payload)
            with SessionLocal.begin() as db:
                for item in page:
                    imported += int(apply_usage_log(db, item, now))
            cursor = str(payload.get("next_page_cursor") or payload.get("next_cursor") or "").strip()
            if not cursor or not page:
                break
        with SessionLocal.begin() as db:
            state = db.get(VoiceUsageSyncState, "soniox")
            state.last_success_at = now
            state.last_imported_count = imported
            state.total_imported_count += imported
            state.consecutive_failures = 0
            state.last_error = ""
        return {"status": "ok", "imported": imported, "window_start": start.isoformat(), "window_end": now.isoformat()}
    except Exception as error:
        with SessionLocal.begin() as db:
            state = db.get(VoiceUsageSyncState, "soniox")
            state.consecutive_failures += 1
            state.last_error = type(error).__name__[:200]
        log.warning("soniox_usage_sync_failed type=%s", type(error).__name__)
        raise


async def run_voice_usage_sync_worker() -> None:
    if not settings.voice_usage_sync_enabled:
        return
    while True:
        try:
            await asyncio.to_thread(sync_soniox_usage)
        except Exception:
            pass
        await asyncio.sleep(settings.voice_usage_sync_interval_seconds)
