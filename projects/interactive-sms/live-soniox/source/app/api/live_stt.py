"""Temporary live PCM transcription proxy for the three-port voice matrix."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import time
import urllib.error
import urllib.request

import websockets
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.database import SessionLocal
from app.language_detection import detect_supported_language
from app.sessions.access import ensure_lead_capture_completed
from app.voice.providers.soniox import (
    SONIOX_CONTEXT,
    SONIOX_STT_WEBSOCKET_URL,
    parse_soniox_transcription_events,
    soniox_api_key,
)
from app.voice.usage import (
    begin_voice_request,
    cancel_voice_request,
    complete_voice_request,
    fail_voice_request,
)


# Match the existing public chat API namespace used by the page configuration.
router = APIRouter(prefix="/api")
TENANT = "central-e-commerce-co-ltd"
PCM_RATE = 24_000
PCM_BYTES_PER_SECOND = PCM_RATE * 2
# Dedicated transcription sessions use the Realtime transport with the
# transcription intent.  Passing the transcription model as the base
# Realtime model is rejected as invalid before session.update is processed.
OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime?intent=transcription"
OPENAI_LIVE_SESSION_URL = "https://api.openai.com/v1/live/sessions"
OPENAI_LIVE_MODEL = "gpt-live-1"
OPENAI_LIVE_VOICE = "marin"


class WebRTCSessionPayload(BaseModel):
    """An authorized browser SDP offer; the OpenAI key never reaches the browser."""

    model_config = ConfigDict(extra="forbid")

    sdp: str = Field(min_length=1, max_length=65_536)
    lead_session_id: str = Field(min_length=1, max_length=120)
    language: str = Field(default="en", max_length=8)

    @field_validator("sdp")
    @classmethod
    def preserve_sdp(cls, value: str) -> str:
        # SDP is line-oriented and its terminating CRLF is significant.
        if not value.strip():
            raise ValueError("The SDP offer is empty.")
        return value

    @field_validator("lead_session_id")
    @classmethod
    def strip_required(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("A required WebRTC session value is empty.")
        return clean

    @field_validator("language")
    @classmethod
    def supported_language(cls, value: str) -> str:
        clean = value.strip().lower()
        if clean not in {"en", "ar"}:
            raise ValueError("Language must be en or ar.")
        return clean


def _openai_key() -> str:
    if settings.openai_api_key is None:
        raise RuntimeError("OpenAI speech services are not configured.")
    value = settings.openai_api_key.get_secret_value().strip()
    if not value:
        raise RuntimeError("OpenAI speech services are not configured.")
    return value


def _language(value: object) -> str:
    clean = str(value or "auto").strip().lower()
    return clean if clean in {"en", "ar", "auto"} else "auto"


def _exchange_live_sdp(payload: WebRTCSessionPayload) -> dict:
    language_instruction = (
        "Speak Modern Standard Arabic when the user speaks Arabic."
        if payload.language == "ar"
        else "Speak clear English when the user speaks English."
    )
    body = json.dumps(
        {
            "session": {
                "model": OPENAI_LIVE_MODEL,
                "audio": {"output": {"voice": OPENAI_LIVE_VOICE}},
                "instructions": (
                    "You are the voice transport for the JorMall assistant. "
                    "Delegate every business question to the client backend. Never answer "
                    "from your own knowledge and do not invent facts. Wait for verified "
                    "client commentary, then say only that result concisely without adding "
                    "new claims. Preserve names, numbers, prices, dates and contact details. "
                    + language_instruction
                ),
                "delegation": {"type": "client"},
            },
            "transport": {"type": "webrtc", "sdp": payload.sdp},
        },
        ensure_ascii=False,
    ).encode("utf-8")
    safety_id = hashlib.sha256(payload.lead_session_id.encode("utf-8")).hexdigest()
    request = urllib.request.Request(
        OPENAI_LIVE_SESSION_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {_openai_key()}",
            "Content-Type": "application/json",
            "OpenAI-Safety-Identifier": safety_id,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.loads(response.read(262_144))
    except urllib.error.HTTPError as error:
        # Reflect only bounded structured validation metadata, never request data or headers.
        error_type = "upstream_error"
        error_code = ""
        error_message = ""
        try:
            upstream = json.loads(error.read(65_536))
            detail = upstream.get("error") if isinstance(upstream, dict) else None
            if isinstance(detail, dict):
                error_type = str(detail.get("type") or error_type)[:80]
                error_code = str(detail.get("code") or "")[:80]
                error_message = str(detail.get("message") or "")[:240]
        except Exception:
            pass
        suffix = ": ".join(part for part in (error_type, error_code, error_message) if part)
        raise RuntimeError(
            f"OpenAI Live session creation failed with status {error.code}: {suffix}"
        ) from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError("OpenAI Live session creation timed out or was unavailable.") from error
    if not isinstance(result, dict):
        raise RuntimeError("OpenAI Live returned an invalid session response.")
    session = result.get("session") if isinstance(result.get("session"), dict) else {}
    transport = result.get("transport") if isinstance(result.get("transport"), dict) else {}
    if not str(session.get("id") or "").strip() or not str(transport.get("sdp") or "").strip():
        raise RuntimeError("OpenAI Live returned an incomplete session response.")
    return result


@router.post("/chat/{client_slug}/webrtc-session", status_code=201)
async def create_webrtc_session(
    client_slug: str,
    payload: WebRTCSessionPayload,
    request: Request,
):
    """Create a private GPT-Live WebRTC session after tenant/session authorization."""
    if client_slug != TENANT:
        raise HTTPException(status_code=404, detail="Client chatbot not found.")
    origin = (request.headers.get("origin") or "").rstrip("/")
    expected_origin = f"{request.url.scheme}://{request.url.netloc}".rstrip("/")
    if origin and origin != expected_origin:
        raise HTTPException(status_code=403, detail="Unexpected request origin.")
    with SessionLocal() as db:
        ensure_lead_capture_completed(
            db=db,
            client_slug=TENANT,
            session_id=payload.lead_session_id,
        )
    try:
        return await run_in_threadpool(_exchange_live_sdp, payload)
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


async def _initial_message(socket: WebSocket) -> tuple[str, str]:
    message = await asyncio.wait_for(socket.receive_json(), timeout=8)
    if message.get("type") != "start":
        raise ValueError("The live transcription start message is missing.")
    lead_session_id = str(message.get("lead_session_id") or "").strip()
    if not lead_session_id:
        raise ValueError("The authorized lead session is missing.")
    language = _language(message.get("language"))
    with SessionLocal() as db:
        ensure_lead_capture_completed(
            db=db, client_slug=TENANT, session_id=lead_session_id
        )
    return lead_session_id, language


async def _send_audio(socket: WebSocket, provider, *, openai: bool) -> int:
    total = 0
    maximum = settings.voice_max_recording_seconds * PCM_BYTES_PER_SECOND + PCM_RATE
    while True:
        message = await socket.receive()
        if message["type"] == "websocket.disconnect":
            raise WebSocketDisconnect(message.get("code", 1000))
        data = message.get("bytes")
        if data is not None:
            total += len(data)
            if total > maximum:
                raise ValueError("The live recording exceeded its allowed duration.")
            if openai:
                await provider.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": base64.b64encode(data).decode("ascii"),
                }))
            else:
                await provider.send(data)
            continue
        text = message.get("text") or ""
        try:
            control = json.loads(text)
        except json.JSONDecodeError:
            control = {}
        if control.get("type") == "cancel":
            raise WebSocketDisconnect(1000)
        if control.get("type") == "stop":
            if not total:
                raise ValueError("The live recording is empty.")
            if openai:
                await provider.send(json.dumps({"type": "input_audio_buffer.commit"}))
            else:
                await provider.send("")
            return total


async def _receive_soniox(socket: WebSocket, provider) -> tuple[str, str, str]:
    events: list[dict] = []
    request_id = ""
    while True:
        raw = await provider.recv()
        if not isinstance(raw, str):
            continue
        event = json.loads(raw)
        if event.get("error_code"):
            raise RuntimeError(str(event.get("error_message") or event["error_code"]))
        events.append(event)
        request_id = str(event.get("request_id") or request_id)
        tokens = event.get("tokens") if isinstance(event.get("tokens"), list) else []
        partial = "".join(str(token.get("text") or "") for token in tokens if isinstance(token, dict)).replace("<end>", "").strip()
        if partial:
            await socket.send_json({"type": "partial", "transcript": partial})
        if event.get("finished") is True:
            result = parse_soniox_transcription_events(events, language="auto")
            transcript = result.transcript.removesuffix("<end>").strip()
            return transcript, result.provider_language, result.request_id or request_id


async def _receive_openai(socket: WebSocket, provider, preferred: str) -> tuple[str, str, str]:
    request_id = ""
    while True:
        event = json.loads(await provider.recv())
        event_type = str(event.get("type") or "")
        request_id = str(event.get("event_id") or request_id)
        if event_type == "error":
            error = event.get("error") if isinstance(event.get("error"), dict) else {}
            raise RuntimeError(str(error.get("message") or "OpenAI live transcription failed."))
        if event_type == "conversation.item.input_audio_transcription.delta":
            delta = str(event.get("delta") or "")
            if delta:
                await socket.send_json({"type": "partial", "delta": delta})
        if event_type == "conversation.item.input_audio_transcription.completed":
            transcript = str(event.get("transcript") or "").strip()
            if not transcript:
                raise RuntimeError("No speech was detected. Please try again.")
            detected = detect_supported_language(transcript)
            if detected not in {"en", "ar"}:
                detected = preferred if preferred in {"en", "ar"} else "en"
            return transcript[:1000], detected, request_id


async def _soniox_session(socket: WebSocket, language: str, reference: str):
    provider = await websockets.connect(
        SONIOX_STT_WEBSOCKET_URL,
        open_timeout=settings.soniox_request_timeout_seconds,
        close_timeout=3,
        ping_interval=20,
        max_size=2 * 1024 * 1024,
    )
    preferred = language if language in {"en", "ar"} else "en"
    config = {
        "api_key": soniox_api_key(), "model": settings.soniox_stt_model,
        "audio_format": "pcm_s16le", "sample_rate": PCM_RATE, "num_channels": 1,
        "language_hints": [preferred, "ar" if preferred == "en" else "en"],
        "language_hints_strict": False, "enable_language_identification": True,
        "enable_speaker_diarization": False, "enable_endpoint_detection": True,
        "context": SONIOX_CONTEXT, "client_reference_id": reference,
    }
    await provider.send(json.dumps(config, ensure_ascii=False))
    return provider, asyncio.create_task(_receive_soniox(socket, provider))


async def _openai_session(socket: WebSocket, language: str, lead_session_id: str):
    model = settings.openai_live_transcription_model
    safety_id = hashlib.sha256(lead_session_id.encode("utf-8")).hexdigest()
    provider = await websockets.connect(
        OPENAI_REALTIME_URL,
        additional_headers={
            "Authorization": f"Bearer {_openai_key()}",
            "OpenAI-Safety-Identifier": safety_id,
        },
        open_timeout=settings.openai_audio_request_timeout_seconds,
        close_timeout=3,
        ping_interval=20,
        max_size=2 * 1024 * 1024,
    )
    created = json.loads(await provider.recv())
    if created.get("type") == "error":
        error = created.get("error") if isinstance(created.get("error"), dict) else {}
        raise RuntimeError(str(error.get("message") or "OpenAI transcription session failed."))
    await provider.send(json.dumps({
        "type": "session.update",
        "session": {
            "type": "transcription",
            "audio": {"input": {
                "format": {"type": "audio/pcm", "rate": PCM_RATE},
                "transcription": {
                    "model": model,
                    "prompt": "JorMall Jordan business assistant. Preserve Arabic, English, numbers, names, dates and amounts exactly.",
                    "keywords": ["JorMall", "Smart Reach SMS", "OTP", "JOD", "جورمول", "جور مول"],
                    "languages": ["en", "ar"],
                    "delay": "minimal",
                },
                "turn_detection": None,
            }},
        },
    }, ensure_ascii=False))
    updated = json.loads(await provider.recv())
    if updated.get("type") == "error":
        error = updated.get("error") if isinstance(updated.get("error"), dict) else {}
        raise RuntimeError(str(error.get("message") or "OpenAI transcription session update failed."))
    if updated.get("type") != "session.updated":
        raise RuntimeError("OpenAI transcription session did not become ready.")
    preferred = language if language in {"en", "ar"} else "en"
    return provider, asyncio.create_task(_receive_openai(socket, provider, preferred))


@router.websocket("/chat/{client_slug}/transcribe-live")
async def live_transcription(socket: WebSocket, client_slug: str):
    await socket.accept()
    started = time.perf_counter()
    usage = None
    provider = None
    receiver = None
    total = 0
    try:
        if client_slug != TENANT:
            raise ValueError("Client chatbot not found.")
        lead_session_id, language = await _initial_message(socket)
        selected = settings.voice_stt_provider
        model = settings.soniox_stt_model if selected == "soniox" else settings.openai_live_transcription_model
        usage = begin_voice_request(
            client_slug=client_slug, provider=selected, operation="stt", model=model,
            language=language, session_id=lead_session_id,
        )
        if selected == "soniox":
            provider, receiver = await _soniox_session(
                socket, language, usage.client_reference_id if usage else ""
            )
        else:
            provider, receiver = await _openai_session(socket, language, lead_session_id)
        await socket.send_json({
            "type": "ready", "provider": selected, "model": model,
            "sample_rate": PCM_RATE,
        })
        total = await asyncio.wait_for(
            _send_audio(socket, provider, openai=selected == "openai"),
            timeout=settings.voice_max_recording_seconds + 12,
        )
        transcript, detected_language, request_id = await asyncio.wait_for(
            receiver, timeout=settings.soniox_request_timeout_seconds
        )
        duration_ms = int(total / PCM_BYTES_PER_SECOND * 1000)
        complete_voice_request(
            usage, language=detected_language, input_audio_duration_ms=duration_ms,
            request_duration_ms=int((time.perf_counter() - started) * 1000),
            provider_request_id=request_id or None,
        )
        await socket.send_json({
            "type": "final", "transcript": transcript,
            "language": detected_language, "provider": selected, "model": model,
            "audio_duration_ms": duration_ms,
        })
    except WebSocketDisconnect:
        cancel_voice_request(
            usage, input_audio_duration_ms=int(total / PCM_BYTES_PER_SECOND * 1000),
            request_duration_ms=int((time.perf_counter() - started) * 1000),
        )
    except Exception as error:
        fail_voice_request(
            usage, error, input_audio_duration_ms=int(total / PCM_BYTES_PER_SECOND * 1000),
            request_duration_ms=int((time.perf_counter() - started) * 1000),
        )
        try:
            await socket.send_json({"type": "error", "detail": str(error)[:240]})
        except Exception:
            pass
    finally:
        if receiver is not None and not receiver.done():
            receiver.cancel()
        if provider is not None:
            await provider.close()
        try:
            await socket.close()
        except Exception:
            pass
