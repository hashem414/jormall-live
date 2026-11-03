import json
import os
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, request, session
from flask_session import Session
from werkzeug.middleware.proxy_fix import ProxyFix


app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
app.secret_key = os.environ["FLASK_SECRET_KEY"]
app.config.update(
    SESSION_TYPE="filesystem",
    SESSION_FILE_DIR=os.getenv("SESSION_FILE_DIR", "/app/flask_sessions"),
    SESSION_PERMANENT=False,
    SESSION_USE_SIGNER=True,
    SESSION_COOKIE_DOMAIN=os.getenv("SESSION_COOKIE_DOMAIN", ".jormallapp.com") or None,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
Session(app)

USER_DIRECTORY_URL = os.getenv(
    "USER_DIRECTORY_URL", "http://172.17.0.1:18101"
).strip().strip('"').strip("'").rstrip("/")
USER_DIRECTORY_TOKEN_FILE = os.getenv(
    "USER_DIRECTORY_TOKEN_FILE", "/app/.user-directory-token"
)
AI_ANALYTICS_USERS = {"admin", "ADMIN", "user30", "user31"}
ACTIVITY_LOG = os.getenv("SSO_ACTIVITY_LOG", "/app/logs/sso_activity.jsonl")


def directory_token():
    token = (os.getenv("USER_DIRECTORY_TOKEN") or "").strip().strip('"').strip("'")
    if token:
        return token
    try:
        with open(USER_DIRECTORY_TOKEN_FILE, "r", encoding="utf-8") as handle:
            return handle.read().strip().strip('"').strip("'")
    except OSError:
        return ""


def directory_request(path, payload):
    token = directory_token()
    if not token:
        return {"success": False, "error": "User directory is not configured."}, 503
    try:
        response = requests.post(
            f"{USER_DIRECTORY_URL}{path}",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        try:
            data = response.json()
        except ValueError:
            data = {"success": False, "error": "Invalid response from user directory."}
        return data, response.status_code
    except requests.RequestException:
        return {"success": False, "error": "User directory is temporarily unavailable."}, 503


def set_session_user(user, fallback_username=""):
    username = str(user.get("username") or fallback_username)
    categories = user.get("categories") or ["General"]
    session["logged_in"] = True
    session["username"] = username
    session["user_id"] = user.get("id")
    session["auth_version"] = user.get("updated_at")
    session["email"] = user.get("email") or ""
    session["role"] = user.get("role") or "user"
    session["allowed_categories"] = categories
    return username, categories


def refresh_session_user():
    username = str(session.get("username") or "")
    if not session.get("logged_in") or not username:
        return None
    identity = {"id": session.get("user_id")} if session.get("user_id") else {
        "identifier": username
    }
    data, status = directory_request("/status", identity)
    if status != 200 or not data.get("success"):
        session.clear()
        return None
    user = data.get("user") or {}
    previous_version = session.get("auth_version")
    current_version = user.get("updated_at")
    if previous_version and current_version and previous_version != current_version:
        session.clear()
        return None
    set_session_user(user, username)
    return user


def verification_response(user):
    username = str(user.get("username") or session.get("username") or "")
    is_admin = user.get("role") == "admin"
    categories = session.get("allowed_categories", ["General"])
    response = jsonify(
        {
            "success": True,
            "username": username,
            "email": session.get("email", ""),
            "is_admin": is_admin,
            "allowed_categories": categories,
            "auto_fill_credentials": "Non-Credentials Login" in categories,
            "can_ai_analytics": username in AI_ANALYTICS_USERS,
        }
    )
    response.headers["X-SSO-User"] = username
    response.headers["X-SSO-Admin"] = "1" if is_admin else "0"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/healthz")
def healthz():
    return jsonify({"status": "healthy", "service": "jormall-sso-auth"})


@app.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    identifier = str(data.get("username") or data.get("email") or "").strip()
    directory_data, directory_status = directory_request(
        "/verify", {"identifier": identifier, "password": data.get("password", "")}
    )
    if directory_status == 200 and directory_data.get("success"):
        user = directory_data.get("user") or {}
        username, categories = set_session_user(user, identifier)
        try:
            os.makedirs(os.path.dirname(ACTIVITY_LOG), exist_ok=True)
            with open(ACTIVITY_LOG, "a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "username": username[:120],
                            "action": "login",
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        except OSError:
            pass
        return jsonify(
            {
                "success": True,
                "username": username,
                "email": user.get("email") or "",
                "is_admin": session["role"] == "admin",
                "allowed_categories": categories,
                "auto_fill_credentials": "Non-Credentials Login" in categories,
                "can_ai_analytics": username in AI_ANALYTICS_USERS,
            }
        )
    if directory_status == 401:
        return jsonify({"success": False, "error": "Invalid username/email or password"}), 401
    return jsonify(directory_data), directory_status


@app.get("/sso/verify")
def sso_verify():
    user = refresh_session_user()
    if user is None:
        return jsonify({"success": False, "error": "Not authorized"}), 401
    return verification_response(user)


@app.get("/sso/verify-admin")
def sso_verify_admin():
    user = refresh_session_user()
    if user is None:
        return jsonify({"success": False, "error": "Not authorized"}), 401
    if user.get("role") != "admin":
        return jsonify({"success": False, "error": "Admin access required"}), 403
    response = jsonify(
        {"success": True, "username": user.get("username") or "", "is_admin": True}
    )
    response.headers["X-SSO-User"] = str(user.get("username") or "")
    response.headers["X-SSO-Admin"] = "1"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.post("/logout")
def logout():
    session.clear()
    response = jsonify({"success": True})
    response.delete_cookie(
        app.config.get("SESSION_COOKIE_NAME", "session"),
        path=app.config.get("SESSION_COOKIE_PATH", "/") or "/",
        domain=None,
        secure=True,
        httponly=True,
        samesite="Lax",
    )
    return response
