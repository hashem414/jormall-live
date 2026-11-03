from __future__ import annotations

from typing import Any, Dict, List

from config import EXCLUSION_RULES_PATH
from .rule_engine import load_rule_file, match_rules


def exclusion_matches(row: Dict[str, Any]) -> List[Dict[str, object]]:
    fields = {"list_name": str(row.get("list_name", "")), "original_category": str(row.get("original_category", ""))}
    return match_rules(fields, load_rule_file(str(EXCLUSION_RULES_PATH))["rules"])


def exclusion_reasons(row: Dict[str, Any]) -> List[str]:
    reasons = [str(match["exclusion_code"]) for match in exclusion_matches(row) if bool(match.get("exclude", True))]
    if not row.get("checked"):
        reasons.append("source_not_checked")
    if int(row.get("quantity", 0)) <= 0:
        reasons.append("nonpositive_quantity")
    if int(row.get("quantity", 0)) != int(row.get("needed_quantity", 0)):
        reasons.append("quantity_mismatch")
    return list(dict.fromkeys(reasons))
