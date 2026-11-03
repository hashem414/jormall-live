from __future__ import annotations

import json
import unittest
import urllib.parse
from pathlib import Path
from unittest.mock import patch

from app.services.deepgram_service import (
    DEEPGRAM_KEYTERMS,
    DeepgramTranscriptionError,
    deepgram_listen_query,
    normalize_audio_content_type,
    normalize_transcript_text,
    parse_deepgram_response,
    provider_language_for,
    transcribe_bilingual_audio,
    TranscriptionResult,
)
from app.services.deepgram_voice_agent_service import (
    build_agent_settings,
    deepgram_speak_provider,
    deepgram_voice_provider_name,
    prepare_deepgram_speech,
)
from app.services.openai_client import model_response_controls
from app.services.openai_speech_service import (
    TRANSCRIPTION_CONTEXT,
    detect_transcript_language,
)
from app.services.chat_service import question_requests_comprehensive_answer
from app.api.public_chat import (
    compact_voice_answer,
    compact_voice_stream_line,
    encode_event,
)
from app.services.chat_stream_service import (
    language_preference_answer,
    normalize_repeated_question,
    repeated_answer_from_history,
    yield_reused_answer,
)
from app.schemas.chat import ChatHistoryTurn
from app.services.answer_safety_service import greeting_only_answer


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DeepgramVoiceAssuranceTests(unittest.TestCase):
    def test_nova_3_has_company_and_bilingual_domain_keyterms(self) -> None:
        for term in ("JorMall", "Smart Reach SMS", "OTP", "جورمول", "رسائل الخدمة"):
            self.assertIn(term, DEEPGRAM_KEYTERMS)

    def test_bilingual_language_mapping_is_explicit(self) -> None:
        self.assertEqual(provider_language_for("en"), "en")
        self.assertEqual(provider_language_for("ar"), "ar-JO")
        with self.assertRaises(ValueError):
            provider_language_for("multi")

    def test_listen_query_preserves_complete_natural_utterances(self) -> None:
        query = urllib.parse.parse_qs(deepgram_listen_query("ar"))
        self.assertEqual(query["language"], ["ar-JO"])
        self.assertEqual(query["utterances"], ["true"])
        self.assertEqual(query["utt_split"], ["1.0"])
        self.assertEqual(query["filler_words"], ["true"])

    def test_safari_and_chromium_content_types_are_normalized(self) -> None:
        self.assertEqual(normalize_audio_content_type("audio/mp4"), "audio/mp4")
        self.assertEqual(
            normalize_audio_content_type("audio/webm;codecs=opus"),
            "audio/webm",
        )

    def test_provider_response_is_bounded_and_does_not_return_credentials(self) -> None:
        result = parse_deepgram_response(
            {
                "metadata": {"request_id": "request-123"},
                "results": {
                    "channels": [{"alternatives": [{
                        "transcript": "كم تبلغ تكلفة الشات بوت؟",
                        "confidence": 0.97,
                    }]}]
                },
            },
            requested_language="ar",
        )
        self.assertEqual(result.transcript, "كم تبلغ تكلفة الشات بوت؟")
        self.assertEqual(result.provider_language, "ar-JO")
        self.assertEqual(result.request_id, "request-123")
        self.assertFalse(hasattr(result, "api_key"))

    def test_empty_provider_transcript_is_rejected(self) -> None:
        with self.assertRaises(DeepgramTranscriptionError):
            parse_deepgram_response(
                {"results": {"channels": [{"alternatives": [{"transcript": ""}]}]}},
                requested_language="en",
            )

    def test_bilingual_selection_can_override_wrong_ui_language(self) -> None:
        results = {
            "en": TranscriptionResult("Giffardak", 0.42, "en", "en", "en-id"),
            "ar": TranscriptionResult("كيف حالك؟", 0.94, "ar", "ar-JO", "ar-id"),
        }
        with patch(
            "app.services.deepgram_service.transcribe_audio",
            side_effect=lambda audio, content_type, language: results[language],
        ):
            selected = transcribe_bilingual_audio(
                b"audio",
                content_type="audio/webm",
                preferred_language="en",
            )
        self.assertEqual(selected.requested_language, "ar")
        self.assertEqual(selected.transcript, "كيف حالك؟")

    def test_arabic_beats_false_english_transliteration(self) -> None:
        results = {
            "en": TranscriptionResult("Shuhedmetakum.", 0.72, "en", "en", "en-id"),
            "ar": TranscriptionResult("شو خدماتكم؟", 0.67, "ar", "ar-JO", "ar-id"),
        }
        with patch(
            "app.services.deepgram_service.transcribe_audio",
            side_effect=lambda audio, content_type, language: results[language],
        ):
            selected = transcribe_bilingual_audio(
                b"audio",
                content_type="audio/webm",
                preferred_language="en",
            )
        self.assertEqual(selected.requested_language, "ar")
        self.assertEqual(selected.transcript, "شو خدماتكم؟")

    def test_arabic_asr_typography_is_normalized_without_rewriting_meaning(self) -> None:
        self.assertEqual(normalize_transcript_text("مِنْ جُورْ-مُولٍ؟"), "مين جورمول؟")
        self.assertEqual(normalize_transcript_text("شوخدماتكم؟"), "شو خدماتكم؟")
        self.assertEqual(normalize_transcript_text("Jor Mall"), "JorMall")

    def test_opening_asr_echo_is_removed_without_touching_later_repetition(self) -> None:
        self.assertEqual(
            normalize_transcript_text("كم كم سعر الشات بوت مهم مهم"),
            "كم سعر الشات بوت مهم مهم",
        )


