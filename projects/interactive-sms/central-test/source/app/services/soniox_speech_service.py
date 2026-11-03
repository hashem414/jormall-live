from __future__ import annotations

import base64
import binascii
import json
import re
import time
import unicodedata
import urllib.error
import urllib.request
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from uuid import uuid4

import websocket

from app.core.config import settings


SONIOX_API_BASE_URL = "https://api.soniox.com/v1"
SONIOX_TTS_URL = "https://tts-rt.soniox.com/tts"
SONIOX_STT_WEBSOCKET_URL = "wss://stt-rt.soniox.com/transcribe-websocket"
SONIOX_TTS_WEBSOCKET_URL = "wss://tts-rt.soniox.com/tts-websocket"
SONIOX_USER_AGENT = "JorMallVoice/1.0"
SONIOX_AUDIO_CHUNK_BYTES = 64 * 1024
SONIOX_TTS_CHUNK_BYTES = 8 * 1024
JORMALL_SPEECH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])jor\s*[-\u2013\u2014]?\s*mall(?![A-Za-z0-9])",
    flags=re.IGNORECASE,
)
SUPPORTED_AUDIO_TYPES = {
    "audio/aac",
    "audio/flac",
    "audio/m4a",
    "audio/mp4",
    "audio/mpeg",
    "audio/ogg",
    "audio/wav",
    "audio/webm",
    "audio/x-m4a",
    "audio/x-wav",
}
SONIOX_CONTEXT = {
    "general": [
        {"key": "domain", "value": "Jordanian business messaging and e-commerce"},
        {"key": "organization", "value": "JorMall, Central E-Commerce Co. Ltd."},
        {"key": "dialect", "value": "Jordanian and Levantine Arabic"},
    ],
    "terms": [
        "JorMall",
        "جورمول",
        "Central E-Commerce Co. Ltd.",
        "الشركة المركزية للتجارة الإلكترونية",
        "Smart Reach SMS",
        "Service Messages",
        "رسائل الخدمة",
        "OTP",
        "API",
        "JOD",
    ],
}


class SonioxConfigurationError(RuntimeError):
    pass


class SonioxSpeechError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        error_type: str = "",
        request_id: str = "",
    ) -> None:
        super().__init__(message)
        self.error_type = error_type[:80]
        self.request_id = request_id[:120]


class SonioxTransportError(SonioxSpeechError):
    """A network/transport failure that may safely use a Soniox fallback."""


@dataclass(frozen=True, slots=True)
class SonioxTranscriptionResult:
    transcript: str
    confidence: float
    requested_language: str
    provider_language: str
    request_id: str = ""


def normalize_audio_content_type(content_type: str | None) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


def normalize_voice_language(language: str) -> str:
    clean_language = language.strip().lower()
    if clean_language not in {"ar", "en"}:
        raise ValueError("Voice language must be English or Arabic.")
    return clean_language


def normalize_soniox_transcript(transcript: str) -> str:
    """Normalize transport artifacts without guessing or rewriting spoken words."""
    normalized = unicodedata.normalize("NFC", transcript)
    normalized = normalized.replace("\u200b", "").replace("\ufeff", "")
    return re.sub(r"\s+", " ", normalized).strip()


def soniox_api_key() -> str:
    if settings.soniox_api_key is None:
        raise SonioxConfigurationError("Soniox speech services are not configured.")
    api_key = settings.soniox_api_key.get_secret_value().strip()
    if not api_key:
        raise SonioxConfigurationError("Soniox speech services are not configured.")
    return api_key


def build_soniox_stt_config(language: str) -> dict:
    clean_language = normalize_voice_language(language)
    return {
        "model": settings.soniox_stt_model,
        "audio_format": "auto",
        "language_hints": [clean_language],
        "language_hints_strict": True,
        "context": SONIOX_CONTEXT,
        "enable_speaker_diarization": False,
        "enable_language_identification": False,
        "enable_endpoint_detection": False,
    }


