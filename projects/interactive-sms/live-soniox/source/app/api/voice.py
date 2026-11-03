"""Authorized saved-message speech and complete-recording transcription routes."""
from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.conversations.store import assistant_message_for_speech
from app.core.config import settings
from app.core.database import get_db
from app.language_detection import detect_supported_language
from app.services.public_branding_service import canonicalize_public_branding
from app.sessions.access import ensure_lead_capture_completed
from app.voice.contracts import SpeechRequest, normalize_language
from app.voice.protocol import MEDIA_TYPE, completion_frame, error_frame, pcm_frame
from app.voice.providers.soniox import SUPPORTED_AUDIO_TYPES, SonioxConfigurationError, SonioxSpeechError, normalize_audio_content_type
from app.voice.stt import transcribe_recording
from app.voice.tts import SpeechJob, VoiceFailure, VoiceOverloaded, identity, speech_text_for_saved_answer
from app.voice.usage import begin_voice_request, cancel_voice_request, complete_voice_request, fail_voice_request, update_voice_request

router = APIRouter()
TENANT = "central-e-commerce-co-ltd"


def guard(db, client_slug, lead_session_id):
    if client_slug != TENANT:
        raise HTTPException(status_code=404, detail="Client chatbot not found.")
    ensure_lead_capture_completed(db=db, client_slug=client_slug, session_id=lead_session_id)


@router.post("/chat/{client_slug}/transcribe")
async def transcribe_client_voice(client_slug: str, audio: UploadFile = File(...), language: str = Form("auto"), lead_session_id: str = Form(...), db: Session = Depends(get_db)):
    route_started = time.perf_counter()
    guard(db, client_slug, lead_session_id)
    try:
        language = normalize_language(language, allow_auto=True)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    content_type = normalize_audio_content_type(audio.content_type)
    if content_type not in SUPPORTED_AUDIO_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported audio format.")
    try:
        data = await audio.read(settings.voice_max_upload_mb * 1024 * 1024 + 1)
    finally:
        await audio.close()
    if not data:
        raise HTTPException(status_code=422, detail="The audio recording is empty.")
    if len(data) > settings.voice_max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="The audio recording is too large.")

    workflow = settings.soniox_stt_workflow
    model = settings.soniox_stt_model if workflow == "realtime" else settings.soniox_stt_fallback_model
    usage = begin_voice_request(client_slug=client_slug, operation="stt", model=model, language=language, session_id=lead_session_id, input_audio_bytes=len(data))
    provider_started = time.perf_counter()
    try:
        result = await run_in_threadpool(transcribe_recording, data, content_type=content_type, language=language, client_reference_id=usage.client_reference_id if usage else "")
    except (SonioxConfigurationError, SonioxSpeechError) as error:
        fail_voice_request(usage, error, request_duration_ms=int((time.perf_counter() - route_started) * 1000), provider_request_id=getattr(error, "request_id", "") or None)
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        fail_voice_request(usage, error, request_duration_ms=int((time.perf_counter() - route_started) * 1000))
        raise HTTPException(status_code=422, detail=str(error)) from error

    provider_ms = (time.perf_counter() - provider_started) * 1000
    total_ms = (time.perf_counter() - route_started) * 1000
    complete_voice_request(usage, language=result.provider_language, request_duration_ms=int(total_ms), provider_request_id=result.request_id or None)
    return JSONResponse(
        {"transcript": result.transcript, "confidence": result.confidence, "language": result.provider_language, "requested_language": result.requested_language, "provider_language": result.provider_language},
        headers={"Server-Timing": f"soniox_stt;dur={provider_ms:.1f}, total;dur={total_ms:.1f}", "X-STT-Provider": "soniox", "X-STT-Model": model, "X-STT-Workflow": workflow, "X-STT-Duration-Ms": f"{provider_ms:.1f}", "X-STT-Language": result.provider_language},
    )