class ModelCompatibilityTests(unittest.TestCase):
    def test_gpt_4o_mini_does_not_receive_gpt5_only_controls(self) -> None:
        self.assertEqual(model_response_controls(model="gpt-4o-mini", verbosity="low"), {})

    def test_gpt5_keeps_reasoning_and_verbosity_controls(self) -> None:
        controls = model_response_controls(model="gpt-5.6-sol", verbosity="low")
        self.assertIn("reasoning", controls)
        self.assertIn("text", controls)

    def test_luna_keeps_gpt56_response_controls(self) -> None:
        controls = model_response_controls(model="gpt-5.6-luna", verbosity="low")
        self.assertIn("reasoning", controls)
        self.assertIn("text", controls)


class RepeatedAnswerConsistencyTests(unittest.TestCase):
    def test_arabic_spelling_and_punctuation_variants_share_a_key(self) -> None:
        self.assertEqual(
            normalize_repeated_question("مَا هي أسعار الاستضافة؟"),
            normalize_repeated_question("ما هي اسعار الاستضافة"),
        )

    def test_latest_answer_is_reused_verbatim_for_same_question(self) -> None:
        history = [
            ChatHistoryTurn(role="user", content="ما هي أسعار الاستضافة؟"),
            ChatHistoryTurn(role="assistant", content="الإجابة المعتمدة نفسها."),
        ]
        self.assertEqual(
            repeated_answer_from_history("ما هي اسعار الاستضافة", history),
            "الإجابة المعتمدة نفسها.",
        )

    def test_different_question_does_not_reuse_an_answer(self) -> None:
        history = [
            ChatHistoryTurn(role="user", content="ما هي أسعار الاستضافة؟"),
            ChatHistoryTurn(role="assistant", content="تفاصيل الاستضافة."),
        ]
        self.assertIsNone(repeated_answer_from_history("ما هي خدماتكم؟", history))

    def test_reused_answer_does_not_claim_a_new_model_call(self) -> None:
        events = [json.loads(line) for line in yield_reused_answer(answer="Same answer")]
        self.assertEqual(events[0]["answer"], "Same answer")
        self.assertFalse(events[-1]["model_called"])
        self.assertTrue(events[-1]["reused_answer"])

