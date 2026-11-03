from __future__ import annotations

import re
from typing import Dict, List

from .location_parser import parse_location
from .raw_parser import split_dash_outside_parentheses


ADMINISTRATIVE_SUFFIXES = re.compile(r"\b(no answer|management|database|customer database|general|branch|delivery|app)\b", re.I)


def _clean(value: str) -> str:
    return " ".join(value.strip(" ,-–—").split())


def parse_entities(source_owner: str, list_name: str, location_hint: str = "", original_category: str = "") -> Dict[str, object]:
    owner = _clean(source_owner)
    represented = ""
    confidence = 0.0
    evidence: List[str] = []

    owner_parts = [_clean(part) for part in re.split(r"\s+[–—]\s+", owner) if _clean(part)]
    if len(owner_parts) > 1 and not ADMINISTRATIVE_SUFFIXES.search(owner_parts[-1]):
        owner = owner_parts[0]
        represented = " - ".join(owner_parts[1:])
        confidence = 0.88
        evidence.append("source_owner_en_dash_suffix")

    explicit_patterns = [
        r"\b(?:customers?|clients?|members?|subscribers?)\s+(?:of|for|at)\s+([^\-(]+)",
        r"\b(?:employees?|staff)\s+(?:of|at)\s+([^\-(]+)",
    ]
    for pattern in explicit_patterns:
        match = re.search(pattern, list_name, re.I)
        if match:
            represented = _clean(match.group(1))
            confidence = 0.95
            evidence = ["explicit_relationship_grammar"]
            break

    if not represented and location_hint:
        segments = split_dash_outside_parentheses(location_hint)
        if len(segments) >= 2:
            candidate = _clean(segments[0])
            rest = " - ".join(segments[1:])
            if candidate and parse_location(rest)["coverage_type"] != "unknown" and parse_location(candidate)["coverage_type"] == "unknown" and not ADMINISTRATIVE_SUFFIXES.search(candidate):
                represented = candidate
                confidence = 0.78
                evidence = ["non_geographic_segment_before_location"]
        elif "(" not in list_name and len(segments) == 1:
            candidate = _clean(segments[0])
            if candidate and parse_location(candidate)["coverage_type"] == "unknown" and candidate.lower() != original_category.lower():
                represented = candidate
                confidence = 0.68
                evidence = ["undated_owner_suffix"]

    return {
        "source_owner": owner,
        "represented_entity": represented,
        "represented_entity_confidence": confidence,
        "represented_entity_evidence": evidence,
    }
