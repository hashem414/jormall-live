"""أدوات نصية: تطبيع عربي للبحث، كشف اللغة، عدّ التوكنز، تطبيع أرقام الهواتف."""

from __future__ import annotations

import re
import unicodedata

# ------------------------------------------------------------------
# تطبيع النص العربي
# ------------------------------------------------------------------
_ARABIC_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_ALEF_VARIANTS = re.compile(r"[إأآا]")
_ARABIC_RANGE = re.compile(r"[؀-ۿ]")
_NON_WORD = re.compile(r"[^\w؀-ۿ]+", re.UNICODE)
_ARABIC_PUNCT = re.compile(r"[،؛؟٪٫٬٭۔«»]")
_ARABIC_INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def normalize_arabic(text: str) -> str:
    """
    تطبيع عربي قياسي للبحث النصي:
    - إزالة التشكيل والتطويل
    - توحيد الألف (إأآ -> ا)، الياء (ى -> ي)، التاء المربوطة (ة -> ه)
    - تحويل الأرقام العربية-الهندية لأرقام لاتينية
    مهم لأن PostgreSQL ما عنده stemmer عربي، فبنعوّض بالتطبيع.
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_ARABIC_INDIC)
    text = _ARABIC_DIACRITICS.sub("", text)
    text = _ALEF_VARIANTS.sub("ا", text)
    text = text.replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي").replace("ة", "ه")
    return text


def build_search_text(text: str) -> str:
    """نسخة مُسطّحة من الشانك تُخزَّن بعمود search_text للبحث بالكلمات المفتاحية."""
    text = normalize_arabic(text.lower())
    text = _ARABIC_PUNCT.sub(" ", text)
    text = _NON_WORD.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def detect_language(text: str) -> str:
    """كشف بسيط وكافٍ: نسبة الحروف العربية للحروف الأبجدية."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return "ar"
    arabic = sum(1 for c in letters if _ARABIC_RANGE.match(c))
    return "ar" if arabic / len(letters) >= 0.25 else "en"


# ------------------------------------------------------------------
# عدّ التوكنز
# ------------------------------------------------------------------
try:  # tiktoken اختياري — لو مش منصّب بنرجع لتقدير تقريبي
    import tiktoken

    _ENCODER = tiktoken.get_encoding("cl100k_base")

    def count_tokens(text: str) -> int:
        return len(_ENCODER.encode(text))

except Exception:  # pragma: no cover

    def count_tokens(text: str) -> int:
        # العربي تقريباً ~2 توكن للكلمة بترميز cl100k
        return max(1, len(text) // 3)


# ------------------------------------------------------------------
# أرقام الهواتف الأردنية
# ------------------------------------------------------------------
_JO_MOBILE = re.compile(r"^(?:00962|\+?962|0)?(7[789]\d{7})$")


def normalize_jordan_phone(raw: str) -> str | None:
    """
    يرجّع الرقم بصيغة موحدة 9627XXXXXXXX، أو None لو الرقم مش صالح.
    بيقبل: 0791234567 / 962791234567 / +962 79 123 4567 / ٠٧٩١٢٣٤٥٦٧
    """
    if not raw:
        return None
    digits = raw.translate(_ARABIC_INDIC)
    digits = re.sub(r"[\s\-().]", "", digits)
    match = _JO_MOBILE.match(digits)
    if not match:
        return None
    return "962" + match.group(1)


def format_phone_display(normalized: str) -> str:
    """9627XXXXXXXX -> 07X XXX XXXX للعرض."""
    if normalized.startswith("962") and len(normalized) == 12:
        local = "0" + normalized[3:]
        return f"{local[:3]} {local[3:6]} {local[6:]}"
    return normalized
