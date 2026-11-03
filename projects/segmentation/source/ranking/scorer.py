from __future__ import annotations

import json
import math
from typing import Dict, List, Tuple

from ai.relevance_policy import RelevancePolicy
from domain.campaign_intent import CampaignIntent
from domain.list_profile import ListProfile
from domain.recommendation_candidate import RecommendationCandidate
from intent.class_affinity import affinity_strength
from .diversity import apply_diversity
from .dynamic_relevance import evaluate_dynamic_relevance
from .eligibility import hard_eligibility
from .recency import recency_factor
from config import AI_RELEVANCE_POLICY_PATH, RANKING_WEIGHTS_PATH


_RANKING_CONFIG = json.loads(RANKING_WEIGHTS_PATH.read_text(encoding="utf-8"))
_AI_CONFIG = json.loads(AI_RELEVANCE_POLICY_PATH.read_text(encoding="utf-8"))
TIER_BASE = _RANKING_CONFIG["tier_base"]
WEIGHTS = _RANKING_CONFIG["weights"]
SEMANTIC_WEIGHTS = _AI_CONFIG["score_weights"]
RANKING_VERSION = f"{_RANKING_CONFIG['version']}+{_AI_CONFIG['version']}"


def _advertiser_match(intent: CampaignIntent, profile: ListProfile) -> bool:
    candidates = {value.lower().strip() for value in [profile.source_owner, profile.represented_entity] if value}
    requested = {value.lower().strip() for value in [*intent.advertisers, *intent.advertiser_catalog_matches] if value}
    return bool(candidates & requested)


def rank_candidates(
    intent: CampaignIntent,
    policy: RelevancePolicy,
    profiles: Dict[str, ListProfile],
    retrieval_rows: List[Dict[str, object]],
) -> Tuple[List[Tuple[ListProfile, RecommendationCandidate]], Dict[str, int]]:
    ranked: List[Tuple[ListProfile, RecommendationCandidate]] = []
    hard_rejected = 0
    zero_evidence = 0
    contradiction_rejected = 0
    for retrieval in retrieval_rows:
        profile = profiles.get(str(retrieval["list_id"]))
        if not profile:
            continue
        eligible, filter_matches, failures = hard_eligibility(intent, profile)
        if not eligible:
            hard_rejected += 1
            continue
        relevance = evaluate_dynamic_relevance(policy, profile, retrieval)
        if relevance["tier"] == "rejected":
            zero_evidence += 1
            contradiction_rejected += int(bool(relevance["contradiction"]))
            continue
        scores = relevance["scores"]
        candidate = RecommendationCandidate(
            list_id=profile.list_id,
            tier=str(relevance["tier"]),
            retrieval_score=float(retrieval.get("fused_score", 0.0)),
            lexical_score=float(retrieval.get("lexical_score", 0.0)),
            semantic_score=float(retrieval.get("semantic_score", 0.0)),
            product_similarity=float(scores["product"]),
            audience_similarity=float(scores["audience"]),
            use_case_similarity=float(scores["use_case"]),
            industry_similarity=float(scores["industry"]),
            adjacent_similarity=float(scores["adjacent"]),
            negative_similarity=float(scores["negative"]),
            filter_matches=filter_matches,
            matched_evidence=list(relevance["evidence"]),
            evidence_families=[f"semantic:{name}" for name in relevance["supported_dimensions"]],
            product_relationship={
                "strength": str(relevance["tier"]),
                "score": round(float(relevance["aggregate"]), 6),
                "semantic_score": round(float(relevance["aggregate"]), 6),
                "contradiction": bool(relevance["contradiction"]),
                "market_compatible": bool(relevance["market_compatible"]),
            },
        )
        score = float(TIER_BASE[candidate.tier])
        dimension_score = sum(float(scores[name]) * float(SEMANTIC_WEIGHTS[name]) for name in ("product", "audience", "use_case", "industry", "adjacent", "negative"))
        lexical_score = min(float(SEMANTIC_WEIGHTS["lexical"]), candidate.lexical_score * float(SEMANTIC_WEIGHTS["lexical"]))
        score += dimension_score + lexical_score
        candidate.eligibility_reason = f"dynamic_semantic_policy:{candidate.tier}"
        if _advertiser_match(intent, profile):
            score += float(WEIGHTS["advertiser"])
            candidate.evidence_families.append("advertiser_relationship")
        candidate.class_affinity = affinity_strength(intent.class_affinity, profile.economic_class)
        candidate.class_fit_source = intent.class_affinity_source
        if candidate.class_affinity == "strong":
            score += float(WEIGHTS["class_affinity_strong"])
        elif candidate.class_affinity == "moderate":
            score += float(WEIGHTS["class_affinity_moderate"])
        if filter_matches and all(bool(value) for value in filter_matches.values()):
            score += float(WEIGHTS["location"])
        score += recency_factor(profile.list_date) * float(WEIGHTS["recency"])
        score += min(2.0, math.log10(max(1, profile.quantity)) * float(WEIGHTS["quantity"]))
        candidate.ranking_breakdown = {
            "tier_base": float(TIER_BASE[candidate.tier]),
            "semantic_dimensions": round(dimension_score, 4),
            "lexical": round(lexical_score, 4),
            "negative_penalty": round(float(scores["negative"]) * abs(float(SEMANTIC_WEIGHTS["negative"])), 4),
        }
        candidate.score = round(score, 4)
        ranked.append((profile, candidate))
    ranked.sort(key=lambda item: (-item[1].score, item[0].list_id))
    ranked = apply_diversity(ranked)
    return ranked, {
        "hard_rejected": hard_rejected,
        "zero_evidence_rejected": zero_evidence,
        "contradiction_rejected": contradiction_rejected,
    }
