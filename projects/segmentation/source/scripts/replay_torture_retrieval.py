from __future__ import annotations

import json
import statistics
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai.campaign_planner import campaign_intent_from_understanding
from ai.query_builder import build_semantic_queries
from ai.relevance_policy import build_relevance_policy
from ai.schemas import CampaignUnderstanding
from engines.hybrid_engine import HybridEngine
from ranking.max_scope import scope_rows
from ranking.scorer import rank_candidates
from scripts.run_ai_torture_tests import CASES, REPORT_DIR, RESULTS_PATH


OUTPUT_PATH = REPORT_DIR / "retrieval_replay_results.jsonl"
REPORT_PATH = REPORT_DIR / "retrieval_tests.md"


def main() -> None:
    live_records = {
        str(record["case_id"]): record
        for record in (json.loads(line) for line in RESULTS_PATH.read_text(encoding="utf-8").splitlines() if line.strip())
    }
    engine = HybridEngine()
    results = []
    for case in CASES:
        understanding = CampaignUnderstanding.model_validate(live_records[case.case_id]["campaign_understanding"])
        intent = campaign_intent_from_understanding(
            understanding,
            f"offline_replay_{case.case_id}",
            engine.company_alias_index,
            "direct_adjacent_contextual",
        )
        allowed_ids, prefilter_rejections, _constraints = engine._allowed_ids(intent, {})
        started = time.perf_counter()
        retrieval = engine.retriever.retrieve(build_semantic_queries(understanding), allowed_ids)
        retrieval_ms = int((time.perf_counter() - started) * 1000)
        rank_started = time.perf_counter()
        ranked, rejection_counts = rank_candidates(
            intent,
            build_relevance_policy(understanding),
            engine.profiles,
            retrieval["candidates"],
        )
        rank_ms = int((time.perf_counter() - rank_started) * 1000)
        qualified = scope_rows(ranked, "direct_adjacent_contextual")
        top = qualified[:10]
        top_blob = " ".join(
            f"{profile.list_name} {profile.original_category} {profile.category_group} {profile.source_industry}"
            for profile, _candidate in top
        ).lower()
        forbidden_clear = not any(term.lower() in top_blob for term in case.forbidden_catalogue_terms)
        positive_present = not top or not case.catalogue_terms or any(term.lower() in top_blob for term in case.catalogue_terms)
        tier_counts = Counter(candidate.tier for _profile, candidate in qualified)
        result = {
            "case_id": case.case_id,
            "prompt": case.prompt,
            "passed": (
                retrieval["profiles_scored"] == len(allowed_ids)
                and retrieval["profiles_vector_scored"] == len(allowed_ids)
                and retrieval["profiles_lexically_scored"] == len(allowed_ids)
                and retrieval["query_embedding_calls"] == 1
                and rejection_counts["hard_rejected"] == 0
                and forbidden_clear
                and positive_present
                and all(candidate.matched_evidence for _profile, candidate in qualified)
            ),
            "allowed_profiles": len(allowed_ids),
            "profiles_scored": retrieval["profiles_scored"],
            "profiles_vector_scored": retrieval["profiles_vector_scored"],
            "profiles_lexically_scored": retrieval["profiles_lexically_scored"],
            "query_embedding_calls": retrieval["query_embedding_calls"],
            "query_embedding_tokens": retrieval["query_embedding_tokens"],
            "catalogue_embedding_cache_hit": retrieval["catalogue_embedding_cache_hit"],
            "qualified_profiles": len(qualified),
            "tier_counts": dict(tier_counts),
            "rejection_counts": rejection_counts,
            "prefilter_rejections": prefilter_rejections,
            "forbidden_clear": forbidden_clear,
            "positive_catalogue_alignment": positive_present,
            "retrieval_ms": retrieval_ms,
            "ranking_ms": rank_ms,
            "top_candidates": [
                {
                    "list_id": profile.list_id,
                    "list_name": profile.list_name,
                    "category": profile.category_group,
                    "tier": candidate.tier,
                    "score": candidate.score,
                    "product_similarity": candidate.product_similarity,
                    "audience_similarity": candidate.audience_similarity,
                    "use_case_similarity": candidate.use_case_similarity,
                    "industry_similarity": candidate.industry_similarity,
                    "negative_similarity": candidate.negative_similarity,
                }
                for profile, candidate in top
            ],
        }
        results.append(result)
        print(json.dumps({
            "case": case.case_id,
            "passed": result["passed"],
            "qualified": len(qualified),
            "top": [profile.list_name for profile, _candidate in top[:2]],
        }, ensure_ascii=True), flush=True)

    OUTPUT_PATH.write_text(
        "".join(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n" for result in results),
        encoding="utf-8",
    )
    retrieval_times = [int(result["retrieval_ms"]) for result in results]
    lines = [
        "# Retrieval Replay Tests",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "",
        "This is an offline replay of the validated CampaignUnderstanding objects produced by the live A-Z run. It deliberately does not call the intent model and is not a substitute for the mandatory per-submission planner call. It generates one batched query-embedding request per case and applies the current retrieval and ranking code.",
        "",
        f"Passed: {sum(bool(result['passed']) for result in results)}/{len(results)}.",
        f"Retrieval latency: median {int(statistics.median(retrieval_times))} ms; maximum {max(retrieval_times)} ms.",
        "",
        "| Case | Result | Allowed/scored | Query calls | Qualified | Direct | Adjacent | Contextual | Forbidden clear | Top category | Retrieval ms |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|",
    ]
    for result in results:
        top_category = result["top_candidates"][0]["category"] if result["top_candidates"] else "No qualified evidence"
        tiers = result["tier_counts"]
        lines.append(
            f"| {result['case_id']} | {'PASS' if result['passed'] else 'FAIL'} | {result['allowed_profiles']}/{result['profiles_scored']} | {result['query_embedding_calls']} | {result['qualified_profiles']} | {tiers.get('direct', 0)} | {tiers.get('adjacent', 0)} | {tiers.get('contextual', 0)} | {'Yes' if result['forbidden_clear'] else 'No'} | {top_category} | {result['retrieval_ms']} |"
        )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({
        "cases": len(results),
        "passed": sum(bool(result["passed"]) for result in results),
        "median_retrieval_ms": int(statistics.median(retrieval_times)),
        "max_retrieval_ms": max(retrieval_times),
        "report": str(REPORT_PATH),
    }, indent=2))


if __name__ == "__main__":
    main()
