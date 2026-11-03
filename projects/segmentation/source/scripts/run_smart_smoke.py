from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engines.hybrid_engine import HybridEngine


PROMPTS = [
    "iPhone 17 Pro Max campaign",
    "SmartBuy Samsung air conditioners in Amman East",
    "professional hair dryers",
    "industrial dryers to factories",
    "mobile telecom package",
    "mobile cranes for construction",
    "AC Milan shirts",
    "car AC maintenance",
    "solar panels to factories and homeowners",
    "حملة لمنتجات العناية بالشعر",
    "A new company called Luna Market wants to promote hair dryers",
    "A new company called Mobile House wants to promote refrigerators",
    "Not hair dryers - industrial dryers",
    "Promote accounting software to accountants",
    "Promote pet grooming dryers to pet salons",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True)
    parser.add_argument("--count", type=int, default=10, choices=(10, 15))
    parser.add_argument("--tests-passed", type=int, default=0)
    parser.add_argument("--tests-failed", type=int, default=0)
    args = parser.parse_args()

    engine = HybridEngine()
    rows = []
    for prompt in PROMPTS[: args.count]:
        result = engine.recommend({"campaign_prompt": prompt, "max_lists": 10, "candidate_scope": "direct_adjacent_contextual"})
        rows.append({
            "query": prompt,
            "recommendations": len(result["recommended"]),
            "latency_ms": result["timings"]["total_ms"],
            "clarification_needed": result["interpreted_intent"]["clarification_needed"],
        })
    latencies = [row["latency_ms"] for row in rows]
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": args.stage,
        "tests_passed": args.tests_passed,
        "tests_failed": args.tests_failed,
        "benchmark_v1": {"status": "not_due"},
        "benchmark_v2": {"status": "not_due"},
        "latency": {"smoke_median_ms": statistics.median(latencies), "smoke_max_ms": max(latencies)},
        "recommendation_counts": {row["query"]: row["recommendations"] for row in rows},
        "zero_result_prompts": [row["query"] for row in rows if row["recommendations"] == 0],
        "regressions": [],
    }
    output = ROOT / "reports" / "smart_rebuild" / "continuous_tests.jsonl"
    with output.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(json.dumps(record, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
