from __future__ import annotations

from typing import Dict, List, Tuple

from config import AUDIENCE_ROLE_RULES_PATH
from .rule_engine import load_rule_file, match_rules, unique_concepts


def classify_audience_roles(fields: Dict[str, str]) -> Tuple[List[str], float, List[Dict[str, object]]]:
    matches = match_rules(fields, load_rule_file(str(AUDIENCE_ROLE_RULES_PATH))["rules"])
    roles = unique_concepts(matches)
    confidence = max((float(match.get("confidence", 0.0)) for match in matches), default=0.2)
    evidence = [
        {"role": match["concept"], "confidence": match["confidence"], "rule_id": match["rule_id"], "source_field": match["source_field"], "matched_text": match["matched_text"]}
        for match in matches
    ]
    return roles, confidence, evidence


def classify_audience_role(evidence: str | Dict[str, str]) -> Tuple[str, float, str]:
    fields = evidence if isinstance(evidence, dict) else {"remainder": evidence, "original_category": evidence}
    roles, confidence, matches = classify_audience_roles(fields)
    return (roles[0], confidence, str(matches[0]["rule_id"])) if roles else ("unknown", 0.2, "role.unknown")
