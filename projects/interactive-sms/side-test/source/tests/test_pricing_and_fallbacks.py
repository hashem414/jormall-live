import os
import unittest


os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://jormall_user:REDACTED_CONFIGURE_LOCALLY@postgres:5432/jormall_chatbot",
)
os.environ.setdefault("CALLBACK_DASHBOARD_PASSWORD", "test-password")

from app.api.public_chat import LeadCapturePayload, stream_done_error_state_from_line, update_streamed_answer
from app.core.config import Settings
from app.services.answer_safety_service import (
    OLD_UNAVAILABLE_MESSAGES,
    business_generation_fallback,
    combine_partial_answer_with_graceful_fallback,
    deterministic_pricing_answer,
    graceful_closing_fallback,
)


class PricingIntentTests(unittest.TestCase):
    def test_greeting_only_returns_natural_greeting(self):
        answer = deterministic_pricing_answer("Hello")
        self.assertEqual(answer, "Hello! Welcome to JorMall. How can I help you today?")
        self.assertNotIn("A New Generation of SMS Communication", answer)

    def test_greeting_variants_return_natural_greeting(self):
        for prompt in ("Hello!", "hi", "good morning", "hello there", "how are you?", "👋 hello"):
            with self.subTest(prompt=prompt):
                self.assertEqual(
                    deterministic_pricing_answer(prompt),
                    "Hello! Welcome to JorMall. How can I help you today?",
                )

    def test_arabic_greetings_return_natural_greeting(self):
        expected = "\u0645\u0631\u062d\u0628\u0627\u064b! \u0623\u0647\u0644\u0627\u064b \u0648\u0633\u0647\u0644\u0627\u064b \u0628\u0643 \u0641\u064a JorMall. \u0643\u064a\u0641 \u064a\u0645\u0643\u0646\u0646\u064a \u0645\u0633\u0627\u0639\u062f\u062a\u0643 \u0627\u0644\u064a\u0648\u0645\u061f"
        for prompt in ("\u0645\u0631\u062d\u0628\u0627", "\u0623\u0647\u0644\u0627\u064b", "\u0643\u064a\u0641\u0643\u061f"):
            with self.subTest(prompt=prompt):
                self.assertEqual(deterministic_pricing_answer(prompt), expected)

    def test_arabic_salam_returns_specific_greeting(self):
        self.assertEqual(
            deterministic_pricing_answer("\u0627\u0644\u0633\u0644\u0627\u0645 \u0639\u0644\u064a\u0643\u0645"),
            "\u0648\u0639\u0644\u064a\u0643\u0645 \u0627\u0644\u0633\u0644\u0627\u0645 \u0648\u0631\u062d\u0645\u0629 \u0627\u0644\u0644\u0647 \u0648\u0628\u0631\u0643\u0627\u062a\u0647! \u0623\u0647\u0644\u0627\u064b \u0648\u0633\u0647\u0644\u0627\u064b \u0628\u0643 \u0641\u064a JorMall. \u0643\u064a\u0641 \u064a\u0645\u0643\u0646\u0646\u064a \u0645\u0633\u0627\u0639\u062f\u062a\u0643 \u0627\u0644\u064a\u0648\u0645\u061f",
        )

    def test_greeting_plus_pricing_keeps_substantive_answer(self):
        answer = deterministic_pricing_answer("Hi, chatbot price")
        self.assertTrue(answer.startswith("Hello! "))
        self.assertIn("JOD 150 plus applicable sales tax", answer)
        self.assertNotIn("JOD 100", answer)

    def test_arabic_sms_pricing_does_not_return_chatbot_price(self):
        answer = deterministic_pricing_answer("كم اسعار ال sms")
        self.assertIn("أسعار رسائل SMS تختلف", answer)
        self.assertIn("للحصول على أسعار وباقات SMS", answer)
        self.assertNotIn("JOD 150", answer)
        self.assertNotIn("دينار أردني", answer)

    def test_arabic_chatbot_pricing_returns_new_price(self):
        answer = deterministic_pricing_answer("كم سعر الشات بوت؟")
        self.assertIn("150 دينار أردني", answer)
        self.assertIn("شهر واحد", answer)
        self.assertIn("200 دينار", answer)
        self.assertIn("يوم عمل واحد", answer)
        self.assertNotIn("30 صفحة", answer)

    def test_english_chatbot_pricing_returns_new_price(self):
        answer = deterministic_pricing_answer("chatbot price")
        self.assertIn("JOD 150 plus applicable sales tax", answer)
        self.assertIn("1 month: JOD 30", answer)
        self.assertIn("12 months: JOD 200", answer)
        self.assertIn("one working day", answer)
        self.assertNotIn("up to 30 pages", answer)

    def test_hosting_overview_returns_all_packages_and_renewal_terms(self):
        answer = deterministic_pricing_answer("Tell me about hosting")
        self.assertIn("one month of hosting", answer)
        self.assertIn("1 month: JOD 30", answer)
        self.assertIn("3 months: JOD 75", answer)
        self.assertIn("6 months: JOD 140", answer)
        self.assertIn("12 months: JOD 200", answer)
        self.assertIn("renewed before expiry", answer)

    def test_arabic_hosting_overview_returns_all_packages(self):
        answer = deterministic_pricing_answer("ما هي باقات الاستضافة؟")
        self.assertIn("شهر واحد", answer)
        self.assertIn("3 أشهر: 75 ديناراً", answer)
        self.assertIn("12 شهراً: 200 ديناراً", answer)
        self.assertIn("تجديد الباقة", answer)

    def test_otp_international_and_whatsapp_do_not_return_chatbot_price(self):
        for prompt in (
            "OTP price",
            "international SMS price",
            "WhatsApp API price",
        ):
            answer = deterministic_pricing_answer(prompt)
            self.assertIsNotNone(answer)
            self.assertNotIn("JOD 150", answer)
            self.assertNotIn("JOD 75", answer)

    def test_mixed_services_uses_chatbot_price_only_in_chatbot_part(self):
        answer = deterministic_pricing_answer(
            "I need SMS inside Jordan, international SMS, API, OTP, chatbot and WhatsApp API. What do you recommend?"
        )
        self.assertIn("SMS inside Jordan", answer)
        self.assertIn("International SMS", answer)
        self.assertIn("API integration", answer)
        self.assertIn("OTP messages", answer)
        self.assertIn("Chatbot", answer)
        self.assertIn("WhatsApp API", answer)
        self.assertEqual(answer.count("JOD 150"), 1)


