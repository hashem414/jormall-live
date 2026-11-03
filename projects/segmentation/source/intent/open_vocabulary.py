from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Dict, List

from config import RELATIONSHIP_RULES_PATH
from .text_normalization import normalize_text, tokenize, unique_normalized


LEAD_WORDS = re.compile(
    r"^(?:please\s+)?(?:find\s+audiences?\s+for|launch\s+a\s+campaign\s+for|create|build|run|launch|make|plan|recommend|find|select|promote|advertise|marketing|campaign|a campaign|an ad|اعمل|انشئ|اطلق|روج|ترويج|حملة)\s+(?:a\s+|an\s+|the\s+|for\s+|ل\s+|لل\s+)*",
    flags=re.I,
)
TARGET_SPLIT = re.compile(r"\s+(?:for|to|targeting|aimed\s+at)\s+", flags=re.I)
LOCATION_SPLIT = re.compile(r"\s+(?:in|across|within)\s+(?:all\s+(?:of\s+)?jordan|jordan|amman|irbid|zarqa|aqaba)\b", flags=re.I)


@lru_cache(maxsize=1)
def relationship_config() -> Dict[str, object]:
    return json.loads(RELATIONSHIP_RULES_PATH.read_text(encoding="utf-8"))


def _without_advertisers(prompt: str, advertisers: List[str]) -> str:
    value = prompt
    for advertiser in sorted(advertisers, key=len, reverse=True):
        value = re.sub(re.escape(advertiser), " ", value, flags=re.I)
    value = re.sub(r"\b(?:on behalf of|campaign for|a company called|company called|store called|brand called)\b", " ", value, flags=re.I)
    value = re.sub(r"\b(?:wants? to promote|is offering|are offering|promoting|selling|sells|promotes|offers|needs)\b", " ", value, flags=re.I)
    return " ".join(value.split())


def _split_negation(value: str) -> tuple[str, List[str]]:
    negated: List[str] = []
    positive = value
    patterns = [
        r"\b(?:not|exclude|excluding|without)\s+(.+?)(?:\s*[-;]\s*|\b(?:but|instead)\b)",
        r"(?:ليس|بدون|استثن(?:اء|ي))\s+(.+?)(?:\s*[-;،]\s*|\bبل\b)",
    ]
    for pattern in patterns:
        match = re.search(pattern, positive, flags=re.I)
        if match:
            negated.append(match.group(1).strip(" ,-"))
            positive = positive[: match.start()] + " " + positive[match.end() :]
    return " ".join(positive.split()), unique_normalized(negated)


def _bridge_arabic(value: str) -> List[str]:
    normalized = normalize_text(value)
    expanded: List[str] = []
    for phrase, concepts in relationship_config().get("arabic_concept_bridge", {}).items():
        if normalize_text(phrase) in normalized:
            expanded.extend(str(concept) for concept in concepts)
    return unique_normalized(expanded)


def expand_open_concepts(values: List[str]) -> List[str]:
    request_text = normalize_text(" ".join(values))
    request_tokens = set(tokenize(request_text))
    expanded: List[str] = []
    for group in relationship_config().get("concept_groups", []):
        seeds = [normalize_text(str(term)) for term in group.get("seed_terms", [])]
        if any((seed in request_text if " " in seed else seed in request_tokens) for seed in seeds if seed):
            expanded.extend(str(term) for term in group.get("evidence_terms", []))
    return unique_normalized(expanded)


def _extract_roles(value: str) -> tuple[List[str], List[str]]:
    normalized = normalize_text(value)
    roles: List[str] = []
    entities: List[str] = []
    for role, aliases in relationship_config().get("role_terms", {}).items():
        hits = [alias for alias in aliases if normalize_text(str(alias)) in normalized]
        if hits:
            roles.append(str(role))
            entities.extend(hits)
    return list(dict.fromkeys(roles)), unique_normalized(entities)


def _campaign_type(value: str) -> str:
    normalized = normalize_text(value)
    scores = {
        name: sum(1 for term in terms if normalize_text(str(term)) in normalized)
        for name, terms in relationship_config().get("campaign_types", {}).items()
    }
    winner = max(scores, key=scores.get, default="")
    return winner if winner and scores[winner] else ""


def extract_open_intent(prompt: str, advertisers: List[str]) -> Dict[str, object]:
    without_advertiser = _without_advertisers(prompt, advertisers)
    positive, negated = _split_negation(without_advertiser)
    product_text = positive
    previous = None
    while product_text != previous:
        previous = product_text
        product_text = LEAD_WORDS.sub("", product_text).strip(" ,-:")
    product_parts = TARGET_SPLIT.split(product_text, maxsplit=1)
    product_text = product_parts[0]
    target_clause = product_parts[1] if len(product_parts) > 1 else ""
    product_text = LOCATION_SPLIT.split(product_text, maxsplit=1)[0]
    product_text = re.sub(r"\s+(?:موجه\s+الى|تستهدف)\s+.*$", "", product_text, flags=re.I)
    product_text = product_text.strip(" ,-:") or positive.strip(" ,-:")

    config = relationship_config()
    stop_terms = {normalize_text(str(term)) for term in config.get("stop_terms", [])}
    concepts = [token for token in tokenize(product_text) if token not in stop_terms and token not in {"for", "the", "and", "with", "من", "في", "على"}]
    concepts.extend(_bridge_arabic(product_text))
    concepts = unique_normalized(concepts)
    roles, entities = _extract_roles(prompt)
    use_cases = unique_normalized([target_clause, *entities])
    confidence = 0.9 if product_text and concepts else (0.55 if product_text else 0.0)
    return {
        "positive_prompt": positive,
        "raw_product_phrases": [product_text] if product_text else [],
        "normalized_product_concepts": concepts,
        "open_product_terms": concepts.copy(),
        "use_cases": use_cases,
        "target_entities": entities,
        "target_roles": roles,
        "campaign_type": _campaign_type(prompt),
        "confidence": confidence,
        "negated_terms": negated,
    }