class DeepgramVoiceAgentTests(unittest.TestCase):
    def test_arabic_uses_pinned_cartesia_sonic_3_6_through_deepgram(self) -> None:
        provider = deepgram_speak_provider("ar")
        self.assertEqual(provider["type"], "cartesia")
        self.assertEqual(provider["model_id"], "sonic-3.6")
        self.assertEqual(provider["language"], "ar")
        self.assertEqual(provider["voice"]["mode"], "id")
        self.assertTrue(provider["voice"]["id"])
        self.assertGreater(provider["speed"], 1.0)

    def test_english_uses_pinned_deepgram_flux_voice(self) -> None:
        provider = deepgram_speak_provider("en")
        self.assertEqual(provider["type"], "deepgram")
        self.assertEqual(provider["version"], "v2")
        self.assertEqual(provider["model"], "flux-kit-en")
        self.assertEqual(deepgram_voice_provider_name("en"), "deepgram-flux")
        self.assertEqual(deepgram_voice_provider_name("ar"), "deepgram-agent-cartesia")

    def test_agent_audio_settings_contain_no_openai_provider(self) -> None:
        for language in ("ar", "en"):
            rendered = json.dumps(build_agent_settings(language))
            self.assertNotIn("open_ai", rendered)
            self.assertNotIn("openai", rendered.lower())

    def test_speech_input_is_bounded_and_bilingual(self) -> None:
        self.assertEqual(prepare_deepgram_speech(text="  مرحبا  ", language="ar"), ("مرحبا", "ar"))
        with self.assertRaises(ValueError):
            prepare_deepgram_speech(text="hello", language="fr")


class MultilingualTranscriptionTests(unittest.TestCase):
    def test_transcription_context_covers_dialect_and_company_vocabulary(self) -> None:
        for term in ("Jordanian", "Levantine", "مين جورمول", "شو خدماتكم", "Service Messages"):
            self.assertIn(term, TRANSCRIPTION_CONTEXT)

    def test_arabic_script_overrides_english_ui_preference(self) -> None:
        self.assertEqual(
            detect_transcript_language("مرحبا، كيف حالك؟", preferred_language="en"),
            "ar",
        )

    def test_english_script_overrides_arabic_ui_preference(self) -> None:
        self.assertEqual(
            detect_transcript_language("Hello, how are you?", preferred_language="ar"),
            "en",
        )

    def test_neutral_transcript_keeps_ui_preference(self) -> None:
        self.assertEqual(
            detect_transcript_language("150", preferred_language="ar"),
            "ar",
        )

    def test_natural_company_questions_request_complete_voice_answers(self) -> None:
        for question in (
            "Who is JorMall?",
            "What does JorMall do?",
            "مين جورمول؟",
            "شو بتعمل جورمول؟",
            "احكيلي عن جورمول",
        ):
            with self.subTest(question=question):
                self.assertTrue(question_requests_comprehensive_answer(question))


class VoiceFrontendContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.template = (PROJECT_ROOT / "app/templates/chat.html").read_text()
        cls.javascript = (PROJECT_ROOT / "app/static/js/chat.js").read_text()
        cls.public_api = (PROJECT_ROOT / "app/api/public_chat.py").read_text()

    def test_frontend_has_one_accessible_circular_voice_control(self) -> None:
        self.assertEqual(self.template.count('id="voice-button"'), 1)
        self.assertIn('aria-pressed="false"', self.template)
        self.assertIn('class="voice-button"', self.template)

    def test_header_has_secure_clickable_phone_and_email_controls(self) -> None:
        self.assertEqual(self.template.count('href="tel:+962775444436"'), 1)
        self.assertEqual(self.template.count('href="mailto:info@jormall.com"'), 1)
        self.assertEqual(self.template.count('class="header-contact-link"'), 2)
        self.assertIn('data-i18n-aria-label="callCompany"', self.template)
        self.assertIn('data-i18n-aria-label="emailCompany"', self.template)

    def test_voice_mode_has_embedded_interactive_orb(self) -> None:
        self.assertEqual(self.template.count('id="voice-experience"'), 1)
        self.assertEqual(self.template.count('id="voice-orb-button"'), 1)
        self.assertIn('aria-labelledby="voice-experience-title"', self.template)
        self.assertIn('data-i18n="voiceDisclosure"', self.template)

    def test_audio_uses_server_endpoint_and_existing_chat_send_path(self) -> None:
        self.assertIn('formData.append("audio"', self.javascript)
        self.assertIn("chatbotConfig.voiceTranscribeEndpoint", self.javascript)
        self.assertIn("await sendMessage(transcript", self.javascript)
        self.assertNotIn("deepgram_api_key", self.javascript.lower())
        self.assertNotIn("Authorization", self.javascript)
        self.assertIn("transcribe_audio", self.public_api)
        self.assertNotIn("transcribe_bilingual_audio", self.public_api)
        self.assertNotIn("openai_speech_service", self.public_api)

    def test_final_voice_streams_deepgram_audio_with_browser_fallback(self) -> None:
        self.assertIn("new SpeechSynthesisUtterance(cleanText)", self.javascript)
        self.assertIn("chatbotConfig.voiceSpeechEndpoint", self.javascript)
        self.assertIn("response.body.getReader()", self.javascript)
        self.assertIn("speech_generation_failed", self.javascript)
        self.assertIn("stream_deepgram_speech", self.public_api)
        self.assertNotIn("openai_speech_service", self.public_api)

    def test_recorder_emits_one_complete_container_for_transcription(self) -> None:
        self.assertIn("mediaRecorder.start();", self.javascript)
        self.assertNotIn("mediaRecorder.start(250)", self.javascript)

    def test_recorder_protects_opening_and_final_words(self) -> None:
        self.assertIn('setVoiceExperienceState("warming")', self.javascript)
        self.assertIn("audioBitsPerSecond: 128000", self.javascript)
        self.assertIn("voiceStopPending", self.javascript)
        self.assertIn("}, 300);", self.javascript)
        self.assertLess(
            self.javascript.index('"audio/webm;codecs=opus"'),
            self.javascript.index('"audio/mp4"'),
        )

    def test_safari_playback_is_unlocked(self) -> None:
        self.assertIn("function primeVoicePlayback()", self.javascript)
        self.assertIn('voiceAudioContext.state !== "running"', self.javascript)
        self.assertIn("window.speechSynthesis.resume()", self.javascript)

    def test_browser_tts_prefers_jordanian_arabic_and_only_speaks_final_answer(self) -> None:
        self.assertIn('["majed", "maged", "tarik"', self.javascript)
        self.assertIn("speakAssistantAnswer(\n                    finalAssistantAnswer", self.javascript)
        self.assertNotIn("speakAssistantAnswer(event.message", self.javascript)

    def test_voice_turns_send_voice_mode_and_keep_page_language(self) -> None:
        self.assertIn('input_mode: options.voiceReply ? "voice" : "text"', self.javascript)
        self.assertIn('const voiceLanguage = language === "ar" ? "ar" : "en"', self.javascript)
        self.assertNotIn("updateLanguage(detectedLanguage)", self.javascript)


