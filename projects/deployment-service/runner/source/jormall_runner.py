#!/usr/bin/env python3
"""Small privileged deployment runner for the JorMall platform.

The runner accepts a fixed JSON protocol over a Unix socket. It never accepts
shell commands or uploaded Compose files. Docker and Nginx inputs are validated
and commands are invoked without a shell.
"""

from __future__ import annotations

import datetime as dt
import fcntl
import grp
import hashlib
import http.client
import json
import os
import re
import secrets
import shutil
import socket
import socketserver
import sqlite3
import stat
import string
import subprocess
import tempfile
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any


SOCKET_PATH = Path("/run/jormall-deployer/runner.sock")
STATE_DB = Path("/var/lib/jormall/deployer/state.db")
AUDIT_LOG = Path("/var/log/jormall/deployer/audit.jsonl")
GENERATED_NGINX = Path("/etc/nginx/jormall/generated")
SSO_BACKEND_CONF = Path("/etc/nginx/conf.d/jormall-sso-backend.conf")
SSO_DEDICATED_PORT = 18027
MAIN_SITE_BACKEND_CONF = Path("/etc/nginx/conf.d/jormall-main-site-backend.conf")
APPS_ROOT = Path("/opt/jormall/apps")
SECRETS_ROOT = Path("/etc/jormall/apps")
AUTH_ROOT = Path("/etc/jormall/nginx/auth")
UPLOAD_ROOT = Path("/var/lib/jormall/deployer/uploads")
PORT_MIN, PORT_MAX = 18000, 19999
MAX_REQUEST = 256 * 1024
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_EXTRACTED_BYTES = 250 * 1024 * 1024
MAX_ARCHIVE_FILES = 5000
APP_RE = re.compile(r"^[a-z][a-z0-9-]{0,39}$")
IMAGE_RE = re.compile(
    r"^(?:[a-zA-Z0-9.-]+(?::[0-9]+)?/)?"
    r"[a-z0-9]+(?:[._/-][a-z0-9]+)*(?::[A-Za-z0-9_.-]{1,128}|@sha256:[a-f0-9]{64})?$"
)
HEALTH_RE = re.compile(r"^/[A-Za-z0-9._~!$&'()*+,;=:@%/-]{0,255}$")
ENV_RE = re.compile(r"^[A-Z_][A-Z0-9_]{0,127}$")
DEPLOYMENT_RE = re.compile(r"^[a-f0-9]{32}$")
UPLOAD_RE = re.compile(r"^[a-f0-9]{32}$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
CONTAINER_RE = re.compile(r"^jormall-[a-z0-9-]+-(?:preview|staging|production)-[a-f0-9]{12}$")
ENVIRONMENTS = {"preview", "staging", "production"}
ALLOWED_OPS = {
    "ping", "list", "deploy", "restart", "stop", "logs", "rollback",
    "promote", "expire", "redeploy", "rotate_password", "delete",
    "catalog", "versions", "release", "rollback_app",
}

# The registry describes every application currently present on this server.
# Managed applications use the runner's blue/green Docker flow.  Compose
# applications keep their database service and persistent data in place while
# only the application image is versioned.  Nova uses a fixed standalone
# container because it predates the generic runner.
BUILTIN_APPLICATIONS: dict[str, dict[str, Any]] = {
    "main-site": {"display_name": "Main Site", "mode": "managed", "environment": "production", "domain": "jormallapp.com", "container_port": 8080, "health_path": "/", "password_protected": False},
    "assistant": {"display_name": "JorMall Assistant", "mode": "managed", "environment": "production", "domain": "assistant.jormallapp.com", "container_port": 2000, "health_path": "/", "password_protected": True},
    "platform-assistant": {"display_name": "Platform Assistant", "mode": "managed", "environment": "production", "domain": "platform-assistant.jormallapp.com", "container_port": 8002, "health_path": "/", "password_protected": True},
    "ai-dashboard": {"display_name": "AI Dashboard", "mode": "managed", "environment": "production", "domain": "ai-dashboard.jormallapp.com", "container_port": 8080, "health_path": "/", "password_protected": True},
    "api": {"display_name": "JorMall API", "mode": "managed", "environment": "staging", "domain": "api.staging.jormallapp.com", "container_port": 8000, "health_path": "/", "password_protected": True},
    "spin": {"display_name": "Spin", "mode": "managed", "environment": "production", "domain": "spin.jormallapp.com", "container_port": 8001, "health_path": "/", "password_protected": True},
    "sma-extension": {"display_name": "SMA Extension", "mode": "managed", "environment": "production", "domain": "sma-extension.jormallapp.com", "container_port": 5056, "health_path": "/", "password_protected": False},
    "sma-backend": {"display_name": "SMA Backend", "mode": "managed", "environment": "production", "domain": "sma-backend.jormallapp.com", "container_port": 5055, "health_path": "/health", "password_protected": False},
    "interactive-sms": {"display_name": "Interactive SMS", "mode": "compose", "environment": "production", "domain": "jormallapp.com/interactive-sms", "source_path": "/opt/jormall/apps/interactive-sms/production", "service_name": "chatbot", "project_name": "central-ecommerce-current", "container_name": "central-ecommerce-current-chatbot-1", "container_port": 8000, "host_port": 3000, "health_path": "/health", "password_protected": False},
    "corolla2026": {"display_name": "Corolla 2026", "mode": "compose", "environment": "production", "domain": "jormallapp.com", "source_path": "/opt/jormall/apps/corolla2026/production", "service_name": "chatbot", "project_name": "markazia-toyota-jordan-standalone", "container_name": "markazia-toyota-jordan-standalone-chatbot-1", "container_port": 8000, "host_port": 3001, "health_path": "/health", "password_protected": False},
    "sms-service-chatbot": {"display_name": "SMS Service Chatbot", "mode": "compose", "environment": "production", "domain": "jormallapp.com/sms-service-chatbot", "source_path": "/opt/jormall/apps/sms-service-chatbot/production", "service_name": "chatbot", "project_name": "sms-service-chatbot", "container_name": "sms-service-chatbot-chatbot-1", "container_port": 8000, "host_port": 3002, "health_path": "/health", "password_protected": False},
    "nova-crm": {"display_name": "Nova CRM", "mode": "standalone", "environment": "production", "domain": "nova.jormallapp.com", "source_path": "/opt/nova-crm", "service_name": "nova-crm", "container_name": "nova-crm", "dockerfile": "Dockerfile.lightsail", "container_port": 8080, "host_port": 18014, "health_path": "/", "password_protected": False},
    "upload-smoke": {"display_name": "ZIP Upload Test", "mode": "managed", "environment": "preview", "domain": "upload-smoke.preview.jormallapp.com", "container_port": 8080, "health_path": "/", "password_protected": False},
}

# The host has 2 GiB RAM and runs several production services.  Keep one
# deployment from consuming the whole machine and forcing every site into swap.
MANAGED_RESOURCE_LIMITS: dict[str, tuple[str, str, str, str]] = {
    "assistant": ("384m", "512m", "1.00", "128"),
    "platform-assistant": ("256m", "320m", "0.75", "128"),
    "main-site": ("128m", "160m", "0.40", "64"),
    "ai-dashboard": ("128m", "160m", "0.40", "64"),
    "spin": ("192m", "256m", "0.60", "96"),
    "api": ("192m", "256m", "0.50", "96"),
    "sma-extension": ("128m", "160m", "0.40", "64"),
    "sma-backend": ("192m", "256m", "0.60", "96"),
    "upload-smoke": ("128m", "160m", "0.30", "64"),
}
DEFAULT_RESOURCE_LIMITS = ("256m", "320m", "0.60", "96")


def managed_resource_limits(app: str, environment: str) -> tuple[str, str, str, str]:
    memory, memory_swap, cpus, pids = MANAGED_RESOURCE_LIMITS.get(
        app, DEFAULT_RESOURCE_LIMITS
    )
    if environment == "preview":
        return "192m", "256m", "0.40", "64"
    return memory, memory_swap, cpus, pids


class RunnerError(RuntimeError):
    pass


def run(args: list[str], *, timeout: int = 300, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)
    if check and result.returncode:
        detail = (result.stderr or result.stdout or f"exit {result.returncode}").strip()
        raise RunnerError(detail[-2000:])
    return result


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def validate_app(value: Any) -> str:
    value = str(value or "").strip().lower()
    if not APP_RE.fullmatch(value):
        raise RunnerError("application must be a lowercase DNS label")
    return value


def validate_environment(value: Any) -> str:
    value = str(value or "").strip().lower()
    if value not in ENVIRONMENTS:
        raise RunnerError("unsupported environment")
    return value


def validate_image(value: Any) -> str:
    value = str(value or "").strip()
    if len(value) > 255 or not IMAGE_RE.fullmatch(value):
        raise RunnerError("unsupported Docker image reference")
    return value


def validate_build_context(value: Any) -> Path | None:
    if value in (None, ""):
        return None
    raw = Path(str(value)).resolve()
    try:
        raw.relative_to(APPS_ROOT.resolve())
    except ValueError as exc:
        raise RunnerError("build context is outside the approved application root") from exc
    if not raw.is_dir() or not (raw / "Dockerfile").is_file() or not (raw / ".jormall-approved").is_file():
        raise RunnerError("build context is not administrator-approved")
    if raw.stat().st_uid != 0 or (raw / ".jormall-approved").stat().st_uid != 0:
        raise RunnerError("approved build context must be root-owned")
    return raw


def validate_upload_id(value: Any) -> str | None:
    if value in (None, ""):
        return None
    value = str(value).strip()
    if not UPLOAD_RE.fullmatch(value):
        raise RunnerError("invalid source upload identifier")
    return value


def validate_version(value: Any) -> str:
    value = str(value or "").strip()
    if not VERSION_RE.fullmatch(value):
        raise RunnerError("version must use 1-64 letters, numbers, dots, dashes, pluses, or underscores")
    return value


def _archive_path(parts: tuple[str, ...]) -> bool:
    lowered = tuple(part.lower() for part in parts)
    if any(part in {".git", "__pycache__", ".svn", ".hg"} for part in lowered):
        return False
    filename = lowered[-1] if lowered else ""
    if filename == ".env" or filename.startswith(".env."):
        return False
    if filename in {"id_rsa", "id_ed25519", "credentials.json"}:
        return False
    if filename.endswith((".pem", ".key", ".p12", ".pfx")):
        return False
    if filename in {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}:
        return False
    return True


def extract_uploaded_context(
    upload_id: str, app: str, deployment_id: str, dockerfile_name: str = "Dockerfile"
) -> Path:
    archive = UPLOAD_ROOT / f"{upload_id}.zip"
    if not archive.is_file() or archive.is_symlink():
        raise RunnerError("source upload was not found")
    info = archive.stat()
    if info.st_uid != 10001 or info.st_size <= 0 or info.st_size > MAX_UPLOAD_BYTES:
        archive.unlink(missing_ok=True)
        raise RunnerError("source upload failed ownership or size validation")

    parent = APPS_ROOT / app / "uploads"
    parent.mkdir(parents=True, exist_ok=True)
    os.chown(parent, 0, 0)
    os.chmod(parent, 0o750)
    target = parent / deployment_id
    staging = parent / f".{deployment_id}.extracting"
    if target.exists() or staging.exists():
        archive.unlink(missing_ok=True)
        raise RunnerError("source deployment context already exists")
    staging.mkdir(mode=0o750)
    try:
        with zipfile.ZipFile(archive) as bundle:
            members = bundle.infolist()
            if not members or len(members) > MAX_ARCHIVE_FILES:
                raise RunnerError("source archive has an invalid file count")
            expanded = 0
            for member in members:
                if member.flag_bits & 0x1:
                    raise RunnerError("encrypted ZIP entries are not supported")
                if "\\" in member.filename:
                    raise RunnerError("source archive contains an invalid path")
                path = PurePosixPath(member.filename)
                parts = tuple(part for part in path.parts if part not in ("", "."))
                if path.is_absolute() or not parts or ".." in parts:
                    raise RunnerError("source archive contains path traversal")
                mode = member.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise RunnerError("source archive cannot contain symbolic links")
                if not _archive_path(parts):
                    raise RunnerError("source archive contains prohibited secrets, metadata, or Compose files")
                expanded += member.file_size
                if expanded > MAX_EXTRACTED_BYTES:
                    raise RunnerError("expanded source exceeds the 250 MiB limit")
                destination = staging.joinpath(*parts)
                destination.resolve().relative_to(staging.resolve())
                if member.is_dir():
                    destination.mkdir(parents=True, exist_ok=True, mode=0o750)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
                with bundle.open(member) as source, destination.open("xb") as output:
                    while chunk := source.read(1024 * 1024):
                        output.write(chunk)
                # Source files copied into an image must remain readable by the
                # image's non-root runtime user. Secrets are rejected earlier.
                os.chmod(destination, 0o644)

        if dockerfile_name not in {"Dockerfile", "Dockerfile.lightsail"}:
            raise RunnerError("unsupported Dockerfile profile")
        dockerfile = staging / dockerfile_name
        if not dockerfile.is_file() or dockerfile.stat().st_size > 1024 * 1024:
            raise RunnerError(f"uploaded source must contain a root-level {dockerfile_name} under 1 MiB")
        try:
            docker_text = dockerfile.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise RunnerError("Dockerfile must be valid UTF-8 text") from exc
        if "\x00" in docker_text or not re.search(r"(?im)^\s*FROM\s+\S+", docker_text):
            raise RunnerError("Dockerfile is invalid or has no FROM instruction")
        if re.search(r"(?im)^\s*ADD\s+(?:--\S+\s+)*(?:https?|git)://", docker_text):
            raise RunnerError("remote URL ADD instructions are not allowed")
        os.chmod(dockerfile, 0o644)
        marker = staging / ".jormall-approved"
        marker.write_text(f"validated-upload={deployment_id}\n", encoding="utf-8")
        os.chmod(marker, 0o640)
        for root, directories, files in os.walk(staging):
            os.chown(root, 0, 0)
            for name in directories:
                os.chown(Path(root) / name, 0, 0)
            for name in files:
                os.chown(Path(root) / name, 0, 0)
        staging.replace(target)
        return target
    except (zipfile.BadZipFile, OSError) as exc:
        raise RunnerError("source upload is not a valid safe ZIP archive") from exc
    finally:
        archive.unlink(missing_ok=True)
        if staging.exists():
            shutil.rmtree(staging)


def validate_port(value: Any) -> int:
    if isinstance(value, bool):
        raise RunnerError("invalid container port")
    try:
        value = int(value)
    except (TypeError, ValueError) as exc:
        raise RunnerError("invalid container port") from exc
    if not 1 <= value <= 65535:
        raise RunnerError("invalid container port")
    return value


def validate_health(value: Any) -> str:
    value = str(value or "/").strip()
    if not HEALTH_RE.fullmatch(value) or ".." in value:
        raise RunnerError("invalid health path")
    return value


def domain_for(app: str, environment: str) -> str:
    if environment == "production":
        return f"{app}.jormallapp.com"
    return f"{app}.{environment}.jormallapp.com"


def password_hash(password: str) -> str:
    result = subprocess.run(
        ["/usr/bin/openssl", "passwd", "-6", "-stdin"],
        input=password,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    if result.returncode or not result.stdout.strip().startswith("$6$"):
        raise RunnerError("could not generate password hash")
    return result.stdout.strip()


def generate_password() -> str:
    alphabet = string.ascii_letters + string.digits + "-_!@"
    return "".join(secrets.choice(alphabet) for _ in range(24))


def db() -> sqlite3.Connection:
    STATE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(STATE_DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS deployments (
          deployment_id TEXT PRIMARY KEY,
          application TEXT NOT NULL,
          environment TEXT NOT NULL,
          image TEXT NOT NULL,
          image_digest TEXT,
          container_name TEXT NOT NULL UNIQUE,
          container_port INTEGER NOT NULL,
          host_port INTEGER NOT NULL,
          domain TEXT NOT NULL,
          health_path TEXT NOT NULL,
          status TEXT NOT NULL,
          health_status TEXT NOT NULL,
          password_protected INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL,
          expires_at TEXT,
          previous_deployment_id TEXT,
          active INTEGER NOT NULL DEFAULT 0,
          persistent_mounts TEXT NOT NULL DEFAULT '[]'
        );
        """
    )
    schema = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='deployments'"
    ).fetchone()[0]
    if "host_port INTEGER NOT NULL UNIQUE" in schema:
        conn.executescript(
            """
            ALTER TABLE deployments RENAME TO deployments_legacy;
            CREATE TABLE deployments (
              deployment_id TEXT PRIMARY KEY,
              application TEXT NOT NULL,
              environment TEXT NOT NULL,
              image TEXT NOT NULL,
              image_digest TEXT,
              container_name TEXT NOT NULL UNIQUE,
              container_port INTEGER NOT NULL,
              host_port INTEGER NOT NULL,
              domain TEXT NOT NULL,
              health_path TEXT NOT NULL,
              status TEXT NOT NULL,
              health_status TEXT NOT NULL,
              password_protected INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              expires_at TEXT,
              previous_deployment_id TEXT,
              active INTEGER NOT NULL DEFAULT 0,
              persistent_mounts TEXT NOT NULL DEFAULT '[]'
            );
            INSERT INTO deployments
              (deployment_id,application,environment,image,image_digest,container_name,container_port,host_port,
               domain,health_path,status,health_status,password_protected,created_at,expires_at,previous_deployment_id,active)
              SELECT deployment_id,application,environment,image,image_digest,container_name,container_port,host_port,
               domain,health_path,status,health_status,password_protected,created_at,expires_at,previous_deployment_id,active
              FROM deployments_legacy;
            DROP TABLE deployments_legacy;
            """
        )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(deployments)")}
    if "persistent_mounts" not in columns:
        conn.execute("ALTER TABLE deployments ADD COLUMN persistent_mounts TEXT NOT NULL DEFAULT '[]'")
    if "release_version" not in columns:
        conn.execute("ALTER TABLE deployments ADD COLUMN release_version TEXT")
    if "release_notes" not in columns:
        conn.execute("ALTER TABLE deployments ADD COLUMN release_notes TEXT NOT NULL DEFAULT ''")
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS deployment_slot
          ON deployments(application, environment, active);
        CREATE UNIQUE INDEX IF NOT EXISTS reserved_host_port
          ON deployments(host_port) WHERE active=1 OR status='STARTING';
        CREATE TABLE IF NOT EXISTS applications (
          application TEXT PRIMARY KEY,
          display_name TEXT NOT NULL,
          mode TEXT NOT NULL,
          environment TEXT NOT NULL,
          domain TEXT NOT NULL,
          source_path TEXT,
          service_name TEXT,
          project_name TEXT,
          container_name TEXT,
          dockerfile TEXT NOT NULL DEFAULT 'Dockerfile',
          container_port INTEGER NOT NULL,
          host_port INTEGER,
          health_path TEXT NOT NULL,
          password_protected INTEGER NOT NULL DEFAULT 0,
          persistent_mounts TEXT NOT NULL DEFAULT '[]',
          enabled INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS app_versions (
          version_id TEXT PRIMARY KEY,
          application TEXT NOT NULL,
          environment TEXT NOT NULL,
          version_label TEXT NOT NULL,
          release_notes TEXT NOT NULL DEFAULT '',
          mode TEXT NOT NULL,
          image TEXT,
          status TEXT NOT NULL,
          active INTEGER NOT NULL DEFAULT 0,
          deployment_id TEXT,
          previous_version_id TEXT,
          created_at TEXT NOT NULL,
          FOREIGN KEY(application) REFERENCES applications(application)
        );
        CREATE INDEX IF NOT EXISTS app_version_history
          ON app_versions(application, created_at DESC);
        CREATE UNIQUE INDEX IF NOT EXISTS active_app_version
          ON app_versions(application, environment) WHERE active=1;
        """
    )
    seed_registry(conn)
    conn.commit()
    return conn


def seed_registry(conn: sqlite3.Connection) -> None:
    """Idempotently register server applications and historic managed releases."""
    now = utc_now()
    for app, profile in BUILTIN_APPLICATIONS.items():
        conn.execute(
            """INSERT INTO applications
               (application,display_name,mode,environment,domain,source_path,service_name,project_name,
                container_name,dockerfile,container_port,host_port,health_path,password_protected,
                persistent_mounts,enabled,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)
               ON CONFLICT(application) DO UPDATE SET
                 display_name=excluded.display_name, mode=excluded.mode,
                 domain=excluded.domain, source_path=excluded.source_path,
                 service_name=excluded.service_name, project_name=excluded.project_name,
                 container_name=excluded.container_name, dockerfile=excluded.dockerfile,
                 environment=excluded.environment, container_port=excluded.container_port,
                 host_port=excluded.host_port, health_path=excluded.health_path,
                 password_protected=excluded.password_protected,
                 updated_at=excluded.updated_at""",
            (
                app, profile["display_name"], profile["mode"], profile["environment"],
                profile["domain"], profile.get("source_path"), profile.get("service_name"),
                profile.get("project_name"), profile.get("container_name"),
                profile.get("dockerfile", "Dockerfile"), profile["container_port"],
                profile.get("host_port"), profile["health_path"],
                int(profile.get("password_protected", False)),
                json.dumps(profile.get("persistent_mounts", []), separators=(",", ":")), now, now,
            ),
        )

    active_rows = conn.execute(
        """SELECT * FROM deployments
           WHERE active=1 AND status NOT IN ('DELETED','EXPIRED')
           ORDER BY created_at DESC"""
    ).fetchall()
    for row in active_rows:
        if row["application"] not in BUILTIN_APPLICATIONS:
            continue
        conn.execute(
            """UPDATE applications SET environment=?,container_port=?,host_port=?,health_path=?,
               password_protected=?,persistent_mounts=?,updated_at=? WHERE application=?""",
            (
                row["environment"], row["container_port"], row["host_port"], row["health_path"],
                row["password_protected"], row["persistent_mounts"], now, row["application"],
            ),
        )

    managed_rows = conn.execute(
        """SELECT d.* FROM deployments d
           JOIN applications a ON a.application=d.application
           WHERE a.mode='managed'"""
    ).fetchall()
    for row in managed_rows:
        label = row["release_version"] or f"legacy-{row['created_at'][:10]}-{row['deployment_id'][:7]}"
        conn.execute(
            """INSERT OR IGNORE INTO app_versions
               (version_id,application,environment,version_label,release_notes,mode,image,status,active,
                deployment_id,previous_version_id,created_at)
               VALUES (?,?,?,?,?,'managed',?,?,?,?,?,?)""",
            (
                row["deployment_id"], row["application"], row["environment"], label,
                row["release_notes"] or "Imported existing deployment", row["image"], row["status"],
                int(row["active"] and row["status"] not in {"DELETED", "EXPIRED"}),
                row["deployment_id"], row["previous_deployment_id"], row["created_at"],
            ),
        )


def audit(actor: str, operation: str, result: str, **fields: Any) -> None:
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    record = {"time": utc_now(), "actor": actor[:128], "operation": operation, "result": result}
    record.update({k: v for k, v in fields.items() if k not in {"environment_variables", "password"}})
    with AUDIT_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    os.chmod(AUDIT_LOG, 0o640)


def preserve_failure_logs(container: str, deployment_id: str) -> None:
    result = run(["/usr/bin/docker", "logs", "--tail", "250", container], check=False)
    content = (result.stdout + result.stderr)[-100000:]
    content = re.sub(
        r"(?i)(authorization|password|passwd|secret|api[_-]?key|token)(\s*[=:]\s*)\S+",
        r"\1\2[REDACTED]",
        content,
    )
    if content.strip():
        target = AUDIT_LOG.parent / f"{deployment_id}.failure.log"
        atomic_write(target, content, 0o640)


def port_available(port: int) -> bool:
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def allocate_port(conn: sqlite3.Connection) -> int:
    used = {int(row[0]) for row in conn.execute(
        "SELECT host_port FROM deployments WHERE active=1 OR status='STARTING'"
    )}
    for port in range(PORT_MIN, PORT_MAX + 1):
        if port not in used and port_available(port):
            return port
    raise RunnerError("managed port range is exhausted")


def write_env(app: str, environment: str, values: Any) -> Path | None:
    if values in (None, {}):
        existing = SECRETS_ROOT / app / environment / "app.env"
        return existing if existing.is_file() else None
    if not isinstance(values, dict) or len(values) > 100:
        raise RunnerError("environment_variables must be an object with at most 100 keys")
    lines: list[str] = []
    for key, value in sorted(values.items()):
        if not isinstance(key, str) or not ENV_RE.fullmatch(key):
            raise RunnerError("invalid environment variable name")
        if not isinstance(value, str) or len(value) > 16384 or any(c in value for c in "\x00\r\n"):
            raise RunnerError(f"invalid value for {key}")
        encoded = value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")
        lines.append(f'{key}="{encoded}"')
    target = SECRETS_ROOT / app / environment / "app.env"
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=target.parent, prefix=".app.env.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target


def validate_persistent_mounts(app: str, environment: str, value: Any) -> list[dict[str, str]]:
    if value in (None, []):
        return []
    if not isinstance(value, list) or len(value) > 10:
        raise RunnerError("persistent_mounts must be a list with at most 10 entries")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            raise RunnerError("invalid persistent mount")
        name = str(item.get("name") or "").strip().lower()
        destination = str(item.get("container_path") or "").strip()
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", name) or name in seen:
            raise RunnerError("invalid or duplicate persistent mount name")
        if not re.fullmatch(r"/app/[A-Za-z0-9._/-]+", destination) or ".." in Path(destination).parts:
            raise RunnerError("persistent mounts must be below /app")
        seen.add(name)
        host = Path("/var/lib/jormall/apps") / app / environment / name
        host.mkdir(parents=True, exist_ok=True)
        os.chown(host, 10001, 10001)
        os.chmod(host, 0o750)
        result.append({"name": name, "host_path": str(host), "container_path": destination})
    return result


def check_health(port: int, path: str, attempts: int = 30) -> None:
    import time
    url = f"http://127.0.0.1:{port}{path}"
    last = "no response"
    for _ in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "jormall-runner/1"})
            with urllib.request.urlopen(request, timeout=3) as response:
                if 200 <= response.status < 400:
                    return
                last = f"HTTP {response.status}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = type(exc).__name__
        time.sleep(2)
    raise RunnerError(f"health check failed: {last}")


