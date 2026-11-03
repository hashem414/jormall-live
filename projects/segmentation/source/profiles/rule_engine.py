from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Mapping

from intent.text_normalization import normalize_text


@lru_cache(maxsize=16)
def load_rule_file(path: str) -> Dict[str, object]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def match_rules(fields: Mapping[str, str], rules: Iterable[Dict[str, object]]) -> List[Dict[str, object]]:
    matches: List[Dict[str, object]] = []
    normalized_fields = {name: normalize_text(value) for name, value in fields.items()}
    for rule in rules:
        source_fields = [str(name) for name in rule.get("source_fields", fields.keys())]
        for source_field in source_fields:
            source_text = normalized_fields.get(source_field, "")
            if not source_text:
                continue
            for pattern in rule.get("patterns", []):
                match = re.search(str(pattern), source_text, flags=re.I | re.UNICODE)
                if not match:
                    continue
                matches.append({
                    **rule,
                    "source_field": source_field,
                    "source_text": fields.get(source_field, ""),
                    "matched_text": match.group(0),
                })
                break
            else:
                continue
            break
    return matches


def unique_concepts(matches: Iterable[Dict[str, object]], key: str = "concept") -> List[str]:
    ordered = sorted(matches, key=lambda item: (-float(item.get("confidence", 0.0)), str(item.get("rule_id", ""))))
    return list(dict.fromkeys(str(item[key]) for item in ordered if item.get(key)))
