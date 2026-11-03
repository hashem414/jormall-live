#!/usr/bin/env python3
"""Internal JorMall user directory with hashed passwords and a small JSON API."""

from __future__ import annotations

import ast
import datetime as dt
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


DB_PATH = Path(os.environ.get("DIRECTORY_DB", "/var/lib/jormall/sso/users.db"))
LEGACY_APP_PATH = Path(os.environ.get("LEGACY_APP_PATH", "/opt/jormall/apps/assistant/build/app.py"))
DIRECTORY_TOKEN = os.environ.get("DIRECTORY_TOKEN", "")
BIND_HOST = os.environ.get("DIRECTORY_BIND", "172.17.0.1")
BIND_PORT = int(os.environ.get("DIRECTORY_PORT", "18101"))
MAX_BODY = 64 * 1024
PBKDF2_ITERATIONS = 600_000
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,64}$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
ALLOWED_ROLES = {"user", "admin"}
ALLOWED_CATEGORIES = {
    "General",
    "Order Processing",
    "Sales",
    "Technical",
    "Non-Credentials Login",
}


class DirectoryError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(message)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=WAL")
    return connection


def initialize_database() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','admin')),
                active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
                categories TEXT NOT NULL DEFAULT '["General"]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS users_email_unique
                ON users(lower(email)) WHERE email IS NOT NULL AND email <> '';
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                user_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            """
        )


def password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${derived.hex()}"


def password_matches(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_hex, expected_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        derived = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(derived.hex(), expected_hex)
    except (TypeError, ValueError):
        return False


def validated_categories(value: object) -> list[str]:
    if value is None:
        return ["General"]
    if not isinstance(value, list):
        raise DirectoryError(HTTPStatus.BAD_REQUEST, "Categories must be a list.")
    categories = [str(item) for item in value if str(item) in ALLOWED_CATEGORIES]
    if not categories:
        categories = ["General"]
    return list(dict.fromkeys(categories))


def public_user(row: sqlite3.Row) -> dict[str, object]:
    return {
        "id": row["id"],
        "username": row["username"],
        "email": row["email"] or "",
        "role": row["role"],
        "active": bool(row["active"]),
        "categories": json.loads(row["categories"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def audit(connection: sqlite3.Connection, actor: str, action: str, user_id: int | None) -> None:
    connection.execute(
        "INSERT INTO audit_log(actor,action,user_id,created_at) VALUES (?,?,?,?)",
        (actor or "system", action, user_id, utc_now()),
    )


def migrate_legacy_users() -> int:
    """Import the original hard-coded accounts once, hashing every password."""
    if not LEGACY_APP_PATH.is_file():
        return 0
    with connect() as connection:
        if connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            return 0

    tree = ast.parse(LEGACY_APP_PATH.read_text(encoding="utf-8"))
    users = None
    categories = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        names = {target.id for target in node.targets if isinstance(target, ast.Name)}
        if "USERS" in names:
            users = ast.literal_eval(node.value)
        elif "USER_CATEGORIES" in names:
            categories = ast.literal_eval(node.value)
    if not isinstance(users, dict):
        return 0
    categories = categories if isinstance(categories, dict) else {}
    now = utc_now()
    imported = 0
    with connect() as connection:
        for username, password in users.items():
            allowed = categories.get(username, ["General"])
            connection.execute(
                """INSERT OR IGNORE INTO users
                   (username,email,password_hash,role,active,categories,created_at,updated_at)
                   VALUES (?,NULL,?,?,?,?,?,?)""",
                (
                    username,
                    password_hash(str(password)),
                    "admin" if username in {"admin", "ADMIN"} else "user",
                    1,
                    json.dumps(allowed, separators=(",", ":")),
                    now,
                    now,
                ),
            )
            imported += connection.execute("SELECT changes()").fetchone()[0]
        audit(connection, "system", f"legacy_import:{imported}", None)
    return imported


def require_token(headers) -> None:
    supplied = headers.get("Authorization", "")
    expected = f"Bearer {DIRECTORY_TOKEN}"
    if not DIRECTORY_TOKEN or not hmac.compare_digest(supplied, expected):
        raise DirectoryError(HTTPStatus.UNAUTHORIZED, "Unauthorized.")


def verify_user(payload: dict[str, object]) -> dict[str, object]:
    identifier = str(payload.get("identifier") or payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    if not identifier or not password:
        raise DirectoryError(HTTPStatus.UNAUTHORIZED, "Invalid username/email or password.")
    with connect() as connection:
        row = connection.execute(
            """SELECT * FROM users
               WHERE active=1 AND (username=? OR (email IS NOT NULL AND lower(email)=lower(?)))
               LIMIT 1""",
            (identifier, identifier),
        ).fetchone()
    if row is None or not password_matches(password, row["password_hash"]):
        raise DirectoryError(HTTPStatus.UNAUTHORIZED, "Invalid username/email or password.")
    return public_user(row)


def active_user(payload: dict[str, object]) -> dict[str, object]:
    user_id = payload.get("id")
    identifier = str(payload.get("identifier") or payload.get("username") or "").strip()
    if not user_id and not identifier:
        raise DirectoryError(HTTPStatus.UNAUTHORIZED, "User is not active.")
    with connect() as connection:
        if user_id:
            row = connection.execute(
                "SELECT * FROM users WHERE active=1 AND id=?", (int(user_id),)
            ).fetchone()
        else:
            row = connection.execute(
                """SELECT * FROM users
                   WHERE active=1 AND (username=? OR (email IS NOT NULL AND lower(email)=lower(?)))
                   LIMIT 1""",
                (identifier, identifier),
            ).fetchone()
    if row is None:
        raise DirectoryError(HTTPStatus.UNAUTHORIZED, "User is not active.")
    return public_user(row)


def list_users() -> list[dict[str, object]]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM users ORDER BY CASE role WHEN 'admin' THEN 0 ELSE 1 END, lower(username)"
        ).fetchall()
    return [public_user(row) for row in rows]


def create_user(payload: dict[str, object]) -> dict[str, object]:
    username = str(payload.get("username") or "").strip()
    email = str(payload.get("email") or "").strip().lower()
    password = str(payload.get("password") or "")
    role = str(payload.get("role") or "user").strip().lower()
    actor = str(payload.get("actor") or "admin")
    if not USERNAME_RE.fullmatch(username):
        raise DirectoryError(HTTPStatus.BAD_REQUEST, "Username must be 3-64 letters, numbers, dots, dashes or underscores.")
    if not EMAIL_RE.fullmatch(email):
        raise DirectoryError(HTTPStatus.BAD_REQUEST, "Enter a valid email address.")
    if len(password) < 8:
        raise DirectoryError(HTTPStatus.BAD_REQUEST, "Password must be at least 8 characters.")
    if role not in ALLOWED_ROLES:
        raise DirectoryError(HTTPStatus.BAD_REQUEST, "Invalid role.")
    categories = validated_categories(payload.get("categories"))
    now = utc_now()
    try:
        with connect() as connection:
            cursor = connection.execute(
                """INSERT INTO users
                   (username,email,password_hash,role,active,categories,created_at,updated_at)
                   VALUES (?,?,?,?,1,?,?,?)""",
                (username, email, password_hash(password), role, json.dumps(categories), now, now),
            )
            audit(connection, actor, "create_user", cursor.lastrowid)
            row = connection.execute("SELECT * FROM users WHERE id=?", (cursor.lastrowid,)).fetchone()
    except sqlite3.IntegrityError as exc:
        raise DirectoryError(HTTPStatus.CONFLICT, "Username or email already exists.") from exc
    return public_user(row)


def update_user(user_id: int, payload: dict[str, object]) -> dict[str, object]:
    actor = str(payload.get("actor") or "admin")
    with connect() as connection:
        current = connection.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if current is None:
            raise DirectoryError(HTTPStatus.NOT_FOUND, "User not found.")
        email = current["email"]
        role = current["role"]
        active = bool(current["active"])
        categories = json.loads(current["categories"])
        if "email" in payload:
            email_value = str(payload.get("email") or "").strip().lower()
            if email_value and not EMAIL_RE.fullmatch(email_value):
                raise DirectoryError(HTTPStatus.BAD_REQUEST, "Enter a valid email address.")
            email = email_value or None
        if "role" in payload:
            role = str(payload.get("role") or "").lower()
            if role not in ALLOWED_ROLES:
                raise DirectoryError(HTTPStatus.BAD_REQUEST, "Invalid role.")
        if "active" in payload:
            active = bool(payload.get("active"))
        if "categories" in payload:
            categories = validated_categories(payload.get("categories"))
        removing_admin = current["role"] == "admin" and current["active"] and (role != "admin" or not active)
        if removing_admin:
            active_admins = connection.execute(
                "SELECT COUNT(*) FROM users WHERE role='admin' AND active=1"
            ).fetchone()[0]
            if active_admins <= 1:
                raise DirectoryError(HTTPStatus.BAD_REQUEST, "At least one active admin is required.")
        try:
            connection.execute(
                """UPDATE users SET email=?,role=?,active=?,categories=?,updated_at=? WHERE id=?""",
                (email, role, int(active), json.dumps(categories), utc_now(), user_id),
            )
            password = str(payload.get("password") or "")
            if password:
                if len(password) < 8:
                    raise DirectoryError(HTTPStatus.BAD_REQUEST, "Password must be at least 8 characters.")
                connection.execute(
                    "UPDATE users SET password_hash=?,updated_at=? WHERE id=?",
                    (password_hash(password), utc_now(), user_id),
                )
            audit(connection, actor, "update_user", user_id)
            row = connection.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        except sqlite3.IntegrityError as exc:
            raise DirectoryError(HTTPStatus.CONFLICT, "Email already belongs to another user.") from exc
    return public_user(row)


class Handler(BaseHTTPRequestHandler):
    server_version = "JorMallUserDirectory/1.0"

    def log_message(self, format_string: str, *args) -> None:
        print(f"{self.address_string()} - {format_string % args}", flush=True)

    def send_json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict[str, object]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise DirectoryError(HTTPStatus.BAD_REQUEST, "Invalid request length.") from exc
        if length <= 0 or length > MAX_BODY:
            raise DirectoryError(HTTPStatus.BAD_REQUEST, "Invalid request body.")
        try:
            payload = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DirectoryError(HTTPStatus.BAD_REQUEST, "Invalid JSON body.") from exc
        if not isinstance(payload, dict):
            raise DirectoryError(HTTPStatus.BAD_REQUEST, "JSON body must be an object.")
        return payload

    def route(self) -> tuple[int, dict[str, object]]:
        path = urlparse(self.path).path
        if path == "/health" and self.command == "GET":
            return HTTPStatus.OK, {"success": True}
        require_token(self.headers)
        if path == "/verify" and self.command == "POST":
            return HTTPStatus.OK, {"success": True, "user": verify_user(self.read_json())}
        if path == "/status" and self.command == "POST":
            return HTTPStatus.OK, {"success": True, "user": active_user(self.read_json())}
        if path == "/users" and self.command == "GET":
            return HTTPStatus.OK, {"success": True, "users": list_users()}
        if path == "/users" and self.command == "POST":
            return HTTPStatus.CREATED, {"success": True, "user": create_user(self.read_json())}
        match = re.fullmatch(r"/users/(\d+)", path)
        if match and self.command == "PATCH":
            return HTTPStatus.OK, {
                "success": True,
                "user": update_user(int(match.group(1)), self.read_json()),
            }
        raise DirectoryError(HTTPStatus.NOT_FOUND, "Not found.")

    def handle_request(self) -> None:
        try:
            status, payload = self.route()
        except DirectoryError as exc:
            status, payload = exc.status, {"success": False, "error": exc.message}
        except Exception as exc:
            print(f"Unhandled directory error: {type(exc).__name__}: {exc}", flush=True)
            status, payload = HTTPStatus.INTERNAL_SERVER_ERROR, {"success": False, "error": "Internal error."}
        self.send_json(int(status), payload)

    do_GET = handle_request
    do_POST = handle_request
    do_PATCH = handle_request


def main() -> None:
    if not DIRECTORY_TOKEN:
        raise SystemExit("DIRECTORY_TOKEN must be configured")
    initialize_database()
    imported = migrate_legacy_users()
    print(f"User directory ready; imported {imported} legacy users.", flush=True)
    server = ThreadingHTTPServer((BIND_HOST, BIND_PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