def check_edge(domain: str, path: str, password: str | None, attempts: int = 15) -> None:
    import time
    headers = {"Host": domain, "User-Agent": "jormall-runner/1"}
    if password:
        import base64
        token = base64.b64encode(("jormall:" + password).encode()).decode()
        headers["Authorization"] = "Basic " + token
    last = "no response"
    for _ in range(attempts):
        connection = http.client.HTTPConnection("127.0.0.1", 80, timeout=3)
        try:
            connection.request("GET", path, headers=headers)
            response = connection.getresponse()
            response.read(4096)
            if 200 <= response.status < 400:
                return
            last = f"HTTP {response.status}"
        except OSError as exc:
            last = type(exc).__name__
        finally:
            connection.close()
        time.sleep(1)
    raise RunnerError(f"edge route check failed: {last}")


def nginx_text(*, app: str, environment: str, domain: str, port: int, protected: bool) -> str:
    auth = ""
    if protected:
        auth_file = AUTH_ROOT / f"{app}-{environment}.htpasswd"
        auth = f'    auth_basic "JorMall {environment}";\n    auth_basic_user_file {auth_file};\n'
    cert = Path(f"/etc/letsencrypt/live/{domain}/fullchain.pem")
    if cert.exists():
        listen = "    listen 443 ssl http2;\n    listen [::]:443 ssl http2;"
        tls = (
            f"    ssl_certificate /etc/letsencrypt/live/{domain}/fullchain.pem;\n"
            f"    ssl_certificate_key /etc/letsencrypt/live/{domain}/privkey.pem;\n"
        )
        redirect = (
            "server {\n    listen 80;\n    listen [::]:80;\n"
            f"    server_name {domain};\n    return 301 https://$host$request_uri;\n}}\n\n"
        )
    else:
        listen = "    listen 80;\n    listen [::]:80;"
        tls = ""
        redirect = ""
    sso_locations = ""
    sso_auth = ""
    sso_user_header = ""
    portal_auth_locations = ""
    offline_behavior = ""
    if environment == "production" and app in {"assistant", "platform-assistant"}:
        sso_locations = """    location = /_sso_verify {
        internal;
        # Pass 401 back to auth_request. Do not let the Assistant maintenance
        # error handler turn it into a 302 inside this subrequest.
        proxy_intercept_errors off;
        proxy_pass http://127.0.0.1:18100/sso/verify;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
        proxy_set_header Cookie $http_cookie;
        proxy_set_header X-Original-URI $request_uri;
    }
    error_page 401 = @sso_login;
    location @sso_login {
        return 302 https://jormallapp.com/?login=1&next=https://$host$request_uri;
    }
"""
        sso_auth = "        auth_request /_sso_verify;\n        auth_request_set $sso_user $upstream_http_x_sso_user;\n"
        sso_user_header = "        proxy_set_header X-Authenticated-User $sso_user;\n"
    if environment == "production" and app == "main-site":
        portal_auth_locations = """    # Same-origin SSO endpoints for the main-site subdomain.
    location = /auth/login {
        proxy_pass http://127.0.0.1:18100/login;
        proxy_set_header Host assistant.jormallapp.com;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        add_header Cache-Control "no-store" always;
    }
    location = /auth/status {
        proxy_pass http://127.0.0.1:18100/sso/verify;
        proxy_set_header Host assistant.jormallapp.com;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        add_header Cache-Control "no-store" always;
    }
    location = /auth/logout {
        proxy_pass http://127.0.0.1:18100/logout;
        proxy_set_header Host assistant.jormallapp.com;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        add_header Cache-Control "no-store" always;
    }
"""
    if environment == "production" and app == "assistant":
        offline_behavior = """    # Keep authentication available independently, while presenting a clear
    # maintenance page whenever the Assistant UI container is stopped.
    proxy_intercept_errors on;
    error_page 502 503 504 =503 /assistant-offline.html;
    location = /assistant-offline.html {
        internal;
        root /var/www/jormall-offline;
        add_header Cache-Control "no-store" always;
    }
"""
    legacy_prefix = ""
    legacy_prefix_name = {
        "assistant": "jormall-assistant",
        "platform-assistant": "platform-assistant",
    }.get(app)
    if legacy_prefix_name:
        legacy_prefix = f"""    # This UI is also served below a legacy prefix on the main site.
    # Keep its absolute URLs working when the same build is opened on this subdomain.
    location = /{legacy_prefix_name} {{
        return 301 /{legacy_prefix_name}/;
    }}
    location ^~ /{legacy_prefix_name}/ {{
{sso_auth}        rewrite ^/{legacy_prefix_name}/?(.*)$ /$1 break;
        proxy_pass http://127.0.0.1:{port};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Prefix /{legacy_prefix_name};
{sso_user_header}        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_read_timeout 300s;
    }}
"""
    return f"""# Generated by jormall-runner. Do not edit.
{redirect}server {{
{listen}
    server_name {domain};
{tls}{auth}    location ~ /\\.(?:env|git) {{ deny all; }}
{sso_locations}{portal_auth_locations}{offline_behavior}{legacy_prefix}    location / {{
{sso_auth}        proxy_pass http://127.0.0.1:{port};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
{sso_user_header}        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_read_timeout 300s;
    }}
}}
"""


