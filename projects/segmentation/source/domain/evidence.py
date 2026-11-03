from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class EvidenceAtom:
    family: str
    subtype: str
    source_field: str
    source_text: str
    source_scope: str = "list"
    explicit: bool = True
    confidence: float = 1.0
    rule_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "EvidenceAtom":
        return cls(**value)

