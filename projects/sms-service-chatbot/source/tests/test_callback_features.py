from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import delete, select

from app.api.public_chat import SalesCallbackPayload
from app.api.sales_callbacks import format_callback_row
from app.core.database import SessionLocal
from app.incremental_document_ingest import (
    DEFAULT_SOURCE_DIR,
    main as ingest_main,
    preservation_counts,
)
from app.models.document import Document, DocumentChunk
from app.services.client_config_service import load_client_config, normalize_starter_question_items


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHAT_JS = PROJECT_ROOT / "app" / "static" / "js" / "chat.js"
DASHBOARD_JS = PROJECT_ROOT / "app" / "static" / "js" / "sales-callbacks.js"
CHAT_CSS = PROJECT_ROOT / "app" / "static" / "css" / "styles.css"


class CallbackFeatureTests(unittest.TestCase):
    def test_callback_payload_accepts_trimmed_client_message(self):
        payload = SalesCallbackPayload(
            session_id="abc",
            client_message="  Please call about API integration.  ",
        )

        self.assertEqual(payload.client_message, "Please call about API integration.")

    def test_callback_payload_keeps_old_payloads_compatible(self):
        payload = SalesCallbackPayload(session_id="abc")

        self.assertEqual(payload.client_message, "")

    def test_callback_dashboard_row_includes_client_message(self):
        requested_at = datetime(2026, 8, 2, 10, 30, tzinfo=UTC)
        callback = SimpleNamespace(
            id=uuid4(),
            requested_at=requested_at,
            contacted_at=None,
            status="pending",
            client_slug="jormall-central-e-commerce-co-ltd",
            client_message="<script>alert(1)</script>",
        )
        lead = SimpleNamespace(name="Test User", phone="0791234567")

        row = format_callback_row(callback, lead)

        self.assertEqual(row["client_message"], "<script>alert(1)</script>")

    def test_final_starter_labels_and_action_types(self):
        config = load_client_config("jormall-central-e-commerce-co-ltd")
        items = config.starter_question_items

        self.assertEqual(items[0]["label_en"], "What are the uses of Service SMS?")
        self.assertEqual(items[0]["label_ar"], "ما استخدامات رسائل الخدمة؟")
        self.assertEqual(items[0]["type"], "question")
        self.assertEqual(items[1]["type"], "question")
        self.assertEqual(items[2]["id"], "contact_us")
        self.assertEqual(items[2]["type"], "contact_us")
        self.assertEqual(items[2]["label_en"], "Contact us")
        self.assertEqual(items[2]["label_ar"], "تواصل معنا")
        self.assertEqual(items[3]["id"], "request_sales_callback")
        self.assertEqual(items[3]["type"], "request_sales_callback")
        self.assertEqual(items[3]["label_en"], "Request a sales callback")
        self.assertEqual(items[3]["label_ar"], "طلب اتصال من فريق المبيعات")

    def test_explicit_arabic_starter_labels_are_preserved_by_normalization(self):
        items = normalize_starter_question_items(
            suggested_questions=None,
            starter_question_items=[
                {
                    "id": "contact_us",
                    "type": "contact_us",
                    "label_en": "Contact us",
                    "label_ar": "تواصل معنا",
                }
            ],
        )

        self.assertEqual(items[0]["label_ar"], "تواصل معنا")
        self.assertEqual(items[0]["type"], "contact_us")

    def test_callback_starter_does_not_submit_rag_question(self):
        source = CHAT_JS.read_text(encoding="utf-8")

        self.assertIn("if (isSalesCallbackStarterItem(item))", source)
        self.assertIn("showSalesCallbackConfirmation", source)
        self.assertIn("return;", source)

    def test_contact_starter_does_not_submit_rag_or_callback(self):
        source = CHAT_JS.read_text(encoding="utf-8")
        contact_branch = source.split("if (isContactStarterItem(item))", 1)[1].split("submitQuestion", 1)[0]

        self.assertIn("appendContactCard", contact_branch)
        self.assertIn("return;", contact_branch)
        self.assertNotIn("sendMessage", contact_branch)
        self.assertNotIn("submitSalesCallbackRequest", contact_branch)

    def test_first_starter_question_continues_through_rag(self):
        source = CHAT_JS.read_text(encoding="utf-8")
        normal_branch = source.split("if (isContactStarterItem(item))", 1)[1]

        self.assertIn("submitQuestion(item.label", normal_branch)
        self.assertIn("sendMessage(question, options)", source)

    def test_phone_number_isolation_is_configured(self):
        source = CHAT_JS.read_text(encoding="utf-8")
        css = CHAT_CSS.read_text(encoding="utf-8")

        self.assertIn("PHONE_NUMBER_PATTERN", source)
        self.assertIn("appendPhoneIsolatedText", source)
        self.assertIn('element.dir = "ltr"', source)
        self.assertIn("unicode-bidi: isolate", css)

    def test_contact_card_uses_configured_contact_details_and_safe_links(self):
        config = load_client_config("jormall-central-e-commerce-co-ltd")
        source = CHAT_JS.read_text(encoding="utf-8")

        self.assertEqual(config.contact_details["email"], "info@jormall.com")
        self.assertEqual(config.contact_details["customer_service_phone"], "+962 7 7544 4418")
        self.assertEqual(config.contact_details["telephone"], "+962 6 582 3961")
        self.assertIn("chatbotConfig.contactDetails", source)
        self.assertIn("mailto:", source)
        self.assertIn("telHref(customerServicePhone)", source)
        self.assertIn("telHref(telephone)", source)
        self.assertIn("phone: true", source)
        self.assertIn("textContent", source)

    def test_dashboard_message_rendering_uses_text_content(self):
        source = DASHBOARD_JS.read_text(encoding="utf-8")

        self.assertIn("messageCell.textContent = request.client_message", source)
        self.assertIn("val.textContent = value", source)

    def test_callback_duplicate_submission_is_prevented(self):
        source = CHAT_JS.read_text(encoding="utf-8")

        self.assertIn("confirmButton.disabled", source)
        self.assertIn("hasPendingSalesCallback", source)
        self.assertIn("isWaitingForResponse || isLeadGateOpen || hasPendingSalesCallback", source)

    def test_ingestion_dry_run_preserves_existing_records(self):
        with SessionLocal() as db:
            before = preservation_counts(db)

        exit_code = ingest_main([
            "--source-dir",
            str(DEFAULT_SOURCE_DIR),
            "--dry-run",
            "--skip-embeddings",
        ])

        with SessionLocal() as db:
            after = preservation_counts(db)

        self.assertEqual(exit_code, 0)
        self.assertEqual(before, after)

    def test_duplicate_ingestion_does_not_duplicate_chunks_or_embeddings(self):
        filename = f"codex-ingestion-regression-{uuid4().hex}.txt"
        with TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / filename
            source_path.write_text(
                "JorMall regression ingestion document.\n\n"
                "Service SMS can be used for customer notifications and OTP messages.",
                encoding="utf-8",
            )

            try:
                first_exit = ingest_main([
                    "--source-dir",
                    temp_dir,
                    "--skip-embeddings",
                ])
                with SessionLocal() as db:
                    after_first = preservation_counts(db)

                second_exit = ingest_main([
                    "--source-dir",
                    temp_dir,
                    "--skip-embeddings",
                ])
                with SessionLocal() as db:
                    after_second = preservation_counts(db)

                self.assertEqual(first_exit, 0)
                self.assertEqual(second_exit, 0)
                self.assertEqual(after_first, after_second)
            finally:
                with SessionLocal() as db:
                    document_ids = [
                        row[0]
                        for row in db.execute(
                            select(Document.id).where(Document.original_filename == filename)
                        ).all()
                    ]
                    if document_ids:
                        db.execute(
                            delete(DocumentChunk).where(
                                DocumentChunk.document_id.in_(document_ids)
                            )
                        )
                        db.execute(delete(Document).where(Document.id.in_(document_ids)))
                        db.commit()

    def test_ingestion_failure_returns_non_zero_status(self):
        exit_code = ingest_main([
            "--source-dir",
            str(PROJECT_ROOT / "does-not-exist"),
            "--dry-run",
            "--skip-embeddings",
        ])

        self.assertNotEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
