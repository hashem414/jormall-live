from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

from config import (
    AI_REVIEW_CANDIDATE_LIMIT,
    LLM_INTENT_ENABLED,
    OPENAI_CHAT_MODEL,
    OPENAI_CONFIGURED,
    OPENAI_REVIEW_TIMEOUT_SECONDS,
)
from domain.list_profile import ListProfile
from domain.recommendation_candidate import RecommendationCandidate

from .openai_client import create_openai_client, safe_openai_error
from .prompt_templates import CANDIDATE_REVIEW_SYSTEM_PROMPT
from .schemas import CampaignUnderstanding, CandidateReview


RankedRow = tuple[ListProfile, RecommendationCandidate]
_RELEVANCE_ORDER = {"strong": 0, "moderate": 1, "weak": 2, "wrong": 3}


@dataclass(frozen=True)
class CandidateReviewResult:
    rows: list[RankedRow]
    attempted: bool = False
    succeeded: bool = False
    call_count: int = 0
    latency_ms: int = 0
    error: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    reviewed_count: int = 0


def _usage(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    return {
        name: value
        for name in ("input_tokens", "output_tokens", "total_tokens")
        if isinstance((value := getattr(usage, name, None)), int)
    }


def _candidate_summary(profile: ListProfile, candidate: RecommendationCandidate) -> dict[str, object]:
    return {
        "candidate_id": profile.list_id,
        "list_name": profile.list_name[:240],
        "represented_entity": profile.represented_entity[:120],
        "original_category": profile.original_category[:120],
        "category_group": profile.category_group[:120],
        "source_industry": profile.source_industry[:120],
        "audience_roles": profile.audience_roles or [profile.audience_role],
        "business_contexts": profile.business_contexts[:8],
        "interests": profile.interests[:8],
        "professional_subtypes": profile.professional_subtypes[:8],
        "candidate_tier": candidate.tier,
        "semantic_similarities": {
            "product": round(candidate.product_similarity, 4),
            "audience": round(candidate.audience_similarity, 4),
            "use_case": round(candidate.use_case_similarity, 4),
            "industry": round(candidate.industry_similarity, 4),
            "adjacent": round(candidate.adjacent_similarity, 4),
            "negative": round(candidate.negative_similarity, 4),
        },
        "matched_evidence": candidate.matched_evidence[:3],
    }


class CandidateReviewer:
    def review(
        self,
        understanding: CampaignUnderstanding,
        rows: Sequence[RankedRow],
        *,
        enabled: bool,
    ) -> CandidateReviewResult:
        original = list(rows)
        if not enabled or not original:
            return CandidateReviewResult(rows=original)
        if not LLM_INTENT_ENABLED or not OPENAI_CONFIGURED:
            return CandidateReviewResult(rows=original, error="not_configured")

        review_rows = original[:AI_REVIEW_CANDIDATE_LIMIT]
        expected_ids = [profile.list_id for profile, _candidate in review_rows]
        payload = {
            "campaign_understanding": understanding.model_dump(
                mode="json",
                exclude={"operational_constraints"},
            ),
            "candidates": [_candidate_summary(profile, candidate) for profile, candidate in review_rows],
        }
        started = time.perf_counter()
        try:
            client = create_openai_client(timeout=OPENAI_REVIEW_TIMEOUT_SECONDS, max_retries=0)
            response = client.responses.parse(
                model=OPENAI_CHAT_MODEL,
                instructions=CANDIDATE_REVIEW_SYSTEM_PROMPT,
                input=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}],
                text_format=CandidateReview,
                store=False,
            )
            parsed = response.output_parsed
            if parsed is None:
                raise ValueError("missing_structured_candidate_review")
            by_id = {item.candidate_id: item for item in parsed.items}
            if set(by_id) != set(expected_ids) or len(by_id) != len(expected_ids):
                raise ValueError("candidate_review_id_mismatch")
            for profile, candidate in review_rows:
                item = by_id[profile.list_id]
                candidate.ai_review_relevance = item.relevance
                candidate.ai_review_reason = item.reason_summary
            ordered = sorted(
                enumerate(review_rows),
                key=lambda item: (
                    _RELEVANCE_ORDER.get(item[1][1].ai_review_relevance, 4),
                    item[0],
                ),
            )
            return CandidateReviewResult(
                rows=[row for _index, row in ordered] + original[len(review_rows):],
                attempted=True,
                succeeded=True,
                call_count=1,
                latency_ms=int((time.perf_counter() - started) * 1000),
                usage=_usage(response),
                reviewed_count=len(review_rows),
            )
        except Exception as exc:
            return CandidateReviewResult(
                rows=original,
                attempted=True,
                call_count=1,
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=safe_openai_error(exc),
            )
