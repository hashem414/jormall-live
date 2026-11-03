from __future__ import annotations

import hmac
import json
import logging
import os
import smtplib
import ssl
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Awaitable, Callable

try:
    from dotenv import load_dotenv
except ImportError:  # The production requirements install python-dotenv.
    def load_dotenv(path: Path) -> None:
        if not path.exists():
            return
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from services.analysis import (
    count_rows,
    local_chat_answer,
    local_followup,
    local_notes_summary,
    summarize_rows,
)
from services.openai_service import OpenAIService

APP_VERSION = "1.0.0"
BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
STORAGE_DIR = BASE_DIR / "storage"
LOG_DIR.mkdir(parents=True, exist_ok=True)
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
load_dotenv(BASE_DIR / ".env")

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("sma-extension")

app = FastAPI(
    title="JorMall SMA Extension AI Gateway",
    version=APP_VERSION,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

openai_service = OpenAIService()
SHARED_SECRET = os.getenv("SMA_SHARED_SECRET", "").strip()
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
MAX_CONTENT_LENGTH_BYTES = int(os.getenv("MAX_CONTENT_LENGTH_BYTES", str(5 * 1024 * 1024)))
RATE_BUCKETS: dict[str, deque[float]] = defaultdict(deque)
RATE_LOCK = threading.Lock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return request.client.host if request.client else "unknown"


def rate_limit_ok(request: Request) -> bool:
    now = time.time()
    cutoff = now - 60
    key = client_ip(request)
    with RATE_LOCK:
        bucket = RATE_BUCKETS[key]
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= RATE_LIMIT_PER_MINUTE:
            return False
        bucket.append(now)
    return True


def auth_ok(request: Request) -> bool:
    if not SHARED_SECRET:
        return True
    provided = request.headers.get("x-sma-extension-key", "")
    return bool(provided) and hmac.compare_digest(provided, SHARED_SECRET)


async def guard(request: Request) -> JSONResponse | None:
    if not rate_limit_ok(request):
        return JSONResponse({"ok": False, "error": "Too many requests. Please retry shortly."}, status_code=429)
    if not auth_ok(request):
        return JSONResponse({"ok": False, "error": "Unauthorized SMA extension request."}, status_code=401)
    return None


async def json_body(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "").lower()
    if "application/json" not in content_type:
        raise ValueError("Content-Type must be application/json")
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_CONTENT_LENGTH_BYTES:
        raise OverflowError("Request payload is too large.")
    raw = await request.body()
    if len(raw) > MAX_CONTENT_LENGTH_BYTES:
        raise OverflowError("Request payload is too large.")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("The request body contains invalid JSON.") from error
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object")
    return payload


def report_meta(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "screen": payload.get("screen") or "unknown",
        "scope": payload.get("scope") or "all",
        "companiesAnalyzed": count_rows(payload),
    }


def append_jsonl(filename: str, record: dict[str, Any]) -> None:
    path = LOG_DIR / filename
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def both_routes(path: str, methods: list[str]) -> Callable[[Callable[..., Awaitable[JSONResponse]]], Callable[..., Awaitable[JSONResponse]]]:
    def decorator(function: Callable[..., Awaitable[JSONResponse]]) -> Callable[..., Awaitable[JSONResponse]]:
        app.add_api_route(path, function, methods=methods, include_in_schema=False)
        prefixed = "/sma-extension" + (path if path.startswith("/") else "/" + path)
        app.add_api_route(prefixed, function, methods=methods, include_in_schema=False)
        return function

    return decorator


@app.middleware("http")
async def security_headers(request: Request, call_next: Callable[..., Awaitable[JSONResponse]]) -> JSONResponse:
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@both_routes("/", ["GET"])
async def index(_: Request) -> JSONResponse:
    return JSONResponse(
        {
            "service": "JorMall SMA Extension AI Gateway",
            "version": APP_VERSION,
            "health": "/health",
            "status": "online",
        }
    )


@both_routes("/health", ["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "status": "online",
            "service": "JorMall SMA Extension AI Gateway",
            "version": APP_VERSION,
            "openaiEnabled": openai_service.enabled,
            "model": openai_service.model,
            "emailNotificationsEnabled": email_enabled(),
            "authenticationEnabled": bool(SHARED_SECRET),
            "authenticationAccepted": auth_ok(request),
            "timestamp": utc_now(),
        }
    )


@both_routes("/api/chat", ["POST"])
async def chat(request: Request) -> JSONResponse:
    denied = await guard(request)
    if denied:
        return denied
    try:
        payload = await json_body(request)
        question = str(payload.get("question") or "").strip()
        if not question:
            return JSONResponse({"ok": False, "error": "A question is required."}, status_code=400)
        if len(question) > 8_000:
            return JSONResponse({"ok": False, "error": "The question is too long."}, status_code=400)

        if openai_service.enabled:
            answer = openai_service.answer(payload)
            mode = "openai"
        else:
            answer = local_chat_answer(payload)
            mode = "local-fallback"

        append_jsonl(
            "chat-audit.jsonl",
            {
                "timestamp": utc_now(),
                "ip": client_ip(request),
                "screen": payload.get("screen"),
                "scope": payload.get("scope"),
                "rows": count_rows(payload),
                "mode": mode,
            },
        )
        return JSONResponse(
            {
                "ok": True,
                "answer": answer,
                "model": openai_service.model if openai_service.enabled else "local-analysis",
                "mode": mode,
                "report": report_meta(payload),
            }
        )
    except OverflowError as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=413)
    except ValueError as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=400)
    except Exception as error:
        logger.exception("Chat request failed")
        return JSONResponse({"ok": False, "error": f"AI analysis failed: {error}"}, status_code=502)


