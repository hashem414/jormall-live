from __future__ import annotations

import csv
import hmac
import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.sales_callbacks import SESSION_COOKIE_NAME, clear_failed_logins, cookie_path, create_session_cookie, dashboard_password, is_https_request, login_blocked, read_session_cookie, remember_failed_login, require_csrf, require_dashboard_session, request_base_path
from app.constants import ASSET_VERSION
from app.core.config import settings
from app.core.database import get_db
from app.models.voice_usage import VoiceApiRequest, VoiceUsageSyncState
from app.voice.usage_sync import sync_soniox_usage


TARGET_CLIENT_SLUG = "central-e-commerce-co-ltd"
MAX_PAGE_SIZE = 100
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))
router = APIRouter(tags=["Voice Usage Dashboard"])


def dashboard_path(request: Request) -> str:
    return f"{request_base_path(request)}/voice-usage/"


def client_usage_path(request: Request) -> str:
    return f"{request_base_path(request)}/client-usage/"


def _redirect(request: Request) -> RedirectResponse:
    return RedirectResponse(url=dashboard_path(request), status_code=303)


def _render(request: Request, *, authenticated: bool, message: str = "", status_code: int = 200):
    session = read_session_cookie(request) if authenticated else None
    return templates.TemplateResponse(
        request=request,
        name="voice_usage.html",
        status_code=status_code,
        context={
            "asset_version": ASSET_VERSION,
            "authenticated": bool(session),
            "login_message": message,
            "csrf_token": str(session.get("csrf") or "") if session else "",
            "app_base_path": request_base_path(request),
            "dashboard_path": dashboard_path(request),
        },
    )


def _render_client(request: Request, *, authenticated: bool, message: str = "", status_code: int = 200):
    session = read_session_cookie(request) if authenticated else None
    response = templates.TemplateResponse(
        request=request,
        name="client_usage.html",
        status_code=status_code,
        context={
            "asset_version": ASSET_VERSION,
            "authenticated": bool(session),
            "login_message": message,
            "csrf_token": str(session.get("csrf") or "") if session else "",
            "app_base_path": request_base_path(request),
            "dashboard_path": client_usage_path(request),
        },
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _statement(*, days: int, provider: str, operation: str, language: str, status: str):
    days = min(max(days, 1), 366)
    statement = select(VoiceApiRequest).where(
        VoiceApiRequest.client_slug == TARGET_CLIENT_SLUG,
        VoiceApiRequest.started_at >= datetime.now(UTC) - timedelta(days=days),
    )
    if provider in {"soniox", "openai"}:
        statement = statement.where(VoiceApiRequest.provider == provider)
    if operation in {"stt", "tts", "chat", "embedding"}:
        statement = statement.where(VoiceApiRequest.operation == operation)
    if language in {"en", "ar", "auto"}:
        statement = statement.where(VoiceApiRequest.language == language)
    if status in {"started", "completed", "failed", "cancelled"}:
        statement = statement.where(VoiceApiRequest.status == status)
    return statement


def _percentile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(len(ordered) * percentile) - 1))]


def _money(value) -> float:
    return float(value or Decimal("0"))


def _voice_allowance(rows: list[VoiceApiRequest], operation: str, limit: int) -> dict[str, float | str]:
    duration_field = "input_audio_duration_ms" if operation == "stt" else "output_audio_duration_ms"
    used = sum(getattr(row, duration_field) or 0 for row in rows if row.operation == operation) / 60000
    remaining = max(0.0, limit - used)
    return {
        "used_minutes": round(used, 3), "limit_minutes": limit,
        "remaining_minutes": round(remaining, 3),
        "status": "red" if remaining <= 30 else "yellow" if remaining <= 50 else "green",
    }


