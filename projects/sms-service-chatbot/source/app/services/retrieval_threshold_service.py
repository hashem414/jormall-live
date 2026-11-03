from __future__ import annotations

import re
from typing import Any

from app.core.config import settings
from app.services.client_config_service import DEFAULT_CLIENT_SLUG, ClientConfig


GENERATED_CLIENT_MIN_SIMILARITY = 0.30
GENERATED_CLIENT_BUSINESS_MIN_SIMILARITY = 0.28
GENERATED_CLIENT_TABLE_MIN_SIMILARITY = 0.27
GENERATED_CLIENT_ABSOLUTE_FLOOR = 0.25

BUSINESS_QUERY_KEYWORDS = (
    "active plan",
    "active plans",
    "affordability",
    "applicant",
    "applicants",
    "application",
    "bank account",
    "service",
    "services",
    "provide",
    "offer",
    "contact",
    "phone",
    "email",
    "whatsapp",
    "location",
    "located",
    "address",
    "where are you",
    "working hours",
    "opening hours",
    "hours",
    "open",
    "bundle",
    "bundles",
    "compare",
    "price",
    "prices",
    "prize",
    "prizes",
    "quantity",
    "cost",
    "reward",
    "rewards",
    "table",
    "tier",
    "positioning",
    "proof of address",
    "salary certificate",
    "required documents",
    "credit review",
    "installment",
    "installments",
    "instalment",
    "instalments",
    "monthly payment",
    "repayment",
    "repayments",
    "processing purpose",
    "collected",
    "processed",
)

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "can",
    "could",
    "does",
    "do",
    "explain",
    "for",
    "from",
    "give",
    "how",
    "i",
    "is",
    "it",
    "me",
    "much",
    "of",
    "on",
    "or",
    "please",
    "show",
    "tell",
    "that",
    "the",
    "this",
    "to",
    "was",
    "what",
    "whats",
    "when",
    "where",
    "who",
    "why",
    "you",
    "your",
}

GENERIC_BUSINESS_TOKENS = {
    "address",
    "business",
    "company",
    "contact",
    "cost",
    "email",
    "hours",
    "image",
    "listed",
    "location",
    "logo",
    "offer",
    "offers",
    "open",
    "package",
    "packages",
    "phone",
    "photo",
    "price",
    "prices",
    "pricing",
    "provide",
    "service",
    "services",
    "site",
    "video",
    "website",
    "whatsapp",
}

PRICING_QUERY_TOKENS = {
    "cost",
    "fee",
    "fees",
    "package",
    "packages",
    "price",
    "prices",
    "pricing",
    "rate",
    "rates",
}

PRICING_CONTEXT_TOKENS = {
    *PRICING_QUERY_TOKENS,
    "contract",
    "contracts",
    "invoice",
    "invoiced",
    "qty",
    "quantity",
    "table",
    "total",
    "usage",
    "validity",
    "value",
}

GENERAL_KNOWLEDGE_PATTERNS = (
    r"\bwhat(?:'s| is)?\s+(?:the\s+)?(?:day|date|time)\b",
    r"\btoday\b",
    r"\btomorrow\b",
    r"\byesterday\b",
    r"\bcurrent\s+(?:day|date|time|year)\b",
    r"\bwho\s+is\s+.+\b(?:king|president|prime minister|queen|ceo)\b",
    r"\bwho\s+is\s+(?:jordan'?s?|jordans?)\s+king\b",
    r"\bwhat\s+is\s+real\s+madrid\b",
    r"\breal\s+madrid\b",
    r"\blamborghini\b",
)

ARABIC_BUSINESS_KEYWORDS = (
    "\u062e\u062f\u0645\u0629",
    "\u062e\u062f\u0645\u0627\u062a",
    "\u0633\u0639\u0631",
    "\u0623\u0633\u0639\u0627\u0631",
    "\u0627\u0633\u0639\u0627\u0631",
    "\u0646\u0633\u0628\u0629",
    "\u0631\u0633\u0627\u0626\u0644",
    "\u0645\u062c\u0627\u0646\u064a\u0629",
    "\u0639\u0642\u062f",
    "\u0639\u0642\u0648\u062f",
    "\u062a\u0648\u0627\u0635\u0644",
    "\u0647\u0627\u062a\u0641",
    "\u0628\u0631\u064a\u062f",
    "\u0645\u0648\u0642\u0639",
    "\u0639\u0646\u0648\u0627\u0646",
    "\u0628\u0627\u0642\u0629",
    "\u0628\u0627\u0642\u0627\u062a",
    "\u062c\u0627\u0626\u0632\u0629",
    "\u062c\u0648\u0627\u0626\u0632",
    "\u0645\u0643\u0627\u0641\u0623\u0629",
    "\u0645\u0643\u0627\u0641\u0622\u062a",
    "\u0643\u0645\u064a\u0629",
    "\u0639\u062f\u062f",
    "\u062c\u062f\u0648\u0644",
    "\u0641\u0626\u0629",
    "\u0641\u0626\u0627\u062a",
    "\u0645\u062a\u0648\u0633\u0637\u0629",
    "\u0643\u0628\u0631\u0649",
)

