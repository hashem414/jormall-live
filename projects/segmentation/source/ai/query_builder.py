from __future__ import annotations

import re
from dataclasses import dataclass

from .operational_reach import (
    clean_operational_reach_text,
    sanitize_operational_reach,
    semantic_text_contains_reach,
)
from .schemas import CampaignUnderstanding
from profiles.location_parser import explicit_geography_terms


@dataclass(frozen=True)
class SemanticQueryBundle:
    dimensions: dict[str, str]
    lexical_query: str
    contains_operational_reach: bool = False
    contains_explicit_geography: bool = False


def _section(title: str, values: list[str]) -> str:
    clean = list(dict.fromkeys(value.strip() for value in values if value and value.strip()))
    return (f"{title}:\n" + "\n".join(f"- {value}" for value in clean)) if clean else ""


def _contains_term(text: str, terms: list[str]) -> bool:
    return any(
        re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, flags=re.IGNORECASE | re.UNICODE)
        for term in terms
        if term
    )


def _strip_explicit_geography(text: str, terms: list[str]) -> str:
    cleaned = text
    for term in terms:
        cleaned = re.sub(
            rf"(?<!\w){re.escape(term)}(?!\w)",
            " ",
            cleaned,
            flags=re.IGNORECASE | re.UNICODE,
        )
    lines = []
    for line in cleaned.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        line = re.sub(r"\b(?:in|within|across|throughout|around)\s*$", "", line, flags=re.IGNORECASE).strip(" ,-:/")
        if line and line != "-":
            lines.append(line)
    return "\n".join(lines)


def build_semantic_queries(understanding: CampaignUnderstanding) -> SemanticQueryBundle:
    understanding = sanitize_operational_reach(understanding)
    products = [item.normalized_description for item in understanding.products_services]
    product_types = [item.type for item in understanding.products_services]
    use_cases = [item.use_case for item in understanding.products_services]
    product_text = "\n".join([
        _section("Products or services", products),
        _section("Product types", product_types),
        _section("Brands", understanding.brands),
        _section("Positive commercial concepts", understanding.positive_concepts),
    ])
    if understanding.explicit_target_audiences:
        audience_text = "\n".join([
            f"Market type: {understanding.market_type}",
            _section("Required explicit target audiences", understanding.explicit_target_audiences),
        ])
    else:
        audience_text = "\n".join([
            f"Market type: {understanding.market_type}",
            _section("Inferred target audiences", understanding.inferred_target_audiences),
            _section("Buyer types", understanding.buyer_types),
            _section("User types", understanding.user_types),
            _section("Target roles", understanding.target_roles),
        ])
    use_case_text = "\n".join([
        _section("Use cases", use_cases),
        _section("Purchase contexts", understanding.purchase_contexts),
        f"Campaign objective: {understanding.campaign_objective}",
    ])
    industry_text = "\n".join([
        f"Market type: {understanding.market_type}",
        _section("Target industries", understanding.target_industries),
        _section("Relevant professional roles", understanding.target_roles),
        _section("Business buyers", understanding.buyer_types),
    ])
    adjacent_text = "\n".join([
        _section("Commercially adjacent concepts", understanding.adjacent_concepts),
        _section("Inferred adjacent audiences", understanding.inferred_target_audiences),
        _section("Additional semantic searches", understanding.semantic_search_queries),
    ])
    # Contrast sentences often repeat the desired concept. Prefer the planner's
    # clean unwanted concepts so the negative vector represents only conflict.
    negative_values = understanding.negative_concepts or understanding.false_friend_concepts
    negative_text = _section("Commercially incompatible concepts", negative_values)
    dimensions = {
        "product": product_text,
        "audience": audience_text,
        "use_case": use_case_text,
        "industry": industry_text,
        "adjacent": adjacent_text,
        "negative": negative_text,
    }
    lexical_values = [
        *understanding.brands,
        *[item.raw_phrase for item in understanding.products_services],
        *products,
        *understanding.explicit_target_audiences,
        *understanding.inferred_target_audiences,
        *understanding.target_roles,
        *understanding.target_industries,
        *understanding.positive_concepts,
    ]
    constraints = understanding.operational_constraints
    geography_terms = explicit_geography_terms(
        understanding.explicit_filters.cities,
        understanding.explicit_filters.areas,
    )
    dimensions = {
        name: _strip_explicit_geography(text, geography_terms)
        for name, text in dimensions.items()
    }
    cleaned_lexical_values = [
        _strip_explicit_geography(value, geography_terms)
        for value in lexical_values
        if value
    ]
    lexical_query = " ".join(dict.fromkeys(value for value in cleaned_lexical_values if value))
    dimensions = {
        name: clean_operational_reach_text(text, constraints)
        for name, text in dimensions.items()
    }
    lexical_query = clean_operational_reach_text(
        lexical_query,
        constraints,
    )
    contains_reach = semantic_text_contains_reach(
        [*dimensions.values(), lexical_query],
        constraints,
    )
    contains_geography = any(
        _contains_term(text, geography_terms)
        for text in [*dimensions.values(), lexical_query]
    )
    return SemanticQueryBundle(
        dimensions=dimensions,
        lexical_query=lexical_query,
        contains_operational_reach=contains_reach,
        contains_explicit_geography=contains_geography,
    )
