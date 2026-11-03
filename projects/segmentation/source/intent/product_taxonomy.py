from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, Tuple

from config import PRODUCT_TAXONOMY_PATH


@dataclass(frozen=True)
class ProductRule:
    family: str
    aliases: Tuple[str, ...]
    required_context_any: Tuple[str, ...] = ()
    forbidden_context: Tuple[str, ...] = ()
    related_interests: Tuple[str, ...] = ()
    direct_evidence: Tuple[str, ...] = ()
    adjacent_evidence: Tuple[str, ...] = ()
    attributes: Dict[str, object] = field(default_factory=dict)


@lru_cache(maxsize=1)
def _payload() -> Dict[str, object]:
    return json.loads(PRODUCT_TAXONOMY_PATH.read_text(encoding="utf-8"))


def _load_product_taxonomy() -> Tuple[ProductRule, ...]:
    return tuple(
        ProductRule(
            family=str(item["family"]),
            aliases=tuple(item.get("aliases", [])),
            required_context_any=tuple(item.get("required_context_any", [])),
            forbidden_context=tuple(item.get("forbidden_context", [])),
            related_interests=tuple(item.get("related_interests", [])),
            direct_evidence=tuple(item.get("direct_evidence", [])),
            adjacent_evidence=tuple(item.get("adjacent_evidence", [])),
            attributes=dict(item.get("attributes", {})),
        )
        for item in _payload().get("products", [])
    )


PRODUCT_TAXONOMY = _load_product_taxonomy()
TAXONOMY_BY_FAMILY = {rule.family: rule for rule in PRODUCT_TAXONOMY}
TAXONOMY_VERSION = str(_payload().get("version", "unknown"))
