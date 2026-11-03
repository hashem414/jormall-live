from __future__ import annotations

import json
import urllib.parse
from collections.abc import Iterator

from websockets.exceptions import WebSocketException
from websockets.sync.client import connect

from app.core.config import settings
from app.services.deepgram_service import deepgram_api_key


DEEPGRAM_AGENT_URL = "wss://agent.deepgram.com/v1/agent/converse"
DEEPGRAM_FLUX_SPEAK_URL = "wss://api.deepgram.com/v2/speak"


class DeepgramVoiceAgentError(RuntimeError):
    pass


def deepgram_voice_provider_name(language: str) -> str:
    return "deepgram-agent-cartesia" if language == "ar" else "deepgram-flux"


def prepare_deepgram_speech(*, text: str, language: str) -> tuple[str, str]:
    clean_text = " ".join((text or "").split()).strip()
    if not clean_text:
        raise ValueError("Speech text is empty.")
    if len(clean_text) > settings.voice_tts_max_characters:
        raise ValueError("Speech text is too long.")
    clean_language = language.strip().lower()
    if clean_language not in {"ar", "en"}:
        raise ValueError("Speech language must be English or Arabic.")
    return clean_text, clean_language


def deepgram_speak_provider(language: str) -> dict:
    if language == "ar":
        return {
            "type": "cartesia",
            "model_id": settings.deepgram_arabic_tts_model,
            "voice": {
                "mode": "id",
                "id": settings.deepgram_arabic_tts_voice_id,
            },
            "language": "ar",
            "speed": settings.deepgram_arabic_tts_speed,
        }
    return {
        "type": "deepgram",
        "version": "v2",
        "model": settings.deepgram_english_tts_model,
        "speed": settings.deepgram_english_tts_speed,
        "expressivity": 0,
    }


def build_agent_settings(language: str) -> dict:
    listen_language = "ar-JO" if language == "ar" else "en"
    return {
        "type": "Settings",
        "mip_opt_out": True,
        "flags": {"history": False},
        "audio": {
            "input": {"encoding": "linear16", "sample_rate": 16000},
            "output": {
                "encoding": "linear16",
                "sample_rate": 24000,
                "container": "none",
            },
        },
        "agent": {
            "listen": {
                "provider": {
                    "type": "deepgram",
                    "model": settings.deepgram_stt_model,
                    "language": listen_language,
                }
            },
            "think": {
                "provider": {
                    "type": "google",
                    "model": "gemini-2.5-flash-lite",
                },
                "prompt": "Do not generate a reply unless explicitly asked.",
            },
            "speak": {"provider": deepgram_speak_provider(language)},
        },
    }


def receive_json_event(connection, *, timeout: float) -> dict:
    message = connection.recv(timeout=timeout)
    if isinstance(message, bytes):
        return {}
    return json.loads(message)


def wait_for_event(connection, event_type: str) -> None:
    while True:
        event = receive_json_event(connection, timeout=settings.deepgram_request_timeout_seconds)
        if event.get("type") == event_type:
            return
        if event.get("type") == "Error":
            raise DeepgramVoiceAgentError(
                str(event.get("description") or event.get("message") or "Voice setup failed.")
            )


def stream_deepgram_flux_speech(*, text: str) -> Iterator[bytes]:
    query = urllib.parse.urlencode(
        {
            "model": settings.deepgram_english_tts_model,
            "encoding": "linear16",
            "sample_rate": 24000,
        }
    )
    try:
        with connect(
            f"{DEEPGRAM_FLUX_SPEAK_URL}?{query}",
            additional_headers={"Authorization": f"Token {deepgram_api_key()}"},
            open_timeout=settings.deepgram_request_timeout_seconds,
            close_timeout=5,
        ) as connection:
            wait_for_event(connection, "Connected")
            if settings.deepgram_english_tts_speed != 1.0:
                connection.send(json.dumps({"type": "Configure", "speed": settings.deepgram_english_tts_speed}))
                wait_for_event(connection, "ConfigureSuccess")
            connection.send(json.dumps({"type": "Speak", "text": text}))
            connection.send(json.dumps({"type": "Flush"}))
            while True:
                message = connection.recv(timeout=settings.deepgram_request_timeout_seconds)
                if isinstance(message, bytes):
                    if message:
                        yield message
                    continue
                event = json.loads(message)
                if event.get("type") == "SpeechMetadata":
                    connection.send(json.dumps({"type": "Close"}))
                    return
                if event.get("type") == "Error":
                    raise DeepgramVoiceAgentError(
                        str(event.get("description") or event.get("message") or "Voice generation failed.")
                    )
    except (OSError, TimeoutError, WebSocketException, json.JSONDecodeError) as error:
        raise DeepgramVoiceAgentError("Voice generation is temporarily unavailable.") from error


def stream_deepgram_speech(*, text: str, language: str) -> Iterator[bytes]:
    clean_text, clean_language = prepare_deepgram_speech(text=text, language=language)
    if clean_language == "en":
        yield from stream_deepgram_flux_speech(text=clean_text)
        return
    try:
        with connect(
            DEEPGRAM_AGENT_URL,
            additional_headers={"Authorization": f"Token {deepgram_api_key()}"},
            open_timeout=settings.deepgram_request_timeout_seconds,
            close_timeout=5,
        ) as connection:
            wait_for_event(connection, "Welcome")
            connection.send(json.dumps(build_agent_settings(clean_language)))
            wait_for_event(connection, "SettingsApplied")
            connection.send(
                json.dumps(
                    {
                        "type": "InjectAgentMessage",
                        "behavior": "interrupt",
                        "message": clean_text,
                    },
                    ensure_ascii=False,
                )
            )
            while True:
                message = connection.recv(timeout=settings.deepgram_request_timeout_seconds)
                if isinstance(message, bytes):
                    if message:
                        yield message
                    continue
                event = json.loads(message)
                if event.get("type") == "AgentAudioDone":
                    return
                if event.get("type") == "Error":
                    raise DeepgramVoiceAgentError(
                        str(event.get("description") or event.get("message") or "Voice generation failed.")
                    )
    except (OSError, TimeoutError, WebSocketException, json.JSONDecodeError) as error:
        raise DeepgramVoiceAgentError("Voice generation is temporarily unavailable.") from error
