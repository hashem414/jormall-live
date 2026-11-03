from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.document import Document, DocumentChunk
from app.services.chat_stream_service import prepare_streaming_plan


CASES_PATH = Path(__file__).with_name("retrieval_cases.json")


def load_cases(path: Path = CASES_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def has_real_openai_key() -> bool:
    if settings.openai_api_key is None:
        return False
    value = settings.openai_api_key.get_secret_value().strip()
    return bool(value and "REPLACE_ME" not in value)


def corpus_coverage(cases: dict[str, Any]) -> dict[str, Any]:
    client_slug = cases["client_slug"]
    with SessionLocal() as db:
        rows = db.execute(
            select(Document.original_filename, DocumentChunk.content)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                Document.client_slug == client_slug,
                DocumentChunk.client_slug == client_slug,
                Document.status == "active",
                Document.visibility == "client",
            )
        ).all()
    results = []
    for case in cases["grounded"]:
        candidate_text = "\n".join(
            content for filename, content in rows if filename == case["expected_document"]
        ).casefold()
        missing = [
            term for term in case["required_terms"] if term.casefold() not in candidate_text
        ]
        results.append({"id": case["id"], "passed": not missing, "missing_terms": missing})
    passed = sum(item["passed"] for item in results)
    return {
        "metric": "approved_corpus_fact_coverage",
        "passed": passed,
        "total": len(results),
        "rate": passed / len(results) if results else 0.0,
        "cases": results,
    }


def live_retrieval_metrics(cases: dict[str, Any]) -> dict[str, Any]:
    client_slug = cases["client_slug"]
    grounded_results, unknown_results = [], []
    with SessionLocal() as db:
        for case in cases["grounded"]:
            plan = prepare_streaming_plan(
                retrieval_question=case["question"], db=db, client_slug=client_slug
            )
            chunks = plan.chunks if plan is not None else []
            source_correct = any(
                chunk.original_filename == case["expected_document"] for chunk in chunks
            )
            combined = "\n".join(chunk.content for chunk in chunks).casefold()
            facts_present = all(
                term.casefold() in combined for term in case["required_terms"]
            )
            grounded_results.append(
                {"id": case["id"], "hit": bool(plan and facts_present), "source_correct": source_correct}
            )
        for case in cases["unknown"]:
            plan = prepare_streaming_plan(
                retrieval_question=case["question"], db=db, client_slug=client_slug
            )
            unknown_results.append({"id": case["id"], "abstained": plan is None})
    grounded_hits = sum(item["hit"] for item in grounded_results)
    source_hits = sum(item["source_correct"] for item in grounded_results)
    abstentions = sum(item["abstained"] for item in unknown_results)
    return {
        "grounded_hit_rate": grounded_hits / len(grounded_results),
        "source_correctness_rate": source_hits / len(grounded_results),
        "unknown_abstention_rate": abstentions / len(unknown_results),
        "incorrect_match_rate": 1 - (abstentions / len(unknown_results)),
        "grounded_cases": grounded_results,
        "unknown_cases": unknown_results,
    }


def evaluate(*, live: bool) -> tuple[dict[str, Any], bool]:
    cases = load_cases()
    report: dict[str, Any] = {
        "schema_version": cases["schema_version"],
        "client_slug": cases["client_slug"],
        "gates": cases["gates"],
        "languages": sorted({case["language"] for case in cases["grounded"]}),
        "corpus": corpus_coverage(cases),
    }
    passed = report["corpus"]["rate"] >= cases["gates"]["grounded_hit_rate"]
    if live:
        if not has_real_openai_key():
            report["live_retrieval"] = {
                "status": "not_run",
                "reason": "A real OPENAI_API_KEY is required for query embeddings.",
            }
            return report, False
        metrics = live_retrieval_metrics(cases)
        report["live_retrieval"] = {"status": "completed", **metrics}
        passed = passed and all((
            metrics["grounded_hit_rate"] >= cases["gates"]["grounded_hit_rate"],
            metrics["unknown_abstention_rate"] >= cases["gates"]["unknown_abstention_rate"],
            metrics["source_correctness_rate"] >= cases["gates"]["source_correctness_rate"],
        ))
    else:
        report["live_retrieval"] = {"status": "not_requested"}
    return report, passed


def main() -> int:
    parser = argparse.ArgumentParser(description="Run bilingual retrieval assurance metrics.")
    parser.add_argument("--live", action="store_true", help="Use configured query embeddings.")
    parser.add_argument("--output", type=Path, help="Write the JSON report to this path.")
    args = parser.parse_args()
    report, passed = evaluate(live=args.live)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
