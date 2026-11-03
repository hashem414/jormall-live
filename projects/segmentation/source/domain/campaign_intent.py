from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ExplicitFilters:
    cities: List[str] = field(default_factory=list)
    areas: List[str] = field(default_factory=list)
    gender: List[str] = field(default_factory=list)
    classes: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    age_min: Optional[int] = None
    age_max: Optional[int] = None


@dataclass(frozen=True)
class ProductAttributes:
    price_band: str = ""
    positioning: List[str] = field(default_factory=list)
    purchase_type: str = ""
    financing_accessible: bool = False
    professional_use: bool = False
    campaign_type: str = ""


@dataclass(frozen=True)
class CampaignIntent:
    raw_prompt: str
    advertisers: List[str] = field(default_factory=list)
    advertiser_catalog_matches: List[str] = field(default_factory=list)
    brands: List[str] = field(default_factory=list)
    products: List[str] = field(default_factory=list)
    product_families: List[str] = field(default_factory=list)
    raw_product_phrases: List[str] = field(default_factory=list)
    normalized_product_concepts: List[str] = field(default_factory=list)
    known_product_families: List[str] = field(default_factory=list)
    open_product_terms: List[str] = field(default_factory=list)
    use_cases: List[str] = field(default_factory=list)
    target_entities: List[str] = field(default_factory=list)
    target_roles: List[str] = field(default_factory=list)
    target_industries: List[str] = field(default_factory=list)
    audience_type: str = "unspecified"
    campaign_type: str = ""
    offer: str = ""
    confidence: float = 0.0
    negated_terms: List[str] = field(default_factory=list)
    intent_schema_version: str = "campaign-intent-v2"
    interpretation_provider: str = "deterministic"
    model_call_count: int = 0
    llm_intent_used: bool = False
    llm_intent_latency_ms: int = 0
    llm_intent_error: str = ""
    explicit_filters: ExplicitFilters = field(default_factory=ExplicitFilters)
    product_attributes: ProductAttributes = field(default_factory=ProductAttributes)
    class_affinity: Dict[str, str] = field(default_factory=dict)
    class_primary: str = ""
    class_broad_market: bool = False
    class_affinity_source: str = "none"
    requested_reach_count: Optional[int] = None
    requested_reach_explicit: bool = False
    requested_reach_source_text: str = ""
    candidate_scope: str = "direct_adjacent_contextual"
    clarification_needed: bool = False
    ambiguity_notes: List[str] = field(default_factory=list)
    interpretation_evidence: List[str] = field(default_factory=list)
    campaign_understanding_id: str = ""
    positive_concepts: List[str] = field(default_factory=list)
    adjacent_concepts: List[str] = field(default_factory=list)
    false_friend_concepts: List[str] = field(default_factory=list)
    semantic_search_queries: List[str] = field(default_factory=list)
    explicit_target_audiences: List[str] = field(default_factory=list)
    inferred_target_audiences: List[str] = field(default_factory=list)
    buyer_types: List[str] = field(default_factory=list)
    user_types: List[str] = field(default_factory=list)
    purchase_contexts: List[str] = field(default_factory=list)
    interpretation_summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "CampaignIntent":
        data = dict(value)
        data["explicit_filters"] = ExplicitFilters(**data.get("explicit_filters", {}))
        data["product_attributes"] = ProductAttributes(**data.get("product_attributes", {}))
        return cls(**data)