def atomic_write(path: Path, content: str, mode: int = 0o640) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def sso_backend_text(port: int) -> str:
    return f"""# Generated by jormall-runner. Do not edit.
server {{
    listen 127.0.0.1:18100;
    server_name _;
    access_log off;
    location / {{
        proxy_pass http://127.0.0.1:{port};
        proxy_http_version 1.1;
        proxy_set_header Host assistant.jormallapp.com;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host assistant.jormallapp.com;
        proxy_read_timeout 30s;
    }}
}}
"""


def activate_sso_backend(port: int) -> None:
    previous = SSO_BACKEND_CONF.read_text(encoding="utf-8") if SSO_BACKEND_CONF.exists() else None
    # Authentication must remain online when the Assistant UI is stopped from
    # Deployer. It therefore has a dedicated local container/port.
    atomic_write(SSO_BACKEND_CONF, sso_backend_text(SSO_DEDICATED_PORT))
    result = run(["/usr/sbin/nginx", "-t"], check=False)
    if result.returncode:
        if previous is None:
            SSO_BACKEND_CONF.unlink(missing_ok=True)
        else:
            atomic_write(SSO_BACKEND_CONF, previous)
        raise RunnerError("SSO backend Nginx validation failed: " + (result.stderr or result.stdout)[-1000:])
    run(["/bin/systemctl", "reload", "nginx"])


