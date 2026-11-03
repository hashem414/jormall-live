from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Dict, List, Tuple

from config import INTENT_RULES_PATH
from .product_taxonomy import PRODUCT_TAXONOMY, ProductRule


@lru_cache(maxsize=1)
def _rules() -> Dict[str, object]:
    return json.loads(INTENT_RULES_PATH.read_text(encoding="utf-8"))


def _contains(text: str, phrase: str) -> bool:
    escaped = re.escape(phrase.strip()).replace(r"\ ", r"\s+")
    return re.search(rf"(?<!\w){escaped}(?!\w)", text, re.I) is not None


def resolve_products(prompt: str) -> Tuple[List[ProductRule], bool, List[str]]:
    text = " ".join(prompt.lower().split())
    matches: List[ProductRule] = []
    evidence: List[str] = []
    for rule in PRODUCT_TAXONOMY:
        alias_hits = [alias for alias in rule.aliases if _contains(text, alias)]
        if not alias_hits:
            continue
        if rule.required_context_any and not any(_contains(text, context) for context in rule.required_context_any):
            continue
        if rule.forbidden_context and any(_contains(text, context) for context in rule.forbidden_context):
            continue
        matches.append(rule)
        evidence.append(f"{rule.family}: alias={alias_hits[0]}")

    matched_names = {rule.family for rule in matches}
    suppressed = {
        family_to_remove
        for matched_family, families_to_remove in _rules().get("family_suppression", {}).items()
        if matched_family in matched_names
        for family_to_remove in families_to_remove
    }
    matches = [rule for rule in matches if rule.family not in suppressed]
    for contextual in _rules().get("contextual_family_rules", []):
        family = str(contextual["family"])
        if family not in matched_names or (contextual.get("when_multiple") and len(matched_names) <= 1):
            continue
        if not any(_contains(text, str(term)) for term in contextual.get("required_offer_terms", [])):
            matches = [rule for rule in matches if rule.family != family]
    ambiguous = any(_contains(text, str(token)) for token in _rules().get("ambiguous_terms", []))
    return matches, ambiguous and not matches, evidence
