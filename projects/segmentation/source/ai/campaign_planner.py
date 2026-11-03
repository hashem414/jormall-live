from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from config import (
    AI_REQUIRED,
    INTENT_SCHEMA_VERSION,
    LLM_INTENT_ENABLED,
    OPENAI_CHAT_MODEL,
    OPENAI_CONFIGURED,
    OPENAI_INTENT_TIMEOUT_SECONDS,
    OPENAI_INTENT_TRANSIENT_RETRIES,
)
from domain.campaign_intent import CampaignIntent, ExplicitFilters, ProductAttributes
from domain.operational_constraints import normalize_requested_count
from intent.advertiser_parser import match_advertisers
from intent.class_affinity import normalize_class_positioning
from intent.product_disambiguation import resolve_products

from .openai_client import create_openai_client, safe_openai_error
from .operational_reach import sanitize_operational_reach
from .prompt_templates import CAMPAIGN_PLANNER_SYSTEM_PROMPT
from .schemas import (
    AdvertiserUnderstanding,
    AmbiguityAssessment,
    CampaignExplicitFilters,
    CampaignUnderstanding,
    ClassAffinityValues,
    ClassPositioning as SchemaClassPositioning,
    InferredPreferences,
    OperationalCampaignConstraints,
    ProductServiceUnderstanding,
)


@dataclass(frozen=True)
class CampaignPlanResult:
    understanding: CampaignUnderstanding | None = None
    understanding_id: str = ""
    provider: str = "openai"
    attempted: bool = False
    succeeded: bool = False
    call_count: int = 0
    latency_ms: int = 0
    error: str = ""
    usage: dict[str, int] = field(default_factory=dict)


def _usage(response: Any) -> dict[str, int]:
    value = getattr(response, "usage", None)
    if value is None:
        return {}
    result = {}
    for source, target in (("input_tokens", "input_tokens"), ("output_tokens", "output_tokens"), ("total_tokens", "total_tokens")):
        item = getattr(value, source, None)
        if isinstance(item, int):
            result[target] = item
    return result