def main_site_backend_text(port: int) -> str:
    return f"""# Generated by jormall-runner. Do not edit.
server {{
    listen 127.0.0.1:18102;
    server_name _;
    access_log off;
    location / {{
        proxy_pass http://127.0.0.1:{port};
        proxy_http_version 1.1;
        proxy_set_header Host jormallapp.com;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host jormallapp.com;
        proxy_read_timeout 300s;
    }}
}}
"""


def activate_main_site_backend(port: int) -> None:
    previous = MAIN_SITE_BACKEND_CONF.read_text(encoding="utf-8") if MAIN_SITE_BACKEND_CONF.exists() else None
    atomic_write(MAIN_SITE_BACKEND_CONF, main_site_backend_text(port))
    result = run(["/usr/sbin/nginx", "-t"], check=False)
    if result.returncode:
        if previous is None:
            MAIN_SITE_BACKEND_CONF.unlink(missing_ok=True)
        else:
            atomic_write(MAIN_SITE_BACKEND_CONF, previous)
        raise RunnerError("Main-site backend Nginx validation failed: " + (result.stderr or result.stdout)[-1000:])
    run(["/bin/systemctl", "reload", "nginx"])


def activate_nginx(app: str, environment: str, content: str) -> None:
    target = GENERATED_NGINX / f"{app}-{environment}.conf"
    previous = target.read_text(encoding="utf-8") if target.exists() else None
    atomic_write(target, content)
    result = run(["/usr/sbin/nginx", "-t"], check=False)
    if result.returncode:
        if previous is None:
            target.unlink(missing_ok=True)
        else:
            atomic_write(target, previous)
        raise RunnerError("Nginx validation failed: " + (result.stderr or result.stdout)[-1000:])
    run(["/bin/systemctl", "reload", "nginx"])