class VoiceResponseBehaviorTests(unittest.TestCase):
    def test_long_direct_answers_are_compacted_for_voice(self) -> None:
        answer = "First direct fact. Second useful detail. Third unnecessary detail. " * 8
        compact = compact_voice_answer(answer)
        self.assertLessEqual(len(compact), 280)
        self.assertNotIn("Third unnecessary detail", compact)

    def test_pricing_and_hosting_voice_answers_are_not_compacted(self) -> None:
        long_answer = "Hosting detail. " * 40
        line = compact_voice_stream_line(
            encode_event({"type": "replace", "answer": long_answer}),
            question="How much are the hosting packages?",
        )
        self.assertEqual(json.loads(line)["answer"], long_answer)

    def test_broad_company_and_service_voice_answers_are_not_compacted(self) -> None:
        long_answer = "Approved company detail. " * 40
        for question in (
            "Tell me fully about JorMall and what the company does.",
            "List all of JorMall's SMS products.",
            "اشرح رسائل الخدمة بالكامل مع جميع متطلبات الامتثال والاستخدامات.",
        ):
            with self.subTest(question=question):
                line = compact_voice_stream_line(
                    encode_event({"type": "replace", "answer": long_answer}),
                    question=question,
                )
                self.assertEqual(json.loads(line)["answer"], long_answer)

    def test_language_switch_requests_get_natural_bilingual_answers(self) -> None:
        self.assertTrue(language_preference_answer("Speak in Arabic").startswith("بالتأكيد"))
        self.assertTrue(language_preference_answer("احكي معي بالإنجليزية").startswith("Of course"))

    def test_compound_english_greeting_is_answered_without_clarification(self) -> None:
        self.assertEqual(
            greeting_only_answer("Hello. How are you? Okay."),
            "Hello! Welcome to JorMall. How can I help you today?",
        )

    def test_compound_arabic_greeting_handles_arabic_question_mark(self) -> None:
        self.assertEqual(
            greeting_only_answer("مرحبا، كيف حالك؟"),
            "مرحباً! أهلاً وسهلاً بك في JorMall. كيف يمكنني مساعدتك اليوم؟",
        )


if __name__ == "__main__":
    unittest.main()
