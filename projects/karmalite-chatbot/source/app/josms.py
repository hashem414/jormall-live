"""JorMall/JOSMS Service SMS client.

The provider uses a GET endpoint whose query string contains credentials.  This
module is deliberately isolated so credentials never reach browser code, API
responses, or application logs.  An HTTP 2xx only proves transport success;
delivery and even provider acceptance require JorMall's official response map.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import httpx

from .config import Settings, get_settings

logger = logging.getLogger(__name__)

# httpx's INFO log includes the complete request URL.  JOSMS credentials are
# query parameters, so INFO-level request logging would leak the password.
logging.getLogger("httpx").setLevel(logging.WARNING)

_PHONE_RE = re.compile(r"^9627\d{8}$")
_MAX_MESSAGE_CHARS = 1000
_MAX_RESPONSE_CHARS = 2000


class JOSMSError(RuntimeError):
    """Base error safe to persist without secrets."""


class JOSMSConfigurationError(JOSMSError):
    pass


class JOSMSTemporaryError(JOSMSError):
    pass


class JOSMSProviderError(JOSMSError):
    pass


@dataclass(frozen=True)
class JOSMSResult:
    reference_id: str
    provider_response: str
    acceptance_verified: bool | None
    http_status: int


def configuration_status(settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    missing = []
    if not settings.josms_sender_id.strip():
        missing.append("JOSMS_SENDER_ID")
    if not settings.josms_accname.strip():
        missing.append("JOSMS_ACCNAME")
    if not settings.josms_accpass.get_secret_value().strip():
        missing.append("JOSMS_ACCPASS")
    return {
        "enabled": settings.sms_enabled,
        "configured": not missing,
        "missing": missing,
        "response_map_configured": bool(settings.josms_success_responses.strip()),
    }


def _validate(phone_number: str, message: str, reference_id: str) -> None:
    if not _PHONE_RE.fullmatch(phone_number or ""):
        raise ValueError("phone_number must use the JOSMS format 9627XXXXXXXX")
    if not (message or "").strip():
        raise ValueError("SMS message is empty")
    if len(message) > _MAX_MESSAGE_CHARS:
        raise ValueError(f"SMS message exceeds {_MAX_MESSAGE_CHARS} characters")
    if len(reference_id) > 100:
        raise ValueError("reference_id exceeds 100 characters")


def send_service_sms(
    *,
    phone_number: str,
    message: str,
    reference_id: str,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> JOSMSResult:
    """Submit one Service SMS without claiming that it was delivered."""
    settings = settings or get_settings()
    _validate(phone_number, message, reference_id)

    state = configuration_status(settings)
    if not settings.sms_enabled:
        raise JOSMSConfigurationError("Service SMS is disabled")
    if not state["configured"]:
        raise JOSMSConfigurationError(
            "Missing JOSMS configuration: " + ", ".join(state["missing"])
        )

    params = {
        "senderid": settings.josms_sender_id,
        "numbers": phone_number,
        "accname": settings.josms_accname,
        "AccPass": settings.josms_accpass.get_secret_value(),
        "msg": message,
        "id": reference_id,
    }

    owns_client = client is None
    http = client or httpx.Client(
        timeout=settings.josms_timeout_seconds,
        follow_redirects=False,
    )
    try:
        try:
            response = http.get(settings.josms_api_url, params=params)
        except httpx.TimeoutException as exc:
            raise JOSMSTemporaryError("JOSMS request timed out") from exc
        except httpx.RequestError as exc:
            raise JOSMSTemporaryError("Unable to connect to JOSMS") from exc
    finally:
        if owns_client:
            http.close()

    if response.status_code >= 500:
        raise JOSMSTemporaryError(f"JOSMS HTTP {response.status_code}")
    if not 200 <= response.status_code < 300:
        raise JOSMSProviderError(f"JOSMS HTTP {response.status_code}")

    provider_response = response.text.strip()[:_MAX_RESPONSE_CHARS]
    success_values = {
        value.strip()
        for value in settings.josms_success_responses.split(",")
        if value.strip()
    }
    acceptance_verified: bool | None = None
    if success_values:
        acceptance_verified = provider_response in success_values
        if not acceptance_verified:
            raise JOSMSProviderError("JOSMS returned an unrecognized/rejected response")

    logger.info(
        "JOSMS request submitted reference=%s verified=%s http=%s",
        reference_id,
        acceptance_verified,
        response.status_code,
    )
    return JOSMSResult(
        reference_id=reference_id,
        provider_response=provider_response,
        acceptance_verified=acceptance_verified,
        http_status=response.status_code,
    )
