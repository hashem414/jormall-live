from __future__ import annotations

import json
import time
from collections import Counter
from typing import Dict, List, Tuple

from ai.campaign_planner import CampaignPlanResult, CampaignPlanner, campaign_intent_from_understanding
from ai.candidate_reviewer import CandidateReviewer
from ai.query_builder import build_semantic_queries
from ai.relevance_policy import build_relevance_policy
from domain.campaign_intent import CampaignIntent, ExplicitFilters
from domain.effective_filters import EffectiveFilters, FilterResolution, resolve_effective_filters
from domain.list_profile import ListProfile
from domain.operational_constraints import EffectiveTarget, resolve_effective_target
from domain.recommendation_candidate import RecommendationCandidate
from explanations.grounded_explanations import explain_candidate
from intent.advertiser_parser import build_company_alias_index
from intent.class_affinity import normalize_class_positioning
from profiles.profile_builder import load_profiles
from ranking.eligibility import geography_filter_match, hard_eligibility, static_profile_eligibility
from ranking.max_scope import (
    SCOPE_TIERS,
    TargetSelectionResult,
    normalize_scope,
    scope_rows,
    select_ranked_for_target,
)
from ranking.scorer import RANKING_VERSION, rank_candidates
from retrieval.hybrid_retriever import HybridRetriever
from engines.result_state import DerivedResultState, derive_result_state
from config import (
    CATALOGUE_MANIFEST_PATH,
    AI_REVIEW_TOP_RESULTS,
    AI_REQUIRED,
    DOTENV_LOADED,
    LLM_INTENT_ENABLED,
    OPENAI_CONFIGURED,
    OPENAI_CHAT_MODEL,
    OPENAI_EMBEDDING_MODEL,
    SEMANTIC_PROVIDER,
)
from intent.product_taxonomy import TAXONOMY_VERSION
from config import CLASSIFICATION_VERSION, RELATIONSHIP_RULES_VERSION
from config import BASE_DIR


def _bool(payload: Dict[str, object], key: str, default: bool = False) -> bool:
    value = payload.get(key, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "on"}


def _int(payload: Dict[str, object], key: str, default: int = 0) -> int:
    try:
        return int(str(payload.get(key, default)).replace(",", ""))
    except (TypeError, ValueError):
        return default


def _values(payload: Dict[str, object], key: str) -> List[str]:
    value = payload.get(key, [])
    values = value if isinstance(value, list) else [value]
    return [str(item).strip() for item in values if str(item).strip() not in {"", "Any", "NA"}]


def _target_diagnostics(
    target: EffectiveTarget,
    selection: TargetSelectionResult,
    qualified_before_target: int,
) -> Dict[str, object]:
    return {
        "prompt_target_count": target.prompt_target_count,
        "ui_target_count": target.ui_target_count,
        "effective_target_count": target.effective_target_count,
        "source": target.source,
        "manual_only": target.manual_only,
        "selection_mode": selection.selection_mode,
        "qualified_before_target": qualified_before_target,
        "selected_after_target": len(selection.rows),
        "gross_selected_quantity": selection.gross_selected_quantity,
        "reached": selection.reached,
        "status": selection.status,
        "overshoot": selection.overshoot,
        "shortage": selection.shortage,
    }


def _class_positioning_diagnostics(intent: CampaignIntent | None) -> Dict[str, object]:
    if intent is None:
        return {
            "explicit": False,
            "broad_market": False,
            "primary_class": "",
            "source": "none",
            "affinity": {},
        }
    return {
        "explicit": intent.class_affinity_source in {"explicit_prompt", "explicit_ui"},
        "broad_market": intent.class_broad_market,
        "primary_class": intent.class_primary,
        "source": intent.class_affinity_source,
        "affinity": intent.class_affinity,
    }


