from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from app.services.chat_service import (
    PRICING_FALLBACK_AR,
    PRICING_FALLBACK_EN,
    SALES_CALLBACK_ACTION_LABELS,
    SALES_CALLBACK_ACTION_MARKER,
    UNWANTED_PRICING_QUALIFICATION_TEXT,
    approved_documented_pricing_answer,
    looks_like_pricing_request,
    pricing_response_with_callback_action,
)
from app.services.chat_stream_service import stream_grounded_chat
from app.services.client_config_service import load_client_config
from app.services.retrieval_service import RetrievedChunk


CLIENT_SLUG = "jormall-central-e-commerce-co-ltd"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def fake_chunk(content: str, metadata: dict | None = None) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_title="Approved Pricing Test",
        original_filename="approved-pricing.txt",
        language="en",
        section_title="Pricing",
        source_reference="approved-pricing.txt",
        content=content,
        similarity=0.99,
        metadata=metadata or {},
        client_slug=CLIENT_SLUG,
    )


class PricingPolicyTests(unittest.TestCase):
    def test_english_pricing_examples_trigger_intent(self):
        for question in [
            "What are your prices?",
            "How much does SMS cost?",
            "I need a quotation",
            "What does the API cost?",
            "How much is OTP SMS?",
            "How much does ACR cost?",
            "What are your platform fees?",
            "What are your rates?",
        ]:
            with self.subTest(question=question):
                self.assertTrue(looks_like_pricing_request(question))

    def test_arabic_pricing_examples_trigger_intent(self):
        for question in [
            "ما هي الأسعار؟",
            "كم سعر الرسالة؟",
            "أريد عرض سعر",
            "كم تكلفة الربط مع API؟",
            "كم سعر رسائل OTP؟",
            "كم تكلفة خدمة ACR؟",
            "ما هي رسوم المنصة؟",
        ]:
            with self.subTest(question=question):
                self.assertTrue(looks_like_pricing_request(question))

    def test_generic_pricing_fallback_is_concise_english_with_callback_action(self):
        answer = pricing_response_with_callback_action(
            question="What are your prices?",
            language="en",
        )

        self.assertIn(PRICING_FALLBACK_EN, answer)
        self.assertEqual(answer.count(SALES_CALLBACK_ACTION_MARKER), 1)
        self.assertNotIn(UNWANTED_PRICING_QUALIFICATION_TEXT, answer)
        for forbidden in [
            "company name",
            "business sector",
            "monthly SMS volume",
            "preferred contact information",
            "API requirements",
            "OTP volume",
            "number of users",
            "ACR configuration",
        ]:
            self.assertNotIn(forbidden, answer)

    def test_generic_pricing_fallback_is_concise_arabic_with_callback_action(self):
        answer = pricing_response_with_callback_action(
            question="ما هي الأسعار؟",
            language="ar",
        )

        self.assertIn(PRICING_FALLBACK_AR, answer)
        self.assertEqual(answer.count(SALES_CALLBACK_ACTION_MARKER), 1)
        self.assertNotIn("اسم الشركة", answer)
        self.assertNotIn("قطاع العمل", answer)
        self.assertNotIn("حجم الرسائل", answer)

    def test_approved_documented_pricing_requires_explicit_approved_marker(self):
        config = load_client_config(CLIENT_SLUG)
        unmarked_chunk = fake_chunk("Setup fee is JOD 99.")

        self.assertIsNone(
            approved_documented_pricing_answer(
                question="What is the setup fee?",
                chunks=[unmarked_chunk],
                config=config,
                language="en",
            )
        )

    def test_approved_documented_pricing_is_returned_when_explicitly_available(self):
        config = load_client_config(CLIENT_SLUG)
        marked_chunk = fake_chunk(
            "Current approved price: Service SMS setup fee is JOD 25, excluding applicable taxes. "
            "The approved offer is valid until 2026-09-30.",
            metadata={"pricing_status": "approved"},
        )

        answer = approved_documented_pricing_answer(
            question="What is the setup fee?",
            chunks=[marked_chunk],
            config=config,
            language="en",
        )

        self.assertIsNotNone(answer)
        self.assertIn("JOD 25", answer or "")
        self.assertIn("excluding applicable taxes", answer or "")
        self.assertEqual((answer or "").count(SALES_CALLBACK_ACTION_MARKER), 1)

    def test_streaming_pricing_fallback_uses_policy_and_no_model(self):
        with patch("app.services.chat_stream_service.prepare_streaming_plan", return_value=None), patch(
            "app.services.chat_stream_service.get_openai_client"
        ) as openai_client:
            lines = list(
                stream_grounded_chat(
                    question="What are your prices?",
                    history=[],
                    evidence_history=[],
                    db=SimpleNamespace(),
                    client_slug=CLIENT_SLUG,
                    response_language="en",
                )
            )

        openai_client.assert_not_called()
        events = [json.loads(line) for line in lines if line.strip()]
        replace_events = [event for event in events if event.get("type") == "replace"]
        action_events = [event for event in events if event.get("type") == "action"]
        self.assertEqual(len(replace_events), 1)
        answer = replace_events[0]["answer"]
        self.assertIn(PRICING_FALLBACK_EN, answer)
        self.assertNotIn(SALES_CALLBACK_ACTION_MARKER, answer)
        self.assertEqual(len(action_events), 1)
        self.assertEqual(
            action_events[0]["action"],
            {
                "type": "request_sales_callback",
                "language": "en",
                "label": SALES_CALLBACK_ACTION_LABELS["en"],
            },
        )
        self.assertFalse(replace_events[0].get("media"))

    def test_frontend_streaming_finish_renders_callback_action_once(self):
        source = (PROJECT_ROOT / "app" / "static" / "js" / "chat.js").read_text(
            encoding="utf-8"
        )

        self.assertIn('bubble.querySelector(".callback-action")', source)
        self.assertIn("state.hasSalesCallbackAction", source)
        self.assertIn("renderSalesCallbackAction(state.bubble", source)
        self.assertIn("state.responseLanguage", source)


if __name__ == "__main__":
    unittest.main()
