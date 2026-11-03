from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import json
import os
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
from app.services import dashboard_auth_service
from app.services.client_config_service import load_client_config


TARGET_CLIENT_SLUG = os.getenv(
    "STANDALONE_CLIENT_SLUG",
    "-".join(["central", "e", "commerce", "co", "ltd"]),
).strip()
SESSION_COOKIE_NAME = dashboard_auth_service.SESSION_COOKIE_NAME
SESSION_MAX_AGE_SECONDS = 8 * 60 * 60
LOGIN_WINDOW_SECONDS = 10 * 60
MAX_FAILED_LOGINS = 5

BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
failed_login_attempts: dict[str, deque[float]] = defaultdict(deque)

router = APIRouter(tags=["Sales Callback Dashboard"])


def dashboard_password() -> str:
    return dashboard_auth_service.dashboard_password()


def session_signing_key() -> bytes:
    return dashboard_auth_service.session_signing_key()


def base64url_encode(payload: bytes) -> str:
    return dashboard_auth_service.base64url_encode(payload)


def base64url_decode(payload: str) -> bytes:
    return dashboard_auth_service.base64url_decode(payload)


def sign_payload(payload: str) -> str:
    return dashboard_auth_service.sign_payload(payload)


def create_session_cookie() -> tuple[str, str]:
    return dashboard_auth_service.create_session_cookie()


def read_session_cookie(request: Request) -> dict[str, object] | None:
    return dashboard_auth_service.read_session_cookie(request)


def require_dashboard_session(request: Request) -> dict[str, object]:
    return dashboard_auth_service.require_dashboard_session(request)


def require_csrf(request: Request, session: dict[str, object]) -> None:
    dashboard_auth_service.require_csrf(request, session)


def is_https_request(request: Request) -> bool:
    return dashboard_auth_service.is_cookie_secure(request)


def client_ip(request: Request) -> str:
    return dashboard_auth_service.client_ip(request)


def login_blocked(request: Request) -> bool:
    return dashboard_auth_service.login_blocked(request)


def remember_failed_login(request: Request) -> None:
    dashboard_auth_service.remember_failed_login(request)


def clear_failed_logins(request: Request) -> None:
    dashboard_auth_service.clear_failed_logins(request)


def redirect_to_dashboard() -> RedirectResponse:
    return RedirectResponse(
        url=dashboard_auth_service.public_path("/sales-callbacks/"),
        status_code=303,
    )


def dashboard_logo_url() -> str:
    try:
        config = load_client_config(TARGET_CLIENT_SLUG)
    except FileNotFoundError:
        return dashboard_auth_service.public_path(
            "/static/client_assets/central-trade-auto-co-markazia-toyota-jordan/logo.jpg"
        )
    logo_url = config.logo_url or "/static/client_assets/central-trade-auto-co-markazia-toyota-jordan/logo.jpg"
    if logo_url.startswith("/"):
        return dashboard_auth_service.public_path(logo_url)
    return logo_url


def dashboard_template_context(
    *,
    authenticated: bool,
    login_message: str = "",
    csrf_token: str = "",
) -> dict[str, object]:
    return {
        "asset_version": ASSET_VERSION,
        "authenticated": authenticated,
        "login_message": login_message,
        "csrf_token": csrf_token,
        "app_base_path": dashboard_auth_service.clean_base_path(),
        "dashboard_base_path": dashboard_auth_service.clean_base_path(),
        "next_path": dashboard_auth_service.public_path("/sales-callbacks/"),
        "logo_url": dashboard_logo_url(),
    }


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
        context=dashboard_template_context(
            authenticated=False,
            login_message=message,
        ),
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
def legacy_sales_callbacks_redirect():
    return redirect_to_dashboard()


@router.get("/sales-callbacks/", response_class=HTMLResponse, include_in_schema=False)
def sales_callbacks_dashboard(request: Request):
    session = read_session_cookie(request)
    if session is None:
        return dashboard_auth_service.redirect_to_login(
            dashboard_auth_service.public_path("/sales-callbacks/")
        )

    return templates.TemplateResponse(
        request=request,
        name="sales_callbacks.html",
        context=dashboard_template_context(
            authenticated=True,
            csrf_token=str(session["csrf"]),
        ),
    )


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
