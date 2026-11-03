from __future__ import annotations

import re
from typing import Dict, List, Tuple

from config import INTEREST_RULES_PATH
from .rule_engine import load_rule_file, match_rules, unique_concepts


def row_evidence_fields(list_name: str, source_owner: str, original_category: str, represented_entity: str = "") -> Dict[str, str]:
    remainder = re.sub(re.escape(source_owner), " ", list_name, count=1, flags=re.I) if source_owner else list_name
    return {
        "list_name": list_name,
        "remainder": " ".join(remainder.split()),
        "source_owner": source_owner,
        "represented_entity": represented_entity,
        "original_category": original_category,
    }


def row_evidence_text(list_name: str, source_owner: str, original_category: str) -> str:
    return " ".join(row_evidence_fields(list_name, source_owner, original_category).values())


def classify_profile_facets(fields: Dict[str, str]) -> List[Dict[str, object]]:
    return match_rules(fields, load_rule_file(str(INTEREST_RULES_PATH))["rules"])


def classify_interests(text: str | Dict[str, str]) -> List[Tuple[str, str]]:
    fields = text if isinstance(text, dict) else {"remainder": text, "original_category": text}
    return [(concept, str(match["rule_id"])) for match in classify_profile_facets(fields) for concept in [str(match["concept"])]]


def classify_product_affinities(text: str | Dict[str, str]) -> List[Tuple[str, str]]:
    fields = text if isinstance(text, dict) else {"remainder": text, "original_category": text}
    return [(str(match["concept"]), str(match["rule_id"])) for match in classify_profile_facets(fields) if match.get("product_affinity")]


def classify_category_group(original_category: str | List[Dict[str, object]]) -> str:
    matches = original_category if isinstance(original_category, list) else classify_profile_facets({"original_category": original_category})
    if not matches:
        return "General / Unclassified"
    scores: Dict[str, float] = {}
    for match in matches:
        category = str(match.get("category_group", ""))
        if category:
            scores[category] = scores.get(category, 0.0) + float(match.get("confidence", 0.0))
    return sorted(scores, key=lambda category: (-scores[category], category))[0] if scores else "General / Unclassified"


def category_facets(matches: List[Dict[str, object]]) -> List[str]:
    return unique_concepts(matches, "facet")