def _row(row: VoiceApiRequest) -> dict[str, object]:
    return {
        "id": str(row.id), "provider": row.provider, "operation": row.operation,
        "model": row.model, "voice": row.voice, "language": row.language,
        "status": row.status, "client_reference_id": row.client_reference_id,
        "provider_request_id": row.provider_request_id or "", "request_scope": row.provider_request_scope,
        "cache_hit": row.cache_hit, "input_audio_bytes": row.input_audio_bytes,
        "output_audio_bytes": row.output_audio_bytes, "input_text_characters": row.input_text_characters,
        "input_audio_duration_ms": row.input_audio_duration_ms, "output_audio_duration_ms": row.output_audio_duration_ms,
        "request_duration_ms": row.request_duration_ms, "first_audio_ms": row.first_audio_ms,
        "confirmed_cost_usd": _money(row.confirmed_cost_usd), "estimated_cost_usd": _money(row.estimated_cost_usd),
        "input_text_tokens": row.input_text_tokens, "output_text_tokens": row.output_text_tokens,
        "reconciled": row.reconciled_at is not None, "error_type": row.error_type,
        "started_at": row.started_at.isoformat() if row.started_at else "",
        "finished_at": row.finished_at.isoformat() if row.finished_at else "",
        "reconciled_at": row.reconciled_at.isoformat() if row.reconciled_at else "",
    }


def _client_row(row: VoiceApiRequest) -> dict[str, object]:
    """Client-safe request representation; billing fields are intentionally omitted."""
    return {
        "id": str(row.id), "provider": row.provider, "operation": row.operation,
        "model": row.model, "voice": row.voice, "language": row.language,
        "status": row.status, "client_reference_id": row.client_reference_id,
        "provider_request_id": row.provider_request_id or "", "request_scope": row.provider_request_scope,
        "cache_hit": row.cache_hit, "input_audio_duration_ms": row.input_audio_duration_ms,
        "output_audio_duration_ms": row.output_audio_duration_ms,
        "input_text_tokens": row.input_text_tokens, "output_text_tokens": row.output_text_tokens,
        "request_duration_ms": row.request_duration_ms, "first_audio_ms": row.first_audio_ms,
        "started_at": row.started_at.isoformat() if row.started_at else "",
        "finished_at": row.finished_at.isoformat() if row.finished_at else "",
        "error_type": row.error_type,
    }


def _budget(current: float, limit: float) -> dict[str, object]:
    percent = current / limit * 100 if limit > 0 else 0.0
    status = "disabled" if limit <= 0 else "exceeded" if percent >= 100 else "warning" if percent >= 80 else "ok"
    return {"spent_usd": current, "limit_usd": limit, "percent": round(percent, 1), "status": status}


@router.get("/voice-usage", include_in_schema=False)
def slash_redirect(request: Request):
    return _redirect(request)


@router.get("/voice-usage/", response_class=HTMLResponse, include_in_schema=False)
def voice_usage_dashboard(request: Request):
    return _render(request, authenticated=read_session_cookie(request) is not None)


@router.get("/client-usage", include_in_schema=False)
def client_usage_slash_redirect(request: Request):
    return RedirectResponse(url=client_usage_path(request), status_code=303)


@router.get("/client-usage/", response_class=HTMLResponse, include_in_schema=False)
def client_usage_dashboard(request: Request):
    return _render_client(request, authenticated=read_session_cookie(request) is not None)


@router.post("/client-usage/login", include_in_schema=False)
def client_usage_login(request: Request, password: str = Form("")):
    configured = dashboard_password()
    if not configured:
        return _render_client(request, authenticated=False, message="Dashboard password is not configured.", status_code=503)
    if login_blocked(request):
        return _render_client(request, authenticated=False, message="Too many failed attempts. Please try again later.", status_code=429)
    if not hmac.compare_digest(password, configured):
        remember_failed_login(request)
        return _render_client(request, authenticated=False, message="Access denied. Please check the password.", status_code=401)
    clear_failed_logins(request)
    value, _ = create_session_cookie()
    response = RedirectResponse(url=client_usage_path(request), status_code=303)
    response.set_cookie(SESSION_COOKIE_NAME, value, max_age=settings.admin_session_timeout, httponly=True, secure=is_https_request(request), samesite="lax", path=cookie_path(request))
    return response


@router.post("/client-usage/logout", include_in_schema=False)
def client_usage_logout(request: Request):
    response = RedirectResponse(url=client_usage_path(request), status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME, path=cookie_path(request))
    return response


