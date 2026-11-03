"""Bounded local-only browser acceptance for the Soniox latency experiment.

This script never targets the deployed website. Chromium receives a controlled
WAV file through its fake microphone so the recording path remains repeatable.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from playwright.sync_api import Response, sync_playwright


DEFAULT_URL = "http://127.0.0.1:5005/interactive-sms/"
DEFAULT_FIXTURE = Path("artifacts/pocket-tts-5005/controlled-microphone.wav")
DEFAULT_OUTPUT = Path("artifacts/voice-latency-production-20260920/browser-local.json")


def _headers(response: Response) -> dict[str, str]:
    return {key.lower(): value for key, value in response.all_headers().items()}


def _last_answer(page) -> str:
    return page.locator(".assistant-message .message-bubble p").last.inner_text().strip()


def _wait_for_new_play_button(page, previous: int) -> None:
    page.wait_for_function(
        "expected => document.querySelectorAll('.assistant-speech-play').length > expected",
        arg=previous,
        timeout=120_000,
    )


def _submit_typed_question(page, question: str) -> None:
    previous = page.locator(".assistant-speech-play").count()
    page.locator("#chat-input").fill(question)
    page.locator("#send-button").click()
    _wait_for_new_play_button(page, previous)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    fixture = args.fixture.resolve()
    if not fixture.is_file():
        raise SystemExit(f"Controlled microphone fixture is missing: {fixture}")

    result: dict[str, object] = {
        "target": args.url,
        "local_only": True,
        "physical_microphone": "NOT RUN",
        "human_listening": "NOT RUN",
        "browser": "chromium-headless",
        "responses": [],
    }
    page_errors: list[str] = []
    console_errors: list[str] = []
    voice_responses: list[dict[str, object]] = []

    started = time.monotonic()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                args=[
                    "--autoplay-policy=no-user-gesture-required",
                    "--use-fake-ui-for-media-stream",
                    "--use-fake-device-for-media-stream",
                    f"--use-file-for-fake-audio-capture={fixture}",
                ],
            )
            context = browser.new_context(permissions=["microphone"])
            page = context.new_page()
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.on(
                "console",
                lambda message: console_errors.append(message.text)
                if message.type == "error"
                else None,
            )

            def capture_voice_response(response: Response) -> None:
                if response.url.endswith("/transcribe") or response.url.endswith("/speak"):
                    headers = _headers(response)
                    voice_responses.append(
                        {
                            "url": response.url,
                            "status": response.status,
                            "headers": {
                                key: headers.get(key, "")
                                for key in (
                                    "content-type",
                                    "server-timing",
                                    "x-stt-provider",
                                    "x-stt-model",
                                    "x-stt-workflow",
                                    "x-stt-duration-ms",
                                    "x-stt-language",
                                    "x-voice-provider",
                                    "x-voice-model",
                                    "x-voice-voice",
                                    "x-voice-cache",
                                    "x-voice-first-audio-ms",
                                    "x-voice-source-characters",
                                    "x-voice-speech-characters",
                                    "x-voice-compacted",
                                    "x-voice-language",
                                )
                                if headers.get(key) is not None
                            },
                        }
                    )

            page.on("response", capture_voice_response)
            page.goto(args.url, wait_until="networkidle", timeout=30_000)
            page.locator("#prechat-lead-name").fill("Local Latency Test")
            page.locator("#prechat-lead-phone").fill("0790000099")
            page.locator("#prechat-lead-submit").click()
            page.wait_for_selector("#prechat-lead-overlay", state="hidden", timeout=15_000)

            # Complete simulated microphone flow: record, transcribe, chat, speak.
            page.locator("#voice-button").click()
            page.wait_for_function("voiceState === 'recording'", timeout=10_000)
            page.wait_for_timeout(8_500)
            page.locator("#voice-orb-button").click()
            page.wait_for_function(
                "window.JorMallVoiceTimings.snapshot()?.current?.marks?.playback_started",
                timeout=120_000,
            )
            microphone_timing = page.evaluate("window.JorMallVoiceTimings.snapshot()")
            microphone_transcript = page.locator(".user-message .message-bubble p").last.inner_text().strip()
            microphone_answer = _last_answer(page)
            page.evaluate("stopBrowserSpeech()")

            transcribe = next(
                item for item in voice_responses if str(item["url"]).endswith("/transcribe")
            )
            microphone_speak = next(
                item for item in voice_responses if str(item["url"]).endswith("/speak")
            )
            assert transcribe["status"] == 200
            assert transcribe["headers"]["x-stt-provider"] == "soniox"
            assert transcribe["headers"]["x-stt-model"] == "stt-rt-v5"
            assert transcribe["headers"]["x-stt-workflow"] == "realtime"
            assert transcribe["headers"]["x-stt-language"] == "en"
            assert microphone_speak["status"] == 200
            assert microphone_speak["headers"]["x-voice-provider"] == "soniox"
            assert microphone_speak["headers"]["x-voice-language"] == "en"
            assert microphone_speak["headers"]["x-voice-compacted"] == "false"

            # A broad written answer stays complete while its spoken view is bounded.
            broad_start = len(voice_responses)
            _submit_typed_question(page, "What services does JorMall provide?")
            broad_answer = _last_answer(page)
            page.locator(".assistant-speech-play").last.click()
            page.wait_for_function(
                "window.JorMallVoiceTimings.snapshot()?.current?.marks?.tts_headers?.compacted === true",
                timeout=120_000,
            )
            page.wait_for_function("activeVoiceSources.size > 0", timeout=30_000)
            page.evaluate("stopBrowserSpeech()")
            broad_speak = next(
                item
                for item in voice_responses[broad_start:]
                if str(item["url"]).endswith("/speak")
            )
            broad_source = int(broad_speak["headers"]["x-voice-source-characters"])
            broad_speech = int(broad_speak["headers"]["x-voice-speech-characters"])
            assert broad_speak["headers"]["x-voice-provider"] == "soniox"
            assert broad_speak["headers"]["x-voice-compacted"] == "true"
            assert len(" ".join(broad_answer.split())) > 360
            assert 0 < broad_speech <= 360 < broad_source

            # Arabic uses the same authorized saved-message Soniox route.
            arabic_start = len(voice_responses)
            _submit_typed_question(page, "ما هو بريدكم الإلكتروني؟")
            assert page.locator("html").get_attribute("lang") == "ar"
            arabic_answer = _last_answer(page)
            page.locator(".assistant-speech-play").last.click()
            page.wait_for_function("activeVoiceSources.size > 0", timeout=120_000)
            page.evaluate("stopBrowserSpeech()")
            arabic_speak = next(
                item
                for item in voice_responses[arabic_start:]
                if str(item["url"]).endswith("/speak")
            )
            assert arabic_speak["headers"]["x-voice-provider"] == "soniox"
            assert arabic_speak["headers"]["x-voice-model"] == "tts-rt-v2"
            assert arabic_speak["headers"]["x-voice-language"] == "ar"
            assert "info@jormall.com" in arabic_answer

            result.update(
                {
                    "status": "PASS",
                    "simulated_microphone": {
                        "status": "PASS",
                        "transcript": microphone_transcript,
                        "answer": microphone_answer,
                        "timing": microphone_timing,
                    },
                    "broad_answer": {
                        "status": "PASS",
                        "written_characters": broad_source,
                        "spoken_characters": broad_speech,
                        "compacted": True,
                    },
                    "arabic_saved_message_speech": {
                        "status": "PASS",
                        "answer": arabic_answer,
                    },
                }
            )
            browser.close()
    except Exception as error:
        result.update(
            {
                "status": "FAIL",
                "error": f"{type(error).__name__}: {error}",
            }
        )

    result["responses"] = voice_responses
    result["page_errors"] = page_errors
    result["console_errors"] = console_errors
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