@router.post("/chat/{client_slug}/speak")
async def speak_client_answer(client_slug: str, payload: SpeechRequest, db: Session = Depends(get_db)):
    route_started = time.perf_counter()
    guard(db, client_slug, payload.lead_session_id)
    message = assistant_message_for_speech(db=db, client_slug=client_slug, session_id=payload.session_id, lead_session_id=payload.lead_session_id, message_id=payload.message_id)
    if message is None:
        raise HTTPException(status_code=404, detail="That saved answer is not available for this session.")
    speech_language = detect_supported_language(message.content) if payload.language == "auto" else payload.language
    speech = speech_text_for_saved_answer(canonicalize_public_branding(message.content, language=speech_language), speech_language)
    info = identity()
    usage = begin_voice_request(client_slug=client_slug, provider=info["provider"], operation="tts", model=info["model"], voice=info["voice"], language=speech_language, session_id=payload.session_id, input_text_characters=speech.speech_characters)
    job = None
    try:
        job = SpeechJob(tenant=client_slug, text=speech.text, language=speech_language, client_reference_id=usage.client_reference_id if usage else "")
        first = await asyncio.wait_for(asyncio.to_thread(job.read), timeout=settings.soniox_request_timeout_seconds)
        if not first:
            raise VoiceFailure("No speech audio was generated.")
    except VoiceOverloaded as error:
        fail_voice_request(usage, error, request_duration_ms=int((time.perf_counter() - route_started) * 1000))
        raise HTTPException(status_code=429, detail=str(error), headers={"Retry-After": "2"}) from error
    except (VoiceFailure, asyncio.TimeoutError) as error:
        if job:
            job.cancel()
        fail_voice_request(usage, error, request_duration_ms=int((time.perf_counter() - route_started) * 1000))
        raise HTTPException(status_code=503, detail="Voice is temporarily unavailable. You can read the written answer.") from error
    except BaseException:
        if job:
            job.cancel()
        fail_voice_request(usage, "unexpected_tts_start_failure", request_duration_ms=int((time.perf_counter() - route_started) * 1000))
        raise

    first_audio_ms = (time.perf_counter() - route_started) * 1000
    update_voice_request(usage, cache_hit=job.cached is not None, first_audio_ms=int(first_audio_ms), first_audio_at=datetime.now(UTC))

    async def chunks():
        output_bytes = len(first)
        terminal = False
        try:
            yield pcm_frame(first)
            while True:
                data = await asyncio.wait_for(asyncio.to_thread(job.read), timeout=settings.soniox_request_timeout_seconds)
                if data is None:
                    break
                output_bytes += len(data)
                yield pcm_frame(data)
            yield completion_frame()
            terminal = True
            complete_voice_request(usage, cache_hit=job.cached is not None, output_audio_bytes=output_bytes, output_audio_duration_ms=int(output_bytes / 2 / 24000 * 1000), request_duration_ms=int((time.perf_counter() - route_started) * 1000), first_audio_ms=int(first_audio_ms), first_audio_at=datetime.now(UTC))
        except asyncio.CancelledError:
            terminal = True
            cancel_voice_request(usage, output_audio_bytes=output_bytes, request_duration_ms=int((time.perf_counter() - route_started) * 1000))
            raise
        except (VoiceFailure, ValueError, asyncio.TimeoutError) as error:
            terminal = True
            fail_voice_request(usage, error, output_audio_bytes=output_bytes, request_duration_ms=int((time.perf_counter() - route_started) * 1000))
            yield error_frame()
        finally:
            job.cancel()
            if not terminal:
                cancel_voice_request(usage, output_audio_bytes=output_bytes, request_duration_ms=int((time.perf_counter() - route_started) * 1000))

    return StreamingResponse(chunks(), media_type=MEDIA_TYPE, headers={
        "Cache-Control": "no-store", "X-Accel-Buffering": "no", "X-Content-Type-Options": "nosniff",
        "Server-Timing": f"{info['provider']}_tts_first_audio;dur={first_audio_ms:.1f}", "X-Voice-Provider": info["provider"],
        "X-Voice-Model": info["model"], "X-Voice-Voice": info["voice"], "X-Voice-Language": speech_language,
        "X-Audio-Format": info["format"], "X-Assistant-Message-ID": str(message.id),
        "X-Voice-Cache": "hit" if job.cached is not None else "miss", "X-Voice-First-Audio-Ms": f"{first_audio_ms:.1f}",
        "X-Voice-Source-Characters": str(speech.source_characters), "X-Voice-Speech-Characters": str(speech.speech_characters),
        "X-Voice-Compacted": "true" if speech.compacted else "false",
    })