def image_digest(image: str) -> str | None:
    result = run(["/usr/bin/docker", "image", "inspect", image, "--format", "{{index .RepoDigests 0}}"], check=False)
    value = result.stdout.strip()
    return value or None


def list_deployments() -> list[dict[str, Any]]:
    with db() as conn:
        rows = [dict(row) for row in conn.execute("SELECT * FROM deployments ORDER BY created_at DESC")]
    running = {line for line in run(["/usr/bin/docker", "ps", "--format", "{{.Names}}"], check=False).stdout.splitlines()}
    for row in rows:
        row["container_state"] = "running" if row["container_name"] in running else "stopped"
        row["password_protected"] = bool(row["password_protected"])
        row["active"] = bool(row["active"])
        row["persistent_mounts"] = json.loads(row.get("persistent_mounts") or "[]")
    return rows


def application_row(application: Any) -> dict[str, Any]:
    app = validate_app(application)
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM applications WHERE application=? AND enabled=1", (app,)
        ).fetchone()
    if not row:
        raise RunnerError("application is not registered")
    result = dict(row)
    result["password_protected"] = bool(result["password_protected"])
    result["persistent_mounts"] = json.loads(result.get("persistent_mounts") or "[]")
    return result


def sync_external_baselines() -> None:
    """Capture pre-deployer Compose/Nova containers as their first version."""
    with db() as conn:
        rows = [dict(row) for row in conn.execute(
            "SELECT * FROM applications WHERE enabled=1 AND mode IN ('compose','standalone')"
        )]
        for profile in rows:
            existing = conn.execute(
                "SELECT 1 FROM app_versions WHERE application=? AND active=1",
                (profile["application"],),
            ).fetchone()
            if existing:
                continue
            inspected = run(
                ["/usr/bin/docker", "inspect", profile["container_name"], "--format", "{{.Config.Image}}"],
                check=False,
            )
            if inspected.returncode:
                continue
            image = inspected.stdout.strip()
            suffix = image.rsplit(":", 1)[-1] if ":" in image else "existing"
            label = suffix if VERSION_RE.fullmatch(suffix) else f"baseline-{utc_now()[:10]}"
            version_id = hashlib.sha256(
                f"baseline:{profile['application']}:{image}".encode()
            ).hexdigest()[:32]
            conn.execute(
                """INSERT OR IGNORE INTO app_versions
                   (version_id,application,environment,version_label,release_notes,mode,image,status,active,
                    deployment_id,previous_version_id,created_at)
                   VALUES (?,?,?,?,?,?,?,'READY',1,NULL,NULL,?)""",
                (
                    version_id, profile["application"], profile["environment"], label,
                    "Imported running server version", profile["mode"], image, utc_now(),
                ),
            )
        conn.commit()


def catalog() -> list[dict[str, Any]]:
    sync_external_baselines()
    running = set(run(["/usr/bin/docker", "ps", "--format", "{{.Names}}"], check=False).stdout.splitlines())
    with db() as conn:
        rows = [dict(row) for row in conn.execute(
            "SELECT * FROM applications WHERE enabled=1 ORDER BY display_name"
        )]
        for row in rows:
            current = conn.execute(
                """SELECT * FROM app_versions WHERE application=? AND environment=? AND active=1
                   ORDER BY created_at DESC LIMIT 1""",
                (row["application"], row["environment"]),
            ).fetchone()
            row["current_version"] = current["version_label"] if current else None
            row["current_version_id"] = current["version_id"] if current else None
            row["version_count"] = conn.execute(
                "SELECT COUNT(*) FROM app_versions WHERE application=?", (row["application"],)
            ).fetchone()[0]
            if row["mode"] == "managed":
                active = conn.execute(
                    """SELECT container_name,status,health_status,host_port FROM deployments
                       WHERE application=? AND environment=? AND active=1
                       ORDER BY created_at DESC LIMIT 1""",
                    (row["application"], row["environment"]),
                ).fetchone()
                row["container_name"] = active["container_name"] if active else None
                row["status"] = active["status"] if active and active["container_name"] in running else "OFFLINE"
                row["health_status"] = active["health_status"] if active else "unknown"
                if active:
                    row["host_port"] = active["host_port"]
            else:
                row["status"] = "READY" if row.get("container_name") in running else "OFFLINE"
                row["health_status"] = "healthy" if row["status"] == "READY" else "unknown"
            row["password_protected"] = bool(row["password_protected"])
            row["enabled"] = bool(row["enabled"])
    return rows


def versions_for(application: Any) -> dict[str, Any]:
    profile = application_row(application)
    sync_external_baselines()
    with db() as conn:
        versions = [dict(row) for row in conn.execute(
            "SELECT * FROM app_versions WHERE application=? ORDER BY created_at DESC",
            (profile["application"],),
        )]
    for version in versions:
        version["active"] = bool(version["active"])
    return {"application": profile, "versions": versions}


def ensure_new_version(conn: sqlite3.Connection, app: str, label: str) -> None:
    if conn.execute(
        "SELECT 1 FROM app_versions WHERE application=? AND version_label=? AND status!='FAILED'",
        (app, label),
    ).fetchone():
        raise RunnerError("this version label already exists for the application")


def compose_override(profile: dict[str, Any], image: str) -> Path:
    image = validate_image(image)
    root = STATE_DB.parent / "compose-overrides"
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{profile['application']}.yml"
    service = validate_app(profile["service_name"])
    atomic_write(target, f"services:\n  {service}:\n    image: {image}\n", 0o640)
    return target


def compose_up(profile: dict[str, Any], image: str) -> None:
    source = Path(profile["source_path"])
    compose_file = source / "docker-compose.yml"
    if not compose_file.is_file() or source.resolve().parent.parent != APPS_ROOT.resolve():
        raise RunnerError("registered Compose project path is unavailable")
    override = compose_override(profile, image)
    run([
        "/usr/bin/docker", "compose", "--project-name", profile["project_name"],
        "--project-directory", str(source), "-f", str(compose_file), "-f", str(override),
        "up", "-d", "--no-build", "--no-deps", profile["service_name"],
    ], timeout=900)


