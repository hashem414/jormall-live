"""
الصوت عبر OpenAI Audio API.

اتجاهين:
  • كلام → نص  (STT): العميل بيحكي بالمايك، بنحوّله لرسالة عادية بتمشي
    بنفس مسار الشات — نفس الأدوات، نفس الحواجز، نفس التدقيق.
  • نص → كلام (TTS): رد البوت بينقرأ بصوت للي بيفضّل يسمع بدل ما يقرأ.

ليش الصوت بيمرّ بنفس مسار النص؟ عشان ما ينفتح باب خلفي: أي حجز أو إلغاء
لازم يعدّي على نفس أدوات `tools.py` وحواجزها، مش على مسار صوتي موازي بقواعد أقل.
"""

from __future__ import annotations

import io
import logging

from .clients import get_openai
from .config import get_settings

logger = logging.getLogger(__name__)

# صيغ الصوت اللي بتطلعها متصفحات مختلفة من MediaRecorder
ALLOWED_AUDIO_TYPES = {
    "audio/webm", "audio/ogg", "audio/mpeg", "audio/mp3", "audio/mp4",
    "audio/m4a", "audio/x-m4a", "audio/wav", "audio/x-wav", "audio/flac",
}

# لو الموديل الحديث مش متاح على الحساب بنرجع للقديم بدل ما نفشل
_STT_FALLBACK = "whisper-1"
_TTS_FALLBACK = "tts-1"

# تلميح مفردات للتفريغ: بدونه اسم العيادة بينكتب «كارميليت» أو «Carmelite»،
# وأسماء الخدمات بتنحرف — وهاي بالضبط الكلمات اللي البوت بيبني عليها الحجز.
_STT_VOCABULARY = (
    "كارماليت, Karmalite, بوتوكس, فيلر, بروفايلو, هيدرافيشل, ديرمابن, ليزر, "
    "بلازما, ميزوثيرابي, هايفو, تقشير كيميائي, كارمافيم, KarmaFemme, "
    "Botox, Filler, Profhilo, Hydrafacial, Dermapen, PRP, HIFU, "
    "عمّان, الصويفية, دير غبار, موعد, حجز"
)

_TTS_INSTRUCTIONS = (
    "You are a warm, calm receptionist at a medical aesthetics clinic. "
    "Speak naturally and unhurriedly, with a reassuring tone. "
    "Read Arabic text in Jordanian-neutral Arabic and English text in English."
)


class VoiceDisabled(RuntimeError):
    """الصوت مطفي بالإعدادات."""


def is_enabled() -> bool:
    return get_settings().voice_enabled


def _ensure_enabled() -> None:
    if not is_enabled():
        raise VoiceDisabled("خاصية الصوت مطفية — فعّلها بـ VOICE_ENABLED=true")


def transcribe(audio: bytes, *, filename: str = "audio.webm", lang: str | None = None) -> str:
    """
    كلام → نص. `lang` تلميح اختياري ('ar' أو 'en') بيحسّن الدقة،
    بس ما بنفرضه: العميل ممكن يحكي إنجليزي والواجهة على عربي.
    """
    _ensure_enabled()
    settings = get_settings()

    def _call(model: str) -> str:
        stream = io.BytesIO(audio)
        stream.name = filename          # الـ SDK بيستنتج الصيغة من الاسم
        kwargs: dict = {"model": model, "file": stream, "prompt": _STT_VOCABULARY}
        if lang in {"ar", "en"}:
            kwargs["language"] = lang
        return (get_openai().audio.transcriptions.create(**kwargs).text or "").strip()

    try:
        return _call(settings.stt_model)
    except Exception as exc:
        if settings.stt_model == _STT_FALLBACK:
            raise
        logger.warning("STT بـ %s فشل (%s) — بنجرّب %s", settings.stt_model, exc, _STT_FALLBACK)
        return _call(_STT_FALLBACK)


def synthesize(text: str, *, lang: str = "ar") -> tuple[bytes, str]:
    """
    نص → كلام. بيرجّع (بايتات الصوت، نوع المحتوى).

    بنقصّ النص الطويل بدل ما نرفض الطلب: رد طويل أحسنله يتقرأ ناقص
    من إنه ما ينقرأ أبداً، والنص الكامل مكتوب قدام العميل بكل الأحوال.
    """
    _ensure_enabled()
    settings = get_settings()

    clean = (text or "").strip()
    if not clean:
        raise ValueError("النص فاضي")
    if len(clean) > settings.tts_max_chars:
        clean = clean[: settings.tts_max_chars].rsplit(" ", 1)[0] + "…"

    fmt = settings.tts_format
    mime = {"mp3": "audio/mpeg", "opus": "audio/ogg", "aac": "audio/aac",
            "flac": "audio/flac", "wav": "audio/wav", "pcm": "audio/pcm"}.get(fmt, "audio/mpeg")

    def _call(model: str) -> bytes:
        kwargs: dict = {
            "model": model,
            "voice": settings.tts_voice,
            "input": clean,
            "response_format": fmt,
        }
        # `instructions` مدعومة بموديلات gpt-4o-*-tts فقط
        if "gpt-4o" in model:
            kwargs["instructions"] = _TTS_INSTRUCTIONS
        return get_openai().audio.speech.create(**kwargs).content

    try:
        return _call(settings.tts_model), mime
    except Exception as exc:
        if settings.tts_model == _TTS_FALLBACK:
            raise
        logger.warning("TTS بـ %s فشل (%s) — بنجرّب %s", settings.tts_model, exc, _TTS_FALLBACK)
        return _call(_TTS_FALLBACK), mime
