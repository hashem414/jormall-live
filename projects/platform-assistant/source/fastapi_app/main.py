import csv
import os
import shutil
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import anyio
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from chatbot import generate_response, get_retriever, suggestions
from model_config import (
    APP_BASE_PATH,
    APP_ENV,
    CHAT_LOG_DIR,
    CHAT_LOG_MAX_BYTES,
    ENABLE_MAINTENANCE_ROUTES,
    OPENAI_CHAT_MODEL,
    OPENAI_EMBEDDING_MODEL,
    SESSION_COOKIE_SAMESITE,
    SESSION_COOKIE_SECURE,
    SESSION_MAX_AGE_SECONDS,
)
from vector_store import build_vector_store
from fastapi_app.session_store import SessionStore


APP_ROOT = Path(__file__).resolve().parent.parent
CHROMA_DIR = APP_ROOT / "chroma_index"
SESSION_COOKIE = "platform_chatbot_session"
LOG_HEADERS = ["Timestamp", "SessionID", "UserQuery", "BotResponse"]
_log_lock = threading.Lock()

templates = Jinja2Templates(directory=str(APP_ROOT / "templates"))
session_store = SessionStore(max_age_seconds=SESSION_MAX_AGE_SECONDS)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)


def current_log_file():
    log_dir = Path(CHAT_LOG_DIR)
    if not log_dir.is_absolute():
        log_dir = APP_ROOT / log_dir
    os.makedirs(log_dir, exist_ok=True)
    day = datetime.now().strftime("%Y-%m-%d")
    base_path = log_dir / f"chat_logs_{day}.csv"
    if CHAT_LOG_MAX_BYTES <= 0 or not os.path.exists(base_path) or os.path.getsize(base_path) < CHAT_LOG_MAX_BYTES:
        return base_path

    index = 1
    while True:
        rotated_path = log_dir / f"chat_logs_{day}_{index}.csv"
        if not os.path.exists(rotated_path) or os.path.getsize(rotated_path) < CHAT_LOG_MAX_BYTES:
            return rotated_path
        index += 1


def ensure_log_file(path=None):
    path = path or current_log_file()
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(LOG_HEADERS)
    return path


def session_cookie_expires():
    return datetime.now(timezone.utc) + timedelta(seconds=SESSION_MAX_AGE_SECONDS)


def vector_store_exists():
    return os.path.exists(CHROMA_DIR / "chroma.sqlite3")


def get_or_create_session_id(request: Request, response: Response):
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        session_id = session_store.new_session_id()
        response.set_cookie(
            SESSION_COOKIE,
            session_id,
            httponly=True,
            secure=SESSION_COOKIE_SECURE,
            samesite=SESSION_COOKIE_SAMESITE,
            max_age=SESSION_MAX_AGE_SECONDS,
            expires=session_cookie_expires(),
            path="/",
        )
    else:
        session_store.touch(session_id)
    return session_id


def log_chat(session_id, query, bot_response):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _log_lock:
        path = ensure_log_file()
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, session_id, query, bot_response])


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_log_file()
    if vector_store_exists():
        print(f"Existing vector store found at '{CHROMA_DIR}'.", flush=True)
        try:
            get_retriever()
            print("Retriever initialized from existing vector store.", flush=True)
        except Exception as exc:
            print(f"Retriever initialization failed: {type(exc).__name__}: {exc}", flush=True)
    else:
        print(f"Vector store not found at '{CHROMA_DIR}'. Use /build or /rebuild-vectorstore manually.", flush=True)
    expired = session_store.cleanup_expired()
    if expired:
        print(f"Expired sessions cleaned: {expired}", flush=True)
    yield


app = FastAPI(title="JorMall Platform Assistant", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(APP_ROOT / "assets")), name="static")


@app.get("/")
async def home(request: Request):
    session_id = request.cookies.get(SESSION_COOKIE)
    created_session = False
    if not session_id:
        session_id = session_store.new_session_id()
        created_session = True
    else:
        session_store.touch(session_id)

    html = templates.get_template("chat.html").render(
        suggestions_ar=suggestions["ar"],
        suggestions_en=suggestions["en"],
        app_base_path=APP_BASE_PATH,
    )
    template_response = HTMLResponse(html)
    if created_session:
        template_response.set_cookie(
            SESSION_COOKIE,
            session_id,
            httponly=True,
            secure=SESSION_COOKIE_SECURE,
            samesite=SESSION_COOKIE_SAMESITE,
            max_age=SESSION_MAX_AGE_SECONDS,
            expires=session_cookie_expires(),
            path="/",
        )
    return template_response


@app.post("/chat")
async def chat(chat_request: ChatRequest, request: Request, response: Response):
    request_start = time.perf_counter()
    session_id = get_or_create_session_id(request, response)
    print(f"[PERF] request_received session={session_id}", flush=True)

    query = chat_request.message.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Please enter a question")

    session_lock = session_store.get_lock(session_id)
    if not session_lock.acquire(blocking=False):
        print(f"[PERF] request_rejected_busy session={session_id} total={time.perf_counter() - request_start:.3f}s", flush=True)
        return JSONResponse(
            status_code=409,
            content={"response": "A previous request is still processing. Please wait for it to finish."},
        )

    try:
        history = session_store.get_history(session_id)
        result = await anyio.to_thread.run_sync(generate_response, query, history)
        if result.get("used_rag", True):
            session_store.append_history(session_id, query, result["result"])
        try:
            log_chat(session_id, query, result["result"])
        except Exception as log_exc:
            print(f"Logging error: {type(log_exc).__name__}: {log_exc}", flush=True)
        print(f"[PERF] request_complete session={session_id} total={time.perf_counter() - request_start:.3f}s", flush=True)
        return {"response": result["result"]}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid input: {exc}") from exc
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {exc}", flush=True)
        print(f"[PERF] request_error session={session_id} total={time.perf_counter() - request_start:.3f}s", flush=True)
        return JSONResponse(status_code=500, content={"response": "ERROR: An internal error occurred."})
    finally:
        session_lock.release()


def maintenance_routes_enabled():
    return ENABLE_MAINTENANCE_ROUTES


def maintenance_disabled_response():
    return JSONResponse(status_code=404, content={"detail": "Not found"})


@app.api_route("/build", methods=["GET", "POST"])
async def build():
    if not maintenance_routes_enabled():
        return maintenance_disabled_response()
    try:
        if not vector_store_exists():
            await anyio.to_thread.run_sync(build_vector_store)
            return {"status": "DB is built successfully."}
        return {"status": "DB already exists."}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"status": f"Error while building the DB: {exc}"})


@app.api_route("/rebuild-vectorstore", methods=["GET", "POST"])
async def manual_rebuild():
    if not maintenance_routes_enabled():
        return maintenance_disabled_response()
    try:
        shutil.rmtree(CHROMA_DIR, ignore_errors=True)
        os.makedirs(CHROMA_DIR, exist_ok=True)
        await anyio.to_thread.run_sync(build_vector_store)
        return {"status": "Vector store rebuilt"}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"status": f"Error while rebuilding the DB: {exc}"})


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    return {
        "status": "ok" if vector_store_exists() else "missing_vector_store",
        "chroma_index": vector_store_exists(),
        "chat_model": OPENAI_CHAT_MODEL,
        "embedding_model": OPENAI_EMBEDDING_MODEL,
        "sessions": session_store.session_count(),
        "app_env": APP_ENV,
        "maintenance_routes_enabled": maintenance_routes_enabled(),
    }
