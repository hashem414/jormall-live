from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


MarketType = Literal["B2B", "B2C", "BOTH", "UNSPECIFIED"]
ProductContext = Literal["professional", "consumer", "both", "unspecified"]
ClassStrength = Literal["strong", "moderate", "weak", "none"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AdvertiserUnderstanding(StrictModel):
    name: str
    explicitly_mentioned: bool


class ProductServiceUnderstanding(StrictModel):
    raw_phrase: str
    normalized_description: str
    type: str
    use_case: str
    professional_or_consumer: ProductContext
    confidence: float = Field(ge=0.0, le=1.0)


class CampaignExplicitFilters(StrictModel):
    cities: list[str]
    areas: list[str]
    gender: Literal["Female", "Male", "Mixed", "unspecified"]
    age_min: Optional[int]
    age_max: Optional[int]
    classes: list[str]
    categories: list[str]


class OperationalCampaignConstraints(StrictModel):
    requested_reach_count: Optional[int] = Field(ge=1)
    requested_reach_explicit: bool
    requested_reach_source_text: Optional[str]


class ClassAffinityValues(StrictModel):
    economy: ClassStrength
    economy_plus: ClassStrength
    middle: ClassStrength
    middle_plus: ClassStrength
    upper: ClassStrength


class ClassPositioning(StrictModel):
    explicit_user_target: bool
    broad_market: bool
    primary_class: Optional[str]
    affinity: ClassAffinityValues


class InferredPreferences(StrictModel):
    age_affinity: str
    gender_affinity: str


class AmbiguityAssessment(StrictModel):
    ambiguous: bool
    description: str
    clarification_required: bool


class CampaignUnderstanding(StrictModel):
    original_request: str
    language: str
    advertiser: AdvertiserUnderstanding
    brands: list[str]
    products_services: list[ProductServiceUnderstanding]
    campaign_objective: str
    market_type: MarketType
    explicit_target_audiences: list[str]
    inferred_target_audiences: list[str]
    target_roles: list[str]
    target_industries: list[str]
    buyer_types: list[str]
    user_types: list[str]
    purchase_contexts: list[str]
    positive_concepts: list[str]
    adjacent_concepts: list[str]
    negative_concepts: list[str]
    false_friend_concepts: list[str]
    semantic_search_queries: list[str]
    operational_constraints: OperationalCampaignConstraints
    class_positioning: ClassPositioning
    explicit_filters: CampaignExplicitFilters
    inferred_preferences: InferredPreferences
    ambiguity: AmbiguityAssessment
    interpretation_summary: str


class CandidateReviewItem(StrictModel):
    candidate_id: str
    relevance: Literal["strong", "moderate", "weak", "wrong"]
    reason_summary: str


class CandidateReview(StrictModel):
    items: list[CandidateReviewItem]
