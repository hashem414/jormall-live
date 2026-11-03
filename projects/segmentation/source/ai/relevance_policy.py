from __future__ import annotations

from dataclasses import dataclass

from .schemas import CampaignUnderstanding


@dataclass(frozen=True)
class RelevancePolicy:
    primary_product_concepts: list[str]
    required_context: list[str]
    strong_audience_signals: list[str]
    adjacent_signals: list[str]
    negative_signals: list[str]
    incompatible_contexts: list[str]
    explicit_targets: list[str]
    inferred_targets: list[str]
    market_type: str


def build_relevance_policy(understanding: CampaignUnderstanding) -> RelevancePolicy:
    products = [item.normalized_description for item in understanding.products_services]
    use_cases = [item.use_case for item in understanding.products_services if item.use_case]
    return RelevancePolicy(
        primary_product_concepts=list(dict.fromkeys([*products, *understanding.positive_concepts])),
        required_context=list(dict.fromkeys([*use_cases, *understanding.purchase_contexts])),
        strong_audience_signals=list(dict.fromkeys([
            *understanding.explicit_target_audiences,
            *understanding.target_roles,
            *understanding.target_industries,
            *understanding.buyer_types,
            *understanding.user_types,
        ])),
        adjacent_signals=understanding.adjacent_concepts,
        negative_signals=understanding.negative_concepts,
        incompatible_contexts=understanding.false_friend_concepts,
        explicit_targets=understanding.explicit_target_audiences,
        inferred_targets=understanding.inferred_target_audiences,
        market_type=understanding.market_type,
    )
