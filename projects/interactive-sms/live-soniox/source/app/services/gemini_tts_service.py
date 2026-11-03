from __future__ import annotations

import hashlib
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterator

import google.auth
from google.api_core.client_options import ClientOptions
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import texttospeech

from app.core.config import settings


class GeminiTTSError(RuntimeError):
    """A safe, provider-independent speech synthesis failure."""


@dataclass(frozen=True)
class SynthesizedSpeech:
    audio: bytes
    media_type: str
    cache_hit: bool


def clean_tts_text(value: str) -> str:
    text = str(value or "")
    text = re.sub(r"\[\[(?:image|video):[^\]]+\]\]", "", text, flags=re.IGNORECASE)
    text = re.sub(
        r"\s*(?:Sources used|المصادر المستخدمة)\s*(?:\r?\n[\s\S]*)?$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_`#>]", "", text)
    text = re.sub(r"\s*[-•]\s+", ". ", text)
    return re.sub(r"\s+", " ", text).strip()


@lru_cache(maxsize=1)
def google_adc_status() -> tuple[bool, str]:
    if not settings.voice_enabled:
        return False, "Voice mode is disabled."
    try:
        _, discovered_project = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
    except DefaultCredentialsError:
        return False, "Google Application Default Credentials are not configured."
    project = settings.google_cloud_project.strip() or str(discovered_project or "").strip()
    if not project:
        return False, "Google Cloud project is not configured for ADC quota and billing."
    return True, ""


@lru_cache(maxsize=1)
def get_google_tts_client() -> texttospeech.TextToSpeechClient:
    region = settings.google_cloud_region.strip().lower() or "global"
    endpoint = (
        "texttospeech.googleapis.com"
        if region == "global"
        else f"{region}-texttospeech.googleapis.com"
    )
    return texttospeech.TextToSpeechClient(
        client_options=ClientOptions(api_endpoint=endpoint)
    )


class _SpeechCache:
    def __init__(self, max_items: int = 24, max_bytes: int = 32 * 1024 * 1024) -> None:
        self.max_items = max_items
        self.max_bytes = max_bytes
        self._total_bytes = 0
        self._items: OrderedDict[str, tuple[float, bytes]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> bytes | None:
        ttl = settings.gemini_tts_cache_ttl_seconds
        if ttl <= 0:
            return None
        now = time.monotonic()
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            created_at, audio = item
            if now - created_at > ttl:
                self._items.pop(key, None)
                self._total_bytes -= len(audio)
                return None
            self._items.move_to_end(key)
            return audio

    def put(self, key: str, audio: bytes) -> None:
        if settings.gemini_tts_cache_ttl_seconds <= 0:
            return
        with self._lock:
            existing = self._items.pop(key, None)
            if existing is not None:
                self._total_bytes -= len(existing[1])
            self._items[key] = (time.monotonic(), audio)
            self._total_bytes += len(audio)
            self._items.move_to_end(key)
            while len(self._items) > self.max_items or self._total_bytes > self.max_bytes:
                _, (_, removed_audio) = self._items.popitem(last=False)
                self._total_bytes -= len(removed_audio)


_speech_cache = _SpeechCache()


def _validated_speech_input(text: str, language: str) -> tuple[str, str, str, str]:
    clean_text = clean_tts_text(text)
    if not clean_text:
        raise GeminiTTSError("There is no assistant answer available to speak.")
    if len(clean_text.encode("utf-8")) > 4000:
        raise GeminiTTSError("The assistant answer is too long for voice playback.")
    available, reason = google_adc_status()
    if not available:
        raise GeminiTTSError(reason)
    language_code, voice_name, prompt = _language_settings(language)
    return clean_text, language_code, voice_name, prompt


def _cache_key(
    *,
    encoding: str,
    clean_text: str,
    language_code: str,
    voice_name: str,
    prompt: str,
) -> str:
    return hashlib.sha256(
        "\0".join(
            [
                settings.gemini_tts_model,
                encoding,
                language_code,
                voice_name,
                prompt,
                clean_text,
            ]
        ).encode("utf-8")
    ).hexdigest()


def _chunk_audio(audio: bytes, chunk_size: int = 16 * 1024) -> Iterator[bytes]:
    for offset in range(0, len(audio), chunk_size):
        yield audio[offset : offset + chunk_size]


def _language_settings(language: str) -> tuple[str, str, str]:
    if language == "ar":
        return (
            settings.gemini_tts_language_ar,
            settings.gemini_tts_voice_ar,
            "اقرأ النص بالعربية الفصحى الطبيعية بوضوح وبسرعة محادثة معتدلة ونبرة ودودة ومهنية. "
            "اقرأ النص مرة واحدة فقط من البداية إلى النهاية، ولا تكرر أي كلمة أو جملة. "
            "انطق JorMall أو جورمول بصيغة جُورمُول، بحرف الجيم كما في كلمة الأردن. لا تضف أي كلمات غير موجودة في النص.",
        )
    if language == "en":
        return (
            settings.gemini_tts_language_en,
            settings.gemini_tts_voice_en,
            "Read naturally in clear conversational English at a moderate pace with a warm, professional tone. "
            "Read the text exactly once from beginning to end, without repeating any word or sentence. "
            "Pronounce JorMall as Jor-Mall, with the J sound in Jordan. Do not add words that are not in the text.",
        )
    raise ValueError("Voice language must be English or Arabic.")


def synthesize_with_gemini(*, text: str, language: str) -> SynthesizedSpeech:
    clean_text, language_code, voice_name, prompt = _validated_speech_input(text, language)
    cache_key = _cache_key(
        encoding="mp3",
        clean_text=clean_text,
        language_code=language_code,
        voice_name=voice_name,
        prompt=prompt,
    )
    cached = _speech_cache.get(cache_key)
    if cached is not None:
        return SynthesizedSpeech(cached, "audio/mpeg", True)

    try:
        response = get_google_tts_client().synthesize_speech(
            input=texttospeech.SynthesisInput(text=clean_text, prompt=prompt),
            voice=texttospeech.VoiceSelectionParams(
                language_code=language_code,
                name=voice_name,
                model_name=settings.gemini_tts_model,
            ),
            audio_config=texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
            ),
        )
    except Exception as error:
        raise GeminiTTSError("Google Gemini speech synthesis is temporarily unavailable.") from error

    audio = bytes(response.audio_content or b"")
    if not audio:
        raise GeminiTTSError("Google Gemini did not return speech audio.")
    _speech_cache.put(cache_key, audio)
    return SynthesizedSpeech(audio, "audio/mpeg", False)


