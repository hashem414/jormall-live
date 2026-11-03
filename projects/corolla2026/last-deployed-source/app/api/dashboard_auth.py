from __future__ import annotations

import hmac
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.constants import ASSET_VERSION
from app.services import dashboard_auth_service
from app.services.client_config_service import load_client_config


BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(tags=["Dashboard Authentication"])
TARGET_CLIENT_SLUG = "central-trade-auto-co-markazia-toyota-jordan"


def default_dashboard_path() -> str:
    if getattr(dashboard_auth_service.settings, "sales_callback_dashboard_enabled", True):
        return dashboard_auth_service.public_path("/sales-callbacks/")
    if getattr(dashboard_auth_service.settings, "chat_history_dashboard_enabled", True):
        return dashboard_auth_service.public_path("/chat-history/")
    return dashboard_auth_service.public_path("/")


def dashboard_logo_url() -> str:
    fallback = "/static/client_assets/central-trade-auto-co-markazia-toyota-jordan/logo.jpg"
    try:
        config = load_client_config(TARGET_CLIENT_SLUG)
    except FileNotFoundError:
        return dashboard_auth_service.public_path(fallback)

    logo_url = config.logo_url or fallback
    if logo_url.startswith("/"):
        return dashboard_auth_service.public_path(logo_url)
    return logo_url


def render_login(
    request: Request,
    *,
    message: str = "",
    status_code: int = 200,
    next_path: str = "",
) -> HTMLResponse:
    safe_next = dashboard_auth_service.safe_next_path(
        next_path or request.query_params.get("next"),
        default=default_dashboard_path(),
    )
    return templates.TemplateResponse(
        request=request,
        name="dashboard_login.html",
        status_code=status_code,
        context={
            "asset_version": ASSET_VERSION,
            "app_base_path": dashboard_auth_service.clean_base_path(),
            "dashboard_base_path": dashboard_auth_service.clean_base_path(),
            "logo_url": dashboard_logo_url(),
            "login_message": message,
            "next_path": safe_next,
        },
    )


@router.get("/admin/login", response_class=HTMLResponse, include_in_schema=False)
def dashboard_login_page(request: Request, next: str = ""):
    if dashboard_auth_service.read_session_cookie(request) is not None:
        return RedirectResponse(
            url=dashboard_auth_service.safe_next_path(next, default=default_dashboard_path()),
            status_code=303,
        )
    return render_login(request, next_path=next)


@router.post("/admin/login", include_in_schema=False)
def dashboard_login(
    request: Request,
    password: str = Form(""),
    next: str = Form(""),
):
    configured_password = dashboard_auth_service.dashboard_password()
    if not configured_password:
        return render_login(
            request,
            message="Dashboard password is not configured.",
            status_code=503,
            next_path=next,
        )

    if dashboard_auth_service.login_blocked(request):
        return render_login(
            request,
            message="Too many failed attempts. Please try again later.",
            status_code=429,
            next_path=next,
        )

    if not hmac.compare_digest(password, configured_password):
        dashboard_auth_service.remember_failed_login(request)
        return render_login(
            request,
            message="Access denied. Please check the password.",
            status_code=401,
            next_path=next,
        )

    dashboard_auth_service.clear_failed_logins(request)
    cookie_value, _ = dashboard_auth_service.create_session_cookie()
    response = RedirectResponse(
        url=dashboard_auth_service.safe_next_path(next, default=default_dashboard_path()),
        status_code=303,
    )
    dashboard_auth_service.set_session_cookie(response, cookie_value, request)
    return response


@router.post("/admin/logout", include_in_schema=False)
def dashboard_logout():
    response = RedirectResponse(url=dashboard_auth_service.public_path("/admin/login"), status_code=303)
    dashboard_auth_service.clear_session_cookie(response)
    return response
