from __future__ import annotations

import os
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
from app.constants import ASSET_VERSION
from app.core.database import SessionLocal
from app.core.db_init import initialize_database
from app.models.document import DocumentChunk
from app.services.client_config_service import load_client_config
from app.services.gemini_tts_service import get_google_tts_client, google_adc_status
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
    if settings.voice_enabled:
        try:
            # Resolve ADC and construct the reusable channel during startup so the
            # first customer voice request does not pay client-initialization cost.
            get_google_tts_client()
        except Exception as error:
            print(f"[gemini voice prewarm warning] {type(error).__name__}: {error}")
    yield


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


def soniox_stt_configured() -> bool:
    return bool(
        settings.voice_enabled
        and settings.soniox_api_key
        and settings.soniox_api_key.get_secret_value().strip()
    )


def gemini_tts_configured() -> bool:
    configured, _ = google_adc_status()
    return configured


def voice_speech_configured() -> bool:
    return soniox_stt_configured() and gemini_tts_configured()


def base_template_context() -> dict:
    from datetime import datetime

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
        "voice_max_recording_seconds": settings.voice_max_recording_seconds,
    }


@app.get("/health")
def health():
    with SessionLocal() as db:
        chunk_count = db.execute(
            select(func.count())
            .select_from(DocumentChunk)
            .where(DocumentChunk.client_slug == CLIENT_SLUG)
        ).scalar_one()
    return {
        "status": "healthy",
        "client_slug": CLIENT_SLUG,
        "database_seed": STARTUP_SEED_RESULT,
        "knowledge_chunks": int(chunk_count or 0),
        "runtime": "production_pgvector",
        "voice_stt": (
            f"soniox_{settings.soniox_stt_fallback_model.replace('-', '_')}"
            if soniox_stt_configured()
            else "not_configured"
        ),
        "voice_tts": (
            settings.gemini_tts_model
            if gemini_tts_configured()
            else "not_configured"
        ),
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
            **base_template_context(),
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