@both_routes("/sma/analyze-notes", ["POST"])
async def analyze_notes(request: Request) -> JSONResponse:
    denied = await guard(request)
    if denied:
        return denied
    try:
        payload = await json_body(request)
        notes_data = payload.get("notesData")
        if not isinstance(notes_data, dict):
            return JSONResponse({"ok": False, "error": "notesData must be an object."}, status_code=400)
        if openai_service.enabled:
            try:
                summary = openai_service.notes_summary(notes_data)
                mode = "openai"
            except Exception:
                logger.exception("OpenAI notes summary failed; using local fallback")
                summary = local_notes_summary(notes_data)
                mode = "local-fallback"
        else:
            summary = local_notes_summary(notes_data)
            mode = "local-fallback"
        return JSONResponse(
            {
                "ok": True,
                "aiSummary": summary,
                "summary": summary.get("executive_summary"),
                "accountFacts": summary.get("account_facts", {}),
                "departmentSummary": summary.get("department_summary", {}),
                "model": openai_service.model if mode == "openai" else "local-analysis",
                "mode": mode,
            }
        )
    except OverflowError as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=413)
    except ValueError as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=400)
    except Exception as error:
        logger.exception("Notes analysis failed")
        return JSONResponse({"ok": False, "error": f"Notes analysis failed: {error}"}, status_code=502)


async def generic_analysis(request: Request, kind: str) -> JSONResponse:
    denied = await guard(request)
    if denied:
        return denied
    try:
        payload = await json_body(request)
        enriched = dict(payload)
        enriched.setdefault("question", f"Analyze this {kind} and recommend practical next actions.")
        if openai_service.enabled:
            answer = openai_service.answer(enriched)
            mode = "openai"
        else:
            answer = local_chat_answer(enriched)
            mode = "local-fallback"
        rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
        return JSONResponse(
            {
                "ok": True,
                "answer": answer,
                "summary": summarize_rows([row for row in rows if isinstance(row, dict)]),
                "model": openai_service.model if mode == "openai" else "local-analysis",
                "mode": mode,
                "report": report_meta(payload),
            }
        )
    except OverflowError as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=413)
    except ValueError as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=400)
    except Exception as error:
        logger.exception("%s failed", kind)
        return JSONResponse({"ok": False, "error": f"{kind} failed: {error}"}, status_code=502)


@both_routes("/sma/analyze-company", ["POST"])
async def analyze_company(request: Request) -> JSONResponse:
    return await generic_analysis(request, "company analysis")


@both_routes("/sma/analyze-page", ["POST"])
async def analyze_page(request: Request) -> JSONResponse:
    return await generic_analysis(request, "page analysis")


@both_routes("/sma/analyze-category-monthly-delivery", ["POST"])
async def analyze_category_monthly_delivery(request: Request) -> JSONResponse:
    return await generic_analysis(request, "category monthly delivery analysis")


@both_routes("/sma/analyze-route", ["POST"])
async def analyze_route(request: Request) -> JSONResponse:
    return await generic_analysis(request, "SMA route analysis")


@both_routes("/sma/draft-followup", ["POST"])
async def draft_followup(request: Request) -> JSONResponse:
    denied = await guard(request)
    if denied:
        return denied
    try:
        payload = await json_body(request)
        if openai_service.enabled:
            message = openai_service.draft_followup(payload)
            mode = "openai"
        else:
            message = local_followup(payload)
            mode = "local-fallback"
        return JSONResponse(
            {
                "ok": True,
                "message": message,
                "answer": message,
                "model": openai_service.model if mode == "openai" else "local-analysis",
                "mode": mode,
            }
        )
    except OverflowError as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=413)
    except ValueError as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=400)
    except Exception as error:
        logger.exception("Follow-up drafting failed")
        return JSONResponse({"ok": False, "error": f"Follow-up drafting failed: {error}"}, status_code=502)


