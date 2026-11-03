from __future__ import annotations

from domain.campaign_intent import CampaignIntent
from domain.list_profile import ListProfile
from domain.recommendation_candidate import RecommendationCandidate
from intent.class_affinity import class_distance


def explain_candidate(intent: CampaignIntent, profile: ListProfile, candidate: RecommendationCandidate) -> str:
    dimensions = [
        ("product", candidate.product_similarity),
        ("target audience", candidate.audience_similarity),
        ("use case", candidate.use_case_similarity),
        ("industry", candidate.industry_similarity),
        ("adjacent audience", candidate.adjacent_similarity),
    ]
    strongest = sorted(dimensions, key=lambda item: -item[1])[:3]
    support = ", ".join(f"{name} {score:.2f}" for name, score in strongest)
    source = f"{profile.list_name} | {profile.original_category}"[:240]
    target = ", ".join(intent.explicit_target_audiences or intent.target_entities[:3]) or "the interpreted campaign audience"
    relationship = {
        "direct": "strong product and audience compatibility",
        "adjacent": "a meaningful commercial audience relationship",
        "contextual": "supporting product or audience context",
        "fallback": "a weaker but genuine commercial relationship",
    }.get(candidate.tier, "supported relevance")
    review = f" AI review: {candidate.ai_review_reason}" if candidate.ai_review_reason else ""
    class_note = ""
    distance = class_distance(intent.class_primary, profile.economic_class)
    if (
        candidate.class_affinity in {"weak", "none"}
        and distance is not None
        and intent.class_primary
        and intent.class_affinity_source != "none"
    ):
        class_note = (
            f" Class fit is {candidate.class_affinity} because {profile.economic_class} is "
            f"{distance} ordinal step{'s' if distance != 1 else ''} from the "
            f"{intent.class_affinity_source.replace('_', ' ')} {intent.class_primary} positioning."
        )
    return f"{candidate.tier.title()}: {relationship} for {target}. Catalogue evidence: {source}. Semantic support: {support}.{class_note}{review}"
