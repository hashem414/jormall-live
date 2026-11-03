from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select, text

from app.api.media import router as media_router
from app.api.public_chat import router as public_chat_router
from app.api.sales_callbacks import router as sales_callbacks_router
from app.api.chat_history import router as chat_history_router
from app.constants import ASSET_VERSION
from app.core.database import SessionLocal
from app.core.db_init import initialize_database
from app.models.document import DocumentChunk
from app.services.client_config_service import load_client_config, normalize_origin
from app.services.route_service import (
    EMBED_LOADER_PATH,
    build_public_url,
    get_public_base_path,
    get_public_chatbot_path,
    get_public_embed_chatbot_path,
    validate_public_client_slug,
)
from app.standalone_db_seed import ensure_vector_extension, seed_standalone_database


APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
CLIENT_SLUG = "jormall-central-e-commerce-co-ltd"
BASE_PATH = "/" + os.getenv("APP_BASE_PATH", "/sms-service-chatbot").strip().strip("/")
BASE_PATH = "" if BASE_PATH == "/" else BASE_PATH.rstrip("/")
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
    yield


app = FastAPI(title=f"{CLIENT_SLUG} Chatbot", lifespan=lifespan)
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

app.mount(f"{BASE_PATH}/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
app.include_router(media_router, prefix=BASE_PATH)
app.include_router(public_chat_router, prefix=BASE_PATH)
app.include_router(sales_callbacks_router, prefix=BASE_PATH)
app.include_router(chat_history_router, prefix=BASE_PATH)


def base_template_context() -> dict:
    from datetime import datetime

    return {
        "asset_version": ASSET_VERSION,
        "current_year": datetime.now().year,
        "website_scraping_ui_enabled": False,
        "upload_limits": {},
        "public_base_path": get_public_base_path(),
        "default_chatbot_path": get_public_chatbot_path(CLIENT_SLUG),
        "app_base_path": BASE_PATH,
        "api_base_path": BASE_PATH,
    }


def ensure_client_slug(client_slug: str) -> str:
    try:
        slug = validate_public_client_slug(client_slug)
    except ValueError as error:
        raise HTTPException(status_code=404, detail="Client chatbot not found.") from error
    if slug != CLIENT_SLUG:
        raise HTTPException(status_code=404, detail="Client chatbot not found.")
    return slug


@app.middleware("http")
async def enforce_single_client_api(request: Request, call_next):
    path = request.url.path.rstrip("/")
    api_path = path[len(BASE_PATH):] if BASE_PATH and path.startswith(BASE_PATH) else path
    if api_path == "/api/chat/stream" and CLIENT_SLUG != "jormall":
        return JSONResponse({"detail": "Client chatbot not found."}, status_code=404)
    prefix = "/api/chat/"
    suffix = "/stream"
    if api_path.startswith(prefix) and api_path.endswith(suffix):
        slug = api_path[len(prefix):-len(suffix)].strip("/")
        if slug and slug != CLIENT_SLUG:
            return JSONResponse({"detail": "Client chatbot not found."}, status_code=404)
    return await call_next(request)


def public_base_url(request: Request) -> str:
    configured = os.getenv("PUBLIC_CHATBOT_BASE_URL", "").strip().rstrip("/")
    if configured:
        return configured
    return str(request.base_url).rstrip("/")


def enforce_embed_origin(request: Request, allowed_origins: list[str]) -> str | None:
    if not allowed_origins:
        return None
    parent_origin = normalize_origin(request.query_params.get("parent_origin") or "")
    header_origin = normalize_origin(request.headers.get("origin") or request.headers.get("referer") or "")
    effective_origin = parent_origin or header_origin
    if not effective_origin or effective_origin not in allowed_origins:
        raise HTTPException(status_code=403, detail="This website is not approved to embed this chatbot.")
    return effective_origin


def render_client_chatbot(request: Request, client_slug: str):
    slug = ensure_client_slug(client_slug)
    config = load_client_config(slug)
    embed_mode = request.query_params.get("embed", "").lower() in {"1", "true", "widget"}
    parent_origin = normalize_origin(request.query_params.get("parent_origin") or "")
    embed_session_id = (request.query_params.get("session_id") or "").strip()[:120]
    if embed_mode:
        enforce_embed_origin(request, config.allowed_embed_origins)
    response = templates.TemplateResponse(
        request=request,
        name="chat.html",
        context={
            **base_template_context(),
            "config": config,
            "embed_mode": embed_mode,
            "embed_session_id": embed_session_id,
            "embed_parent_origin": parent_origin,
            "pre_chat_lead_capture_enabled": True,
        },
    )
    if embed_mode and config.allowed_embed_origins:
        response.headers["Content-Security-Policy"] = (
            "frame-ancestors 'self' " + " ".join(config.allowed_embed_origins)
        )
    return response


@app.get("/health")
@app.get(f"{BASE_PATH}/health")
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
    }


