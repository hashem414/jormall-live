import os

from dotenv import load_dotenv


load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-5.5")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")

APP_ENV = os.getenv("APP_ENV", "development").lower()


def normalize_base_path(value):
    value = (value or "").strip().replace("\\", "/")
    parts = [part for part in value.split("/") if part]
    if not parts:
        return ""
    return "/" + "/".join(parts)


APP_BASE_PATH = normalize_base_path(os.getenv("APP_BASE_PATH", ""))


def public_path(path):
    path = "/" + str(path).lstrip("/")
    return f"{APP_BASE_PATH}{path}"


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


SESSION_COOKIE_SECURE = True if APP_ENV == "production" else env_bool("SESSION_COOKIE_SECURE", False)
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "lax").lower()
SESSION_MAX_AGE_SECONDS = int(os.getenv("SESSION_MAX_AGE_SECONDS", str(7 * 24 * 60 * 60)))

ENABLE_MAINTENANCE_ROUTES = env_bool("ENABLE_MAINTENANCE_ROUTES", False) and APP_ENV != "production"

CHAT_LOG_DIR = os.getenv("CHAT_LOG_DIR", "logs")
CHAT_LOG_MAX_BYTES = int(os.getenv("CHAT_LOG_MAX_BYTES", str(10 * 1024 * 1024)))


def log_openai_model(purpose, model):
    print(f"[OPENAI] purpose={purpose} model={model}", flush=True)
