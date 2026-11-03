import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace


os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://jormall_user:REDACTED_CONFIGURE_LOCALLY@postgres:5432/jormall_chatbot",
)
os.environ.setdefault("CALLBACK_DASHBOARD_PASSWORD", "test-password")

from app.api.chat_history import format_conversation_row, mask_mobile, safe_csv_value, router


class ChatHistoryHelperTests(unittest.TestCase):
    def test_browser_conversation_memory_is_versioned_by_approved_knowledge(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        template = (project_root / "app/templates/chat.html").read_text(encoding="utf-8-sig")
        javascript = (project_root / "app/static/js/chat.js").read_text(encoding="utf-8-sig")
        self.assertIn("knowledgeVersion", template)
        self.assertIn("KNOWLEDGE_MEMORY_VERSION", javascript)
        self.assertIn("chatbotConfig.knowledgeVersion", javascript)

    def test_mask_mobile_hides_middle_digits(self):
        self.assertEqual(mask_mobile("0791234123"), "079****123")

    def test_mask_mobile_keeps_short_values_unchanged(self):
        self.assertEqual(mask_mobile("07912"), "07912")

    def test_safe_csv_value_prevents_formula_execution(self):
        self.assertEqual(safe_csv_value("=SUM(1,1)"), "'=SUM(1,1)")
        self.assertEqual(safe_csv_value("+962791234123"), "'+962791234123")

    def test_format_conversation_row_omits_company_name(self):
        now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
        conversation = SimpleNamespace(
            id="00000000-0000-0000-0000-000000000001",
            public_session_id="session-1",
            client_slug="central-e-commerce-co-ltd",
            campaign_name="A New Generation of SMS Communication",
            chatbot_name="JorMall Assistant",
            customer_name="Test User",
            company_name="Example Co",
            customer_mobile="0791234123",
            language="en",
            source="interactive_sms",
            status="open",
            assigned_employee="",
            follow_up_required=False,
            internal_notes="",
            started_at=now,
            last_activity_at=now,
            completed_at=None,
        )
        row = format_conversation_row(conversation, reveal_phone=True)
        self.assertNotIn("company_name", row)

    def test_export_route_is_registered_before_dynamic_conversation_route(self):
        paths = [route.path for route in router.routes]
        self.assertLess(
            paths.index("/api/admin/conversations/export.csv"),
            paths.index("/api/admin/conversations/{conversation_id}"),
        )


if __name__ == "__main__":
    unittest.main()
