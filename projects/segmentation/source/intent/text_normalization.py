from __future__ import annotations

import re
import unicodedata
from typing import Iterable, List


ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]")
TOKEN_PATTERN = re.compile(r"[\w]+", flags=re.UNICODE)
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").translate(ARABIC_DIGITS)
    text = ARABIC_DIACRITICS.sub("", text).replace("ـ", "")
    text = text.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ؤ": "و", "ئ": "ي"}))
    text = text.lower().replace("’", "'")
    text = re.sub(r"[^\w\s'&+/-]", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def tokenize(value: str, minimum_length: int = 2) -> List[str]:
    return [token for token in TOKEN_PATTERN.findall(normalize_text(value)) if len(token) >= minimum_length]


def unique_normalized(values: Iterable[str]) -> List[str]:
    return list(dict.fromkeys(normalize_text(value) for value in values if normalize_text(value)))
