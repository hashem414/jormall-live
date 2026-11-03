from __future__ import annotations

import json
import http.cookiejar
import os
import time
import unittest
import urllib.error
import urllib.request
import urllib.parse
from uuid import uuid4

from sqlalchemy import delete

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.document import ChatbotLead, ChatConversation


class HttpAssuranceIntegrationTests(unittest.TestCase):
    origin = os.getenv("ASSURANCE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    base_url = f"{origin}/interactive-sms"

    @classmethod
    def setUpClass(cls) -> None:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"{cls.origin}/health", timeout=2) as response:
                    if response.status == 200:
                        return
            except (OSError, urllib.error.URLError):
                time.sleep(0.25)
        raise RuntimeError(f"Application did not become healthy at {cls.origin}.")

    @classmethod
    def request(cls, method: str, path: str, payload: dict | None = None, headers: dict | None = None):
        body = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            cls.base_url + path,
            data=body,
            headers={"Content-Type": "application/json", **(headers or {})},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                raw = response.read()
                return response.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as error:
            raw = error.read()
            return error.code, json.loads(raw) if raw else {}

    def setUp(self) -> None:
        suffix = uuid4().int % 10_000_000
        self.session_id = f"assurance-{uuid4().hex}"
        self.chat_session_id = f"chat-{uuid4().hex}"
        self.phone = f"079{suffix:07d}"

    def tearDown(self) -> None:
        with SessionLocal() as db:
            db.execute(
                delete(ChatConversation).where(
                    ChatConversation.public_session_id == self.chat_session_id
                )
            )
            db.execute(delete(ChatbotLead).where(ChatbotLead.session_id == self.session_id))
            db.commit()

    def test_tenant_boundary_lead_gate_and_admin_auth(self) -> None:
        status, _ = self.request("POST", "/api/chat/not-this-client/stream", {"message": "hello"})
        self.assertEqual(status, 404)
        status, _ = self.request(
            "POST", "/api/chat/central-e-commerce-co-ltd/stream", {"message": "hello"}
        )
        self.assertEqual(status, 403)
        status, _ = self.request("GET", "/api/admin/sales-callback-dashboard/requests")
        self.assertEqual(status, 401)

    def test_input_validation_rejects_invalid_phone_markup_and_oversized_prompt(self) -> None:
        status, _ = self.request(
            "POST", "/api/chat/central-e-commerce-co-ltd/lead",
            {"session_id": self.session_id, "chat_session_id": self.chat_session_id,
             "name": "<script> Tester", "phone": "123"},
        )
        self.assertEqual(status, 422)
        status, _ = self.request(
            "POST", "/api/chat/central-e-commerce-co-ltd/stream",
            {"message": "x" * 1001, "lead_session_id": self.session_id},
        )
        self.assertEqual(status, 422)

    def test_callback_is_idempotent_and_authorized_listing_works(self) -> None:
        status, created = self.request(
            "POST", "/api/chat/central-e-commerce-co-ltd/lead",
            {"session_id": self.session_id, "chat_session_id": self.chat_session_id,
             "name": "Assurance Tester", "phone": self.phone,
             "cookie_notice_opened": True, "privacy_notice_opened": True},
        )
        self.assertEqual(status, 200)
        self.assertTrue(created["success"])
        path = "/api/chat/central-e-commerce-co-ltd/request-sales-call"
        status, first = self.request("POST", path, {"session_id": self.session_id})
        self.assertEqual(status, 200)
        self.assertFalse(first["already_pending"])
        status, second = self.request("POST", path, {"session_id": self.session_id})
        self.assertEqual(status, 200)
        self.assertTrue(second["already_pending"])
        password = settings.callback_dashboard_password.get_secret_value()
        cookie_jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
        login = urllib.request.Request(
            self.base_url + "/sales-callbacks/login",
            data=urllib.parse.urlencode({"password": password}).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with opener.open(login, timeout=8) as response:
            self.assertEqual(response.status, 200)
        with opener.open(
            self.base_url + "/api/admin/sales-callback-dashboard/requests", timeout=8
        ) as response:
            self.assertEqual(response.status, 200)
            listing = json.loads(response.read())
        self.assertTrue(any(item["phone"] == self.phone for item in listing["requests"]))