def build_soniox_async_stt_config(language: str) -> dict:
    config = build_soniox_stt_config(language)
    config["model"] = settings.soniox_stt_fallback_model
    config.pop("audio_format", None)
    config.pop("enable_endpoint_detection", None)
    return config


def prepare_soniox_speech(*, text: str, language: str) -> tuple[str, str]:
    clean_language = normalize_voice_language(language)
    clean_text = re.sub(r"\s+", " ", text or "").strip()
    if not clean_text:
        raise ValueError("Speech text is empty.")
    # Keep the official JorMall spelling in chat and storage, but give TTS a
    # language-specific pronunciation form. Kayla otherwise pronounces the
    # compact English brand spelling as "Your Mall".
    spoken_brand = "جورمول" if clean_language == "ar" else "Jor-Mall"
    clean_text = JORMALL_SPEECH_PATTERN.sub(spoken_brand, clean_text)
    if len(clean_text) > settings.voice_tts_max_characters:
        raise ValueError("Speech text is too long.")
    return clean_text, clean_language


def soniox_tts_speed(language: str) -> float:
    clean_language = normalize_voice_language(language)
    if clean_language == "ar":
        return settings.soniox_tts_arabic_speed
    return settings.soniox_tts_english_speed


def build_soniox_tts_config(language: str) -> dict:
    clean_language = normalize_voice_language(language)
    return {
        "model": settings.soniox_tts_model,
        "language": clean_language,
        "voice": settings.soniox_tts_voice,
        "audio_format": "pcm_s16le",
        "sample_rate": 24000,
        "speed": soniox_tts_speed(clean_language),
        "reduce_silence": settings.soniox_tts_reduce_silence,
    }


def soniox_voice_provider_name() -> str:
    return f"soniox-{settings.soniox_tts_model}"


def _provider_error(payload: dict, *, user_message: str) -> SonioxSpeechError:
    return SonioxSpeechError(
        user_message,
        error_type=str(payload.get("error_type") or "provider_error"),
        request_id=str(payload.get("request_id") or ""),
    )


