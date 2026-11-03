from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Dict

from ai.relevance_policy import RelevancePolicy
from config import AI_RELEVANCE_POLICY_PATH
from domain.list_profile import ListProfile


BUSINESS_ROLES = {
    "companies", "owners", "decision_makers", "procurement", "professionals",
    "business_contacts", "employees", "investors",
}
CONSUMER_ROLES = {
    "customers_or_prospects", "parents", "patients", "subscribers", "retail_shoppers",
    "students", "graduates", "members",
}
_STRUCTURAL_WORDS = {
    "and", "for", "from", "with", "that", "this", "into", "only", "general",
    "consumer", "commercial", "professional", "equipment", "service", "services",
    "product", "products", "system", "systems", "company", "companies",
}


@lru_cache(maxsize=1)
def relevance_config() -> Dict[str, object]:
    return json.loads(AI_RELEVANCE_POLICY_PATH.read_text(encoding="utf-8"))


def _market_compatible(policy: RelevancePolicy, profile: ListProfile, industry_similarity: float, audience_similarity: float) -> bool:
    roles = set(profile.audience_roles or [profile.audience_role])
    if policy.market_type == "B2B":
        return bool(roles & BUSINESS_ROLES) or "b2b" in profile.business_contexts or (industry_similarity >= 0.46 and audience_similarity >= 0.43)
    if policy.market_type == "B2C":
        return bool(roles & CONSUMER_ROLES) or "consumer_or_individual" in profile.business_contexts or audience_similarity >= 0.42
    return True


def _negative_lexical_hits(policy: RelevancePolicy, profile: ListProfile) -> list[str]:
    profile_text = " ".join([
        profile.list_name,
        profile.original_category,
        profile.category_group,
        profile.source_industry,
        *profile.interests,
        *profile.product_affinities,
        *profile.professional_subtypes,
    ]).lower()
    profile_tokens = set(re.findall(r"[a-z0-9]+", profile_text))
    negative_tokens = {
        token
        for signal in [*policy.negative_signals, *policy.incompatible_contexts]
        for token in re.findall(r"[a-z0-9]+", signal.lower())
        if len(token) >= 4 and token not in _STRUCTURAL_WORDS
    }
    positive_tokens = {
        token
        for signal in [
            *policy.primary_product_concepts,
            *policy.required_context,
            *policy.strong_audience_signals,
            *policy.adjacent_signals,
            *policy.explicit_targets,
            *policy.inferred_targets,
        ]
        for token in re.findall(r"[a-z0-9]+", signal.lower())
        if len(token) >= 4
    }
    negative_tokens -= positive_tokens
    return sorted(profile_tokens & negative_tokens)


def evaluate_dynamic_relevance(policy: RelevancePolicy, profile: ListProfile, retrieval: Dict[str, object]) -> Dict[str, object]:
    thresholds = relevance_config()["thresholds"]
    scores = {
        name: max(-1.0, min(1.0, float(retrieval.get(f"{name}_similarity", 0.0))))
        for name in ("product", "audience", "use_case", "industry", "adjacent", "negative")
    }
    product_context = max(scores["product"], scores["use_case"])
    audience_context = max(scores["audience"], scores["industry"])
    positive_peak = max(product_context, audience_context, scores["adjacent"])
    aggregate = float(retrieval.get("semantic_score", 0.0))
    lexical_support = float(retrieval.get("lexical_score", 0.0)) > 0.0
    supported_dimensions = [
        name for name in ("product", "audience", "use_case", "industry", "adjacent")
        if scores[name] >= float(thresholds["semantic_evidence"])
    ]
    negative_lexical_hits = _negative_lexical_hits(policy, profile)
    contradiction = (
        scores["negative"] >= float(thresholds["negative_material"])
        and (
            scores["negative"] >= positive_peak + float(thresholds["negative_margin"])
            or scores["negative"] >= min(scores["product"], scores["use_case"]) - float(thresholds["negative_margin"])
            or len(negative_lexical_hits) >= 2
        )
    )
    market_compatible = _market_compatible(policy, profile, scores["industry"], scores["audience"])
    meaningful_source = bool(profile.list_name and (profile.original_category or profile.evidence))
    adjacent_audience_threshold = float(
        thresholds["explicit_audience"] if policy.explicit_targets else thresholds["adjacent_audience"]
    )

    tier = "rejected"
    if not contradiction and meaningful_source:
        if (
            scores["product"] >= float(thresholds["direct_product"])
            and scores["use_case"] >= float(thresholds["direct_use_case"])
            and scores["audience"] >= float(thresholds["direct_audience"])
            and max(scores["industry"], scores["adjacent"]) >= float(thresholds["semantic_evidence"])
            and market_compatible
            and len(supported_dimensions) >= 3
        ):
            tier = "direct"
        elif (
            scores["product"] >= float(thresholds["adjacent_product"])
            and scores["audience"] >= adjacent_audience_threshold
            and max(scores["use_case"], scores["industry"], scores["adjacent"]) >= float(thresholds["semantic_evidence"])
            and market_compatible
            and len(supported_dimensions) >= 2
        ):
            tier = "adjacent"
        elif (
            scores["product"] >= float(thresholds["contextual_primary"])
            and scores["use_case"] >= float(thresholds["semantic_evidence"])
            and scores["audience"] >= adjacent_audience_threshold
            and (scores["adjacent"] >= float(thresholds["semantic_evidence"]) or scores["industry"] >= float(thresholds["direct_audience"]))
            and market_compatible
            and len(supported_dimensions) >= 3
        ):
            tier = "contextual"
        elif (
            aggregate >= float(thresholds["fallback_aggregate"])
            and scores["product"] >= float(thresholds["adjacent_product"])
            and scores["audience"] >= adjacent_audience_threshold
            and max(scores["use_case"], scores["adjacent"]) >= float(thresholds["semantic_evidence"])
            and market_compatible
            and len(supported_dimensions) >= 2
        ):
            tier = "fallback"

    evidence = []
    if tier != "rejected":
        evidence.append({
            "source_field": "list_name+original_category",
            "source_text": f"{profile.list_name} | {profile.original_category}"[:500],
            "matched_terms": supported_dimensions,
            "similarities": {name: round(scores[name], 4) for name in supported_dimensions},
        })
    return {
        "tier": tier,
        "scores": scores,
        "aggregate": aggregate,
        "supported_dimensions": supported_dimensions,
        "contradiction": contradiction,
        "market_compatible": market_compatible,
        "lexical_support": lexical_support,
        "negative_lexical_hits": negative_lexical_hits,
        "evidence": evidence,
    }