@app.get("/db-health")
@app.get(f"{BASE_PATH}/db-health")
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


@app.get("/")
def root():
    return RedirectResponse(url=get_public_chatbot_path(CLIENT_SLUG))


@app.get(f"{BASE_PATH}")
@app.get(f"{BASE_PATH}/")
def short_chatbot(request: Request):
    return render_client_chatbot(request, CLIENT_SLUG)


@app.get("/chat")
@app.get(f"{BASE_PATH}/chat")
def chat_shortcut():
    return RedirectResponse(url=get_public_chatbot_path(CLIENT_SLUG))


@app.get(f"{BASE_PATH}/chat/{{client_slug}}")
@app.get("/chat/{client_slug}")
def legacy_chat(client_slug: str):
    slug = ensure_client_slug(client_slug)
    return RedirectResponse(url=get_public_chatbot_path(slug))


@app.get(f"{get_public_base_path()}/chatbots/{{client_slug}}")
@app.get(f"{get_public_base_path()}/chatbots/{{client_slug}}/")
def client_chatbot(request: Request, client_slug: str):
    return render_client_chatbot(request, client_slug)


@app.get("/favicon.ico", include_in_schema=False)
@app.get(f"{BASE_PATH}/favicon.ico", include_in_schema=False)
def favicon():
    config = load_client_config(CLIENT_SLUG)
    favicon_url = config.favicon_url or "/static/images/favicon.png"
    if favicon_url.startswith("/static/"):
        path = APP_DIR / favicon_url.lstrip("/")
        if path.is_file():
            return FileResponse(path)
    fallback = APP_DIR / "static" / "images" / "favicon.png"
    if fallback.is_file():
        return FileResponse(fallback)
    raise HTTPException(status_code=404, detail="Favicon not found.")


@app.get(f"{BASE_PATH}/embed/jormall-chatbot.js", include_in_schema=False)
def embed_loader():
    return FileResponse(APP_DIR / "static" / "js" / "embed-widget.js", media_type="application/javascript")


@app.get(f"{BASE_PATH}/embed/{{client_slug}}/config")
def embed_config(request: Request, client_slug: str):
    slug = ensure_client_slug(client_slug)
    config = load_client_config(slug)
    allowed_origin = enforce_embed_origin(request, config.allowed_embed_origins)
    base_url = public_base_url(request)
    loader_url = build_public_url(base_url, EMBED_LOADER_PATH)
    snippet = (
        f'<script async src="{loader_url}" '
        f'data-client-slug="{config.client_slug}" data-position="right"></script>'
    )
    headers = {"Vary": "Origin"}
    if allowed_origin:
        headers["Access-Control-Allow-Origin"] = allowed_origin
    elif not config.allowed_embed_origins:
        headers["Access-Control-Allow-Origin"] = "*"
    payload = {
        "client_slug": config.client_slug,
        "company_name": config.company_name,
        "assistant_name": config.assistant_name,
        "chatbot_type": config.chatbot_type,
        "campaign_name": config.campaign_name,
        "campaign_language": config.campaign_language,
        "logo_url": config.logo_url,
        "favicon_url": config.favicon_url,
        "primary_color": config.primary_color,
        "secondary_color": config.secondary_color,
        "button_color": config.button_color,
        "background_color": config.background_color,
        "suggested_questions": config.suggested_questions,
        "starter_question_items": config.starter_question_items,
        "contact_details": config.contact_details,
        "chatbot_url": build_public_url(base_url, get_public_chatbot_path(config.client_slug)),
        "embed_url": build_public_url(base_url, get_public_embed_chatbot_path(config.client_slug)),
        "loader_url": loader_url,
        "snippet": snippet,
        "allowed_embed_origins_configured": bool(config.allowed_embed_origins),
    }
    return JSONResponse(payload, headers=headers)