TABLE_QUERY_KEYWORDS = (
    "active",
    "address",
    "affordability",
    "applicant",
    "applicants",
    "application",
    "amount",
    "bundle",
    "bundles",
    "certificate",
    "collected",
    "column",
    "compare",
    "count",
    "credit",
    "document",
    "documents",
    "highest",
    "incomplete",
    "installment",
    "installments",
    "instalment",
    "instalments",
    "listed",
    "lowest",
    "monthly",
    "number",
    "package",
    "packages",
    "performs",
    "plans",
    "position",
    "positioned",
    "positioning",
    "processed",
    "proof",
    "provider",
    "purpose",
    "prize",
    "prizes",
    "quantity",
    "repayment",
    "repayments",
    "required",
    "requirement",
    "requirements",
    "review",
    "reward",
    "rewards",
    "row",
    "salary",
    "table",
    "tier",
)


def contains_arabic(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", text))


def question_language(question: str) -> str:
    return "ar" if contains_arabic(question) else "en"


def looks_like_basic_business_question(question: str) -> bool:
    normalized = question.lower()

    return any(keyword in normalized for keyword in BUSINESS_QUERY_KEYWORDS) or any(
        keyword in question for keyword in ARABIC_BUSINESS_KEYWORDS
    )


def looks_like_table_lookup_question(question: str) -> bool:
    normalized = question.lower()
    return bool(
        any(keyword in normalized for keyword in TABLE_QUERY_KEYWORDS)
        or re.search(r"\b\d[\d,]*(?:\.\d+)?\s*[km]\b", normalized)
        or any(keyword in question for keyword in ARABIC_BUSINESS_KEYWORDS)
    )


def normalize_token(value: str) -> str:
    token = value.lower().strip()

    if token.endswith("'s"):
        token = token[:-2]
    elif token.endswith("s") and len(token) > 4:
        token = token[:-1]

    return token


def tokenize(value: Any) -> set[str]:
    return {
        normalize_token(token)
        for token in re.findall(r"[a-zA-Z0-9]+", str(value or "").lower())
        if len(normalize_token(token)) > 1
        and normalize_token(token) not in STOPWORDS
    }


def looks_like_general_knowledge_question(question: str) -> bool:
    normalized = question.lower().strip()

    return any(
        re.search(pattern, normalized, flags=re.IGNORECASE)
        for pattern in GENERAL_KNOWLEDGE_PATTERNS
    )


def client_identity_tokens(config: ClientConfig) -> set[str]:
    return tokenize(
        " ".join(
            [
                config.company_name,
                config.client_slug.replace("-", " "),
                config.assistant_name,
                config.business_type,
            ]
        )
    )


def chunk_text(chunk: Any) -> str:
    metadata = getattr(chunk, "metadata", {}) or {}

    return " ".join(
        [
            str(getattr(chunk, "document_title", "") or ""),
            str(getattr(chunk, "section_title", "") or ""),
            str(getattr(chunk, "content", "") or ""),
            " ".join(str(value) for value in metadata.values() if isinstance(value, str)),
        ]
    )


def has_strong_context_overlap(
    *,
    question: str,
    chunks: list[Any],
    client_config: ClientConfig,
) -> bool:
    if looks_like_general_knowledge_question(question):
        return False

    question_tokens = tokenize(question)

    context_tokens: set[str] = set()
    for chunk in chunks[:5]:
        context_tokens.update(tokenize(chunk_text(chunk)))

    if not context_tokens:
        return False

    if contains_arabic(question) and looks_like_basic_business_question(question):
        best_similarity = float(getattr(chunks[0], "similarity", 0.0) or 0.0)
        best_language = str(getattr(chunks[0], "language", "") or "")
        if is_similarity_allowed(
            similarity=best_similarity,
            question=question,
            chunk_language=best_language,
            client_slug=client_config.client_slug,
        ):
            return True

    if not question_tokens:
        return False

    client_tokens = client_identity_tokens(client_config)
    meaningful_question_tokens = question_tokens - GENERIC_BUSINESS_TOKENS

    if question_tokens & client_tokens:
        return bool((question_tokens & context_tokens) or looks_like_basic_business_question(question))

    if looks_like_basic_business_question(question) and not meaningful_question_tokens:
        return True

    meaningful_overlap = meaningful_question_tokens & context_tokens

    if (
        question_tokens & PRICING_QUERY_TOKENS
        and context_tokens & PRICING_CONTEXT_TOKENS
    ):
        return True

    if meaningful_question_tokens and not meaningful_overlap:
        return False

    if len(meaningful_overlap) >= 1:
        return True

    return bool(looks_like_basic_business_question(question) and (question_tokens & context_tokens))


def required_similarity_for_client(
    *,
    question: str,
    chunk_language: str,
    client_slug: str,
) -> float:
    if question_language(question) != chunk_language:
        return settings.cross_language_min_retrieval_similarity

    if client_slug == DEFAULT_CLIENT_SLUG:
        return settings.min_retrieval_similarity

    if looks_like_table_lookup_question(question):
        return GENERATED_CLIENT_TABLE_MIN_SIMILARITY

    if looks_like_basic_business_question(question):
        return GENERATED_CLIENT_BUSINESS_MIN_SIMILARITY

    return GENERATED_CLIENT_MIN_SIMILARITY


def is_similarity_allowed(
    *,
    similarity: float,
    question: str,
    chunk_language: str,
    client_slug: str,
) -> bool:
    if client_slug != DEFAULT_CLIENT_SLUG and similarity < GENERATED_CLIENT_ABSOLUTE_FLOOR:
        return False

    return similarity >= required_similarity_for_client(
        question=question,
        chunk_language=chunk_language,
        client_slug=client_slug,
    )
