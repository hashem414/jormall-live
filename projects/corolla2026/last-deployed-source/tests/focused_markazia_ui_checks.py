from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app.api.public_chat_shared import (  # noqa: E402
    LeadCapturePayload,
    callback_response_message,
    lead_session_has_current_consent,
)
from app.core.database import SessionLocal  # noqa: E402
from app.models.document import SalesCallbackRequest  # noqa: E402
from app.services import dashboard_auth_service  # noqa: E402


CONFIG_PATH = (
    ROOT
    / "data"
    / "clients"
    / "central-trade-auto-co-markazia-toyota-jordan"
    / "config.json"
)
SERVER_URL = "http://127.0.0.1:8000"
BASE_URL = f"{SERVER_URL}/central-trade-auto-co-markazia-toyota-jordan"
NEW_STARTER_EN = "I would like the sales team to call me."
NEW_STARTER_AR = "أرغب أن يتصل بي فريق المبيعات."
CONTACT_NOTICE_EN = (
    "The contact information you provide will be used to respond to your enquiry "
    "and to arrange sales follow-up when you request it."
)
CONTACT_NOTICE_AR = (
    "سيتم استخدام معلومات الاتصال التي تقدمها للرد على استفسارك وترتيب متابعة فريق المبيعات عند طلبك."
)
CONFIRM_PROMPT_EN = "Would you like me to submit a request for the sales team to call you?"
CONFIRM_PROMPT_AR = "هل ترغب في إرسال طلب ليتصل بك فريق المبيعات؟"
CANCELLED_EN = "The callback request was cancelled. No request was submitted."
CANCELLED_AR = "تم إلغاء طلب الاتصال، ولم يتم إرسال أي طلب."


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def post_json(path: str, payload: dict[str, str], *, language: str = "en") -> dict:
    url = f"{BASE_URL}{path}"
    if language:
        url = f"{url}?language={language}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise AssertionError(f"{path} returned {error.code}: {body}") from error


def pending_callback_ids(session_id: str) -> set[str]:
    with SessionLocal() as db:
        rows = db.scalars(
            select(SalesCallbackRequest).where(
                SalesCallbackRequest.session_id == session_id,
                SalesCallbackRequest.status == "pending",
            )
        ).all()
    return {str(row.id) for row in rows}


def get_text(path: str) -> str:
    with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=10) as response:
        return response.read().decode("utf-8", errors="replace")


def get_server_text(path: str) -> str:
    with urllib.request.urlopen(f"{SERVER_URL}{path}", timeout=10) as response:
        return response.read().decode("utf-8", errors="replace")