def _authenticated_headers(*, content_type: str | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {soniox_api_key()}",
        "Accept": "application/json",
        "User-Agent": SONIOX_USER_AGENT,
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _decode_json(data: bytes) -> dict:
    payload = json.loads(data.decode("utf-8"))
    if not isinstance(payload, dict):
        raise json.JSONDecodeError("Expected an object", "", 0)
    return payload


def _json_request(
    path: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
    user_error: str,
) -> dict:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{SONIOX_API_BASE_URL}{path}",
        data=data,
        headers=_authenticated_headers(
            content_type="application/json" if payload is not None else None
        ),
        method=method,
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=settings.soniox_request_timeout_seconds,
        ) as response:
            return _decode_json(response.read())
    except urllib.error.HTTPError as error:
        try:
            error_payload = _decode_json(error.read())
        except (UnicodeDecodeError, json.JSONDecodeError):
            error_payload = {"error_type": f"http_{error.code}"}
        raise _provider_error(error_payload, user_message=user_error) from error
    except (urllib.error.URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SonioxSpeechError(user_error) from error


def _audio_filename(content_type: str) -> str:
    extension = {
        "audio/aac": "aac",
        "audio/flac": "flac",
        "audio/m4a": "m4a",
        "audio/mp4": "m4a",
        "audio/mpeg": "mp3",
        "audio/ogg": "ogg",
        "audio/wav": "wav",
        "audio/webm": "webm",
        "audio/x-m4a": "m4a",
        "audio/x-wav": "wav",
    }[content_type]
    return f"voice-message.{extension}"


def _upload_audio(audio: bytes, *, content_type: str) -> str:
    boundary = f"----JorMallVoice{uuid4().hex}"
    filename = _audio_filename(content_type)
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("ascii") + audio + f"\r\n--{boundary}--\r\n".encode("ascii")
    request = urllib.request.Request(
        f"{SONIOX_API_BASE_URL}/files",
        data=body,
        headers=_authenticated_headers(
            content_type=f"multipart/form-data; boundary={boundary}"
        ),
        method="POST",
    )
    user_error = "Speech recognition is temporarily unavailable. Please try again."
    try:
        with urllib.request.urlopen(
            request,
            timeout=settings.soniox_request_timeout_seconds,
        ) as response:
            payload = _decode_json(response.read())
    except urllib.error.HTTPError as error:
        try:
            error_payload = _decode_json(error.read())
        except (UnicodeDecodeError, json.JSONDecodeError):
            error_payload = {"error_type": f"http_{error.code}"}
        raise _provider_error(error_payload, user_message=user_error) from error
    except (urllib.error.URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SonioxSpeechError(user_error) from error

    file_id = str(payload.get("id") or "").strip()
    if not file_id:
        raise SonioxSpeechError(user_error)
    return file_id


def _delete_resource(path: str) -> None:
    """Best-effort privacy cleanup; cleanup failure must not hide a valid answer."""
    try:
        request = urllib.request.Request(
            f"{SONIOX_API_BASE_URL}{path}",
            headers=_authenticated_headers(),
            method="DELETE",
        )
        with urllib.request.urlopen(
            request,
            timeout=settings.soniox_request_timeout_seconds,
        ):
            pass
    except (SonioxConfigurationError, urllib.error.URLError, TimeoutError):
        return


def parse_soniox_async_transcript(
    payload: dict,
    *,
    language: str,
) -> SonioxTranscriptionResult:
    tokens = payload.get("tokens")
    token_items = tokens if isinstance(tokens, list) else []
    transcript = str(payload.get("text") or "")
    if not transcript:
        transcript = "".join(
            str(token.get("text") or "")
            for token in token_items
            if isinstance(token, dict)
        )
    transcript = normalize_soniox_transcript(transcript)
    if not transcript:
        raise SonioxSpeechError("No speech was detected. Please try again.")

    confidences = [
        float(token.get("confidence") or 0.0)
        for token in token_items
        if isinstance(token, dict) and str(token.get("text") or "").strip()
    ]
    confidence = sum(confidences) / len(confidences) if confidences else 0.0
    clean_language = normalize_voice_language(language)
    return SonioxTranscriptionResult(
        transcript=transcript[:1000],
        confidence=confidence,
        requested_language=clean_language,
        provider_language=clean_language,
    )


def parse_soniox_transcription_events(
    events: Iterable[dict],
    *,
    language: str,
) -> SonioxTranscriptionResult:
    """Compatibility helper for deterministic token-parser assurance tests."""
    final_tokens: dict[tuple[object, object, str], dict] = {}
    pending_tokens: list[dict] = []
    for payload in events:
        if payload.get("error_code"):
            raise _provider_error(
                payload,
                user_message="Speech recognition is temporarily unavailable. Please try again.",
            )
        current_pending: list[dict] = []
        tokens = payload.get("tokens")
        if not isinstance(tokens, list):
            continue
        for token in tokens:
            if not isinstance(token, dict):
                continue
            if token.get("is_final") is True:
                key = (token.get("start_ms"), token.get("end_ms"), str(token.get("text") or ""))
                final_tokens[key] = token
            else:
                current_pending.append(token)
        pending_tokens = current_pending
    ordered = list(final_tokens.values()) + pending_tokens
    return parse_soniox_async_transcript(
        {
            "text": "".join(str(token.get("text") or "") for token in ordered),
            "tokens": ordered,
        },
        language=language,
    )


def _connect_soniox_websocket(url: str):
    return websocket.create_connection(
        url,
        timeout=settings.soniox_request_timeout_seconds,
        header=[f"User-Agent: {SONIOX_USER_AGENT}"],
        enable_multithread=False,
    )


def _transcribe_soniox_realtime(
    audio: bytes,
    *,
    language: str,
) -> SonioxTranscriptionResult:
    connection = None
    events: list[dict] = []
    user_error = "Speech recognition is temporarily unavailable. Please try again."
    try:
        connection = _connect_soniox_websocket(SONIOX_STT_WEBSOCKET_URL)
        connection.send(
            json.dumps(
                {**build_soniox_stt_config(language), "api_key": soniox_api_key()},
                ensure_ascii=False,
            )
        )
        for start in range(0, len(audio), SONIOX_AUDIO_CHUNK_BYTES):
            connection.send_binary(audio[start : start + SONIOX_AUDIO_CHUNK_BYTES])
        # websocket-client doesn't emit a zero-length binary frame reliably.
        # Soniox accepts an empty text frame for graceful manual finalization.
        connection.send("")

        while True:
            message = connection.recv()
            if not isinstance(message, str):
                raise SonioxTransportError(user_error)
            payload = _decode_json(message.encode("utf-8"))
            if payload.get("error_code"):
                raise _provider_error(payload, user_message=user_error)
            events.append(payload)
            if payload.get("finished") is True:
                break
    except SonioxSpeechError:
        raise
    except (
        websocket.WebSocketException,
        OSError,
        TimeoutError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        raise SonioxTransportError(user_error) from error
    finally:
        if connection is not None:
            try:
                connection.close()
            except websocket.WebSocketException:
                pass

    return parse_soniox_transcription_events(events, language=language)


def _transcribe_soniox_async_audio(
    audio: bytes,
    *,
    content_type: str,
    language: str,
) -> SonioxTranscriptionResult:
    if not audio:
        raise ValueError("The audio recording is empty.")
    normalized_type = normalize_audio_content_type(content_type)
    if normalized_type not in SUPPORTED_AUDIO_TYPES:
        raise ValueError("Unsupported audio format.")

    clean_language = normalize_voice_language(language)
    file_id = ""
    transcription_id = ""
    user_error = "Speech recognition is temporarily unavailable. Please try again."
    try:
        file_id = _upload_audio(audio, content_type=normalized_type)
        transcription = _json_request(
            "/transcriptions",
            method="POST",
            payload={**build_soniox_async_stt_config(clean_language), "file_id": file_id},
            user_error=user_error,
        )
        transcription_id = str(transcription.get("id") or "").strip()
        if not transcription_id:
            raise SonioxSpeechError(user_error)

        deadline = time.monotonic() + settings.soniox_request_timeout_seconds
        while True:
            status_payload = _json_request(
                f"/transcriptions/{transcription_id}",
                user_error=user_error,
            )
            status = str(status_payload.get("status") or "").lower()
            if status == "completed":
                break
            if status in {"error", "failed"}:
                raise _provider_error(status_payload, user_message=user_error)
            if time.monotonic() >= deadline:
                raise SonioxSpeechError(user_error, error_type="request_timeout")
            time.sleep(0.2)

        transcript_payload = _json_request(
            f"/transcriptions/{transcription_id}/transcript",
            user_error=user_error,
        )
        return parse_soniox_async_transcript(
            transcript_payload,
            language=clean_language,
        )
    finally:
        if transcription_id:
            _delete_resource(f"/transcriptions/{transcription_id}")
        if file_id:
            _delete_resource(f"/files/{file_id}")


def transcribe_soniox_audio(
    audio: bytes,
    *,
    content_type: str,
    language: str,
) -> SonioxTranscriptionResult:
    if not audio:
        raise ValueError("The audio recording is empty.")
    normalized_type = normalize_audio_content_type(content_type)
    if normalized_type not in SUPPORTED_AUDIO_TYPES:
        raise ValueError("Unsupported audio format.")
    clean_language = normalize_voice_language(language)
    try:
        realtime_result = _transcribe_soniox_realtime(audio, language=clean_language)
    except SonioxTransportError:
        return _transcribe_soniox_async_audio(
            audio,
            content_type=normalized_type,
            language=clean_language,
        )
    if realtime_result.confidence >= settings.soniox_stt_min_confidence:
        return realtime_result
    return _transcribe_soniox_async_audio(
        audio,
        content_type=normalized_type,
        language=clean_language,
    )


def _stream_soniox_realtime_speech(*, text: str, language: str) -> Iterator[bytes]:
    stream_id = f"voice-{uuid4()}"
    connection = None
    audio_received = False
    user_error = "Voice playback is temporarily unavailable."
    try:
        connection = _connect_soniox_websocket(SONIOX_TTS_WEBSOCKET_URL)
        connection.send(
            json.dumps(
                {
                    **build_soniox_tts_config(language),
                    "api_key": soniox_api_key(),
                    "stream_id": stream_id,
                },
                ensure_ascii=False,
            )
        )
        connection.send(
            json.dumps(
                {"text": text, "text_end": True, "stream_id": stream_id},
                ensure_ascii=False,
            )
        )
        while True:
            message = connection.recv()
            if not isinstance(message, str):
                raise SonioxTransportError(user_error)
            payload = _decode_json(message.encode("utf-8"))
            if payload.get("error_code"):
                raise _provider_error(payload, user_message=user_error)
            payload_stream_id = payload.get("stream_id")
            if payload_stream_id and payload_stream_id != stream_id:
                continue
            encoded_audio = payload.get("audio")
            if encoded_audio:
                audio = base64.b64decode(encoded_audio, validate=True)
                if audio:
                    audio_received = True
                    yield audio
            if payload.get("terminated") is True:
                break
    except SonioxSpeechError:
        raise
    except (
        websocket.WebSocketException,
        OSError,
        TimeoutError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        binascii.Error,
        ValueError,
    ) as error:
        raise SonioxTransportError(user_error) from error
    finally:
        if connection is not None:
            try:
                connection.close()
            except websocket.WebSocketException:
                pass

    if not audio_received:
        raise SonioxTransportError("Voice playback returned no audio.")


def _stream_soniox_rest_speech(*, text: str, language: str) -> Iterator[bytes]:
    clean_text, clean_language = prepare_soniox_speech(text=text, language=language)
    payload = {**build_soniox_tts_config(clean_language), "text": clean_text}
    request = urllib.request.Request(
        SONIOX_TTS_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            **_authenticated_headers(content_type="application/json"),
            "Accept": "audio/pcm",
        },
        method="POST",
    )
    user_error = "Voice playback is temporarily unavailable."
    audio_received = False
    try:
        with urllib.request.urlopen(
            request,
            timeout=settings.soniox_request_timeout_seconds,
        ) as response:
            while True:
                audio = response.read(SONIOX_TTS_CHUNK_BYTES)
                if not audio:
                    break
                audio_received = True
                yield audio
    except urllib.error.HTTPError as error:
        try:
            error_payload = _decode_json(error.read())
        except (UnicodeDecodeError, json.JSONDecodeError):
            error_payload = {"error_type": f"http_{error.code}"}
        raise _provider_error(error_payload, user_message=user_error) from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise SonioxSpeechError(user_error) from error

    if not audio_received:
        raise SonioxSpeechError("Voice playback returned no audio.")


def stream_soniox_speech(*, text: str, language: str) -> Iterator[bytes]:
    clean_text, clean_language = prepare_soniox_speech(text=text, language=language)
    realtime_audio_started = False
    try:
        for audio in _stream_soniox_realtime_speech(
            text=clean_text,
            language=clean_language,
        ):
            realtime_audio_started = True
            yield audio
        return
    except SonioxTransportError:
        if realtime_audio_started:
            raise SonioxSpeechError("Voice playback is temporarily unavailable.")

    yield from _stream_soniox_rest_speech(
        text=clean_text,
        language=clean_language,
    )
