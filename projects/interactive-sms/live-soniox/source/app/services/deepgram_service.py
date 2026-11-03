from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from app.core.config import settings


DEEPGRAM_LISTEN_URL = "https://api.deepgram.com/v1/listen"
SUPPORTED_VOICE_LANGUAGES = {
    "en": "en",
    "ar": "ar-JO",
}
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
DEEPGRAM_KEYTERMS = (
    "JorMall",
    "Smart Reach SMS",
    "Service Messages",
    "Interactive Campaign Chatbot",
    "OTP",
    "API",
    "JOD",
    "Jordanian dinar",
    "جورمول",
    "رسائل الخدمة",
)


class DeepgramConfigurationError(RuntimeError):
    pass


class DeepgramTranscriptionError(RuntimeError):
    pass


@dataclass(frozen=True)
class TranscriptionResult:
    transcript: str
    confidence: float
    requested_language: str
    provider_language: str
    request_id: str


def normalize_audio_content_type(content_type: str | None) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


def provider_language_for(language: str) -> str:
    try:
        return SUPPORTED_VOICE_LANGUAGES[language.strip().lower()]
    except KeyError as error:
        raise ValueError("Voice language must be 'en' or 'ar'.") from error


def deepgram_api_key() -> str:
    if settings.deepgram_api_key is None:
        raise DeepgramConfigurationError("Deepgram speech recognition is not configured.")
    api_key = settings.deepgram_api_key.get_secret_value().strip()
    if not api_key:
        raise DeepgramConfigurationError("Deepgram speech recognition is not configured.")
    return api_key


def deepgram_listen_query(language: str) -> str:
    requested_language = language.strip().lower()
    query_parameters: list[tuple[str, str]] = [
        ("model", settings.deepgram_stt_model),
        ("language", provider_language_for(requested_language)),
        ("smart_format", "true"),
        ("punctuate", "true"),
        # Preserve complete natural questions, including words around pauses.
        ("utterances", "true"),
        ("utt_split", "1.0"),
        ("filler_words", "true"),
    ]
    query_parameters.extend(("keyterm", term) for term in DEEPGRAM_KEYTERMS)
    return urllib.parse.urlencode(query_parameters)


def normalize_transcript_text(transcript: str) -> str:
    """Normalize ASR typography without changing the user's intended words."""
    text = re.sub(r"[\u0640\u064B-\u065F\u0670\u06D6-\u06ED]", "", transcript)
    # Streaming/endpointing boundaries can repeat the first recognized token
    # (for example, "كم كم سعر..."). Remove only that adjacent opening echo;
    # repetitions elsewhere may be intentional and are preserved.
    text = re.sub(
        r"^([^\W\d_]+)\s+\1(?=\s|[؟?!.,،]|$)",
        r"\1",
        text,
        count=1,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"جور\s*[-–—]?\s*مول", "جورمول", text, flags=re.IGNORECASE)
    text = re.sub(r"\bjor\s*[-–—]?\s*mall\b", "JorMall", text, flags=re.IGNORECASE)
    # Jordanian "مين جورمول؟" is occasionally transcribed as the otherwise
    # incomplete phrase "من جورمول؟". Correct only this question form; do not
    # rewrite ordinary uses of the preposition "من".
    text = re.sub(r"^من\s+(?=جورمول(?:\s|[؟?!.,،]|$))", "مين ", text)
    text = re.sub(
        r"^(مين|شو|ايش|إيش)(?=(?:جورمول|خدمات|بتعمل|بتقدم|السعر))",
        r"\1 ",
        text,
    )
    return re.sub(r"\s+", " ", text).strip()


def parse_deepgram_response(payload: dict, *, requested_language: str) -> TranscriptionResult:
    try:
        alternative = payload["results"]["channels"][0]["alternatives"][0]
    except (KeyError, IndexError, TypeError) as error:
        raise DeepgramTranscriptionError("Speech recognition returned an invalid response.") from error

    transcript = normalize_transcript_text(
        str(alternative.get("transcript") or "").strip()
    )
    if not transcript:
        raise DeepgramTranscriptionError("No speech was detected. Please try again.")

    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    return TranscriptionResult(
        transcript=transcript[:1000],
        confidence=float(alternative.get("confidence") or 0.0),
        requested_language=requested_language,
        provider_language=provider_language_for(requested_language),
        request_id=str(metadata.get("request_id") or "")[:120],
    )


def transcribe_audio(
    audio: bytes,
    *,
    content_type: str,
    language: str,
) -> TranscriptionResult:
    if not audio:
        raise ValueError("The audio recording is empty.")

    normalized_type = normalize_audio_content_type(content_type)
    if normalized_type not in SUPPORTED_AUDIO_TYPES:
        raise ValueError("Unsupported audio format.")

    requested_language = language.strip().lower()
    query = deepgram_listen_query(requested_language)
    request = urllib.request.Request(
        f"{DEEPGRAM_LISTEN_URL}?{query}",
        data=audio,
        headers={
            "Authorization": f"Token {deepgram_api_key()}",
            "Content-Type": normalized_type,
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=settings.deepgram_request_timeout_seconds,
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise DeepgramTranscriptionError(
            "Speech recognition is temporarily unavailable. Please try again."
        ) from error

    return parse_deepgram_response(payload, requested_language=requested_language)


def transcript_matches_language(result: TranscriptionResult) -> bool:
    has_arabic = any("\u0600" <= character <= "\u06ff" for character in result.transcript)
    return has_arabic if result.requested_language == "ar" else not has_arabic


def transcription_selection_score(
    result: TranscriptionResult,
    *,
    preferred_language: str,
) -> float:
    score = result.confidence
    if result.requested_language == preferred_language:
        score += 0.04

    # An Arabic model returning Arabic script is stronger evidence than an
    # English model returning a phonetic Latin spelling of Arabic speech.
    if result.requested_language == "ar":
        score += 0.08
    else:
        latin_words = re.findall(r"[A-Za-z]+", result.transcript)
        if len(latin_words) == 1 and len(latin_words[0]) >= 11:
            score -= 0.12
    return score


def transcribe_bilingual_audio(
    audio: bytes,
    *,
    content_type: str,
    preferred_language: str,
) -> TranscriptionResult:
    """Try both supported languages and select the strongest script-consistent result."""
    clean_preference = preferred_language.strip().lower()
    provider_language_for(clean_preference)
    candidates: list[TranscriptionResult] = []
    errors: list[Exception] = []

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(
                transcribe_audio,
                audio,
                content_type=content_type,
                language=language,
            ): language
            for language in ("en", "ar")
        }
        for future in as_completed(futures):
            try:
                candidates.append(future.result())
            except (DeepgramTranscriptionError, ValueError) as error:
                errors.append(error)

    script_consistent = [item for item in candidates if transcript_matches_language(item)]
    selectable = script_consistent or candidates
    if not selectable:
        if errors:
            raise DeepgramTranscriptionError(str(errors[0])) from errors[0]
        raise DeepgramTranscriptionError("No speech was detected. Please try again.")

    return max(
        selectable,
        key=lambda item: (
            transcription_selection_score(
                item,
                preferred_language=clean_preference,
            ),
            item.requested_language == clean_preference,
        ),
    )
