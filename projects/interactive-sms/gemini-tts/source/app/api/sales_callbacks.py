from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import json
import secrets
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.constants import ASSET_VERSION
from app.core.config import settings
from app.core.database import get_db
from app.models.document import ChatbotLead, SalesCallbackRequest
from app.services.route_service import get_app_base_path


TARGET_CLIENT_SLUG = "central-e-commerce-co-ltd"
SESSION_COOKIE_NAME = "jormall_interactive_sms_sales_session"
SESSION_MAX_AGE_SECONDS = settings.admin_session_timeout
APP_BASE_PATH = get_app_base_path()
LOGIN_WINDOW_SECONDS = 10 * 60
MAX_FAILED_LOGINS = 5

BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
failed_login_attempts: dict[str, deque[float]] = defaultdict(deque)

router = APIRouter(tags=["Sales Callback Dashboard"])


def dashboard_password() -> str:
    secret = settings.callback_dashboard_password
    return secret.get_secret_value() if secret else ""


def session_signing_key() -> bytes:
    password = dashboard_password()
    if not password:
        raise HTTPException(
            status_code=503,
            detail="Sales callback dashboard password is not configured.",
        )
    return hashlib.sha256(f"sales-callback-dashboard:{password}".encode("utf-8")).digest()


def base64url_encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def base64url_decode(payload: str) -> bytes:
    padding = "=" * (-len(payload) % 4)
    return base64.urlsafe_b64decode(payload + padding)


def sign_payload(payload: str) -> str:
    signature = hmac.new(
        session_signing_key(),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64url_encode(signature)


def create_session_cookie() -> tuple[str, str]:
    session_payload = {
        "iat": int(time.time()),
        "csrf": secrets.token_urlsafe(24),
        "nonce": secrets.token_urlsafe(16),
    }
    encoded_payload = base64url_encode(
        json.dumps(session_payload, separators=(",", ":")).encode("utf-8")
    )
    signature = sign_payload(encoded_payload)
    return f"{encoded_payload}.{signature}", session_payload["csrf"]


def read_session_cookie(request: Request) -> dict[str, object] | None:
    cookie_value = request.cookies.get(SESSION_COOKIE_NAME, "")
    try:
        encoded_payload, signature = cookie_value.split(".", 1)
    except ValueError:
        return None

    expected_signature = sign_payload(encoded_payload)
    if not hmac.compare_digest(signature, expected_signature):
        return None

    try:
        payload = json.loads(base64url_decode(encoded_payload).decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return None

    issued_at = int(payload.get("iat") or 0)
    if issued_at <= 0 or time.time() - issued_at > SESSION_MAX_AGE_SECONDS:
        return None

    csrf = payload.get("csrf")
    if not isinstance(csrf, str) or not csrf:
        return None

    return payload


def require_dashboard_session(request: Request) -> dict[str, object]:
    session = read_session_cookie(request)
    if session is None:
        raise HTTPException(status_code=401, detail="Dashboard login is required.")
    return session


def require_csrf(request: Request, session: dict[str, object]) -> None:
    supplied = request.headers.get("x-csrf-token", "")
    expected = str(session.get("csrf") or "")
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=403, detail="Request could not be verified.")


def is_https_request(request: Request) -> bool:
    return (
        request.url.scheme == "https"
        or request.headers.get("x-forwarded-proto", "").lower() == "https"
    )


def client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def login_blocked(request: Request) -> bool:
    now = time.time()
    attempts = failed_login_attempts[client_ip(request)]
    while attempts and now - attempts[0] > LOGIN_WINDOW_SECONDS:
        attempts.popleft()
    return len(attempts) >= MAX_FAILED_LOGINS


def remember_failed_login(request: Request) -> None:
    failed_login_attempts[client_ip(request)].append(time.time())


def clear_failed_logins(request: Request) -> None:
    failed_login_attempts.pop(client_ip(request), None)


def request_base_path(request: Request) -> str:
    return APP_BASE_PATH if APP_BASE_PATH and request.url.path.startswith(APP_BASE_PATH) else ""


def dashboard_path(request: Request) -> str:
    return f"{request_base_path(request)}/sales-callbacks/"


def cookie_path(request: Request) -> str:
    return f"{APP_BASE_PATH}/" if APP_BASE_PATH and request.url.path.startswith(APP_BASE_PATH) else "/"


def redirect_to_dashboard(request: Request) -> RedirectResponse:
    return RedirectResponse(url=dashboard_path(request), status_code=303)


def render_login(
    request: Request,
    *,
    message: str = "",
    status_code: int = 200,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="sales_callbacks.html",
        status_code=status_code,
        context={
            "asset_version": ASSET_VERSION,
            "authenticated": False,
            "login_message": message,
            "csrf_token": "",
            "app_base_path": request_base_path(request),
            "dashboard_path": dashboard_path(request),
        },
    )


def request_filters(
    *,
    status: str = "pending",
    search: str = "",
    date_range: str = "",
) -> dict[str, str]:
    clean_status = status if status in {"pending", "contacted", "all"} else "pending"
    clean_date_range = date_range if date_range in {"today", "7d", "all"} else "all"
    return {
        "status": clean_status,
        "search": search.strip()[:100],
        "date_range": clean_date_range,
    }


def callback_statement(*, status: str, search: str, date_range: str):
    filters = request_filters(status=status, search=search, date_range=date_range)
    statement = (
        select(SalesCallbackRequest, ChatbotLead)
        .join(ChatbotLead, ChatbotLead.id == SalesCallbackRequest.lead_id)
        .where(SalesCallbackRequest.client_slug == TARGET_CLIENT_SLUG)
        .order_by(
            case(
                (SalesCallbackRequest.status == "pending", 0),
                (SalesCallbackRequest.status == "contacted", 1),
                else_=2,
            ),
            SalesCallbackRequest.requested_at.desc(),
        )
    )

    if filters["status"] != "all":
        statement = statement.where(SalesCallbackRequest.status == filters["status"])

    if filters["search"]:
        like_pattern = f"%{filters['search']}%"
        statement = statement.where(
            or_(
                ChatbotLead.name.ilike(like_pattern),
                ChatbotLead.phone.ilike(like_pattern),
            )
        )

    now = datetime.now(UTC)
    if filters["date_range"] == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        statement = statement.where(SalesCallbackRequest.requested_at >= start)
    elif filters["date_range"] == "7d":
        statement = statement.where(
            SalesCallbackRequest.requested_at >= now - timedelta(days=7)
        )

    return statement


def format_callback_row(
    callback: SalesCallbackRequest,
    lead: ChatbotLead,
) -> dict[str, str]:
    requested_at = callback.requested_at
    contacted_at = callback.contacted_at
    return {
        "id": str(callback.id),
        "name": lead.name,
        "phone": lead.phone,
        "requested_at": requested_at.isoformat(),
        "request_date": requested_at.strftime("%Y-%m-%d"),
        "request_time": requested_at.strftime("%H:%M"),
        "status": callback.status,
        "contacted_at": contacted_at.isoformat() if contacted_at else "",
        "contacted_date": contacted_at.strftime("%Y-%m-%d") if contacted_at else "",
        "contacted_time": contacted_at.strftime("%H:%M") if contacted_at else "",
        "client": callback.client_slug,
    }


@router.get("/sales-callbacks", include_in_schema=False)
def sales_callbacks_slash_redirect(request: Request):
    return redirect_to_dashboard(request)


@router.get("/sales-callbacks/", response_class=HTMLResponse, include_in_schema=False)
def sales_callbacks_dashboard(request: Request):
    session = read_session_cookie(request)
    if session is None:
        return render_login(request)

    return templates.TemplateResponse(
        request=request,
        name="sales_callbacks.html",
        context={
            "asset_version": ASSET_VERSION,
            "authenticated": True,
            "login_message": "",
            "csrf_token": session["csrf"],
            "app_base_path": request_base_path(request),
            "dashboard_path": dashboard_path(request),
        },
    )


@router.post("/sales-callbacks/login", include_in_schema=False)
def sales_callbacks_login(request: Request, password: str = Form("")):
    configured_password = dashboard_password()
    if not configured_password:
        return render_login(
            request,
            message="Dashboard password is not configured.",
            status_code=503,
        )

    if login_blocked(request):
        return render_login(
            request,
            message="Too many failed attempts. Please try again later.",
            status_code=429,
        )

    if not hmac.compare_digest(password, configured_password):
        remember_failed_login(request)
        return render_login(
            request,
            message="Access denied. Please check the password.",
            status_code=401,
        )

    clear_failed_logins(request)
    cookie_value, _ = create_session_cookie()
    response = redirect_to_dashboard(request)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        cookie_value,
        max_age=settings.admin_session_timeout,
        httponly=True,
        secure=is_https_request(request),
        samesite="lax",
        path=cookie_path(request),
    )
    return response