def stream_with_gemini(*, text: str, language: str) -> Iterator[bytes]:
    """Stream raw 24 kHz mono PCM so playback can begin before synthesis ends."""
    clean_text, language_code, voice_name, prompt = _validated_speech_input(text, language)
    cache_key = _cache_key(
        encoding="pcm-s16le-24000",
        clean_text=clean_text,
        language_code=language_code,
        voice_name=voice_name,
        prompt=prompt,
    )
    cached = _speech_cache.get(cache_key)
    if cached is not None:
        yield from _chunk_audio(cached)
        return

    config = texttospeech.StreamingSynthesizeConfig(
        voice=texttospeech.VoiceSelectionParams(
            language_code=language_code,
            name=voice_name,
            model_name=settings.gemini_tts_model,
        ),
        streaming_audio_config=texttospeech.StreamingAudioConfig(
            audio_encoding=texttospeech.AudioEncoding.PCM,
            sample_rate_hertz=24000,
        ),
    )

    def requests():
        yield texttospeech.StreamingSynthesizeRequest(streaming_config=config)
        yield texttospeech.StreamingSynthesizeRequest(
            input=texttospeech.StreamingSynthesisInput(text=clean_text, prompt=prompt)
        )

    complete_audio = bytearray()
    pending = bytearray()
    try:
        for response in get_google_tts_client().streaming_synthesize(requests=requests()):
            chunk = bytes(response.audio_content or b"")
            if not chunk:
                continue
            complete_audio.extend(chunk)
            pending.extend(chunk)
            if len(pending) >= 16 * 1024:
                yield bytes(pending)
                pending.clear()
    except Exception as error:
        raise GeminiTTSError("Google Gemini speech synthesis is temporarily unavailable.") from error
    if pending:
        yield bytes(pending)
    if not complete_audio:
        raise GeminiTTSError("Google Gemini did not return speech audio.")
    _speech_cache.put(cache_key, bytes(complete_audio))
