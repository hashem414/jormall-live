from __future__ import annotations

import re

from domain.operational_constraints import normalize_requested_count

from .schemas import CampaignUnderstanding, OperationalCampaignConstraints


_GENERIC_REACH_WORDS = {
    "a", "an", "the", "to", "for", "of", "among", "about", "campaign",
    "customer", "customers", "user", "users", "person", "people", "recipient",
    "recipients", "audience", "audiences", "reach", "requested", "goal", "send",
    "sending", "target", "targets", "عميل", "عملاء", "مستخدم", "مستخدمين",
    "شخص", "أشخاص", "اشخاص", "حملة", "ل", "لـ",
}
_ASCII_TO_ARABIC_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def _number_patterns(count: int) -> list[str]:
    if count <= 0:
        return []
    patterns = [
        rf"(?<!\d){re.escape(str(count))}(?!\d)",
        rf"(?<!\d){re.escape(f'{count:,}')}(?!\d)",
        rf"(?<!\d){re.escape(str(count).translate(_ASCII_TO_ARABIC_DIGITS))}(?!\d)",
        rf"(?<!\d){re.escape(f'{count:,}'.translate(_ASCII_TO_ARABIC_DIGITS).replace(',', '٬'))}(?!\d)",
    ]
    if count % 1_000_000 == 0:
        units = count // 1_000_000
        patterns.extend([
            rf"(?<!\d){units}\s*m(?![a-z])",
            rf"(?<!\d){units}\s+million\b",
            rf"(?<!\d){units}\s+مليون\b",
            rf"(?<!\d){str(units).translate(_ASCII_TO_ARABIC_DIGITS)}\s+مليون\b",
        ])
    if count % 1_000 == 0:
        units = count // 1_000
        patterns.extend([
            rf"(?<!\d){units}\s*k(?![a-z])",
            rf"(?<!\d){units}\s+thousand\b",
            rf"(?<!\d){units}\s+(?:ألف|الف)\b",
            rf"(?<!\d){str(units).translate(_ASCII_TO_ARABIC_DIGITS)}\s+(?:ألف|الف)\b",
        ])
    return patterns


def _source_pattern(source: str | None) -> str:
    if not source or not source.strip():
        return ""
    parts = [re.escape(part) for part in source.strip().split()]
    return r"\s+".join(parts)


def _contains_reach_marker(text: str, constraints: OperationalCampaignConstraints) -> bool:
    count = normalize_requested_count(constraints.requested_reach_count)
    if count <= 0:
        return False
    source_pattern = _source_pattern(constraints.requested_reach_source_text)
    if source_pattern and re.search(source_pattern, text, re.IGNORECASE):
        return True
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in _number_patterns(count))


def clean_operational_reach_text(text: str, constraints: OperationalCampaignConstraints) -> str:
    value = str(text or "").strip()
    if not value or not _contains_reach_marker(value, constraints):
        return value
    source_pattern = _source_pattern(constraints.requested_reach_source_text)
    if source_pattern:
        value = re.sub(source_pattern, " ", value, flags=re.IGNORECASE)
    for pattern in _number_patterns(normalize_requested_count(constraints.requested_reach_count)):
        value = re.sub(pattern, " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\b(?:requested\s+reach|reach\s+goal|recipient\s+count)\b", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value).strip(" ,;:-")
    tokens = set(re.findall(r"[\w]+", value.lower(), flags=re.UNICODE))
    return "" if tokens and tokens <= _GENERIC_REACH_WORDS else value


def _clean_values(values: list[str], constraints: OperationalCampaignConstraints) -> list[str]:
    cleaned = [clean_operational_reach_text(value, constraints) for value in values]
    return list(dict.fromkeys(value for value in cleaned if value))


def sanitize_operational_reach(understanding: CampaignUnderstanding) -> CampaignUnderstanding:
    constraints = understanding.operational_constraints
    if normalize_requested_count(constraints.requested_reach_count) <= 0:
        return understanding
    products = [
        item.model_copy(update={
            "raw_phrase": clean_operational_reach_text(item.raw_phrase, constraints),
            "normalized_description": clean_operational_reach_text(item.normalized_description, constraints),
            "type": clean_operational_reach_text(item.type, constraints),
            "use_case": clean_operational_reach_text(item.use_case, constraints),
        })
        for item in understanding.products_services
    ]
    updates = {
        "products_services": products,
        "campaign_objective": clean_operational_reach_text(understanding.campaign_objective, constraints),
    }
    for field_name in (
        "explicit_target_audiences", "inferred_target_audiences", "target_roles",
        "target_industries", "buyer_types", "user_types", "purchase_contexts",
        "positive_concepts", "adjacent_concepts", "negative_concepts",
        "false_friend_concepts", "semantic_search_queries",
    ):
        updates[field_name] = _clean_values(getattr(understanding, field_name), constraints)
    return understanding.model_copy(update=updates)


def semantic_text_contains_reach(
    texts: list[str],
    constraints: OperationalCampaignConstraints,
) -> bool:
    return any(_contains_reach_marker(text, constraints) for text in texts if text)