@router.post("/sales-callbacks/logout", include_in_schema=False)
def sales_callbacks_logout(request: Request):
    response = redirect_to_dashboard(request)
    response.delete_cookie(SESSION_COOKIE_NAME, path=cookie_path(request))
    return response


@router.get("/api/admin/sales-callback-dashboard/requests")
def dashboard_callback_requests(
    request: Request,
    status: str = "pending",
    search: str = "",
    date_range: str = "all",
    _: dict[str, object] = Depends(require_dashboard_session),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        callback_statement(status=status, search=search, date_range=date_range)
    ).all()
    return {
        "client_slug": TARGET_CLIENT_SLUG,
        "total": len(rows),
        "requests": [
            format_callback_row(callback, lead)
            for callback, lead in rows
        ],
    }


@router.post("/api/admin/sales-callback-requests/{request_id}/contacted")
def mark_sales_callback_contacted(
    request_id: UUID,
    request: Request,
    session: dict[str, object] = Depends(require_dashboard_session),
    db: Session = Depends(get_db),
):
    require_csrf(request, session)
    callback = db.scalar(
        select(SalesCallbackRequest).where(
            SalesCallbackRequest.id == request_id,
            SalesCallbackRequest.client_slug == TARGET_CLIENT_SLUG,
        )
    )
    if callback is None:
        raise HTTPException(status_code=404, detail="Callback request not found.")

    if callback.status != "contacted":
        callback.status = "contacted"
    if callback.contacted_at is None:
        callback.contacted_at = func.now()
    callback.updated_at = func.now()
    db.commit()

    return {
        "success": True,
        "message": "The request has been marked as contacted.",
        "status": "contacted",
    }


@router.get("/api/admin/sales-callback-dashboard/export.csv")
def dashboard_callback_export(
    request: Request,
    status: str = "all",
    search: str = "",
    date_range: str = "all",
    _: dict[str, object] = Depends(require_dashboard_session),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        callback_statement(status=status, search=search, date_range=date_range)
    ).all()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Customer Name",
            "Mobile Number",
            "Request Date",
            "Request Time",
            "Status",
            "Contacted At",
            "Client",
        ]
    )
    for callback, lead in rows:
        formatted = format_callback_row(callback, lead)
        writer.writerow(
            [
                formatted["name"],
                formatted["phone"],
                formatted["request_date"],
                formatted["request_time"],
                formatted["status"],
                formatted["contacted_at"],
                formatted["client"],
            ]
        )

    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=sales_callback_requests.csv"},
    )