def _understanding_id(understanding: CampaignUnderstanding) -> str:
    canonical = json.dumps(understanding.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256((uuid.uuid4().hex + canonical).encode("utf-8")).hexdigest()[:20]
    return f"cu_{digest}"


def _schema_affinity(understanding: CampaignUnderstanding) -> dict[str, str]:
    values = understanding.class_positioning.affinity
    return {
        "Economy": values.economy,
        "Economy Plus": values.economy_plus,
        "Middle": values.middle,
        "Middle Plus": values.middle_plus,
        "Upper": values.upper,
    }


def _schema_positioning(value: object) -> SchemaClassPositioning:
    positioning = value
    return SchemaClassPositioning(
        explicit_user_target=positioning.explicit,
        broad_market=positioning.broad_market,
        primary_class=positioning.primary_class or None,
        affinity=ClassAffinityValues(
            economy=positioning.affinity["Economy"],
            economy_plus=positioning.affinity["Economy Plus"],
            middle=positioning.affinity["Middle"],
            middle_plus=positioning.affinity["Middle Plus"],
            upper=positioning.affinity["Upper"],
        ),
    )


def normalize_campaign_understanding(understanding: CampaignUnderstanding) -> CampaignUnderstanding:
    constraints = understanding.operational_constraints
    reach_count = normalize_requested_count(constraints.requested_reach_count)
    normalized_constraints = OperationalCampaignConstraints(
        requested_reach_count=reach_count or None,
        requested_reach_explicit=bool(reach_count),
        requested_reach_source_text=(constraints.requested_reach_source_text or "").strip() or None,
    )
    understanding = understanding.model_copy(update={"operational_constraints": normalized_constraints})
    understanding = sanitize_operational_reach(understanding)
    schema_positioning = understanding.class_positioning
    explicit_classes = understanding.explicit_filters.classes if (
        schema_positioning.explicit_user_target or understanding.explicit_filters.classes
    ) else []
    normalized_positioning = normalize_class_positioning(
        _schema_affinity(understanding),
        primary_class=schema_positioning.primary_class or "",
        broad_market=schema_positioning.broad_market,
        explicit_classes=explicit_classes,
        source="explicit_prompt" if explicit_classes else "inferred",
    )
    return understanding.model_copy(update={"class_positioning": _schema_positioning(normalized_positioning)})


def _local_development_understanding(prompt: str) -> CampaignUnderstanding:
    return CampaignUnderstanding(
        original_request=prompt,
        language="unknown",
        advertiser=AdvertiserUnderstanding(name="", explicitly_mentioned=False),
        brands=[],
        products_services=[ProductServiceUnderstanding(
            raw_phrase=prompt,
            normalized_description=prompt,
            type="unknown",
            use_case="",
            professional_or_consumer="unspecified",
            confidence=0.25,
        )],
        campaign_objective="promote",
        market_type="UNSPECIFIED",
        explicit_target_audiences=[],
        inferred_target_audiences=[],
        target_roles=[],
        target_industries=[],
        buyer_types=[],
        user_types=[],
        purchase_contexts=[],
        positive_concepts=[prompt],
        adjacent_concepts=[],
        negative_concepts=[],
        false_friend_concepts=[],
        semantic_search_queries=[prompt],
        operational_constraints=OperationalCampaignConstraints(
            requested_reach_count=None,
            requested_reach_explicit=False,
            requested_reach_source_text=None,
        ),
        class_positioning=SchemaClassPositioning(
            explicit_user_target=False,
            broad_market=False,
            primary_class=None,
            affinity=ClassAffinityValues(
                economy="none",
                economy_plus="none",
                middle="none",
                middle_plus="none",
                upper="none",
            ),
        ),
        explicit_filters=CampaignExplicitFilters(cities=[], areas=[], gender="unspecified", age_min=None, age_max=None, classes=[], categories=[]),
        inferred_preferences=InferredPreferences(age_affinity="", gender_affinity=""),
        ambiguity=AmbiguityAssessment(ambiguous=True, description="Local development interpretation only.", clarification_required=False),
        interpretation_summary="Local development interpretation; OpenAI campaign understanding was not used.",
    )


class CampaignPlanner:
    def plan(self, prompt: str) -> CampaignPlanResult:
        started = time.perf_counter()
        if not LLM_INTENT_ENABLED or not OPENAI_CONFIGURED:
            error = "not_configured" if not OPENAI_CONFIGURED else "intent_disabled"
            if AI_REQUIRED:
                return CampaignPlanResult(attempted=True, error=error)
            understanding = _local_development_understanding(prompt)
            return CampaignPlanResult(
                understanding=understanding,
                understanding_id=_understanding_id(understanding),
                provider="local_development",
                succeeded=True,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

        calls = 0
        attempts = 1 + OPENAI_INTENT_TRANSIENT_RETRIES
        for attempt in range(attempts):
            try:
                client = create_openai_client(timeout=OPENAI_INTENT_TIMEOUT_SECONDS, max_retries=0)
                calls += 1
                response = client.responses.parse(
                    model=OPENAI_CHAT_MODEL,
                    instructions=CAMPAIGN_PLANNER_SYSTEM_PROMPT,
                    input=[{"role": "user", "content": prompt}],
                    text_format=CampaignUnderstanding,
                    store=False,
                )
                understanding = response.output_parsed
                if understanding is None:
                    raise ValueError("missing_structured_campaign_understanding")
                understanding = normalize_campaign_understanding(
                    understanding.model_copy(update={"original_request": prompt})
                )
                return CampaignPlanResult(
                    understanding=understanding,
                    understanding_id=_understanding_id(understanding),
                    attempted=True,
                    succeeded=True,
                    call_count=calls,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    usage=_usage(response),
                )
            except Exception as exc:
                error = safe_openai_error(exc)
                transient = error in {"timeout", "rate_limit_429", "unavailable"}
                if not transient or attempt + 1 >= attempts:
                    if not AI_REQUIRED:
                        understanding = _local_development_understanding(prompt)
                        return CampaignPlanResult(
                            understanding=understanding,
                            understanding_id=_understanding_id(understanding),
                            provider="local_development_fallback",
                            attempted=True,
                            succeeded=True,
                            call_count=calls,
                            latency_ms=int((time.perf_counter() - started) * 1000),
                            error=error,
                        )
                    return CampaignPlanResult(
                        attempted=True,
                        call_count=calls,
                        latency_ms=int((time.perf_counter() - started) * 1000),
                        error=error,
                    )
        return CampaignPlanResult(attempted=True, call_count=calls, error="unavailable")


def campaign_intent_from_understanding(
    understanding: CampaignUnderstanding,
    understanding_id: str,
    catalogue_companies: Iterable[str] | Mapping[str, str] = (),
    candidate_scope: str = "direct_adjacent_contextual",
) -> CampaignIntent:
    understanding = normalize_campaign_understanding(understanding)
    advertisers = [understanding.advertiser.name] if understanding.advertiser.explicitly_mentioned and understanding.advertiser.name else []
    advertiser_matches, _ = match_advertisers(advertisers, catalogue_companies) if advertisers else ([], 0)
    raw_phrases = [item.raw_phrase for item in understanding.products_services if item.raw_phrase]
    normalized = [item.normalized_description for item in understanding.products_services if item.normalized_description]
    use_cases = [item.use_case for item in understanding.products_services if item.use_case]
    taxonomy_rules = []
    for value in [*raw_phrases, *normalized]:
        rules, _clarification, _evidence = resolve_products(value)
        taxonomy_rules.extend(rules)
    known_families = list(dict.fromkeys(rule.family for rule in taxonomy_rules))
    taxonomy_attributes = ProductAttributes().__dict__.copy()
    for rule in taxonomy_rules:
        for key, value in rule.attributes.items():
            if value not in (None, "", [], False):
                taxonomy_attributes[key] = value
    if understanding.market_type == "B2B":
        taxonomy_attributes["professional_use"] = True
        taxonomy_attributes["campaign_type"] = "b2b"
    positioning = list(dict.fromkeys(understanding.purchase_contexts))
    if positioning:
        taxonomy_attributes["positioning"] = list(dict.fromkeys([*taxonomy_attributes.get("positioning", []), *positioning]))
    attributes = ProductAttributes(**taxonomy_attributes)
    filters = understanding.explicit_filters
    gender = [] if filters.gender == "unspecified" else [filters.gender]
    target_entities = list(dict.fromkeys([
        *understanding.explicit_target_audiences,
        *understanding.inferred_target_audiences,
        *understanding.buyer_types,
        *understanding.user_types,
    ]))
    open_terms = list(dict.fromkeys([
        *normalized,
        *understanding.positive_concepts,
        *understanding.semantic_search_queries,
    ]))
    class_positioning = normalize_class_positioning(
        _schema_affinity(understanding),
        primary_class=understanding.class_positioning.primary_class or "",
        broad_market=understanding.class_positioning.broad_market,
        explicit_classes=filters.classes if understanding.class_positioning.explicit_user_target else [],
        source="explicit_prompt" if understanding.class_positioning.explicit_user_target else "inferred",
    )
    operational = understanding.operational_constraints
    return CampaignIntent(
        raw_prompt=understanding.original_request,
        advertisers=advertisers,
        advertiser_catalog_matches=advertiser_matches,
        brands=understanding.brands,
        products=normalized,
        product_families=known_families,
        raw_product_phrases=raw_phrases,
        normalized_product_concepts=normalized,
        known_product_families=known_families,
        open_product_terms=open_terms,
        use_cases=list(dict.fromkeys([*use_cases, *understanding.purchase_contexts])),
        target_entities=target_entities,
        target_roles=understanding.target_roles,
        target_industries=understanding.target_industries,
        audience_type=understanding.market_type.lower(),
        campaign_type=understanding.market_type.lower(),
        confidence=max((item.confidence for item in understanding.products_services), default=0.5),
        negated_terms=list(dict.fromkeys([*understanding.negative_concepts, *understanding.false_friend_concepts])),
        interpretation_provider="openai",
        model_call_count=1,
        llm_intent_used=True,
        explicit_filters=ExplicitFilters(
            cities=filters.cities,
            areas=filters.areas,
            gender=gender,
            classes=filters.classes,
            categories=filters.categories,
            age_min=filters.age_min,
            age_max=filters.age_max,
        ),
        product_attributes=attributes,
        class_affinity=class_positioning.affinity,
        class_primary=class_positioning.primary_class,
        class_broad_market=class_positioning.broad_market,
        class_affinity_source=class_positioning.source,
        requested_reach_count=operational.requested_reach_count,
        requested_reach_explicit=operational.requested_reach_explicit,
        requested_reach_source_text=operational.requested_reach_source_text or "",
        candidate_scope=candidate_scope,
        clarification_needed=understanding.ambiguity.clarification_required,
        ambiguity_notes=[understanding.ambiguity.description] if understanding.ambiguity.description else [],
        interpretation_evidence=[understanding.interpretation_summary],
        campaign_understanding_id=understanding_id,
        positive_concepts=understanding.positive_concepts,
        adjacent_concepts=understanding.adjacent_concepts,
        false_friend_concepts=understanding.false_friend_concepts,
        semantic_search_queries=understanding.semantic_search_queries,
        explicit_target_audiences=understanding.explicit_target_audiences,
        inferred_target_audiences=understanding.inferred_target_audiences,
        buyer_types=understanding.buyer_types,
        user_types=understanding.user_types,
        purchase_contexts=understanding.purchase_contexts,
        interpretation_summary=understanding.interpretation_summary,
    )
