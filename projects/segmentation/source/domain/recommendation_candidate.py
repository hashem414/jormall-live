from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class RecommendationCandidate:
    list_id: str
    tier: str = "rejected"
    score: float = 0.0
    retrieval_score: float = 0.0
    lexical_score: float = 0.0
    semantic_score: float = 0.0
    product_similarity: float = 0.0
    audience_similarity: float = 0.0
    use_case_similarity: float = 0.0
    industry_similarity: float = 0.0
    adjacent_similarity: float = 0.0
    negative_similarity: float = 0.0
    matched_evidence: List[Dict[str, Any]] = field(default_factory=list)
    evidence_families: List[str] = field(default_factory=list)
    supported_product_families: List[str] = field(default_factory=list)
    filter_matches: Dict[str, Any] = field(default_factory=dict)
    class_affinity: str = ""
    class_fit_source: str = "none"
    explanation: str = ""
    diversity_signature: str = ""
    rejected_reasons: List[str] = field(default_factory=list)
    product_relationship: Dict[str, Any] = field(default_factory=dict)
    ranking_breakdown: Dict[str, float] = field(default_factory=dict)
    eligibility_reason: str = ""
    ai_review_relevance: str = ""
    ai_review_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
