from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

from openai import OpenAIError

from app.core.config import settings
from app.services.deepgram_service import (
    SUPPORTED_AUDIO_TYPES,
    normalize_audio_content_type,
)
from app.services.openai_client import get_openai_client


class SpeechServiceError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MultilingualTranscription:
    transcript: str
    language: str
    provider_language: str = "ar,en"
    confidence: float = 0.0


TRANSCRIPTION_CONTEXT = (
    "Transcribe the user's exact words without translating or answering. The speaker "
    "may use Jordanian or Levantine Arabic, Modern Standard Arabic, English, or "
    "Arabic-English code-switching. Preserve the spoken language. This is a JorMall "
    "business assistant. Vocabulary and likely topics include: JorMall (جورمول or "
    "جور مول), Central E-Commerce Co. Ltd. (الشركة المركزية للتجارة الإلكترونية), "
    "Smart Reach SMS, bulk SMS, Service Messages (رسائل الخدمة), promotional messages "
    "(الرسائل الترويجية), OTP, API, interactive campaign chatbot, hosting, Jordanian "
    "dinar, and JOD. Common Jordanian questions include: مين جورمول؟ شو بتعمل جورمول؟ "
    "شو خدماتكم؟ شو بتقدموا؟ كم السعر؟ Do not add an introduction or commentary."
)


def detect_transcript_language(transcript: str, *, preferred_language: str) -> str:
    """Detect the reply language from the final multilingual transcript.

    Arabic script is decisive. For short neutral utterances (numbers, brand names,
    or punctuation), the current UI language remains the least surprising choice.
    """
    arabic_letters = len(re.findall(r"[\u0600-\u06FF]", transcript))
    latin_letters = len(re.findall(r"[A-Za-z]", transcript))
    if arabic_letters:
        return "ar"
    if latin_letters:
        return "en"
    return preferred_language


def transcribe_multilingual_audio(
    audio: bytes,
    *,
    content_type: str,
    preferred_language: str,
) -> MultilingualTranscription:
    if not audio:
        raise ValueError("The audio recording is empty.")

    clean_preference = preferred_language.strip().lower()
    if clean_preference not in {"ar", "en"}:
        raise ValueError("Voice language must be English or Arabic.")

    normalized_type = normalize_audio_content_type(content_type)
    if normalized_type not in SUPPORTED_AUDIO_TYPES:
        raise ValueError("Unsupported audio format.")

    extension = {
        "audio/mp4": "m4a",
        "audio/m4a": "m4a",
        "audio/x-m4a": "m4a",
        "audio/mpeg": "mp3",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/ogg": "ogg",
        "audio/flac": "flac",
    }.get(normalized_type, "webm")

    try:
        response = get_openai_client().audio.transcriptions.create(
            model=settings.openai_transcription_model,
            file=(f"voice-message.{extension}", audio, normalized_type),
            languages=["ar", "en"],
            prompt=TRANSCRIPTION_CONTEXT,
            response_format="json",
            timeout=settings.openai_audio_request_timeout_seconds,
        )
    except (OpenAIError, TimeoutError) as error:
        raise SpeechServiceError(
            "Speech recognition is temporarily unavailable. Please try again."
        ) from error

    transcript = str(getattr(response, "text", "") or "").strip()
    if not transcript:
        raise SpeechServiceError("No speech was detected. Please try again.")

    language = detect_transcript_language(
        transcript,
        preferred_language=clean_preference,
    )
    return MultilingualTranscription(
        transcript=transcript[:1000],
        language=language,
    )


def prepare_speech_request(*, text: str, language: str) -> tuple[str, str]:
    clean_text = re.sub(r"\s+", " ", text or "").strip()
    if not clean_text:
        raise ValueError("Speech text is empty.")
    if len(clean_text) > settings.voice_tts_max_characters:
        raise ValueError("Speech text is too long.")

    clean_language = language.strip().lower()
    if clean_language not in {"ar", "en"}:
        raise ValueError("Speech language must be English or Arabic.")

    instructions = (
        "Speak in clear, warm, natural Jordanian Arabic. Keep the same voice, "
        "a conversational pace, and pronounce English brand names naturally. "
        "Read only the supplied text."
        if clean_language == "ar"
        else "Speak in clear, warm, natural English at a conversational pace. "
        "Keep the same voice and read only the supplied text."
    )
    return clean_text, instructions


def synthesize_assistant_speech(*, text: str, language: str) -> bytes:
    clean_text, instructions = prepare_speech_request(text=text, language=language)
    try:
        response = get_openai_client().audio.speech.create(
            model=settings.openai_tts_model,
            voice=settings.openai_tts_voice,
            input=clean_text,
            instructions=instructions,
            response_format="mp3",
            timeout=settings.openai_audio_request_timeout_seconds,
        )
        return response.content
    except (OpenAIError, TimeoutError) as error:
        raise SpeechServiceError(
            "Voice playback is temporarily unavailable."
        ) from error


def stream_assistant_speech(*, text: str, language: str) -> Iterator[bytes]:
    """Yield raw 24 kHz mono PCM as OpenAI produces it.

    Streaming raw PCM lets the browser schedule the first samples immediately,
    without waiting for a complete encoded audio file.
    """
    clean_text, instructions = prepare_speech_request(text=text, language=language)
    try:
        with get_openai_client().audio.speech.with_streaming_response.create(
            model=settings.openai_tts_model,
            voice=settings.openai_tts_voice,
            input=clean_text,
            instructions=instructions,
            response_format="pcm",
            stream_format="audio",
            timeout=settings.openai_audio_request_timeout_seconds,
        ) as response:
            yield from response.iter_bytes(chunk_size=4096)
    except (OpenAIError, TimeoutError) as error:
        raise SpeechServiceError(
            "Voice playback is temporarily unavailable."
        ) from error
