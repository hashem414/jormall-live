from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from app.services.chat_service import (
    ABOUT_JORMALL_ANSWER_AR,
    ABOUT_JORMALL_ANSWER_EN,
    PRICING_FALLBACK_AR,
    PRICING_FALLBACK_EN,
    SALES_CALLBACK_ACTION_LABELS,
    SALES_CALLBACK_ACTION_MARKER,
    contains_arabic,
    looks_like_pricing_request,
    pricing_response_with_callback_action,
    response_language_code,
    split_pricing_and_non_pricing,
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
        document_title="Approved Test Document",
        original_filename="test-document.txt",
        language="en",
        section_title="Services",
        source_reference="test-document.txt",
        content=content,
        similarity=0.99,
        metadata=metadata or {},
        client_slug=CLIENT_SLUG,
    )


class FakeDelta:
    type = "response.output_text.delta"

    def __init__(self, delta: str):
        self.delta = delta


class FakeResponsesStream:
    def __init__(self, answer: str):
        self.answer = answer

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def __iter__(self):
        payload = json.dumps(
            {
                "can_answer": True,
                "answer": self.answer,
                "used_source_ids": ["S1"],
            }
        )
        midpoint = max(1, len(payload) // 2)
        yield FakeDelta(payload[:midpoint])
        yield FakeDelta(payload[midpoint:])

    def get_final_response(self):
        return SimpleNamespace(
            output_parsed={
                "can_answer": True,
                "answer": self.answer,
                "used_source_ids": ["S1"],
            }
        )


class FakeOpenAIClient:
    def __init__(self, answer: str):
        self.answer = answer
        self.responses = self

    def stream(self, **kwargs):
        return FakeResponsesStream(self.answer)


class CompoundQueryDecompositionTests(unittest.TestCase):
    """Tests for split_pricing_and_non_pricing clause extraction."""

    def test_arabic_compound_pricing_and_services(self):
        pricing, non_pricing = split_pricing_and_non_pricing(
            "اعطيني الاسعار و انواع الخدمات"
        )
        self.assertTrue(pricing, "Pricing clause should be non-empty")
        self.assertEqual(non_pricing, "ما أنواع الخدمات؟")

    def test_arabic_compound_pricing_and_how_api_works(self):
        pricing, non_pricing = split_pricing_and_non_pricing(
            "أريد الأسعار وكيف يعمل API؟"
        )
        self.assertTrue(pricing)
        self.assertTrue(non_pricing)

    def test_english_compound_pricing_and_services(self):
        pricing, non_pricing = split_pricing_and_non_pricing(
            "What are your prices and what services do you provide?"
        )
        self.assertTrue(pricing)
        self.assertTrue(non_pricing)

    def test_english_compound_api_cost_and_how(self):
        pricing, non_pricing = split_pricing_and_non_pricing(
            "How much does the API cost and how does it work?"
        )
        self.assertTrue(pricing)
        self.assertTrue(non_pricing)

    def test_arabic_pricing_only(self):
        pricing, non_pricing = split_pricing_and_non_pricing("اعطيني الاسعار")
        self.assertTrue(pricing)
        self.assertFalse(non_pricing, "Non-pricing clause should be empty for pricing-only")

    def test_english_pricing_only(self):
        pricing, non_pricing = split_pricing_and_non_pricing("What are your prices?")
        self.assertTrue(pricing)
        self.assertFalse(non_pricing)

    def test_arabic_services_only(self):
        pricing, non_pricing = split_pricing_and_non_pricing("ما انواع الخدمات")
        self.assertFalse(pricing, "Pricing clause should be empty for non-pricing question")
        self.assertTrue(non_pricing)

    def test_english_services_only(self):
        pricing, non_pricing = split_pricing_and_non_pricing(
            "What services do you provide?"
        )
        self.assertFalse(pricing)
        self.assertTrue(non_pricing)


class LanguageDetectionTests(unittest.TestCase):
    """Tests for message-language detection rules."""

    def test_arabic_message_returns_arabic(self):
        self.assertEqual(response_language_code("اعطيني الاسعار"), "ar")

    def test_arabic_with_technical_terms_returns_arabic(self):
        for question in [
            "كم تكلفة API وكيف يعمل؟",
            "كم تكلفة ACR وما فائدته؟",
            "أريد معلومات عن OTP",
            "ما هي خدمات JorMall؟",
            "كيف يعمل CRM مع SMS؟",
        ]:
            with self.subTest(question=question):
                self.assertEqual(
                    response_language_code(question), "ar",
                    f"Arabic question with technical term should return 'ar': {question}"
                )

    def test_english_message_returns_english(self):
        self.assertEqual(response_language_code("What are your prices?"), "en")

    def test_fallback_to_interface_language(self):
        self.assertEqual(response_language_code("123", "ar"), "ar")
        self.assertEqual(response_language_code("456", "en"), "en")

    def test_fallback_default_is_english(self):
        self.assertEqual(response_language_code("789"), "en")


class PricingFallbackLanguageTests(unittest.TestCase):
    """Tests for pricing fallback language matching the message."""

    def test_arabic_pricing_returns_arabic_fallback(self):
        answer = pricing_response_with_callback_action(
            question="اعطيني الاسعار",
            language="en",
        )
        self.assertIn(PRICING_FALLBACK_AR, answer)
        self.assertNotIn(PRICING_FALLBACK_EN, answer)

    def test_english_pricing_returns_english_fallback(self):
        answer = pricing_response_with_callback_action(
            question="What are your prices?",
            language="ar",
        )
        self.assertIn(PRICING_FALLBACK_EN, answer)
        self.assertNotIn(PRICING_FALLBACK_AR, answer)

    def test_arabic_pricing_on_english_interface_still_arabic(self):
        answer = pricing_response_with_callback_action(
            question="اعطيني الاسعار",
            language="en",
        )
        self.assertIn(PRICING_FALLBACK_AR, answer)
        self.assertEqual(answer.count(SALES_CALLBACK_ACTION_MARKER), 1)


class StreamingCompoundQueryTests(unittest.TestCase):
    """Tests for compound queries through the streaming pipeline."""

    def test_arabic_pricing_only_returns_arabic_callback(self):
        with patch(
            "app.services.chat_stream_service.prepare_streaming_plan",
            return_value=None,
        ), patch("app.services.chat_stream_service.get_openai_client"):
            lines = list(
                stream_grounded_chat(
                    question="اعطيني الاسعار",
                    history=[],
                    evidence_history=[],
                    db=SimpleNamespace(),
                    client_slug=CLIENT_SLUG,
                    response_language="en",
                )
            )

        events = [json.loads(line) for line in lines if line.strip()]
        replace_events = [e for e in events if e.get("type") == "replace"]
        action_events = [e for e in events if e.get("type") == "action"]
        self.assertEqual(len(replace_events), 1)
        answer = replace_events[0]["answer"]
        self.assertIn(PRICING_FALLBACK_AR, answer)
        self.assertNotIn(SALES_CALLBACK_ACTION_MARKER, answer)
        self.assertEqual(len(action_events), 1)
        self.assertEqual(action_events[0]["action"]["language"], "ar")
        self.assertEqual(action_events[0]["action"]["label"], SALES_CALLBACK_ACTION_LABELS["ar"])

    def test_english_pricing_only_returns_english_callback(self):
        with patch(
            "app.services.chat_stream_service.prepare_streaming_plan",
            return_value=None,
        ), patch("app.services.chat_stream_service.get_openai_client"):
            lines = list(
                stream_grounded_chat(
                    question="What are your prices?",
                    history=[],
                    evidence_history=[],
                    db=SimpleNamespace(),
                    client_slug=CLIENT_SLUG,
                    response_language="ar",
                )
            )

        events = [json.loads(line) for line in lines if line.strip()]
        replace_events = [e for e in events if e.get("type") == "replace"]
        action_events = [e for e in events if e.get("type") == "action"]
        self.assertEqual(len(replace_events), 1)
        answer = replace_events[0]["answer"]
        self.assertIn(PRICING_FALLBACK_EN, answer)
        self.assertNotIn(SALES_CALLBACK_ACTION_MARKER, answer)
        self.assertEqual(len(action_events), 1)
        self.assertEqual(action_events[0]["action"]["language"], "en")
        self.assertEqual(action_events[0]["action"]["label"], SALES_CALLBACK_ACTION_LABELS["en"])

    def test_arabic_compound_invokes_rag_and_sends_one_action(self):
        chunk = fake_chunk("الخدمات تشمل Service SMS و SMS API و OTP و ACR.")
        services_plan = SimpleNamespace(
            context="S1: الخدمات تشمل Service SMS و SMS API و OTP و ACR.",
            source_map={"S1": chunk},
            chunks=[chunk],
        )
        with patch(
            "app.services.chat_stream_service.prepare_streaming_plan",
            side_effect=[None, services_plan],
        ) as prepare_plan, patch(
            "app.services.chat_stream_service.get_openai_client",
            return_value=FakeOpenAIClient("تشمل الخدمات Service SMS و SMS API و OTP و ACR."),
        ):
            lines = list(
                stream_grounded_chat(
                    question="اعطيني الاسعار و انواع الخدمات",
                    history=[],
                    evidence_history=[],
                    db=SimpleNamespace(),
                    client_slug=CLIENT_SLUG,
                    response_language="en",
                )
            )

        events = [json.loads(line) for line in lines if line.strip()]
        text = "".join(event.get("text", "") for event in events if event.get("type") == "delta")
        action_events = [event for event in events if event.get("type") == "action"]
        self.assertEqual(prepare_plan.call_count, 2)
        self.assertIn("أنواع الخدمات", text)
        self.assertLess(text.index("الخدمات"), text.index("الأسعار"))
        self.assertIn(PRICING_FALLBACK_AR, text)
        self.assertNotIn(SALES_CALLBACK_ACTION_MARKER, text)
        self.assertEqual(len(action_events), 1)
        self.assertEqual(action_events[0]["action"]["language"], "ar")

    def test_english_compound_invokes_rag_and_sends_one_action(self):
        chunk = fake_chunk("Services include Service SMS, SMS API, OTP SMS, and ACR.")
        services_plan = SimpleNamespace(
            context="S1: Services include Service SMS, SMS API, OTP SMS, and ACR.",
            source_map={"S1": chunk},
            chunks=[chunk],
        )
        with patch(
            "app.services.chat_stream_service.prepare_streaming_plan",
            side_effect=[None, services_plan],
        ) as prepare_plan, patch(
            "app.services.chat_stream_service.get_openai_client",
            return_value=FakeOpenAIClient("Services include Service SMS, SMS API, OTP SMS, and ACR."),
        ):
            lines = list(
                stream_grounded_chat(
                    question="What are your prices and what services do you provide?",
                    history=[],
                    evidence_history=[],
                    db=SimpleNamespace(),
                    client_slug=CLIENT_SLUG,
                    response_language="ar",
                )
            )

        events = [json.loads(line) for line in lines if line.strip()]
        text = "".join(event.get("text", "") for event in events if event.get("type") == "delta")
        action_events = [event for event in events if event.get("type") == "action"]
        self.assertEqual(prepare_plan.call_count, 2)
        self.assertIn("Services", text)
        self.assertLess(text.index("Services"), text.index("Pricing"))
        self.assertIn(PRICING_FALLBACK_EN, text)
        self.assertNotIn(SALES_CALLBACK_ACTION_MARKER, text)
        self.assertEqual(len(action_events), 1)
        self.assertEqual(action_events[0]["action"]["language"], "en")


class NoRequestACallRegressionTests(unittest.TestCase):
    """Ensures 'Request a Call' no longer appears anywhere."""

    def test_chat_js_has_no_request_a_call(self):
        source = (PROJECT_ROOT / "app" / "static" / "js" / "chat.js").read_text(
            encoding="utf-8"
        )
        self.assertNotIn(
            "Request a Call",
            source,
            "'Request a Call' (capital C) must not appear in chat.js",
        )
        self.assertNotIn(
            "Request a call",
            source,
            "'Request a call' (lowercase c) must not appear in chat.js as a callbackTitle",
        )

    def test_chat_service_has_no_request_a_call_from_sales(self):
        source = (
            PROJECT_ROOT / "app" / "services" / "chat_service.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn(
            "request a call from the sales team",
            source,
            "'request a call from the sales team' must not appear in chat_service.py",
        )
        self.assertNotIn(
            "request a call from our sales team",
            source,
            "'request a call from our sales team' must not appear in chat_service.py",
        )


class NoUpsellingSentencesTests(unittest.TestCase):
    """Ensures the ABOUT_JORMALL constants don't contain upselling text."""

    def test_about_en_no_request_a_call(self):
        self.assertNotIn("request a call", ABOUT_JORMALL_ANSWER_EN.lower())

    def test_about_ar_no_upselling_sentence(self):
        self.assertNotIn("طلب مكالمة من فريق", ABOUT_JORMALL_ANSWER_AR)

    def test_about_en_no_interested_customers(self):
        self.assertNotIn("interested customers", ABOUT_JORMALL_ANSWER_EN)

    def test_pricing_fallback_no_qualification_questions(self):
        for question, lang in [
            ("What are your prices?", "en"),
            ("ما هي الأسعار؟", "ar"),
        ]:
            answer = pricing_response_with_callback_action(
                question=question, language=lang
            )
            for forbidden in [
                "company name",
                "business sector",
                "monthly SMS volume",
                "preferred contact information",
                "حسب نوع شركتك",
                "حجم الرسائل الشهري المتوقع",
            ]:
                self.assertNotIn(
                    forbidden,
                    answer,
                    f"Pricing fallback must not contain qualification text: {forbidden}",
                )


class FrontendLanguageTrackingTests(unittest.TestCase):
    """Ensures chat.js uses response language, not interface language."""

    def test_render_callback_accepts_response_language(self):
        source = (PROJECT_ROOT / "app" / "static" / "js" / "chat.js").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "function renderSalesCallbackAction(bubble, actionOrLanguage)",
            source,
            "renderSalesCallbackAction must accept action payloads",
        )

    def test_stream_state_has_response_language(self):
        source = (PROJECT_ROOT / "app" / "static" / "js" / "chat.js").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "responseLanguage: null",
            source,
            "Stream state must initialize responseLanguage",
        )

    def test_callback_action_stores_response_language(self):
        source = (PROJECT_ROOT / "app" / "static" / "js" / "chat.js").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "actionWrapper.dataset.actionLabel = action.label",
            source,
            "Callback action wrapper must store the backend action label",
        )


if __name__ == "__main__":
    unittest.main()
