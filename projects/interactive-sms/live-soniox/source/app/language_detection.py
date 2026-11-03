"""Deterministic English/Arabic language selection shared by chat and voice."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping


SUPPORTED_LANGUAGES = {"ar", "en"}
WORD_PATTERN = re.compile(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*", re.UNICODE)
ADDRESS_PATTERN = re.compile(
    r"https?://[^\s]+|www\.[^\s]+|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|"
    r"\b(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}(?:/[^\s]*)?",
    re.IGNORECASE,
)


def _script_counts(value: str) -> tuple[int, int]:
    arabic = 0
    latin = 0
    for character in value:
        if not unicodedata.category(character).startswith("L"):
            continue
        codepoint = ord(character)
        if 0x0600 <= codepoint <= 0x06FF:
            arabic += 1
        elif "LATIN" in unicodedata.name(character, ""):
            latin += 1
    return arabic, latin


def detect_supported_language(text: str, *, fallback: str = "en") -> str:
    """Choose the dominant supported script without flipping for one foreign name."""
    fallback = fallback if fallback in SUPPORTED_LANGUAGES else "en"
    votes: list[str] = []
    language_text = ADDRESS_PATTERN.sub(" ", text or "")
    for word in WORD_PATTERN.findall(language_text):
        arabic, latin = _script_counts(word)
        if arabic > latin:
            votes.append("ar")
        elif latin > arabic:
            votes.append("en")
    if not votes:
        return fallback
    arabic_votes = votes.count("ar")
    english_votes = votes.count("en")
    if arabic_votes > english_votes:
        return "ar"
    if english_votes > arabic_votes:
        return "en"
    # A short greeting plus a brand name is common. On a tie, the first spoken
    # language-bearing word is a better signal than the brand's character count.
    return votes[0]


def detected_token_language(
    tokens: Iterable[Mapping[str, object]],
    *,
    transcript: str,
    fallback: str = "en",
) -> str:
    """Select a dominant Soniox token language and fall back to script analysis."""
    weights = {"ar": 0, "en": 0}
    for token in tokens:
        language = str(token.get("language") or "").split("-", 1)[0].lower()
        if language not in weights:
            continue
        text = str(token.get("text") or "")
        weight = sum(
            1 for character in text if unicodedata.category(character).startswith("L")
        )
        weights[language] += max(1, weight)
    if weights["ar"] > weights["en"]:
        return "ar"
    if weights["en"] > weights["ar"]:
        return "en"
    return detect_supported_language(transcript, fallback=fallback)