def dashboard_login_opener() -> urllib.request.OpenerDirector:
    password = dashboard_auth_service.dashboard_password()
    assert password, "dashboard password must be configured for the local smoke check"

    cookie_jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    data = urllib.parse.urlencode(
        {
            "password": password,
            "next": "/central-trade-auto-co-markazia-toyota-jordan/sales-callbacks/",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE_URL}/admin/login",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with opener.open(request, timeout=10) as response:
        body = response.read().decode("utf-8", errors="replace")
        assert response.status == 200
        assert "Sales Callback Requests" in body
    return opener


def test_starter_question_pair_and_order() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    items = config["starter_question_items"]

    assert len(items) == 4
    assert [item["id"] for item in items] == [
        "specifications",
        "grades_colours_features",
        "financing_trade_in",
        "request_sales_callback",
    ]
    assert items[3]["type"] == "request_sales_callback"
    assert items[3]["label_en"] == NEW_STARTER_EN
    assert items[3]["label_ar"] == NEW_STARTER_AR
    assert config["suggested_questions"]["en"][3] == NEW_STARTER_EN
    assert config["suggested_questions"]["ar"][3] == NEW_STARTER_AR


def test_public_prechat_form_is_simplified() -> None:
    template = read_text("app/templates/chat.html")
    script = read_text("app/static/js/chat.js")
    css = read_text("app/static/css/styles.css")

    assert 'id="prechat-lead-name"' in template
    assert 'id="prechat-lead-phone"' in template
    assert 'id="prechat-lead-company"' not in template
    assert 'name="company"' not in template
    assert 'id="prechat-privacy-consent"' not in template
    assert "TRC requirements" not in template
    assert "Personal Data Protection Law" not in template
    assert "هيئة تنظيم قطاع الاتصالات" not in template
    assert "قانون حماية البيانات الشخصية" not in template
    assert "leadConsentVersion" not in template
    assert CONTACT_NOTICE_EN in template

    assert "leadCompany" not in script
    assert "prechat-lead-company" not in script
    assert "leadPrivacyConsent" not in script
    assert "prechat-privacy-consent" not in script
    assert "privacy_consent_accepted" not in script
    assert "cookie_consent_accepted" not in script
    assert CONTACT_NOTICE_EN in script
    assert CONTACT_NOTICE_AR in script
    assert "prechat-consent" not in css


def test_backend_lead_payload_allows_missing_company_and_consent() -> None:
    payload = LeadCapturePayload(
        session_id="focused-test-session",
        name="Test User",
        phone="0791234567",
    )
    assert payload.company is None
    assert payload.cookie_consent_accepted is None
    assert payload.privacy_consent_accepted is None

    old_payload = LeadCapturePayload(
        session_id="focused-test-session",
        name="Test User",
        phone="0791234567",
        company=None,
        privacy_consent_accepted=False,
        cookie_consent_accepted=False,
    )
    assert old_payload.company is None
    assert old_payload.privacy_consent_accepted is False

    session = SimpleNamespace(lead_id="linked", privacy_consent_accepted=False)
    assert lead_session_has_current_consent(session, consent_version="unused")


def test_callback_confirmation_static_flow() -> None:
    script = read_text("app/static/js/chat.js")
    starter_block = script[
        script.index("function submitSalesCallbackStarter"):
        script.index("function normalizeCallbackDecisionText")
    ]

    assert CONFIRM_PROMPT_EN in script
    assert CONFIRM_PROMPT_AR in script
    assert 'callbackConfirm: "Confirm request"' in script
    assert 'callbackCancel: "Cancel"' in script
    assert 'callbackConfirm: "تأكيد الطلب"' in script
    assert 'callbackCancel: "إلغاء"' in script
    assert CANCELLED_EN in script
    assert CANCELLED_AR in script
    assert "pendingSalesCallbackConfirmation" in script
    assert "handlePendingSalesCallbackDecision(message)" in script
    assert "submitSalesCallbackRequest" not in starter_block
    assert "fetch(" not in starter_block


def test_callback_endpoint_duplicate_protection_with_existing_service() -> None:
    suffix = str(int(time.time() * 1000))[-7:]
    session_id = f"focused-callback-{suffix}"
    phone = f"079{suffix}"

    lead = post_json(
        "/api/chat/lead",
        {"session_id": session_id, "name": "Focused User", "phone": phone},
        language="",
    )
    assert lead["success"] is True
    assert pending_callback_ids(session_id) == set()

    first = post_json(
        "/api/chat/request-sales-call",
        {"session_id": session_id},
        language="en",
    )
    first_ids = pending_callback_ids(session_id)
    assert first["success"] is True
    assert first["already_pending"] is False
    assert len(first_ids) == 1
    assert first["message"] == (
        "Your request has been recorded. A member of the sales team will contact you."
    )

    duplicate = post_json(
        "/api/chat/request-sales-call",
        {"session_id": session_id},
        language="en",
    )
    second_ids = pending_callback_ids(session_id)
    assert duplicate["success"] is True
    assert duplicate["already_pending"] is True
    assert second_ids == first_ids


def test_callback_language_responses() -> None:
    english = callback_response_message(already_pending=False, language="en")
    duplicate = callback_response_message(already_pending=True, language="en")
    arabic = callback_response_message(already_pending=False, language="ar")
    arabic_duplicate = callback_response_message(already_pending=True, language="ar")

    assert english == "Your request has been recorded. A member of the sales team will contact you."
    assert "already" in duplicate
    assert arabic == "تم تسجيل طلبك، وسيتواصل معك أحد أعضاء فريق المبيعات."
    assert "مسبقًا" in arabic_duplicate


def test_local_public_and_dashboard_smoke_without_chat_stream() -> None:
    health = get_server_text("/health")
    public_page = get_text("/")
    sales_login_page = get_text("/sales-callbacks/")
    chat_history_login_page = get_text("/chat-history/")
    logo_response = urllib.request.urlopen(
        f"{BASE_URL}/static/client_assets/central-trade-auto-co-markazia-toyota-jordan/logo.jpg",
        timeout=10,
    )

    assert '"status":"healthy"' in health
    assert '"media_images":10' in health
    assert "Markazia Toyota Assistant" in public_page
    assert 'id="prechat-lead-company"' not in public_page
    assert 'id="prechat-privacy-consent"' not in public_page
    assert CONTACT_NOTICE_EN in public_page
    assert "Markazia Toyota" in sales_login_page
    assert "Markazia Toyota" in chat_history_login_page
    assert logo_response.status == 200

    opener = dashboard_login_opener()
    with opener.open(f"{BASE_URL}/chat-history/", timeout=10) as response:
        body = response.read().decode("utf-8", errors="replace")
        assert response.status == 200
        assert "Chat History" in body


def test_dashboard_safe_next_does_not_double_prefix() -> None:
    target = "/central-trade-auto-co-markazia-toyota-jordan/sales-callbacks/"
    assert dashboard_auth_service.safe_next_path("", default=target) == target
    assert dashboard_auth_service.safe_next_path(target, default="/") == target


if __name__ == "__main__":
    tests = [
        test_starter_question_pair_and_order,
        test_public_prechat_form_is_simplified,
        test_backend_lead_payload_allows_missing_company_and_consent,
        test_callback_confirmation_static_flow,
        test_callback_endpoint_duplicate_protection_with_existing_service,
        test_callback_language_responses,
        test_local_public_and_dashboard_smoke_without_chat_stream,
        test_dashboard_safe_next_does_not_double_prefix,
    ]
    for test in tests:
        test()
    print(f"{len(tests)} focused Markazia UI checks passed.")
