from __future__ import annotations

from typing import Dict, List, Tuple

from config import FINANCE_RULES_PATH
from .rule_engine import load_rule_file, match_rules


def classify_finance_subtypes(evidence: str | Dict[str, str]) -> List[Tuple[str, str]]:
    fields = evidence if isinstance(evidence, dict) else {"remainder": evidence, "original_category": evidence}
    return [(str(match["concept"]), str(match["rule_id"])) for match in match_rules(fields, load_rule_file(str(FINANCE_RULES_PATH))["rules"])]
