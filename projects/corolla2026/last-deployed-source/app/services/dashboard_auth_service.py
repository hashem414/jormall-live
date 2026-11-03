from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections import defaultdict, deque
from urllib.parse import quote

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app.core.config import settings


SESSION_COOKIE_NAME = "chatbot_dashboard_session"
SESSION_MAX_AGE_SECONDS = 8 * 60 * 60
LOGIN_WINDOW_SECONDS = 10 * 60
MAX_FAILED_LOGINS = 5

failed_login_attempts: dict[str, deque[float]] = defaultdict(deque)


def clean_base_path(value: str | None = None) -> str:
    raw = settings.app_base_path if value is None else value
    cleaned = "/" + str(raw or "").strip().strip("/")
    return "" if cleaned == "/" else cleaned.rstrip("/")


def public_path(path: str) -> str:
    base_path = clean_base_path()
    suffix = "/" + str(path or "").strip().lstrip("/")
    return f"{base_path}{suffix}" if base_path else suffix


def safe_next_path(value: str | None, *, default: str = "") -> str:
    base_path = clean_base_path()
    default_candidate = str(default or "/").strip()
    fallback = (
        default_candidate
        if (
            default_candidate == base_path
            or default_candidate == f"{base_path}/"
            or (base_path and default_candidate.startswith(f"{base_path}/"))
            or (not base_path and default_candidate.startswith("/"))
        )
        else public_path(default_candidate)
    )
    candidate = str(value or "").strip()
    if not candidate or candidate.startswith("//"):
        return fallback
    if "://" in candidate:
        return fallback
    if candidate == base_path or candidate == f"{base_path}/":
        return candidate or "/"
    if base_path and candidate.startswith(f"{base_path}/"):
        return candidate
    if not base_path and candidate.startswith("/"):
        return candidate
    return fallback


def login_path(next_path: str | None = "") -> str:
    path = public_path("/admin/login")
    safe_next = safe_next_path(next_path, default="/")
    if safe_next:
        return f"{path}?next={quote(safe_next, safe='')}"
    return path


def redirect_to_login(next_path: str | None = "") -> RedirectResponse:
    return RedirectResponse(url=login_path(next_path), status_code=303)


def set_session_cookie(response: Response, cookie_value: str, request: Request) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        cookie_value,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=is_cookie_secure(request),
        samesite="lax",
        path=cookie_path(),
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path=cookie_path())


def cookie_path() -> str:
    return clean_base_path() or "/"


def configured_username() -> str:
    return settings.dashboard_username.strip()


def dashboard_password() -> str:
    secret = settings.dashboard_password or settings.callback_dashboard_password
    return secret.get_secret_value() if secret else ""


def configured_secret(value, *, fallback: str) -> str:
    return value.get_secret_value() if value else fallback


def session_signing_key() -> bytes:
    password = dashboard_password()
    if not password:
        raise HTTPException(
            status_code=503,
            detail="Dashboard password is not configured.",
        )
    material = configured_secret(settings.session_secret, fallback=password)
    return hashlib.sha256(f"chatbot-dashboard-session:{material}".encode("utf-8")).digest()


def csrf_signing_key() -> bytes:
    password = dashboard_password()
    material = configured_secret(settings.csrf_secret, fallback=password)
    return hashlib.sha256(f"chatbot-dashboard-csrf:{material}".encode("utf-8")).digest()


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


def sign_csrf(payload: str) -> str:
    signature = hmac.new(
        csrf_signing_key(),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64url_encode(signature)


def create_session_cookie() -> tuple[str, str]:
    csrf_payload = secrets.token_urlsafe(24)
    csrf_token = f"{csrf_payload}.{sign_csrf(csrf_payload)}"
    session_payload = {
        "iat": int(time.time()),
        "csrf": csrf_token,
        "nonce": secrets.token_urlsafe(16),
    }
    encoded_payload = base64url_encode(
        json.dumps(session_payload, separators=(",", ":")).encode("utf-8")
    )
    signature = sign_payload(encoded_payload)
    return f"{encoded_payload}.{signature}", csrf_token


def valid_csrf_token(value: str) -> bool:
    try:
        payload, signature = value.split(".", 1)
    except ValueError:
        return False
    return hmac.compare_digest(signature, sign_csrf(payload))


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
    if not isinstance(csrf, str) or not csrf or not valid_csrf_token(csrf):
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


def is_cookie_secure(request: Request) -> bool:
    return bool(settings.cookie_secure and is_https_request(request))


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