def compose_release(
    profile: dict[str, Any], upload_id: str, version_label: str, notes: str, actor: str
) -> dict[str, Any]:
    version_id = uuid.uuid4().hex
    context = extract_uploaded_context(upload_id, profile["application"], version_id)
    image = f"jormall-local/{profile['application']}:{version_id}"
    with db() as conn:
        ensure_new_version(conn, profile["application"], version_label)
        previous = conn.execute(
            "SELECT * FROM app_versions WHERE application=? AND environment=? AND active=1",
            (profile["application"], profile["environment"]),
        ).fetchone()
        conn.execute(
            """INSERT INTO app_versions
               (version_id,application,environment,version_label,release_notes,mode,image,status,active,
                deployment_id,previous_version_id,created_at)
               VALUES (?,?,?,?,?,'compose',?,'STARTING',0,NULL,?,?)""",
            (
                version_id, profile["application"], profile["environment"], version_label, notes,
                image, previous["version_id"] if previous else None, utc_now(),
            ),
        )
        conn.commit()
    try:
        run(["/usr/bin/docker", "build", "--pull", "--tag", image, str(context)], timeout=1800)
        compose_up(profile, image)
        check_health(int(profile["host_port"]), profile["health_path"], attempts=30)
        with db() as conn:
            conn.execute(
                "UPDATE app_versions SET active=0 WHERE application=? AND environment=?",
                (profile["application"], profile["environment"]),
            )
            conn.execute("UPDATE app_versions SET active=1,status='READY' WHERE version_id=?", (version_id,))
            conn.commit()
        audit(actor, "release", "success", application=profile["application"], version=version_label, version_id=version_id)
        return {"application": profile["application"], "version": version_label, "version_id": version_id, "status": "READY", "domain": profile["domain"]}
    except Exception as exc:
        with db() as conn:
            conn.execute("UPDATE app_versions SET status='FAILED' WHERE version_id=?", (version_id,))
            conn.commit()
        if previous and previous["image"]:
            try:
                compose_up(profile, previous["image"])
            except Exception:
                pass
        audit(actor, "release", "failed", application=profile["application"], version=version_label, error=type(exc).__name__)
        raise


def standalone_release(
    profile: dict[str, Any], upload_id: str, version_label: str, notes: str, actor: str
) -> dict[str, Any]:
    version_id = uuid.uuid4().hex
    context = extract_uploaded_context(
        upload_id, profile["application"], version_id, profile["dockerfile"]
    )
    image = f"jormall-local/{profile['application']}:{version_id}"
    with db() as conn:
        ensure_new_version(conn, profile["application"], version_label)
        previous = conn.execute(
            "SELECT * FROM app_versions WHERE application=? AND environment=? AND active=1",
            (profile["application"], profile["environment"]),
        ).fetchone()
        conn.execute(
            """INSERT INTO app_versions
               (version_id,application,environment,version_label,release_notes,mode,image,status,active,
                deployment_id,previous_version_id,created_at)
               VALUES (?,?,?,?,?,'standalone',?,'STARTING',0,NULL,?,?)""",
            (
                version_id, profile["application"], profile["environment"], version_label, notes,
                image, previous["version_id"] if previous else None, utc_now(),
            ),
        )
        conn.commit()
    fixed_name = profile["container_name"]
    backup_name = f"{fixed_name}-version-{previous['version_id'][:12]}" if previous else None
    try:
        run([
            "/usr/bin/docker", "build", "--pull", "--file", str(context / profile["dockerfile"]),
            "--tag", image, str(context),
        ], timeout=1800)
        if previous:
            if run(["/usr/bin/docker", "inspect", backup_name], check=False).returncode == 0:
                run(["/usr/bin/docker", "rm", "-f", backup_name])
            run(["/usr/bin/docker", "stop", fixed_name])
            run(["/usr/bin/docker", "rename", fixed_name, backup_name])
        args = [
            "/usr/bin/docker", "run", "-d", "--name", fixed_name, "--restart", "unless-stopped",
            "--security-opt", "no-new-privileges:true", "--pids-limit", "128",
            "--memory", "320m", "--memory-swap", "384m", "--cpus", "0.80",
            "--env-file", "/opt/nova-crm/runtime.env", "--mount", "type=bind,src=/opt/nova-crm/data,dst=/data",
            "--publish", f"127.0.0.1:{profile['host_port']}:{profile['container_port']}", image,
        ]
        run(args)
        check_health(int(profile["host_port"]), profile["health_path"], attempts=40)
        with db() as conn:
            conn.execute(
                "UPDATE app_versions SET active=0 WHERE application=? AND environment=?",
                (profile["application"], profile["environment"]),
            )
            conn.execute("UPDATE app_versions SET active=1,status='READY' WHERE version_id=?", (version_id,))
            conn.commit()
        audit(actor, "release", "success", application=profile["application"], version=version_label, version_id=version_id)
        return {"application": profile["application"], "version": version_label, "version_id": version_id, "status": "READY", "domain": profile["domain"]}
    except Exception as exc:
        run(["/usr/bin/docker", "rm", "-f", fixed_name], check=False)
        if previous and backup_name:
            run(["/usr/bin/docker", "rename", backup_name, fixed_name], check=False)
            run(["/usr/bin/docker", "start", fixed_name], check=False)
        with db() as conn:
            conn.execute("UPDATE app_versions SET status='FAILED' WHERE version_id=?", (version_id,))
            conn.commit()
        audit(actor, "release", "failed", application=profile["application"], version=version_label, error=type(exc).__name__)
        raise


def release_application(payload: dict[str, Any], actor: str) -> dict[str, Any]:
    profile = application_row(payload.get("application"))
    upload_id = validate_upload_id(payload.get("upload_id"))
    if not upload_id:
        raise RunnerError("a ZIP source upload is required")
    version_label = validate_version(payload.get("version"))
    notes = str(payload.get("release_notes") or "").strip()[:2000]
    if profile["mode"] == "managed":
        with db() as conn:
            ensure_new_version(conn, profile["application"], version_label)
        return deploy({
            "application": profile["application"], "environment": profile["environment"],
            "upload_id": upload_id, "container_port": profile["container_port"],
            "health_path": profile["health_path"],
            "password_protected": profile["password_protected"],
            "persistent_mounts": profile["persistent_mounts"],
            "release_version": version_label, "release_notes": notes,
        }, actor)
    if profile["mode"] == "compose":
        return compose_release(profile, upload_id, version_label, notes, actor)
    if profile["mode"] == "standalone":
        return standalone_release(profile, upload_id, version_label, notes, actor)
    raise RunnerError("application release mode is unsupported")


def rollback_application(payload: dict[str, Any], actor: str) -> dict[str, Any]:
    profile = application_row(payload.get("application"))
    with db() as conn:
        current = conn.execute(
            "SELECT * FROM app_versions WHERE application=? AND environment=? AND active=1",
            (profile["application"], profile["environment"]),
        ).fetchone()
        if not current or not current["previous_version_id"]:
            raise RunnerError("no previous application version is available")
        previous = conn.execute(
            "SELECT * FROM app_versions WHERE version_id=? AND application=?",
            (current["previous_version_id"], profile["application"]),
        ).fetchone()
    if not previous:
        raise RunnerError("previous application version is missing")
    if profile["mode"] == "managed":
        result = rollback({"deployment_id": current["deployment_id"]}, actor)
        result.update({"application": profile["application"], "version": previous["version_label"], "domain": profile["domain"]})
        return result
    if profile["mode"] == "compose":
        compose_up(profile, previous["image"])
        check_health(int(profile["host_port"]), profile["health_path"], attempts=30)
    elif profile["mode"] == "standalone":
        fixed_name = profile["container_name"]
        current_backup = f"{fixed_name}-version-{current['version_id'][:12]}"
        previous_backup = f"{fixed_name}-version-{previous['version_id'][:12]}"
        if run(["/usr/bin/docker", "inspect", previous_backup], check=False).returncode:
            raise RunnerError("previous standalone container is unavailable")
        run(["/usr/bin/docker", "stop", fixed_name])
        run(["/usr/bin/docker", "rename", fixed_name, current_backup])
        run(["/usr/bin/docker", "rename", previous_backup, fixed_name])
        run(["/usr/bin/docker", "start", fixed_name])
        check_health(int(profile["host_port"]), profile["health_path"], attempts=30)
    else:
        raise RunnerError("application rollback mode is unsupported")
    with db() as conn:
        conn.execute(
            "UPDATE app_versions SET active=0 WHERE application=? AND environment=?",
            (profile["application"], profile["environment"]),
        )
        conn.execute("UPDATE app_versions SET active=1,status='READY' WHERE version_id=?", (previous["version_id"],))
        conn.commit()
    audit(actor, "rollback_app", "success", application=profile["application"], version=previous["version_label"])
    return {"application": profile["application"], "version": previous["version_label"], "version_id": previous["version_id"], "status": "READY", "domain": profile["domain"]}