@both_routes("/sma/log-action", ["POST"])
async def log_action(request: Request) -> JSONResponse:
    denied = await guard(request)
    if denied:
        return denied
    try:
        payload = await json_body(request)
        safe_record = {
            "timestamp": utc_now(),
            "ip": client_ip(request),
            "action": str(payload.get("action") or "unknown")[:120],
            "screen": str(payload.get("screen") or "")[:120],
            "companyId": str(payload.get("companyId") or "")[:120],
            "companyName": str(payload.get("companyName") or "")[:240],
            "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        }
        append_jsonl("extension-actions.jsonl", safe_record)
        return JSONResponse({"ok": True, "logged": True})
    except OverflowError as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=413)
    except ValueError as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=400)
    except Exception as error:
        logger.exception("Action logging failed")
        return JSONResponse({"ok": False, "error": f"Action logging failed: {error}"}, status_code=500)


def email_enabled() -> bool:
    required = ["SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM"]
    return os.getenv("ENABLE_EMAIL_NOTIFICATIONS", "false").lower() == "true" and all(os.getenv(name) for name in required)


def send_priority_email(payload: dict[str, Any]) -> None:
    if not email_enabled():
        raise RuntimeError("SMTP email notifications are not configured")

    recipients = os.getenv("SALES_NOTIFICATION_TO", str(payload.get("to") or "sales@jormall.com"))
    to_list = [item.strip() for item in recipients.split(",") if item.strip()]
    companies = payload.get("veryUrgentCompanies") if isinstance(payload.get("veryUrgentCompanies"), list) else []

    lines = [
        "Very urgent SMA sales-priority accounts were detected.",
        "",
        f"Generated at: {payload.get('generatedAt') or utc_now()}",
        f"Page: {payload.get('pageUrl') or '-'}",
        "",
    ]
    for item in companies[:25]:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"- {item.get('companyName') or '-'} | PB: {item.get('currentPb')} | Minimum: {item.get('minPb')} | "
            f"Priority: {item.get('priority')} | Tasks: {', '.join(item.get('tasks') or [])} | Expiry: {item.get('expiryDate') or '-'}"
        )

    message = EmailMessage()
    message["Subject"] = f"SMA urgent sales priority ({len(companies)} account(s))"
    message["From"] = os.environ["SMTP_FROM"]
    message["To"] = ", ".join(to_list)
    message.set_content("\n".join(lines))

    host = os.environ["SMTP_HOST"]
    port = int(os.environ["SMTP_PORT"])
    username = os.environ["SMTP_USERNAME"]
    password = os.environ["SMTP_PASSWORD"]
    use_ssl = os.getenv("SMTP_USE_SSL", "false").lower() == "true"
    use_starttls = os.getenv("SMTP_USE_STARTTLS", "true").lower() == "true"

    if use_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=30, context=ssl.create_default_context()) as smtp:
            smtp.login(username, password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.ehlo()
            if use_starttls:
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            smtp.login(username, password)
            smtp.send_message(message)


@both_routes("/sma/notify-sales-priority", ["POST"])
async def notify_sales_priority(request: Request) -> JSONResponse:
    denied = await guard(request)
    if denied:
        return denied
    try:
        payload = await json_body(request)
        companies = payload.get("veryUrgentCompanies")
        if not isinstance(companies, list) or not companies:
            return JSONResponse(
                {"ok": False, "error": "veryUrgentCompanies must contain at least one account."},
                status_code=400,
            )
        append_jsonl(
            "sales-priority.jsonl",
            {
                "timestamp": utc_now(),
                "ip": client_ip(request),
                "pageUrl": payload.get("pageUrl"),
                "companyCount": len(companies),
                "companies": companies[:25],
            },
        )
        if not email_enabled():
            return JSONResponse(
                {
                    "ok": False,
                    "error": "Priority accounts were logged, but SMTP email notifications are not configured.",
                    "logged": True,
                },
                status_code=503,
            )
        send_priority_email(payload)
        return JSONResponse(
            {
                "ok": True,
                "sent": True,
                "recipients": os.getenv("SALES_NOTIFICATION_TO", str(payload.get("to") or "sales@jormall.com")),
            }
        )
    except OverflowError as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=413)
    except ValueError as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=400)
    except Exception as error:
        logger.exception("Priority notification failed")
        return JSONResponse({"ok": False, "error": f"Priority notification failed: {error}"}, status_code=502)


@app.exception_handler(404)
async def not_found(_: Request, __: Exception) -> JSONResponse:
    return JSONResponse({"ok": False, "error": "Endpoint not found."}, status_code=404)
