from __future__ import annotations

import hmac
import logging
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from flask import Flask, current_app, jsonify, request
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from .config import Settings, load_settings
from .emailer import send_sales_priority
from .hybrid import answer_hybrid
from .openai_http import OpenAIHTTPClient, OpenAIUpstreamError


LOGGER = logging.getLogger("jormall_gateway")


def _settings() -> Settings:
    return current_app.extensions["jormall_settings"]


def _client() -> OpenAIHTTPClient:
    return current_app.extensions["jormall_openai_client"]


def require_extension_auth(handler: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(handler)
    def wrapped(*args: Any, **kwargs: Any):
        expected = _settings().extension_shared_key
        supplied = request.headers.get("X-SMA-Extension-Key", "")
        if not expected or not supplied or not hmac.compare_digest(expected, supplied):
            return jsonify(ok=False, error="Unauthorized SMA extension request."), 401
        return handler(*args, **kwargs)

    return wrapped


def _json_payload() -> dict[str, Any]:
    payload = request.get_json(force=False, silent=False)
    if not isinstance(payload, dict):
        raise BadRequest("A JSON object is required.")
    return payload


def _validate_question(payload: dict[str, Any]) -> str:
    question = str(payload.get("question") or "").strip()
    if not question:
        raise BadRequest("A question is required.")
    if len(question) > _settings().max_question_chars:
        raise BadRequest(f"The question exceeds {_settings().max_question_chars} characters.")
    return question


def create_app(
    settings: Settings | None = None,
    openai_client: OpenAIHTTPClient | None = None,
) -> Flask:
    backend_root = Path(__file__).resolve().parents[1]
    cfg = settings or load_settings(backend_root)
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=cfg.max_request_bytes, JSON_AS_ASCII=False)
    app.extensions["jormall_settings"] = cfg
    app.extensions["jormall_openai_client"] = openai_client or OpenAIHTTPClient(cfg)

    @app.after_request
    def security_headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/health")
    def health():
        supplied = request.headers.get("X-SMA-Extension-Key", "")
        auth_accepted = bool(cfg.extension_shared_key and supplied and hmac.compare_digest(cfg.extension_shared_key, supplied))
        return jsonify(
            ok=True,
            status="online",
            service="JorMall SMA Extension AI Gateway",
            version="2.0.0",
            openaiEnabled=cfg.openai_enabled,
            model=cfg.model,
            documentRetrievalEnabled=cfg.retrieval_enabled,
            emailNotificationsEnabled=cfg.email_enabled,
            authenticationEnabled=bool(cfg.extension_shared_key),
            authenticationAccepted=auth_accepted,
        )

    @app.post("/api/chat")
    @require_extension_auth
    def chat():
        if not cfg.openai_enabled:
            return jsonify(ok=False, error="OpenAI is not configured on the gateway."), 503
        payload = _json_payload()
        _validate_question(payload)
        result = answer_hybrid(payload, cfg, _client())
        return jsonify(result)

    @app.post("/sma/analyze-notes")
    @require_extension_auth
    def analyze_notes():
        if not cfg.openai_enabled:
            return jsonify(ok=False, error="OpenAI is not configured on the gateway."), 503
        source = _json_payload()
        payload = {
            "screen": "company-notes",
            "question": (
                "Summarize the latest customer updates, payment and response attitude, risks, "
                "department ownership, and next best action."
            ),
            "notesData": source.get("notesData") or {},
            "pageInfo": {"url": source.get("pageUrl") or ""},
        }
        result = answer_hybrid(payload, cfg, _client())
        return jsonify(
            ok=True,
            summary=result["answer"],
            aiSummary={"raw": result["answer"]},
            sources=result["sources"],
            retrieval=result["retrieval"],
            model=result["model"],
        )

    @app.post("/sma/notify-sales-priority")
    @require_extension_auth
    def notify_sales_priority():
        try:
            count = send_sales_priority(cfg, _json_payload())
        except RuntimeError as exc:
            return jsonify(ok=False, error=str(exc)), 503
        except ValueError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        return jsonify(ok=True, sent=True, companies=count)

    @app.errorhandler(BadRequest)
    def bad_request(error):
        return jsonify(ok=False, error=str(error.description or "Invalid request.")), 400

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_error):
        return jsonify(ok=False, error="The request payload is too large."), 413

    @app.errorhandler(OpenAIUpstreamError)
    def upstream_error(error):
        LOGGER.warning("OpenAI upstream error: %s", error)
        return jsonify(ok=False, error=str(error)), 502

    @app.errorhandler(Exception)
    def unexpected_error(error):
        LOGGER.exception("Unhandled gateway error")
        return jsonify(ok=False, error="The gateway could not complete the request."), 500

    return app