def deploy(payload: dict[str, Any], actor: str) -> dict[str, Any]:
    app = validate_app(payload.get("application"))
    environment = validate_environment(payload.get("environment"))
    build_context = validate_build_context(payload.get("build_context"))
    upload_id = validate_upload_id(payload.get("upload_id"))
    deployment_id = uuid.uuid4().hex
    release_version = validate_version(payload.get("release_version") or f"build-{deployment_id[:12]}")
    release_notes = str(payload.get("release_notes") or "").strip()[:2000]
    supplied_image = str(payload.get("image") or "").strip()
    source_count = int(build_context is not None) + int(upload_id is not None) + int(bool(supplied_image))
    if source_count != 1:
        raise RunnerError("choose exactly one source: Docker image, source ZIP, or approved build context")
    if upload_id:
        build_context = extract_uploaded_context(upload_id, app, deployment_id)
    image = f"jormall-local/{app}:{deployment_id}" if build_context else validate_image(supplied_image)
    container_port = validate_port(payload.get("container_port"))
    health_path = validate_health(payload.get("health_path", "/"))
    protected = bool(payload.get("password_protected", environment != "production"))
    mounts = validate_persistent_mounts(app, environment, payload.get("persistent_mounts"))
    expiry_hours = payload.get("expiry_hours")
    if expiry_hours not in (None, 24, 72, 168):
        raise RunnerError("expiry_hours must be 24, 72, 168, or null")
    if environment != "preview" and expiry_hours is not None:
        raise RunnerError("expiry is only supported for preview deployments")
    container = f"jormall-{app}-{environment}-{deployment_id[:12]}"
    domain = domain_for(app, environment)
    expires_at = None
    if expiry_hours:
        expires_at = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=expiry_hours)).isoformat()

    STATE_DB.parent.mkdir(parents=True, exist_ok=True)
    lock_path = STATE_DB.parent / "deploy.lock"
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            host_port = allocate_port(conn)
            previous = conn.execute(
                "SELECT deployment_id,container_name,host_port FROM deployments WHERE application=? AND environment=? AND active=1",
                (app, environment),
            ).fetchone()
            conn.execute(
                """INSERT INTO deployments
                (deployment_id,application,environment,image,container_name,container_port,host_port,domain,
                 health_path,status,health_status,password_protected,created_at,expires_at,previous_deployment_id,
                 active,persistent_mounts,release_version,release_notes)
                VALUES (?,?,?,?,?,?,?,?,?,'STARTING','pending',?,?,?,?,0,?,?,?)""",
                (deployment_id, app, environment, image, container, container_port, host_port, domain,
                 health_path, int(protected), utc_now(), expires_at, previous[0] if previous else None,
                 json.dumps(mounts, separators=(",", ":")), release_version, release_notes),
            )
            conn.commit()

    env_path = write_env(app, environment, payload.get("environment_variables"))
    password: str | None = None
    try:
        if build_context:
            run(["/usr/bin/docker", "build", "--pull", "--tag", image, str(build_context)], timeout=1800)
        elif run(["/usr/bin/docker", "image", "inspect", image], check=False).returncode:
            run(["/usr/bin/docker", "pull", image], timeout=900)
        memory, memory_swap, cpus, pids_limit = managed_resource_limits(app, environment)
        args = [
            "/usr/bin/docker", "run", "-d", "--name", container,
            "--restart", "unless-stopped", "--security-opt", "no-new-privileges:true",
            "--cap-drop", "ALL", "--pids-limit", pids_limit,
            "--memory", memory, "--memory-swap", memory_swap, "--cpus", cpus,
            "--label", "jormall.managed=true", "--label", f"jormall.deployment={deployment_id}",
            "--publish", f"127.0.0.1:{host_port}:{container_port}",
        ]
        if env_path:
            args += ["--env-file", str(env_path)]
        for mount in mounts:
            args += ["--mount", f"type=bind,src={mount['host_path']},dst={mount['container_path']}"]
        args.append(image)
        run(args)
        # The Assistant indexes its approved document corpus before serving.
        # Give that one application enough time without slowing other releases.
        health_attempts = 150 if app == "assistant" and environment == "production" else 30
        check_health(host_port, health_path, attempts=health_attempts)
        digest = image_digest(image)
        if app == "assistant" and environment == "production":
            activate_sso_backend(host_port)
        if app == "main-site" and environment == "production":
            activate_main_site_backend(host_port)
        if protected:
            password = generate_password()
            AUTH_ROOT.mkdir(parents=True, exist_ok=True)
            auth_file = AUTH_ROOT / f"{app}-{environment}.htpasswd"
            atomic_write(auth_file, "jormall:" + password_hash(password) + "\n", 0o640)
            os.chown(auth_file, 0, grp.getgrnam("www-data").gr_gid)
        activate_nginx(app, environment, nginx_text(
            app=app, environment=environment, domain=domain, port=host_port, protected=protected
        ))
        check_edge(domain, health_path, password)
        with db() as conn:
            conn.execute(
                "UPDATE deployments SET active=0 WHERE application=? AND environment=? AND active=1",
                (app, environment),
            )
            conn.execute(
                "UPDATE deployments SET active=1,status='READY',health_status='healthy',image_digest=? WHERE deployment_id=?",
                (digest, deployment_id),
            )
            conn.execute(
                "UPDATE app_versions SET active=0 WHERE application=? AND environment=? AND active=1",
                (app, environment),
            )
            conn.execute(
                """INSERT OR REPLACE INTO app_versions
                   (version_id,application,environment,version_label,release_notes,mode,image,status,active,
                    deployment_id,previous_version_id,created_at)
                   VALUES (?,?,?,?,?,'managed',?,'READY',1,?,?,?)""",
                (
                    deployment_id, app, environment, release_version, release_notes, image,
                    deployment_id, previous[0] if previous else None, utc_now(),
                ),
            )
            conn.commit()
        # Keep the immediately previous container for rollback, but do not leave it
        # consuming resources after traffic has successfully moved to the new one.
        if previous:
            run(["/usr/bin/docker", "stop", previous[1]], check=False)
        audit(actor, "deploy", "success", application=app, environment=environment, deployment_id=deployment_id)
        return {"deployment_id": deployment_id, "status": "READY", "domain": domain,
                "host_port": host_port, "password": password, "password_username": "jormall" if password else None}
    except Exception as exc:
        preserve_failure_logs(container, deployment_id)
        run(["/usr/bin/docker", "rm", "-f", container], check=False)
        if app == "assistant" and environment == "production" and previous:
            activate_sso_backend(int(previous[2]))
        if app == "main-site" and environment == "production" and previous:
            activate_main_site_backend(int(previous[2]))
        with db() as conn:
            conn.execute("UPDATE deployments SET status='FAILED',health_status='unhealthy' WHERE deployment_id=?", (deployment_id,))
            conn.execute(
                """INSERT OR REPLACE INTO app_versions
                   (version_id,application,environment,version_label,release_notes,mode,image,status,active,
                    deployment_id,previous_version_id,created_at)
                   VALUES (?,?,?,?,?,'managed',?,'FAILED',0,?,?,?)""",
                (
                    deployment_id, app, environment, release_version, release_notes, image,
                    deployment_id, previous[0] if previous else None, utc_now(),
                ),
            )
            conn.commit()
        audit(actor, "deploy", "failed", application=app, environment=environment,
              deployment_id=deployment_id, error=type(exc).__name__)
        raise


def find_row(deployment_id: Any) -> dict[str, Any]:
    deployment_id = str(deployment_id or "").strip().lower()
    if not DEPLOYMENT_RE.fullmatch(deployment_id):
        raise RunnerError("invalid deployment ID")
    with db() as conn:
        row = conn.execute("SELECT * FROM deployments WHERE deployment_id=?", (deployment_id,)).fetchone()
    if not row:
        raise RunnerError("deployment not found")
    return dict(row)


