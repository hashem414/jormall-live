from __future__ import annotations

import os
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select, text

from app.api.chat_history import router as chat_history_router
from app.api.public_chat import router as public_chat_router
from app.api.sales_callbacks import router as sales_callbacks_router
from app.api.voice_usage import router as voice_usage_router
from app.api.live_stt import router as live_stt_router
from app.constants import ASSET_VERSION
from app.core.database import SessionLocal
from app.core.db_init import initialize_database
from app.models.document import DocumentChunk
from app.services.client_config_service import load_client_config
from app.services.soniox_speech_service import soniox_voice_provider_name
from app.services.route_service import (
    get_app_base_path,
    get_public_chatbot_path,
    with_app_base_path,
)
from app.standalone_db_seed import ensure_vector_extension, seed_standalone_database
from app.core.config import settings


APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
CLIENT_SLUG = "central-e-commerce-co-ltd"
APP_BASE_PATH = get_app_base_path()
STARTUP_SEED_RESULT: dict[str, int | str] = {}

if os.getenv("STANDALONE_CLIENT_SLUG", CLIENT_SLUG).strip() not in {"", CLIENT_SLUG}:
    raise RuntimeError("STANDALONE_CLIENT_SLUG does not match this exported chatbot package.")


templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_vector_extension()
    initialize_database()
    global STARTUP_SEED_RESULT
    STARTUP_SEED_RESULT = seed_standalone_database()
    (DATA_DIR / "conversations").mkdir(parents=True, exist_ok=True)
    sync_task = None
    if settings.voice_usage_sync_enabled:
        from app.voice.usage_sync import run_voice_usage_sync_worker
        sync_task = asyncio.create_task(run_voice_usage_sync_worker())
    try:
        yield
    finally:
        if sync_task is not None:
            sync_task.cancel()
            try:
                await sync_task
            except asyncio.CancelledError:
                pass
        from app.voice.tts import cancel_all
        await asyncio.to_thread(cancel_all)


app = FastAPI(
    title=f"{CLIENT_SLUG} Chatbot",
    lifespan=lifespan,
    docs_url="/docs" if settings.enable_api_docs else None,
    redoc_url="/redoc" if settings.enable_api_docs else None,
    openapi_url="/openapi.json" if settings.enable_api_docs else None,
)
allowed_origins = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
if allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

app.mount(
    f"{APP_BASE_PATH}/static",
    StaticFiles(directory=str(APP_DIR / "static")),
    name="static_app_base",
)
app.include_router(public_chat_router, prefix=APP_BASE_PATH)
app.include_router(sales_callbacks_router, prefix=APP_BASE_PATH)
app.include_router(chat_history_router, prefix=APP_BASE_PATH)
app.include_router(voice_usage_router, prefix=APP_BASE_PATH)
app.include_router(live_stt_router, prefix=APP_BASE_PATH)


def soniox_stt_configured() -> bool:
    return bool(
        settings.voice_enabled
        and settings.soniox_api_key
        and settings.soniox_api_key.get_secret_value().strip()
    )


def voice_speech_configured() -> bool:
    openai_ready = bool(settings.openai_api_key and settings.openai_api_key.get_secret_value().strip())
    stt_ready = soniox_stt_configured() if settings.voice_stt_provider == "soniox" else openai_ready
    tts_ready = soniox_stt_configured() if settings.voice_tts_provider == "soniox" else openai_ready
    return bool(settings.voice_enabled and stt_ready and tts_ready)


def base_template_context(request: Request | None = None) -> dict:
    from datetime import datetime

    request_port = request.url.port if request is not None else None
    webrtc_mode = request_port == 5008
    return {
        "asset_version": ASSET_VERSION,
        "current_year": datetime.now().year,
        "website_scraping_ui_enabled": False,
        "upload_limits": {},
        "app_base_path": APP_BASE_PATH,
        "app_url": with_app_base_path,
        "default_chatbot_path": get_public_chatbot_path(CLIENT_SLUG),
        "knowledge_version": str(
            STARTUP_SEED_RESULT.get("seed_version") or ASSET_VERSION
        ),
        "voice_stt_enabled": voice_speech_configured(),
        "voice_browser_fallback_enabled": settings.voice_browser_fallback_enabled,
        "voice_tts_provider": settings.voice_tts_provider,
        "voice_transport": "openai_webrtc" if webrtc_mode else "http_pcm",
        "voice_webrtc_model": "gpt-live-1" if webrtc_mode else "",
        "voice_webrtc_voice": "marin" if webrtc_mode else "",
        "voice_max_recording_seconds": settings.voice_max_recording_seconds,
    }


@app.get("/health")
def health(request: Request):
    with SessionLocal() as db:
        chunk_count = db.execute(
            select(func.count())
            .select_from(DocumentChunk)
            .where(DocumentChunk.client_slug == CLIENT_SLUG)
        ).scalar_one()
    webrtc_mode = request.url.port == 5008
    return {
        "status": "healthy",
        "client_slug": CLIENT_SLUG,
        "database_seed": STARTUP_SEED_RESULT,
        "knowledge_chunks": int(chunk_count or 0),
        "runtime": "production_pgvector",
        "voice_stt": (
            (
                "openai_gpt-live-1" if webrtc_mode else f"{settings.voice_stt_provider}_" + (
                    settings.soniox_stt_model if settings.voice_stt_provider == "soniox"
                    else settings.openai_live_transcription_model
                )
            ) if voice_speech_configured() else "not_configured"
        ),
        "voice_stt_workflow": "browser_openai_webrtc" if webrtc_mode else "browser_pcm_live_stream",
        "voice_tts": (
            "openai-gpt-live-1-marin" if webrtc_mode else (
                soniox_voice_provider_name() if settings.voice_tts_provider == "soniox"
                else f"openai-{settings.openai_tts_model}"
            )
        ) if voice_speech_configured() else "not_configured",
        "voice_transport": "openai_webrtc" if webrtc_mode else "http_pcm",
        "voice_live_model": "gpt-live-1" if webrtc_mode else None,
        "voice_live_voice": "marin" if webrtc_mode else None,
        "experimental_voice_matrix": True,
    }


@app.get("/db-health")
def db_health():
    with SessionLocal() as db:
        vector_version = db.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one_or_none()
    return {
        "status": "healthy",
        "database": "client_chatbot",
        "vector_extension": "enabled" if vector_version else "missing",
        "vector_version": vector_version,
        "database_seed": STARTUP_SEED_RESULT,
    }

def client_chatbot(request: Request):
    config = load_client_config(CLIENT_SLUG)
    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context={
            **base_template_context(request),
            "config": config,
            "embed_mode": False,
            "embed_session_id": "",
            "embed_parent_origin": "",
            "pre_chat_lead_capture_enabled": True,
        },
    )


def interactive_sms_redirect():
    return RedirectResponse(url=f"{APP_BASE_PATH}/", status_code=307)


def interactive_sms_chatbot(request: Request):
    return client_chatbot(request)


app.add_api_route(
    APP_BASE_PATH,
    interactive_sms_redirect,
    methods=["GET"],
    include_in_schema=False,
)
app.add_api_route(
    f"{APP_BASE_PATH}/",
    interactive_sms_chatbot,
    methods=["GET"],
    include_in_schema=False,
)