@router.get("/api/client/usage/summary")
def client_usage_summary(
    request: Request,
    days: int = 30,
    provider: str = "",
    operation: str = "",
    language: str = "",
    status: str = "",
    _: dict = Depends(require_dashboard_session),
    db: Session = Depends(get_db),
):
    rows = list(db.execute(_statement(days=days, provider=provider, operation=operation, language=language, status=status).order_by(VoiceApiRequest.started_at)).scalars())
    now = datetime.now(UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_rows = list(db.execute(select(VoiceApiRequest).where(
        VoiceApiRequest.client_slug == TARGET_CLIENT_SLUG,
        VoiceApiRequest.provider == "openai",
        VoiceApiRequest.started_at >= month_start,
    )).scalars())
    monthly_voice_rows = list(db.execute(select(VoiceApiRequest).where(
        VoiceApiRequest.client_slug == TARGET_CLIENT_SLUG,
        VoiceApiRequest.provider == "soniox",
        VoiceApiRequest.started_at >= month_start,
        VoiceApiRequest.operation.in_(("stt", "tts")),
    )).scalars())
    input_tokens = sum(row.input_text_tokens for row in rows if row.provider == "openai")
    output_tokens = sum(row.output_text_tokens for row in rows if row.provider == "openai")
    monthly_input = sum(row.input_text_tokens for row in monthly_rows)
    monthly_output = sum(row.output_text_tokens for row in monthly_rows)
    monthly_used = monthly_input + monthly_output
    limit = settings.client_chatgpt_monthly_token_limit
    percent = round(monthly_used / limit * 100, 1) if limit else 0.0
    durations = [row.request_duration_ms for row in rows if row.request_duration_ms]
    first_audio = [row.first_audio_ms for row in rows if row.operation == "tts" and row.first_audio_ms]
    return {
        "requests": len(rows), "completed": sum(row.status == "completed" for row in rows),
        "failed": sum(row.status == "failed" for row in rows), "cancelled": sum(row.status == "cancelled" for row in rows),
        "cache_hits": sum(bool(row.cache_hit) for row in rows),
        "openai": {"requests": sum(row.provider == "openai" for row in rows), "input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": input_tokens + output_tokens, "chat_requests": sum(row.provider == "openai" and row.operation == "chat" for row in rows), "embedding_requests": sum(row.provider == "openai" and row.operation == "embedding" for row in rows)},
        "monthly_limit": {"month": month_start.date().isoformat(), "used_tokens": monthly_used, "input_tokens": monthly_input, "output_tokens": monthly_output, "limit_tokens": limit, "percent": percent, "status": "exceeded" if monthly_used >= limit else "warning" if percent >= 80 else "ok"},
        "monthly_voice": {
            "input": _voice_allowance(monthly_voice_rows, "stt", settings.client_voice_input_monthly_minutes),
            "output": _voice_allowance(monthly_voice_rows, "tts", settings.client_voice_output_monthly_minutes),
        },
        "stt_minutes": round(sum(row.input_audio_duration_ms for row in rows if row.operation == "stt") / 60000, 3),
        "tts_minutes": round(sum(row.output_audio_duration_ms for row in rows if row.operation == "tts") / 60000, 3),
        "request_ms": {"p50": _percentile(durations, .5), "p95": _percentile(durations, .95), "avg": round(sum(durations) / len(durations)) if durations else 0},
        "first_audio_ms": {"p50": _percentile(first_audio, .5), "p95": _percentile(first_audio, .95)},
    }


@router.get("/api/client/usage/requests")
def client_usage_requests(
    request: Request, page: int = 1, page_size: int = 25, days: int = 30,
    provider: str = "", operation: str = "", language: str = "", status: str = "",
    _: dict = Depends(require_dashboard_session), db: Session = Depends(get_db),
):
    page, page_size = max(page, 1), min(max(page_size, 1), MAX_PAGE_SIZE)
    base = _statement(days=days, provider=provider, operation=operation, language=language, status=status)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(base.order_by(VoiceApiRequest.started_at.desc()).offset((page - 1) * page_size).limit(page_size)).scalars()
    return {"items": [_client_row(row) for row in rows], "page": page, "page_size": page_size, "total": total}


@router.get("/api/client/usage/requests/{request_id}")
def client_usage_request_detail(request_id: UUID, request: Request, _: dict = Depends(require_dashboard_session), db: Session = Depends(get_db)):
    row = db.get(VoiceApiRequest, request_id)
    if row is None or row.client_slug != TARGET_CLIENT_SLUG:
        raise HTTPException(status_code=404, detail="Usage request not found.")
    return _client_row(row)


@router.post("/voice-usage/login", include_in_schema=False)
def login(request: Request, password: str = Form("")):
    configured = dashboard_password()
    if not configured:
        return _render(request, authenticated=False, message="Dashboard password is not configured.", status_code=503)
    if login_blocked(request):
        return _render(request, authenticated=False, message="Too many failed attempts. Please try again later.", status_code=429)
    if not hmac.compare_digest(password, configured):
        remember_failed_login(request)
        return _render(request, authenticated=False, message="Access denied. Please check the password.", status_code=401)
    clear_failed_logins(request)
    value, _ = create_session_cookie()
    response = _redirect(request)
    response.set_cookie(SESSION_COOKIE_NAME, value, max_age=settings.admin_session_timeout, httponly=True, secure=is_https_request(request), samesite="lax", path=cookie_path(request))
    return response


@router.post("/voice-usage/logout", include_in_schema=False)
def logout(request: Request):
    response = _redirect(request)
    response.delete_cookie(SESSION_COOKIE_NAME, path=cookie_path(request))
    return response


@router.get("/api/admin/voice-usage/summary")
def summary(request: Request, days: int = 30, provider: str = "", operation: str = "", language: str = "", status: str = "", _: dict = Depends(require_dashboard_session), db: Session = Depends(get_db)):
    rows = list(db.execute(_statement(days=days, provider=provider, operation=operation, language=language, status=status).order_by(VoiceApiRequest.started_at)).scalars())
    now = datetime.now(UTC)
    daily = {}
    for row in rows:
        key = row.started_at.date().isoformat()
        bucket = daily.setdefault(key, {"date": key, "requests": 0, "cost_usd": 0.0})
        bucket["requests"] += 1
        bucket["cost_usd"] += _money(row.confirmed_cost_usd)
    today_cost = sum(_money(row.confirmed_cost_usd) for row in rows if row.started_at.date() == now.date())
    month_cost = sum(_money(row.confirmed_cost_usd) for row in rows if row.started_at.year == now.year and row.started_at.month == now.month)
    durations = [row.request_duration_ms for row in rows if row.request_duration_ms]
    first_audio = [row.first_audio_ms for row in rows if row.operation == "tts" and row.first_audio_ms]
    openai_rows = [row for row in rows if row.provider == "openai"]
    soniox_cost = sum(_money(row.confirmed_cost_usd) for row in rows if row.provider == "soniox")
    openai_cost = sum(_money(row.estimated_cost_usd) for row in openai_rows)
    return {
        "requests": len(rows), "completed": sum(row.status == "completed" for row in rows),
        "failed": sum(row.status == "failed" for row in rows), "cancelled": sum(row.status == "cancelled" for row in rows),
        "cache_hits": sum(bool(row.cache_hit) for row in rows), "confirmed_cost_usd": round(soniox_cost, 6),
        "estimated_cost_usd": round(openai_cost, 6), "total_cost_usd": round(soniox_cost + openai_cost, 6),
        "openai": {"requests": len(openai_rows), "input_tokens": sum(row.input_text_tokens for row in openai_rows), "output_tokens": sum(row.output_text_tokens for row in openai_rows), "chat_requests": sum(row.operation == "chat" for row in openai_rows), "embedding_requests": sum(row.operation == "embedding" for row in openai_rows)},
        "stt_minutes": round(sum(row.input_audio_duration_ms for row in rows if row.operation == "stt") / 60000, 3),
        "tts_minutes": round(sum(row.output_audio_duration_ms for row in rows if row.operation == "tts") / 60000, 3),
        "request_ms": {"p50": _percentile(durations, .5), "p95": _percentile(durations, .95)},
        "first_audio_ms": {"p50": _percentile(first_audio, .5), "p95": _percentile(first_audio, .95)},
        "daily": list(daily.values()),
        "budgets": {"daily": _budget(today_cost + sum(_money(row.estimated_cost_usd) for row in openai_rows if row.started_at.date() == now.date()), settings.voice_daily_budget_usd), "monthly": _budget(month_cost + sum(_money(row.estimated_cost_usd) for row in openai_rows if row.started_at.year == now.year and row.started_at.month == now.month), settings.voice_monthly_budget_usd)},
        "cost_note": "Soniox cost is confirmed from provider logs. OpenAI cost is estimated only when per-million token rates are configured; token counts are recorded from API responses.",
    }


@router.get("/api/admin/voice-usage/requests")
def requests_list(request: Request, page: int = 1, page_size: int = 25, days: int = 30, provider: str = "", operation: str = "", language: str = "", status: str = "", _: dict = Depends(require_dashboard_session), db: Session = Depends(get_db)):
    page, page_size = max(page, 1), min(max(page_size, 1), MAX_PAGE_SIZE)
    base = _statement(days=days, provider=provider, operation=operation, language=language, status=status)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(base.order_by(VoiceApiRequest.started_at.desc()).offset((page - 1) * page_size).limit(page_size)).scalars()
    return {"items": [_row(row) for row in rows], "page": page, "page_size": page_size, "total": total}


@router.get("/api/admin/voice-usage/requests/{request_id}")
def request_detail(request_id: UUID, request: Request, _: dict = Depends(require_dashboard_session), db: Session = Depends(get_db)):
    row = db.get(VoiceApiRequest, request_id)
    if row is None or row.client_slug != TARGET_CLIENT_SLUG:
        raise HTTPException(status_code=404, detail="Voice request not found.")
    return _row(row)


def _csv(value) -> str:
    text = str(value or "")
    return f"'{text}" if text[:1] in {"=", "+", "-", "@"} else text


@router.get("/api/admin/voice-usage/export.csv")
def export_csv(request: Request, days: int = 30, provider: str = "", operation: str = "", language: str = "", status: str = "", _: dict = Depends(require_dashboard_session), db: Session = Depends(get_db)):
    rows = db.execute(_statement(days=days, provider=provider, operation=operation, language=language, status=status).order_by(VoiceApiRequest.started_at.desc()).limit(10000)).scalars()
    output = StringIO(); writer = csv.writer(output)
    fields = ["id", "started_at", "provider", "operation", "language", "model", "voice", "status", "cache_hit", "request_duration_ms", "first_audio_ms", "input_audio_duration_ms", "output_audio_duration_ms", "input_text_tokens", "output_text_tokens", "confirmed_cost_usd", "estimated_cost_usd", "reconciled", "client_reference_id", "provider_request_id", "error_type"]
    writer.writerow(fields)
    for row in rows:
        item = _row(row); writer.writerow([_csv(item[field]) for field in fields])
    return Response(output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=voice_api_usage.csv"})


@router.get("/api/admin/voice-usage/sync-status")
def sync_status(request: Request, _: dict = Depends(require_dashboard_session), db: Session = Depends(get_db)):
    state = db.get(VoiceUsageSyncState, "soniox")
    if state is None:
        return {"provider": "soniox", "status": "never_run", "enabled": settings.voice_usage_sync_enabled}
    return {"provider": "soniox", "status": "error" if state.last_error else "ok", "enabled": settings.voice_usage_sync_enabled, "last_attempt_at": state.last_attempt_at.isoformat() if state.last_attempt_at else "", "last_success_at": state.last_success_at.isoformat() if state.last_success_at else "", "last_imported_count": state.last_imported_count, "total_imported_count": state.total_imported_count, "consecutive_failures": state.consecutive_failures, "last_error": state.last_error}


@router.post("/api/admin/voice-usage/sync")
async def synchronize(request: Request, session: dict = Depends(require_dashboard_session)):
    require_csrf(request, session)
    try:
        return await run_in_threadpool(sync_soniox_usage)
    except Exception as error:
        raise HTTPException(status_code=502, detail="Soniox usage synchronization failed.") from error