def lifecycle(operation: str, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    row = find_row(payload.get("deployment_id"))
    container = row["container_name"]
    if not CONTAINER_RE.fullmatch(container):
        raise RunnerError("stored container name is invalid")
    if operation == "restart":
        run(["/usr/bin/docker", "restart", container])
        check_health(row["host_port"], row["health_path"], attempts=15)
        status = "READY"
    elif operation == "stop":
        run(["/usr/bin/docker", "stop", container])
        status = "STOPPED"
    elif operation == "logs":
        lines = int(payload.get("lines", 200))
        if not 1 <= lines <= 1000:
            raise RunnerError("lines must be between 1 and 1000")
        output = run(["/usr/bin/docker", "logs", "--tail", str(lines), container], check=False)
        audit(actor, operation, "success", application=row["application"], environment=row["environment"], deployment_id=row["deployment_id"])
        return {"deployment_id": row["deployment_id"], "logs": (output.stdout + output.stderr)[-100000:]}
    elif operation == "delete":
        run(["/usr/bin/docker", "rm", "-f", container], check=False)
        if row["active"]:
            (GENERATED_NGINX / f"{row['application']}-{row['environment']}.conf").unlink(missing_ok=True)
            result = run(["/usr/sbin/nginx", "-t"], check=False)
            if result.returncode:
                raise RunnerError("Nginx validation failed during cleanup")
            run(["/bin/systemctl", "reload", "nginx"])
            (AUTH_ROOT / f"{row['application']}-{row['environment']}.htpasswd").unlink(missing_ok=True)
        status = "DELETED"
    else:
        raise RunnerError("unsupported lifecycle operation")
    with db() as conn:
        conn.execute("UPDATE deployments SET status=? WHERE deployment_id=?", (status, row["deployment_id"]))
        conn.commit()
    audit(actor, operation, "success", application=row["application"], environment=row["environment"], deployment_id=row["deployment_id"])
    return {"deployment_id": row["deployment_id"], "status": status}


def rotate_password(payload: dict[str, Any], actor: str) -> dict[str, Any]:
    row = find_row(payload.get("deployment_id"))
    if not row["active"] or not row["password_protected"]:
        raise RunnerError("only an active protected deployment can rotate its password")
    password = generate_password()
    auth_file = AUTH_ROOT / f"{row['application']}-{row['environment']}.htpasswd"
    atomic_write(auth_file, "jormall:" + password_hash(password) + "\n", 0o640)
    os.chown(auth_file, 0, grp.getgrnam("www-data").gr_gid)
    audit(actor, "rotate_password", "success", application=row["application"],
          environment=row["environment"], deployment_id=row["deployment_id"])
    return {"deployment_id": row["deployment_id"], "password_username": "jormall", "password": password}


def redeploy(payload: dict[str, Any], actor: str) -> dict[str, Any]:
    source = find_row(payload.get("deployment_id"))
    return deploy({
        "application": source["application"],
        "environment": source["environment"],
        "image": source.get("image_digest") or source["image"],
        "container_port": source["container_port"],
        "health_path": source["health_path"],
        "password_protected": bool(source["password_protected"]),
        "persistent_mounts": json.loads(source.get("persistent_mounts") or "[]"),
    }, actor)


def rollback(payload: dict[str, Any], actor: str) -> dict[str, Any]:
    current = find_row(payload.get("deployment_id"))
    previous_id = current.get("previous_deployment_id")
    if not previous_id:
        raise RunnerError("no previous deployment is recorded")
    previous = find_row(previous_id)
    run(["/usr/bin/docker", "start", previous["container_name"]])
    check_health(previous["host_port"], previous["health_path"], attempts=20)
    if previous["application"] == "assistant" and previous["environment"] == "production":
        activate_sso_backend(previous["host_port"])
    if previous["application"] == "main-site" and previous["environment"] == "production":
        activate_main_site_backend(previous["host_port"])
    activate_nginx(previous["application"], previous["environment"], nginx_text(
        app=previous["application"], environment=previous["environment"], domain=previous["domain"],
        port=previous["host_port"], protected=bool(previous["password_protected"])
    ))
    with db() as conn:
        conn.execute("UPDATE deployments SET active=0 WHERE application=? AND environment=?",
                     (previous["application"], previous["environment"]))
        conn.execute("UPDATE deployments SET active=1,status='READY',health_status='healthy' WHERE deployment_id=?",
                     (previous_id,))
        conn.execute("UPDATE app_versions SET active=0 WHERE application=? AND environment=?",
                     (previous["application"], previous["environment"]))
        conn.execute("UPDATE app_versions SET active=1,status='READY' WHERE version_id=?",
                     (previous_id,))
        conn.commit()
    run(["/usr/bin/docker", "stop", current["container_name"]], check=False)
    audit(actor, "rollback", "success", application=previous["application"], environment=previous["environment"], deployment_id=previous_id)
    return {"deployment_id": previous_id, "status": "READY"}


def promote(payload: dict[str, Any], actor: str) -> dict[str, Any]:
    source = find_row(payload.get("deployment_id"))
    if source["environment"] not in {"preview", "staging"}:
        raise RunnerError("only preview or staging can be promoted")
    image = source.get("image_digest") or source["image"]
    return deploy({"application": source["application"], "environment": "production", "image": image,
                   "container_port": source["container_port"], "health_path": source["health_path"],
                   "password_protected": False,
                   "persistent_mounts": json.loads(source.get("persistent_mounts") or "[]")}, actor)


def expire(actor: str) -> dict[str, Any]:
    now = utc_now()
    expired = []
    with db() as conn:
        rows = [dict(row) for row in conn.execute(
            "SELECT * FROM deployments WHERE environment='preview' AND expires_at IS NOT NULL AND expires_at<=? AND active=1", (now,)
        )]
    for row in rows:
        run(["/usr/bin/docker", "rm", "-f", row["container_name"]], check=False)
        config = GENERATED_NGINX / f"{row['application']}-preview.conf"
        config.unlink(missing_ok=True)
        if run(["/usr/sbin/nginx", "-t"], check=False).returncode == 0:
            run(["/bin/systemctl", "reload", "nginx"])
        with db() as conn:
            conn.execute("UPDATE deployments SET active=0,status='EXPIRED' WHERE deployment_id=?", (row["deployment_id"],))
            conn.commit()
        expired.append(row["deployment_id"])
        audit(actor, "expire", "success", application=row["application"], environment="preview", deployment_id=row["deployment_id"])
    return {"expired": expired}


def dispatch(request: dict[str, Any]) -> dict[str, Any]:
    operation = str(request.get("operation") or "")
    if operation not in ALLOWED_OPS:
        raise RunnerError("operation is not allowlisted")
    actor = str(request.get("actor") or "unknown")[:128]
    payload = request.get("payload") or {}
    if not isinstance(payload, dict):
        raise RunnerError("payload must be an object")
    if operation == "ping":
        return {"status": "ok", "time": utc_now()}
    if operation == "list":
        return {"deployments": list_deployments()}
    if operation == "catalog":
        return {"applications": catalog()}
    if operation == "versions":
        return versions_for(payload.get("application"))
    if operation == "release":
        return release_application(payload, actor)
    if operation == "rollback_app":
        return rollback_application(payload, actor)
    if operation == "deploy":
        return deploy(payload, actor)
    if operation in {"restart", "stop", "logs", "delete"}:
        return lifecycle(operation, payload, actor)
    if operation == "rollback":
        return rollback(payload, actor)
    if operation == "promote":
        return promote(payload, actor)
    if operation == "redeploy":
        return redeploy(payload, actor)
    if operation == "rotate_password":
        return rotate_password(payload, actor)
    return expire(actor)


class Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        raw = self.rfile.readline(MAX_REQUEST + 1)
        if not raw or len(raw) > MAX_REQUEST:
            return
        try:
            request = json.loads(raw)
            if not isinstance(request, dict):
                raise RunnerError("request must be an object")
            response = {"ok": True, "result": dispatch(request)}
        except Exception as exc:
            response = {"ok": False, "error": str(exc)[:2000], "error_type": type(exc).__name__}
        self.wfile.write(json.dumps(response, separators=(",", ":")).encode() + b"\n")


class UnixServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True


def main() -> None:
    www_gid = grp.getgrnam("www-data").gr_gid
    AUTH_ROOT.parent.mkdir(parents=True, exist_ok=True)
    os.chown(AUTH_ROOT.parent, 0, www_gid)
    os.chmod(AUTH_ROOT.parent, 0o750)
    AUTH_ROOT.mkdir(parents=True, exist_ok=True)
    os.chown(AUTH_ROOT, 0, www_gid)
    os.chmod(AUTH_ROOT, 0o750)
    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    SOCKET_PATH.unlink(missing_ok=True)
    db().close()
    with UnixServer(str(SOCKET_PATH), Handler) as server:
        os.chmod(SOCKET_PATH, 0o660)
        gid = int(os.environ.get("JORMALL_RUNNER_GID", "0"))
        os.chown(SOCKET_PATH, 0, gid)
        server.serve_forever()


if __name__ == "__main__":
    main()