class FallbackTests(unittest.TestCase):
    def test_failure_before_output_returns_business_fallbacks(self):
        self.assertIn("JorMall can assist", business_generation_fallback("SMS and OTP help"))
        self.assertIn("يسعدنا مساعدتك", business_generation_fallback("رسائل و OTP"))

    def test_partial_output_gets_one_graceful_fallback(self):
        partial = "JorMall can help you review SMS needs by destination and volume."
        combined = combine_partial_answer_with_graceful_fallback("SMS help", partial)
        self.assertTrue(combined.startswith(partial))
        self.assertEqual(combined.count(graceful_closing_fallback("SMS help")), 1)
        combined_again = combine_partial_answer_with_graceful_fallback("SMS help", combined)
        self.assertEqual(combined_again.count(graceful_closing_fallback("SMS help")), 1)

    def test_old_unavailable_messages_are_not_in_fallbacks(self):
        combined = combine_partial_answer_with_graceful_fallback("SMS help", "Useful answer.")
        fallback = business_generation_fallback("SMS help")
        for old_message in OLD_UNAVAILABLE_MESSAGES:
            self.assertNotIn(old_message, combined)
            self.assertNotIn(old_message, fallback)

    def test_stream_helpers_accumulate_visible_answer_and_private_error_state(self):
        answer = update_streamed_answer("", '{"type":"delta","text":"Useful"}')
        answer = update_streamed_answer(answer, '{"type":"delta","text":" answer."}')
        error_state = stream_done_error_state_from_line(
            '{"type":"done","error_state":"partial_generation_error"}'
        )
        self.assertEqual(answer, "Useful answer.")
        self.assertEqual(error_state, "partial_generation_error")


class ConfigTests(unittest.TestCase):
    def test_chat_max_output_tokens_accepts_2000(self):
        settings = Settings(
            database_url="postgresql+psycopg://example:REDACTED_CONFIGURE_LOCALLY@localhost:5432/example",
            chat_max_output_tokens=2000,
        )
        self.assertEqual(settings.chat_max_output_tokens, 2000)


class LeadCapturePayloadTests(unittest.TestCase):
    def valid_payload(self) -> dict[str, object]:
        return {
            "session_id": "lead-session-1",
            "chat_session_id": "chat-session-1",
            "name": "JorMall QA",
            "phone": "0791234567",
            "cookie_notice_opened": True,
            "privacy_notice_opened": True,
        }

    def test_company_name_is_not_required(self):
        payload = LeadCapturePayload(**self.valid_payload())
        self.assertEqual(payload.name, "JorMall QA")
        self.assertEqual(payload.phone, "0791234567")

    def test_legacy_company_name_field_is_ignored(self):
        data = self.valid_payload()
        data["company_name"] = "Legacy Company"
        payload = LeadCapturePayload(**data)
        self.assertFalse(hasattr(payload, "company_name"))


if __name__ == "__main__":
    unittest.main()
