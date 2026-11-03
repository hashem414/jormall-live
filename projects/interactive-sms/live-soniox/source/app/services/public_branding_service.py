from __future__ import annotations

import re


_ARABIC_CHARACTER_PATTERN = re.compile(r"[\u0600-\u06FF]")
_FORMER_ENGLISH_NAME_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])central\s+e\s*[-\u2010-\u2015]?\s*commerce"
    r"(?:\s+co(?:mpany)?\.?\s*,?\s*ltd\.?)?",
    flags=re.IGNORECASE,
)
_FORMER_ARABIC_NAME_PATTERN = re.compile(
    r"(?:(?:\u0634\u0631\u0643\u0629|\u0627\u0644\u0634\u0631\u0643\u0629)\s+)?"
    r"\u0627\u0644\u0645\u0631\u0643\u0632\u064a\u0629\s+\u0644\u0644\u062a\u062c\u0627\u0631\u0629\s+"
    r"\u0627\u0644\u0625\u0644\u0643\u062a\u0631\u0648\u0646\u064a\u0629"
)
_LATIN_JORMALL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9@._/\-])jor\s*[-\u2010-\u2015]?\s*mall(?P<possessive>['\u2019]s)?"
    r"(?![A-Za-z0-9@_/\-]|\.[A-Za-z0-9])",
    flags=re.IGNORECASE,
)
_SPACED_ARABIC_JORMALL_PATTERN = re.compile(
    r"(?<![\u0600-\u06FF])\u062c\u0648\u0631\s+\u0645\u0648\u0644(?![\u0600-\u06FF])"
)
_ARABIC_JORMALL_PATTERN = re.compile(
    r"(?<![\u0600-\u06FF])\u062c\u0648\u0631\u0645\u0648\u0644(?![\u0600-\u06FF])"
)
_DUPLICATE_LATIN_NAME_PATTERN = re.compile(
    r"\bJorMall\s*\(\s*JorMall\s*\)",
    flags=re.IGNORECASE,
)
_DUPLICATE_ARABIC_NAME_PATTERN = re.compile(
    r"\u062c\u0648\u0631\u0645\u0648\u0644\s*\(\s*\u062c\u0648\u0631\u0645\u0648\u0644\s*\)"
)
_DUPLICATE_ENGLISH_RELATIONSHIP_PATTERN = re.compile(
    r"\bJorMall\s*,\s*(?:operated\s+by|owned\s+by|a\s+subsidiary\s+of)\s+JorMall\b\s*,?",
    flags=re.IGNORECASE,
)
_DUPLICATE_ARABIC_RELATIONSHIP_PATTERN = re.compile(
    r"\u062c\u0648\u0631\u0645\u0648\u0644\s*[\u060c,]\s*"
    r"(?:\u0627\u0644\u062a\u0627\u0628\u0639\u0629|\u0627\u0644\u062a\u0627\u0628\u0639|\u0627\u0644\u0645\u0645\u0644\u0648\u0643\u0629)\s+"
    r"\u0644\u0640?\s*\u062c\u0648\u0631\u0645\u0648\u0644\s*[\u060c,]?"
)
_STREAM_TOKEN_PATTERN = re.compile(r"\S+")
_STREAM_SENSITIVE_PATTERNS = (
    _FORMER_ENGLISH_NAME_PATTERN,
    _FORMER_ARABIC_NAME_PATTERN,
    _LATIN_JORMALL_PATTERN,
    _SPACED_ARABIC_JORMALL_PATTERN,
    _ARABIC_JORMALL_PATTERN,
    _DUPLICATE_LATIN_NAME_PATTERN,
    _DUPLICATE_ARABIC_NAME_PATTERN,
    _DUPLICATE_ENGLISH_RELATIONSHIP_PATTERN,
    _DUPLICATE_ARABIC_RELATIONSHIP_PATTERN,
)


def canonicalize_company_aliases(text: str) -> str:
    """Replace former company-name aliases without changing the response language."""
    normalized = _FORMER_ENGLISH_NAME_PATTERN.sub("JorMall", str(text or ""))
    normalized = _FORMER_ARABIC_NAME_PATTERN.sub("جورمول", normalized)
    normalized = _DUPLICATE_LATIN_NAME_PATTERN.sub("JorMall", normalized)
    normalized = _DUPLICATE_ARABIC_NAME_PATTERN.sub("جورمول", normalized)
    normalized = _LATIN_JORMALL_PATTERN.sub(
        lambda match: f"JorMall{match.group('possessive') or ''}",
        normalized,
    )
    normalized = _SPACED_ARABIC_JORMALL_PATTERN.sub("جورمول", normalized)
    normalized = _DUPLICATE_ENGLISH_RELATIONSHIP_PATTERN.sub("JorMall", normalized)
    normalized = _DUPLICATE_ARABIC_RELATIONSHIP_PATTERN.sub("جورمول", normalized)
    return normalized


def canonicalize_public_branding(text: str, *, language: str | None = None) -> str:
    """Return customer-facing text using only the canonical bilingual brand names."""
    normalized = canonicalize_company_aliases(text)
    answer_language = (language or "").strip().lower().split("-", 1)[0]
    if not answer_language:
        answer_language = "ar" if _ARABIC_CHARACTER_PATTERN.search(normalized) else "en"

    if answer_language == "ar":
        normalized = _LATIN_JORMALL_PATTERN.sub("جورمول", normalized)
    else:
        normalized = _LATIN_JORMALL_PATTERN.sub(
            lambda match: f"JorMall{match.group('possessive') or ''}",
            normalized,
        )
        normalized = _ARABIC_JORMALL_PATTERN.sub("JorMall", normalized)
    if answer_language == "ar":
        normalized = _SPACED_ARABIC_JORMALL_PATTERN.sub("جورمول", normalized)
    normalized = _DUPLICATE_ENGLISH_RELATIONSHIP_PATTERN.sub("JorMall", normalized)
    normalized = _DUPLICATE_ARABIC_RELATIONSHIP_PATTERN.sub("جورمول", normalized)
    return normalized


def canonicalize_public_payload(value, *, language: str | None = None):
    """Canonicalize public text recursively while preserving payload structure."""
    if isinstance(value, str):
        return canonicalize_public_branding(value, language=language)
    if isinstance(value, list):
        return [
            canonicalize_public_payload(item, language=language)
            for item in value
        ]
    if isinstance(value, tuple):
        return tuple(
            canonicalize_public_payload(item, language=language)
            for item in value
        )
    if isinstance(value, dict):
        return {
            key: canonicalize_public_payload(item, language=language)
            for key, item in value.items()
        }
    return value


class PublicBrandingStreamGuard:
    """Canonicalize streamed text without exposing aliases split across deltas."""

    def __init__(self, *, language: str | None = None, tail_token_count: int = 8):
        self.language = language
        self.tail_token_count = max(1, tail_token_count)
        self._pending = ""

    def feed(self, text: str) -> str:
        self._pending += str(text or "")
        tokens = list(_STREAM_TOKEN_PATTERN.finditer(self._pending))
        if len(tokens) <= self.tail_token_count:
            return ""

        cutoff = tokens[-self.tail_token_count].start()
        for pattern in _STREAM_SENSITIVE_PATTERNS:
            for match in pattern.finditer(self._pending):
                if match.start() < cutoff < match.end():
                    cutoff = min(cutoff, match.start())

        if cutoff <= 0:
            return ""
        safe_text = self._pending[:cutoff]
        self._pending = self._pending[cutoff:]
        return canonicalize_public_branding(safe_text, language=self.language)

    def flush(self) -> str:
        safe_text = canonicalize_public_branding(
            self._pending,
            language=self.language,
        )
        self._pending = ""
        return safe_text
