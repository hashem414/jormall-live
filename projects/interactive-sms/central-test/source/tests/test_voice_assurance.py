from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import call, patch

from app.services.soniox_speech_service import (
    SONIOX_CONTEXT,
    SonioxSpeechError,
    SonioxTranscriptionResult,
    SonioxTransportError,
    build_soniox_async_stt_config,
    build_soniox_stt_config,
    build_soniox_tts_config,
    normalize_audio_content_type,
    normalize_soniox_transcript,
    normalize_voice_language,
    parse_soniox_async_transcript,
    parse_soniox_transcription_events,
    prepare_soniox_speech,
    soniox_voice_provider_name,
    stream_soniox_speech,
    transcribe_soniox_audio,
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


class SonioxVoiceAssuranceTests(unittest.TestCase):
    def test_context_contains_bilingual_company_and_service_terms(self) -> None:
        terms = SONIOX_CONTEXT["terms"]
        for term in ("JorMall", "Smart Reach SMS", "OTP", "جورمول", "رسائل الخدمة"):
            self.assertIn(term, terms)

    def test_page_language_is_strict_and_explicit(self) -> None:
        self.assertEqual(normalize_voice_language("en"), "en")
        self.assertEqual(normalize_voice_language("ar"), "ar")
        with self.assertRaises(ValueError):
            normalize_voice_language("multi")

        with patch(
            "app.services.soniox_speech_service.soniox_api_key",
            return_value="test-key",
        ):
            config = build_soniox_stt_config("ar")
        self.assertEqual(config["model"], "stt-rt-v5")
        self.assertEqual(config["audio_format"], "auto")
        self.assertEqual(config["language_hints"], ["ar"])
        self.assertTrue(config["language_hints_strict"])
        self.assertFalse(config["enable_language_identification"])
        self.assertFalse(config["enable_endpoint_detection"])
        fallback = build_soniox_async_stt_config("ar")
        self.assertEqual(fallback["model"], "stt-async-v5")
        self.assertNotIn("audio_format", fallback)

    def test_safari_and_chromium_content_types_are_normalized(self) -> None:
        self.assertEqual(normalize_audio_content_type("audio/mp4"), "audio/mp4")
        self.assertEqual(
            normalize_audio_content_type("audio/webm;codecs=opus"),
            "audio/webm",
        )

    def test_streaming_tokens_are_joined_once_and_confidence_is_averaged(self) -> None:
        events = [
            {
                "tokens": [
                    {"text": "شو ", "start_ms": 0, "end_ms": 200, "confidence": 0.98, "is_final": True},
                    {"text": "خدمات", "start_ms": 200, "end_ms": 500, "confidence": 0.90, "is_final": False},
                ]
            },
            {
                "tokens": [
                    {"text": "شو ", "start_ms": 0, "end_ms": 200, "confidence": 0.98, "is_final": True},
                    {"text": "خدماتكم؟", "start_ms": 200, "end_ms": 700, "confidence": 0.96, "is_final": True},
                ]
            },
            {"tokens": [], "finished": True},
        ]
        result = parse_soniox_transcription_events(events, language="ar")
        self.assertEqual(result.transcript, "شو خدماتكم؟")
        self.assertAlmostEqual(result.confidence, 0.97)
        self.assertEqual(result.provider_language, "ar")
        self.assertFalse(hasattr(result, "api_key"))

    def test_async_transcript_parser_uses_exact_provider_text(self) -> None:
        result = parse_soniox_async_transcript(
            {
                "text": "كم كم سعر جور مول؟",
                "tokens": [
                    {"text": "كم ", "confidence": 0.99},
                    {"text": "كم سعر جور مول؟", "confidence": 0.97},
                ],
            },
            language="ar",
        )
        self.assertEqual(result.transcript, "كم كم سعر جور مول؟")
        self.assertAlmostEqual(result.confidence, 0.98)

    def test_uploaded_audio_and_transcription_are_deleted_after_success(self) -> None:
        with (
            patch(
                "app.services.soniox_speech_service._upload_audio",
                return_value="file-id",
            ),
            patch(
                "app.services.soniox_speech_service._transcribe_soniox_realtime",
                side_effect=SonioxTransportError("transport failed"),
            ),
            patch(
                "app.services.soniox_speech_service._json_request",
                side_effect=[
                    {"id": "transcription-id", "status": "queued"},
                    {"status": "completed"},
                    {"text": "What are your services?", "tokens": []},
                ],
            ),
            patch("app.services.soniox_speech_service._delete_resource") as delete,
        ):
            result = transcribe_soniox_audio(
                b"recording",
                content_type="audio/webm;codecs=opus",
                language="en",
            )
        self.assertEqual(result.transcript, "What are your services?")
        self.assertEqual(
            delete.call_args_list,
            [call("/transcriptions/transcription-id"), call("/files/file-id")],
        )

    def test_uploaded_audio_is_deleted_when_job_creation_fails(self) -> None:
        with (
            patch(
                "app.services.soniox_speech_service._upload_audio",
                return_value="file-id",
            ),
            patch(
                "app.services.soniox_speech_service._transcribe_soniox_realtime",
                side_effect=SonioxTransportError("transport failed"),
            ),
            patch(
                "app.services.soniox_speech_service._json_request",
                side_effect=SonioxSpeechError("temporary failure"),
            ),
            patch("app.services.soniox_speech_service._delete_resource") as delete,
        ):
            with self.assertRaises(SonioxSpeechError):
                transcribe_soniox_audio(
                    b"recording",
                    content_type="audio/webm",
                    language="en",
                )
        delete.assert_called_once_with("/files/file-id")

    def test_high_confidence_realtime_transcript_avoids_async_cost(self) -> None:
        realtime = SonioxTranscriptionResult(
            transcript="What are your services?",
            confidence=0.995,
            requested_language="en",
            provider_language="en",
        )
        with (
            patch(
                "app.services.soniox_speech_service._transcribe_soniox_realtime",
                return_value=realtime,
            ),
            patch("app.services.soniox_speech_service._transcribe_soniox_async_audio") as fallback,
        ):
            result = transcribe_soniox_audio(
                b"recording",
                content_type="audio/webm",
                language="en",
            )
        self.assertEqual(result, realtime)
        fallback.assert_not_called()

    def test_uncertain_realtime_transcript_uses_higher_accuracy_soniox_model(self) -> None:
        realtime = SonioxTranscriptionResult(
            transcript="What are you hosting plans?",
            confidence=0.973,
            requested_language="en",
            provider_language="en",
        )
        accurate = SonioxTranscriptionResult(
            transcript="What are your hosting plans?",
            confidence=0.999,
            requested_language="en",
            provider_language="en",
        )
        with (
            patch(
                "app.services.soniox_speech_service._transcribe_soniox_realtime",
                return_value=realtime,
            ),
            patch(
                "app.services.soniox_speech_service._transcribe_soniox_async_audio",
                return_value=accurate,
            ) as fallback,
        ):
            result = transcribe_soniox_audio(
                b"recording",
                content_type="audio/webm",
                language="en",
            )
        self.assertEqual(result, accurate)
        fallback.assert_called_once_with(
            b"recording",
            content_type="audio/webm",
            language="en",
        )

    def test_normalization_does_not_guess_or_rewrite_spoken_words(self) -> None:
        self.assertEqual(
            normalize_soniox_transcript("  كم   كم سعر جور مول؟  "),
            "كم كم سعر جور مول؟",
        )

    def test_empty_and_provider_error_responses_are_rejected(self) -> None:
        with self.assertRaises(SonioxSpeechError):
            parse_soniox_transcription_events([{"tokens": [], "finished": True}], language="en")
        with self.assertRaises(SonioxSpeechError):
            parse_soniox_transcription_events(
                [{"error_code": 429, "error_type": "limit_exceeded", "request_id": "safe-id"}],
                language="en",
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

class SonioxSpeechGenerationTests(unittest.TestCase):
    def test_one_fixed_current_voice_is_used_for_both_languages(self) -> None:
        with patch(
            "app.services.soniox_speech_service.soniox_api_key",
            return_value="test-key",
        ):
            arabic = build_soniox_tts_config("ar")
            english = build_soniox_tts_config("en")
        self.assertEqual(arabic["model"], "tts-rt-v2")
        self.assertEqual(english["model"], "tts-rt-v2")
        self.assertEqual(arabic["voice"], "Kayla")
        self.assertEqual(english["voice"], "Kayla")
        self.assertEqual(arabic["audio_format"], "pcm_s16le")
        self.assertEqual(arabic["sample_rate"], 24000)
        self.assertTrue(arabic["reduce_silence"])
        self.assertGreater(arabic["speed"], english["speed"])
        self.assertNotIn("api_key", arabic)
        self.assertNotIn("api_key", english)
        self.assertEqual(soniox_voice_provider_name(), "soniox-tts-rt-v2")

    def test_speech_input_is_bounded_and_bilingual(self) -> None:
        self.assertEqual(prepare_soniox_speech(text="  مرحبا  ", language="ar"), ("مرحبا", "ar"))
        with self.assertRaises(ValueError):
            prepare_soniox_speech(text="hello", language="fr")

    def test_jormall_keeps_official_text_but_uses_clear_tts_pronunciation(self) -> None:
        self.assertEqual(
            prepare_soniox_speech(text="Welcome to JorMall.", language="en"),
            ("Welcome to Jor-Mall.", "en"),
        )
        self.assertEqual(
            prepare_soniox_speech(text="مرحباً بك في JorMall.", language="ar"),
            ("مرحباً بك في جورمول.", "ar"),
        )

    def test_soniox_adapter_contains_no_openai_or_deepgram_call(self) -> None:
        source = (PROJECT_ROOT / "app/services/soniox_speech_service.py").read_text()
        self.assertNotIn("openai", source.lower())
        self.assertNotIn("deepgram", source.lower())

    def test_tts_transport_failure_uses_soniox_rest_without_switching_provider(self) -> None:
        with (
            patch(
                "app.services.soniox_speech_service._stream_soniox_realtime_speech",
                side_effect=SonioxTransportError("transport failed"),
            ),
            patch(
                "app.services.soniox_speech_service._stream_soniox_rest_speech",
                return_value=iter([b"pcm"]),
            ) as fallback,
        ):
            self.assertEqual(
                b"".join(stream_soniox_speech(text="Hello", language="en")),
                b"pcm",
            )
        fallback.assert_called_once_with(text="Hello", language="en")


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
            "احكي لي عن جورمول ورسائل الخدمة",
            "What SMS products and business uses does JorMall offer?",
            "ما هي منتجات الرسائل النصية واستخداماتها التي تقدمها جورمول؟",
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
        self.assertNotIn("soniox_api_key", self.javascript.lower())
        self.assertNotIn("Authorization", self.javascript)
        self.assertIn("transcribe_soniox_audio", self.public_api)
        self.assertNotIn("deepgram", self.public_api.lower())
        self.assertNotIn("openai_speech_service", self.public_api)

    def test_final_voice_streams_soniox_audio_with_browser_fallback(self) -> None:
        self.assertIn("new SpeechSynthesisUtterance(cleanText)", self.javascript)
        self.assertIn("chatbotConfig.voiceSpeechEndpoint", self.javascript)
        self.assertIn("response.body.getReader()", self.javascript)
        self.assertIn("speech_generation_failed", self.javascript)
        self.assertIn("stream_soniox_speech", self.public_api)
        self.assertNotIn("deepgram", self.public_api.lower())
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
