from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .evidence import EvidenceAtom


@dataclass(frozen=True)
class ListProfile:
    list_id: str
    list_name: str
    source_owner: str = ""
    represented_entity: str = ""
    represented_entity_confidence: float = 0.0
    represented_entity_evidence: List[str] = field(default_factory=list)
    source_industry: str = ""
    category_group: str = ""
    category_facets: List[str] = field(default_factory=list)
    business_contexts: List[str] = field(default_factory=list)
    original_category: str = ""
    original_row_text: str = ""
    audience_role: str = "unknown"
    audience_role_confidence: float = 0.0
    audience_roles: List[str] = field(default_factory=list)
    audience_role_evidence: List[Dict[str, Any]] = field(default_factory=list)
    interests: List[str] = field(default_factory=list)
    product_affinities: List[str] = field(default_factory=list)
    professional_subtypes: List[str] = field(default_factory=list)
    finance_subtypes: List[str] = field(default_factory=list)
    gender: str = ""
    economic_class: str = ""
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    cities: List[str] = field(default_factory=list)
    governorates: List[str] = field(default_factory=list)
    areas: List[str] = field(default_factory=list)
    coverage_type: str = "unknown"
    country: str = "Jordan"
    location_source: str = "none"
    location_confidence: float = 0.0
    location_evidence: str = ""
    quantity: int = 0
    list_date: Optional[str] = None
    eligible: bool = True
    exclusion_reasons: List[str] = field(default_factory=list)
    evidence: List[EvidenceAtom] = field(default_factory=list)
    classification_version: str = "list-profile-v1"

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["evidence"] = [item.to_dict() for item in self.evidence]
        return value

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "ListProfile":
        data = dict(value)
        data["evidence"] = [EvidenceAtom.from_dict(item) for item in data.get("evidence", [])]
        return cls(**data)