class HybridEngine:
    def __init__(self) -> None:
        started = time.perf_counter()
        loaded = load_profiles()
        self.profiles: Dict[str, ListProfile] = {profile.list_id: profile for profile in loaded}
        self.companies = sorted({profile.source_owner for profile in loaded if profile.source_owner})
        self.company_alias_index = build_company_alias_index(self.companies)
        self.campaign_planner = CampaignPlanner()
        self.candidate_reviewer = CandidateReviewer()
        manifest = json.loads(CATALOGUE_MANIFEST_PATH.read_text(encoding="utf-8"))
        self.duplicates_suppressed = max(0, int(manifest["raw_rows"]) - int(manifest["unique_list_ids"]))
        self.retriever = HybridRetriever()
        index_report_path = BASE_DIR / "reports" / "index_build_report.json"
        if index_report_path.exists():
            index_report = json.loads(index_report_path.read_text(encoding="utf-8"))
            lexical = index_report.get("lexical", {})
            semantic = index_report.get("semantic", {})
            self.index_version = f"{lexical.get('provider', 'unknown')}:{str(lexical.get('source_hash', ''))[:12]}|{semantic.get('provider', 'unknown')}"
        else:
            self.index_version = "unknown"
        self.profile_load_ms = int((time.perf_counter() - started) * 1000)

    def _apply_effective_filters(self, intent: CampaignIntent, resolution: FilterResolution) -> CampaignIntent:
        ui_classes = resolution.ui.classes
        data = intent.to_dict()
        data["explicit_filters"] = resolution.effective.to_explicit_filters()
        data["product_attributes"] = intent.product_attributes
        if ui_classes:
            positioning = normalize_class_positioning(
                intent.class_affinity,
                primary_class=ui_classes[0],
                explicit_classes=ui_classes,
                source="explicit_ui",
            )
            data.update({
                "class_affinity": positioning.affinity,
                "class_primary": positioning.primary_class,
                "class_broad_market": positioning.broad_market,
                "class_affinity_source": positioning.source,
            })
        return CampaignIntent(**data)

    def _merge_manual_filters(self, intent: CampaignIntent, payload: Dict[str, object]) -> CampaignIntent:
        resolution = resolve_effective_filters(
            intent.explicit_filters,
            payload,
            manual_only=_bool(payload, "reset_ai_fields", False),
        )
        return self._apply_effective_filters(intent, resolution)

    @staticmethod
    def _intent_diagnostics(intent: CampaignIntent | None, plan: CampaignPlanResult) -> Dict[str, object]:
        return {
            "dotenv_loaded": DOTENV_LOADED,
            "openai_configured": OPENAI_CONFIGURED,
            "ai_required": AI_REQUIRED,
            "ai_call_attempted": plan.attempted,
            "ai_call_succeeded": plan.succeeded and plan.provider == "openai",
            "ai_intent_calls": plan.call_count,
            "ai_review_calls": 0,
            "llm_intent_enabled": LLM_INTENT_ENABLED,
            "llm_intent_used": bool(intent and intent.llm_intent_used),
            "llm_intent_calls": plan.call_count,
            "intent_provider": plan.provider if plan.succeeded else "unavailable",
            "intent_model": OPENAI_CHAT_MODEL if plan.call_count else "",
            "intent_latency_ms": plan.latency_ms,
            "intent_error": plan.error,
            "campaign_understanding_id": plan.understanding_id,
            "intent_token_usage": plan.usage,
            "embedding_provider": "openai" if SEMANTIC_PROVIDER == "openai_embeddings" else SEMANTIC_PROVIDER,
            "embedding_model": OPENAI_EMBEDDING_MODEL if SEMANTIC_PROVIDER == "openai_embeddings" else "",
        }

    def _allowed_ids(
        self,
        intent: CampaignIntent,
        effective: EffectiveFilters,
    ) -> Tuple[set[str], Dict[str, int], Dict[str, object], Dict[str, int]]:
        min_quantity = effective.minimum_list_count
        allowed: set[str] = set()
        rejected = Counter()
        profiles_before_hard_filters = 0
        profiles_after_geography_filter = 0
        for list_id, profile in self.profiles.items():
            static_ok, _static_failures = static_profile_eligibility(profile)
            if not static_ok:
                rejected["static_profile_filter"] += 1
                continue
            profiles_before_hard_filters += 1
            geography_ok, _geography_matches, _geography_failures = geography_filter_match(
                intent.explicit_filters,
                profile,
            )
            if not geography_ok:
                rejected["geography_filter"] += 1
                continue
            profiles_after_geography_filter += 1
            if not hard_eligibility(intent, profile)[0]:
                rejected["hard_or_explicit_filter"] += 1
                continue
            if profile.quantity < min_quantity:
                rejected["minimum_quantity_filter"] += 1
                continue
            allowed.add(list_id)
        constraints = {"categories": list(effective.categories), "min_quantity": min_quantity}
        counts = {
            "profiles_before_hard_filters": profiles_before_hard_filters,
            "profiles_after_geography_filter": profiles_after_geography_filter,
            "profiles_after_all_hard_filters": len(allowed),
        }
        return allowed, dict(rejected), constraints, counts

    @staticmethod
    def _scope_ids(rows: List[Tuple[ListProfile, RecommendationCandidate]]) -> Dict[str, List[str]]:
        return {scope: [profile.list_id for profile, _candidate in scope_rows(rows, scope)] for scope in SCOPE_TIERS}

    @staticmethod
    def _serialize(profile: ListProfile, candidate: RecommendationCandidate, audit_mode: bool = False) -> Dict[str, object]:
        age = "Any" if profile.age_min is None else f"{profile.age_min} - {profile.age_max or 100}"
        location = (
            "All Jordan"
            if profile.coverage_type in {"national", "all_jordan"}
            else ", ".join(profile.cities + profile.areas) or "Unknown"
        )
        row = {
            "List ID": profile.list_id,
            "List Name": profile.list_name,
            "Company": profile.source_owner,
            "Represented Entity": profile.represented_entity,
            "Source Industry": profile.source_industry,
            "Category": profile.category_group,
            "Business Category Group": profile.category_group,
            "Audience Role": profile.audience_role,
            "Audience Roles": profile.audience_roles,
            "Category Facets": profile.category_facets,
            "Audience": f"{profile.gender or 'Any'} / {profile.audience_role}",
            "Class": profile.economic_class or "Any",
            "Age Range": age,
            "Location": location,
            "Canonical Cities": list(profile.cities),
            "Canonical Areas": list(profile.areas),
            "Coverage Type": profile.coverage_type,
            "Quantity": profile.quantity,
            "Created Date": profile.list_date or "Unknown",
            "Candidate Tier": candidate.tier,
            "Recommendation Score": round(candidate.score, 3),
            "Retrieval Score": round(candidate.retrieval_score, 6),
            "Semantic Similarities": {
                "product": round(candidate.product_similarity, 6),
                "audience": round(candidate.audience_similarity, 6),
                "use_case": round(candidate.use_case_similarity, 6),
                "industry": round(candidate.industry_similarity, 6),
                "adjacent": round(candidate.adjacent_similarity, 6),
                "negative": round(candidate.negative_similarity, 6),
            },
            "Why Recommended": candidate.explanation,
            "Evidence Families": candidate.evidence_families,
            "Matched Evidence": candidate.matched_evidence,
            "Supported Product Families": candidate.supported_product_families,
            "Filter Matches": candidate.filter_matches,
            "Class Affinity": candidate.class_affinity,
            "Class Fit": candidate.class_affinity,
            "Class Fit Source": candidate.class_fit_source,
            "Diversity Signature": candidate.diversity_signature,
            "AI Review Relevance": candidate.ai_review_relevance,
            "AI Review Reason": candidate.ai_review_reason,
        }
        if audit_mode:
            row["Audit"] = {
                "raw_list_text": profile.original_row_text,
                "represented_entity": profile.represented_entity,
                "represented_entity_confidence": profile.represented_entity_confidence,
                "source_owner": profile.source_owner,
                "audience_role": profile.audience_role,
                "audience_role_confidence": profile.audience_role_confidence,
                "evidence_atoms": [atom.to_dict() for atom in profile.evidence],
                "lexical_score": candidate.lexical_score,
                "semantic_score": candidate.semantic_score,
                "product_relationship": candidate.product_relationship,
                "eligibility_reason": candidate.eligibility_reason,
                "tier": candidate.tier,
                "ranking_breakdown": candidate.ranking_breakdown,
            }
        return row

    def recompute_interaction_state(
        self,
        state: Dict[str, object],
        *,
        excluded_ids: List[str] | None = None,
        selected_ids: List[str] | None = None,
        revision: int = 0,
        auto_select_replacements: bool = True,
    ) -> Tuple[Dict[str, object], Dict[str, object], DerivedResultState]:
        started = time.perf_counter()
        pool = state["ranked_qualified_candidates"]
        previous_selected = state.get("selected_ids")
        derived = derive_result_state(
            pool,
            excluded_ids=excluded_ids if excluded_ids is not None else state.get("excluded_ids", []),
            selected_ids=selected_ids if selected_ids is not None else previous_selected,
            previous_active_ids=state.get("active_ids", []),
            previous_excluded_ids=state.get("excluded_ids", []),
            target_count=int(state["target_count"]),
            max_lists=int(state["max_lists"]),
            max_mode=bool(state["max_mode"]),
            revision=revision,
            auto_select_replacements=auto_select_replacements,
        )

        explanation_started = time.perf_counter()
        intent = state["intent"]
        for profile, candidate in derived.active_rows:
            if not candidate.explanation:
                candidate.explanation = explain_candidate(intent, profile, candidate)
        explanation_ms = int((time.perf_counter() - explanation_started) * 1000)

        serialization_started = time.perf_counter()
        audit_mode = bool(state.get("audit_mode", False))
        output = [self._serialize(profile, candidate, audit_mode) for profile, candidate in derived.active_rows]
        pool_order = [profile.list_id for profile, _candidate in pool]
        selected_active_ids = [
            profile.list_id for profile, _candidate in derived.selected_rows
        ]
        excluded_items = [
            {
                "list_id": profile.list_id,
                "list_name": profile.list_name,
                "quantity": profile.quantity,
            }
            for profile, _candidate in derived.excluded_rows
        ]
        target_resolution = state["target_resolution"]
        summary = {
            **derived.summary,
            "selected_lists": derived.summary["active_recommendation_list_count"],
            "total_quantity": derived.summary["active_recommended_quantity"],
            "gross_selected_quantity": derived.summary["active_recommended_quantity"],
            "target_quantity": int(state["target_count"]),
            "requested_reach_count": int(state["target_count"]),
            "prompt_target_count": target_resolution.prompt_target_count,
            "ui_target_count": target_resolution.ui_target_count,
            "target_source": target_resolution.source,
            "target_status": derived.target_selection.status,
            "target_match_mode": derived.target_selection.selection_mode,
        }
        result_state = {
            "revision": derived.revision,
            "active_ids": [value for value in pool_order if value in derived.active_ids],
            "selected_ids": [value for value in pool_order if value in derived.selected_ids],
            "selected_active_ids": selected_active_ids,
            "excluded_ids": [value for value in pool_order if value in derived.excluded_ids],
            "excluded_items": excluded_items,
            **derived.summary,
            "class_distribution": derived.class_distribution,
            "tier_distribution": derived.tier_distribution,
        }
        serialization_ms = int((time.perf_counter() - serialization_started) * 1000)
        recompute_ms = int((time.perf_counter() - started) * 1000)
        public = {
            "recommendations": output,
            "summary": summary,
            "result_category_groups": derived.category_groups,
            "result_state": result_state,
            "interaction_diagnostics": {
                "revision": derived.revision,
                "recompute_latency_ms": recompute_ms,
                "ai_intent_calls_delta": 0,
                "embedding_calls_delta": 0,
                "retrieval_executions_delta": 0,
                "ranking_executions_delta": 0,
                "explanation_generation_ms": explanation_ms,
                "serialization_ms": serialization_ms,
            },
        }
        updated_state = {
            **state,
            "excluded_ids": set(derived.excluded_ids),
            "selected_ids": set(derived.selected_ids),
            "active_ids": set(derived.active_ids),
            "revision": derived.revision,
            "serialized_active": output,
            "result_state": result_state,
        }
        return public, updated_state, derived

    def recommend(self, payload: Dict[str, object]) -> Dict[str, object]:
        total_started = time.perf_counter()
        timings: Dict[str, int] = {"profile_loading_ms": 0}
        prompt = str(payload.get("campaign_prompt", "") or "").strip()
        scope = normalize_scope(str(payload.get("candidate_scope", "direct_adjacent_contextual")))
        max_mode = _bool(payload, "max_mode", False)
        max_lists = _int(payload, "max_lists", 30)
        manual_only = _bool(payload, "reset_ai_fields", False)
        target_resolution = resolve_effective_target(
            payload.get("target_quantity", 0),
            None,
            manual_only=manual_only,
        )
        target_quantity = target_resolution.effective_target_count
        filter_resolution = resolve_effective_filters(
            ExplicitFilters(),
            payload,
            manual_only=manual_only,
        )

        plan_started = time.perf_counter()
        plan = self.campaign_planner.plan(prompt)
        timings["intent_parsing_ms"] = int((time.perf_counter() - plan_started) * 1000)
        if not plan.succeeded or plan.understanding is None:
            empty_selection = select_ranked_for_target(
                [], target_count=target_quantity, max_lists=max_lists, max_mode=max_mode
            )
            timings.update({
                "lexical_retrieval_ms": 0,
                "semantic_retrieval_ms": 0,
                "fusion_ms": 0,
                "reranking_ms": 0,
                "duplicate_suppression_ms": 0,
                "explanation_generation_ms": 0,
                "serialization_ms": 0,
                "total_ms": int((time.perf_counter() - total_started) * 1000),
            })
            diagnostics = {
                **self._intent_diagnostics(None, plan),
                "recommendation_execution": "blocked",
                "query_embedding_generated": False,
                "catalogue_embedding_cache_hit": False,
                "retrieval_mode": "not_started",
                "allowed_profiles": 0,
                "profiles_vector_scored": 0,
                "profiles_lexically_scored": 0,
                "profiles_scored": 0,
                "qualified_profiles": 0,
                "returned_profiles": 0,
                "zero_evidence_leakage": 0,
                "rejected_leakage": 0,
                "age_filter_active": False,
                "semantic_query_contains_reach_number": False,
                "semantic_query_contains_explicit_geography": False,
                "filters": filter_resolution.diagnostics(),
                "target": _target_diagnostics(target_resolution, empty_selection, 0),
                "class_positioning": _class_positioning_diagnostics(None),
            }
            return {
                "recommended": [],
                "summary": {
                    "selected_lists": 0,
                    "total_quantity": 0,
                    "target_quantity": target_quantity,
                    "requested_reach_count": target_quantity,
                    "prompt_target_count": target_resolution.prompt_target_count,
                    "ui_target_count": target_resolution.ui_target_count,
                    "target_source": target_resolution.source,
                    "target_status": empty_selection.status,
                    "target_reached": empty_selection.reached,
                    "target_met": empty_selection.reached,
                    "target_difference": -target_quantity if target_quantity else 0,
                    "target_overshoot": empty_selection.overshoot,
                    "target_shortage": empty_selection.shortage,
                    "gross_selected_quantity": 0,
                    "target_match_mode": "AI unavailable",
                    "available_recommendable_lists": 0,
                    "duplicate_profiles_suppressed": self.duplicates_suppressed,
                    "message": "AI campaign understanding unavailable. No recommendations were generated.",
                },
                "campaign_understanding": None,
                "interpreted_intent": {},
                "interpreted_filters": {},
                "manual_constraints": {"categories": _values(payload, "category"), "min_quantity": max(0, _int(payload, "min_quantity", 0))},
                "candidate_scope": scope,
                "max_mode": max_mode,
                "numeric_limit_applied": not max_mode,
                "result_category_groups": [],
                "diagnostics": diagnostics,
                "timings": timings,
                "debug": {"scope_result_ids": {name: [] for name in SCOPE_TIERS}, "tier_counts": {tier: 0 for tier in ("direct", "adjacent", "contextual", "fallback")}},
                "ai_note": "AI campaign understanding unavailable. No recommendations were generated.",
                "ai_error": plan.error,
            }

        understanding = plan.understanding
        target_resolution = resolve_effective_target(
            payload.get("target_quantity", 0),
            understanding.operational_constraints.requested_reach_count,
            manual_only=manual_only,
        )
        target_quantity = target_resolution.effective_target_count
        intent = campaign_intent_from_understanding(
            understanding,
            plan.understanding_id,
            self.company_alias_index,
            scope,
        )
        intent_data = intent.to_dict()
        intent_data.update({
            "interpretation_provider": plan.provider,
            "model_call_count": plan.call_count,
            "llm_intent_used": plan.provider == "openai",
            "llm_intent_latency_ms": plan.latency_ms,
            "llm_intent_error": plan.error,
            "explicit_filters": intent.explicit_filters,
            "product_attributes": intent.product_attributes,
        })
        intent = CampaignIntent(**intent_data)
        filter_resolution = resolve_effective_filters(
            intent.explicit_filters,
            payload,
            manual_only=manual_only,
        )
        intent = self._apply_effective_filters(intent, filter_resolution)

        if understanding.ambiguity.clarification_required:
            empty_selection = select_ranked_for_target(
                [], target_count=target_quantity, max_lists=max_lists, max_mode=max_mode
            )
            timings.update({
                "lexical_retrieval_ms": 0,
                "semantic_retrieval_ms": 0,
                "fusion_ms": 0,
                "reranking_ms": 0,
                "duplicate_suppression_ms": 0,
                "explanation_generation_ms": 0,
                "serialization_ms": 0,
                "total_ms": int((time.perf_counter() - total_started) * 1000),
            })
            diagnostics = {
                **self._intent_diagnostics(intent, plan),
                "recommendation_execution": "blocked_clarification",
                "query_embedding_generated": False,
                "catalogue_embedding_cache_hit": False,
                "retrieval_mode": "not_started",
                "allowed_profiles": 0,
                "profiles_vector_scored": 0,
                "profiles_lexically_scored": 0,
                "profiles_scored": 0,
                "qualified_profiles": 0,
                "returned_profiles": 0,
                "zero_evidence_leakage": 0,
                "rejected_leakage": 0,
                "age_filter_active": intent.explicit_filters.age_min is not None,
                "semantic_query_contains_reach_number": False,
                "target": _target_diagnostics(target_resolution, empty_selection, 0),
                "class_positioning": _class_positioning_diagnostics(intent),
            }
            return {
                "recommended": [],
                "summary": {
                    "selected_lists": 0,
                    "total_quantity": 0,
                    "target_quantity": target_quantity,
                    "requested_reach_count": target_quantity,
                    "prompt_target_count": target_resolution.prompt_target_count,
                    "ui_target_count": target_resolution.ui_target_count,
                    "target_source": target_resolution.source,
                    "target_status": empty_selection.status,
                    "target_reached": empty_selection.reached,
                    "target_met": empty_selection.reached,
                    "target_difference": -target_quantity if target_quantity else 0,
                    "target_overshoot": empty_selection.overshoot,
                    "target_shortage": empty_selection.shortage,
                    "gross_selected_quantity": 0,
                    "target_match_mode": "Clarification required",
                    "available_recommendable_lists": 0,
                    "duplicate_profiles_suppressed": self.duplicates_suppressed,
                    "message": understanding.ambiguity.description or "The campaign needs clarification before retrieval.",
                },
                "campaign_understanding": understanding.model_dump(mode="json"),
                "interpreted_intent": intent.to_dict(),
                "interpreted_filters": filter_resolution.effective.to_dict(),
                "effective_filters": filter_resolution.effective.to_dict(),
                "manual_constraints": {
                    "categories": list(filter_resolution.effective.categories),
                    "min_quantity": filter_resolution.effective.minimum_list_count,
                },
                "candidate_scope": scope,
                "max_mode": max_mode,
                "numeric_limit_applied": not max_mode,
                "result_category_groups": [],
                "diagnostics": diagnostics,
                "timings": timings,
                "debug": {"scope_result_ids": {name: [] for name in SCOPE_TIERS}, "tier_counts": {tier: 0 for tier in ("direct", "adjacent", "contextual", "fallback")}},
                "ai_note": f"OpenAI understood the request but needs clarification: {understanding.ambiguity.description}",
                "ai_error": None,
            }

        policy = build_relevance_policy(understanding)
        query_bundle = build_semantic_queries(understanding)
        allowed_ids, prefilter_rejections, manual_constraints, filter_counts = self._allowed_ids(
            intent,
            filter_resolution.effective,
        )
        retrieval = self.retriever.retrieve(query_bundle, allowed_ids, exhaustive=max_mode)
        timings.update(retrieval["timings"])

        rerank_started = time.perf_counter()
        ranked, rejection_counts = rank_candidates(intent, policy, self.profiles, retrieval["candidates"])
        for _profile, candidate in ranked:
            if manual_constraints["categories"]:
                candidate.filter_matches["category"] = True
            if manual_constraints["min_quantity"]:
                candidate.filter_matches["minimum_quantity"] = True
        timings["reranking_ms"] = int((time.perf_counter() - rerank_started) * 1000)

        scope_result_ids = self._scope_ids(ranked)
        selected_scope_rows = scope_rows(ranked, scope)
        review = self.candidate_reviewer.review(
            understanding,
            selected_scope_rows,
            enabled=AI_REVIEW_TOP_RESULTS and _bool(payload, "ai_review_top_results", True),
        )
        selected_scope_rows = review.rows
        timings["ai_review_ms"] = review.latency_ms
        duplicate_started = time.perf_counter()
        duplicate_profiles_suppressed = self.duplicates_suppressed
        timings["duplicate_suppression_ms"] = int((time.perf_counter() - duplicate_started) * 1000)

        audit_mode = _bool(payload, "audit_mode", False)
        interaction_state: Dict[str, object] = {
            "ranked_qualified_candidates": tuple(selected_scope_rows),
            "intent": intent,
            "target_resolution": target_resolution,
            "target_count": target_quantity,
            "max_lists": max_lists,
            "max_mode": max_mode,
            "audit_mode": audit_mode,
        }
        interaction_public, interaction_state, derived_state = self.recompute_interaction_state(
            interaction_state,
            revision=0,
        )
        selection = derived_state.target_selection
        output = interaction_public["recommendations"]
        category_groups = interaction_public["result_category_groups"]
        timings["explanation_generation_ms"] = interaction_public["interaction_diagnostics"]["explanation_generation_ms"]
        timings["serialization_ms"] = interaction_public["interaction_diagnostics"]["serialization_ms"]
        timings["total_ms"] = int((time.perf_counter() - total_started) * 1000)
        tier_counts = Counter(candidate.tier for _profile, candidate in ranked)
        zero_message = (
            "No catalogue profiles contained sufficient evidence of the requested audience."
            if not output else
            "OpenAI understood the campaign; hybrid semantic retrieval and evidence-based ranking were applied."
        )
        diagnostics = {
            **self._intent_diagnostics(intent, plan),
            "ai_review_attempted": review.attempted,
            "ai_review_succeeded": review.succeeded,
            "ai_review_calls": review.call_count,
            "ai_review_error": review.error,
            "ai_reviewed_candidates": review.reviewed_count,
            "ai_review_token_usage": review.usage,
            "recommendation_execution": "executed",
            "interpretation_call_count": 1,
            "candidate_evaluation_passes": 1,
            "model_call_count": plan.call_count + review.call_count,
            "company_fuzzy_comparisons": 0,
            "advertiser_resolution_count": len(intent.advertisers),
            "advertiser_exact_lookups": len(intent.advertisers),
            "wrong_advertiser_substitution": 0,
            "target_expansion_ran": target_quantity > 0,
            "semantic_query_contains_reach_number": query_bundle.contains_operational_reach,
            "semantic_query_contains_explicit_geography": query_bundle.contains_explicit_geography,
            "target": _target_diagnostics(target_resolution, selection, len(selected_scope_rows)),
            "class_positioning": _class_positioning_diagnostics(intent),
            "zero_evidence_leakage": 0,
            "rejected_leakage": 0,
            "retrieval_counts": retrieval["counts"],
            "retrieval_mode": retrieval["mode"],
            "allowed_profile_count": len(allowed_ids),
            "allowed_profiles": len(allowed_ids),
            "profiles_relevance_scored": retrieval["profiles_scored"],
            "profiles_scored": retrieval["profiles_scored"],
            "profiles_vector_scored": retrieval["profiles_vector_scored"],
            "profiles_lexically_scored": retrieval["profiles_lexically_scored"],
            "eligible_after_evidence": len(selected_scope_rows),
            "qualified_profiles": len(selected_scope_rows),
            "qualified_candidates": len(selected_scope_rows),
            "returned_count": len(output),
            "returned_profiles": len(output),
            "returned_candidates": len(output),
            "query_embedding_generated": retrieval["query_embedding_generated"],
            "query_embedding_calls": retrieval["query_embedding_calls"],
            "query_embedding_tokens": retrieval["query_embedding_tokens"],
            "catalogue_embedding_cache_hit": retrieval["catalogue_embedding_cache_hit"],
            "age_filter_active": intent.explicit_filters.age_min is not None,
            "prefilter_rejections": prefilter_rejections,
            "filters": {
                **filter_resolution.diagnostics(),
                **filter_counts,
            },
            **filter_counts,
            "interaction": interaction_public["interaction_diagnostics"],
            "taxonomy_version": TAXONOMY_VERSION,
            "profile_version": CLASSIFICATION_VERSION,
            "ranking_version": RANKING_VERSION,
            "relationship_version": RELATIONSHIP_RULES_VERSION,
            "index_version": self.index_version,
            **rejection_counts,
        }
        return {
            "recommended": output,
            "summary": {
                **interaction_public["summary"],
                "duplicate_profiles_suppressed": duplicate_profiles_suppressed,
                "message": zero_message,
                "campaign_understood": understanding.interpretation_summary,
                "searched_for": list(dict.fromkeys([
                    *policy.primary_product_concepts,
                    *policy.strong_audience_signals,
                    *policy.adjacent_signals,
                ])),
                "profiles_considered": retrieval["profiles_scored"],
            },
            "campaign_understanding": understanding.model_dump(mode="json"),
            "interpreted_intent": intent.to_dict(),
            "interpreted_filters": filter_resolution.effective.to_dict(),
            "effective_filters": filter_resolution.effective.to_dict(),
            "manual_constraints": manual_constraints,
            "candidate_scope": scope,
            "max_mode": max_mode,
            "audit_mode": audit_mode,
            "numeric_limit_applied": selection.list_limit_applied,
            "result_category_groups": category_groups,
            "result_state": interaction_public["result_state"],
            "diagnostics": diagnostics,
            "timings": timings,
            "debug": {
                "scope_result_ids": scope_result_ids,
                "qualified_before_target_ids": [profile.list_id for profile, _candidate in selected_scope_rows],
                "tier_counts": {tier: tier_counts.get(tier, 0) for tier in ("direct", "adjacent", "contextual", "fallback")},
            },
            "ai_note": zero_message,
            "ai_error": None,
            "_interaction_state": interaction_state,
        }
