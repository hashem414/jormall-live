from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Iterable, List, Mapping

from domain.campaign_intent import CampaignIntent, ExplicitFilters, ProductAttributes
from .advertiser_parser import extract_advertisers, match_advertisers
from .class_affinity import infer_class_positioning, normalize_class_positioning
from .filters import parse_explicit_filters
from .open_vocabulary import extract_open_intent
from .llm_parser import parse_optional_structured_intent
from .product_disambiguation import resolve_products
from config import INTENT_RULES_PATH


@lru_cache(maxsize=1)
def _intent_rules() -> dict[str, object]:
    return json.loads(INTENT_RULES_PATH.read_text(encoding="utf-8"))


def parse_campaign_intent(
    prompt: str,
    catalogue_companies: Iterable[str] | Mapping[str, str] = (),
    candidate_scope: str = "direct_adjacent_contextual",
    parsed_advertisers: List[str] | None = None,
    parsed_advertiser_matches: List[str] | None = None,
    llm_intent_enabled: bool | None = None,
) -> CampaignIntent:
    advertisers = extract_advertisers(prompt) if parsed_advertisers is None else parsed_advertisers
    llm_result = parse_optional_structured_intent(prompt, enabled=llm_intent_enabled)
    model_intent = llm_result.payload
    advertisers = list(dict.fromkeys([*advertisers, *model_intent.get("advertisers", [])]))
    advertiser_matches = parsed_advertiser_matches
    if advertiser_matches is None or model_intent.get("advertisers"):
        advertiser_matches, _comparisons = match_advertisers(advertisers, catalogue_companies) if advertisers else ([], 0)
    open_intent = extract_open_intent(prompt, advertisers)
    product_rules, clarification, interpretation_evidence = resolve_products(str(open_intent["positive_prompt"]))
    products = []
    named_families = set()
    for named in _intent_rules().get("named_product_patterns", []):
        match = re.search(str(named["pattern"]), prompt, re.I)
        if match:
            product_name = str(named["name_template"])
            for index in range(1, len(match.groups()) + 1):
                product_name = product_name.replace("{" + str(index) + "}", (match.group(index) or "").title())
            products.append(" ".join(product_name.split()))
            named_families.add(str(named["family"]))
    products.extend(rule.family.replace("_", " ").title() for rule in product_rules if rule.family not in named_families)
    brands = [str(brand["name"]) for brand in _intent_rules().get("brands", []) if any(re.search(str(pattern), prompt, re.I) for pattern in brand.get("patterns", []))]
    brands = list(dict.fromkeys([*brands, *model_intent.get("brands", [])]))
    attributes_data = ProductAttributes().__dict__.copy()
    for rule in product_rules:
        for key, value in rule.attributes.items():
            if value not in (None, "", [], False):
                attributes_data[key] = value
    attributes = ProductAttributes(**attributes_data)
    known_families = [rule.family for rule in product_rules]
    known_alias_tokens = {
        token
        for rule in product_rules
        for alias in rule.aliases
        for token in re.findall(r"[\w]+", alias.lower(), flags=re.UNICODE)
    }
    for key in ("raw_product_phrases", "normalized_product_concepts", "open_product_terms", "use_cases", "target_entities", "target_roles"):
        if model_intent.get(key):
            open_intent[key] = list(dict.fromkeys([*open_intent[key], *model_intent[key]]))
    if model_intent.get("campaign_type"):
        open_intent["campaign_type"] = model_intent["campaign_type"]
    if model_intent.get("confidence") is not None:
        open_intent["confidence"] = max(float(open_intent["confidence"]), float(model_intent["confidence"]))

    open_terms = [term for term in open_intent["open_product_terms"] if term not in known_alias_tokens]
    # A qualified open phrase resolves otherwise ambiguous short tokens such as
    # "AC Milan shirts" and "mobile cranes" without forcing a known family.
    ambiguous_tokens = {token for term in _intent_rules().get("ambiguous_terms", []) for token in re.findall(r"[\w]+", str(term).lower(), flags=re.UNICODE)}
    meaningful_open = [term for term in open_terms if term not in ambiguous_tokens]
    clarification = clarification and not meaningful_open
    if llm_result.used:
        clarification = bool(model_intent.get("clarification_needed", clarification))

    local_filters = parse_explicit_filters(prompt)
    model_filters = model_intent.get("explicit_filters", {})
    explicit_filters = ExplicitFilters(
        cities=list(dict.fromkeys([*local_filters.cities, *model_filters.get("cities", [])])),
        areas=list(dict.fromkeys([*local_filters.areas, *model_filters.get("areas", [])])),
        gender=list(dict.fromkeys([*local_filters.gender, *model_filters.get("gender", [])])),
        classes=list(dict.fromkeys([*local_filters.classes, *model_filters.get("classes", [])])),
        age_min=local_filters.age_min if local_filters.age_min is not None else model_filters.get("age_min"),
        age_max=local_filters.age_max if local_filters.age_max is not None else model_filters.get("age_max"),
    )
    model_positioning = list(model_intent.get("product_positioning", []))
    if model_positioning:
        attributes = ProductAttributes(**{
            **attributes.__dict__,
            "positioning": list(dict.fromkeys([*attributes.positioning, *model_positioning])),
        })
    legacy_positioning = infer_class_positioning(attributes)
    class_positioning = normalize_class_positioning(
        [
            *(f"{name}:{strength}" for name, strength in legacy_positioning.affinity.items()),
            *model_intent.get("likely_class_affinity", []),
        ],
        primary_class=legacy_positioning.primary_class,
        broad_market=legacy_positioning.broad_market,
        explicit_classes=explicit_filters.classes,
        source="explicit_prompt" if explicit_filters.classes else "legacy_inference",
    )
    intent = CampaignIntent(
        raw_prompt=prompt,
        advertisers=advertisers,
        advertiser_catalog_matches=advertiser_matches,
        brands=brands,
        products=list(dict.fromkeys(products)),
        product_families=known_families,
        raw_product_phrases=list(open_intent["raw_product_phrases"]),
        normalized_product_concepts=list(open_intent["normalized_product_concepts"]),
        known_product_families=known_families,
        open_product_terms=open_terms,
        use_cases=list(open_intent["use_cases"]),
        target_entities=list(open_intent["target_entities"]),
        target_roles=list(open_intent["target_roles"]),
        target_industries=list(model_intent.get("target_industries", [])),
        audience_type=str(model_intent.get("audience_type", "unspecified")),
        campaign_type=str(open_intent["campaign_type"] or attributes.campaign_type),
        offer=str(model_intent.get("offer", "")),
        confidence=float(open_intent["confidence"]),
        negated_terms=list(open_intent["negated_terms"]),
        interpretation_provider=llm_result.provider,
        model_call_count=llm_result.call_count,
        llm_intent_used=llm_result.used,
        llm_intent_latency_ms=llm_result.latency_ms,
        llm_intent_error=llm_result.error,
        explicit_filters=explicit_filters,
        product_attributes=attributes,
        class_affinity=class_positioning.affinity,
        class_primary=class_positioning.primary_class,
        class_broad_market=class_positioning.broad_market,
        class_affinity_source=class_positioning.source,
        candidate_scope=candidate_scope,
        clarification_needed=clarification,
        ambiguity_notes=list(model_intent.get("ambiguity_notes", [])),
        interpretation_evidence=interpretation_evidence,
    )
    return intent
