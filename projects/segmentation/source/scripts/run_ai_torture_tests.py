from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai.schemas import CampaignUnderstanding
from engines.hybrid_engine import HybridEngine


REPORT_DIR = ROOT / "reports" / "ai_rebuild"
RESULTS_PATH = REPORT_DIR / "torture_results.jsonl"
REPORT_PATH = REPORT_DIR / "torture_tests.md"


@dataclass(frozen=True)
class TortureCase:
    case_id: str
    prompt: str
    product_groups: tuple[tuple[str, ...], ...]
    target_groups: tuple[tuple[str, ...], ...] = ()
    market_types: tuple[str, ...] = ("B2B", "B2C", "BOTH", "UNSPECIFIED")
    negative_groups: tuple[tuple[str, ...], ...] = ()
    advertiser: str = ""
    catalogue_terms: tuple[str, ...] = ()
    forbidden_catalogue_terms: tuple[str, ...] = ()


CASES = (
    TortureCase("A", "Promote pet grooming dryers to pet salons and veterinary grooming centers", (("pet",), ("groom", "animal care")), (("pet salon",), ("veterinary",)), ("B2B", "BOTH"), (("human", "beauty salon", "hair salon"),), catalogue_terms=("pet", "veter"), forbidden_catalogue_terms=("hair saloon", "beauty - cosmetics")),
    TortureCase("B", "Promote freeze dryers to pharmaceutical laboratories and food manufacturers", (("freeze dryer", "freeze-drying"),), (("pharmaceutical",), ("food manufact",)), ("B2B", "BOTH"), (("hair dryer", "beauty"),), catalogue_terms=("pharma", "food", "lab", "industr"), forbidden_catalogue_terms=("hair saloon", "beauty - cosmetics")),
    TortureCase("C", "Promote dryer vent cleaning services to homeowners", (("dryer vent",), ("clean",)), (("homeowner", "household"),), ("B2C", "BOTH"), catalogue_terms=("home", "clean", "residential")),
    TortureCase("D", "Promote mobile cranes to construction companies", (("mobile crane", "crane"),), (("construction",),), ("B2B", "BOTH"), (("smartphone", "mobile phone", "telecom"),), catalogue_terms=("construction", "engineer", "contractor", "industrial"), forbidden_catalogue_terms=("smartphone", "mobiles", "telecom")),
    TortureCase("E", "Promote mobile blood donation units to hospitals", (("blood donation", "blood collection"), ("mobile unit", "mobile clinic", "mobile blood")), (("hospital",),), ("B2B", "BOTH"), (("smartphone", "mobile phone", "telecom"),), catalogue_terms=("hospital", "medical", "health", "clinic"), forbidden_catalogue_terms=("smartphone", "telecom")),
    TortureCase("F", "Promote smart irrigation controllers to farms", (("irrigation",), ("controller", "automation")), (("farm", "agricultur"),), ("B2B", "BOTH"), catalogue_terms=("agricultur", "farm", "irrigation")),
    TortureCase("G", "Promote AC Milan shirts to football fans", (("ac milan",), ("shirt", "apparel", "jersey")), (("football fan", "supporter"),), ("B2C", "BOTH"), (("air conditioning", "hvac"),), catalogue_terms=("sport", "football", "fashion", "clothing"), forbidden_catalogue_terms=("aircondition", "hvac", "cooling")),
    TortureCase("H", "Promote car AC compressors to vehicle maintenance centers", (("car ac", "automotive air conditioning"), ("compressor",)), (("vehicle maintenance", "automotive service", "repair center"),), ("B2B", "BOTH"), (("residential", "home air conditioning"),), catalogue_terms=("auto", "vehicle", "car", "spare parts")),
    TortureCase("I", "Promote precision cooling systems to data centers", (("precision cooling",),), (("data center",),), ("B2B", "BOTH"), catalogue_terms=("data", "technology", "software", "industrial", "electro")),
    TortureCase("J", "Promote dental autoclaves to dental clinics", (("dental autoclave", "steriliz"),), (("dental clinic", "dentist"),), ("B2B", "BOTH"), catalogue_terms=("dental", "clinic", "medical", "doctor")),
    TortureCase("K", "Promote commercial dishwashers to restaurants and hotels", (("commercial dishwasher", "dishwashing equipment"),), (("restaurant",), ("hotel", "hospitality")), ("B2B", "BOTH"), catalogue_terms=("restaurant", "hotel", "hospitality", "catering")),
    TortureCase("L", "Promote POS software to restaurant owners", (("pos software", "point of sale"),), (("restaurant owner", "restaurant"),), ("B2B", "BOTH"), catalogue_terms=("restaurant", "software", "business")),
    TortureCase("M", "Promote cybersecurity services to banks and insurance companies", (("cybersecurity", "information security"),), (("bank",), ("insurance",)), ("B2B", "BOTH"), catalogue_terms=("bank", "insurance", "finance", "software", "technology")),
    TortureCase("N", "Promote portable power stations to campers", (("portable power station",),), (("camper", "outdoor"),), ("B2C", "BOTH"), catalogue_terms=("sport", "outdoor", "travel", "electronics")),
    TortureCase("O", "Promote ultrasonic jewellery cleaning machines to jewellery stores", (("ultrasonic",), ("jewellery cleaning", "jewelry cleaning")), (("jewellery store", "jewelry store"),), ("B2B", "BOTH"), catalogue_terms=("jewel", "retail", "store")),
    TortureCase("P", "Promote commercial dough sheeters to bakeries", (("dough sheeter",),), (("baker",),), ("B2B", "BOTH"), catalogue_terms=("baker", "food", "restaurant", "catering")),
    TortureCase("Q", "Promote automatic chicken-feeding systems to poultry farms", (("chicken", "poultry"), ("feeding system", "feeder")), (("poultry farm", "farm"),), ("B2B", "BOTH"), catalogue_terms=("agricultur", "farm", "poultry", "food industr")),
    TortureCase("R", "Promote laboratory centrifuges to diagnostic laboratories", (("centrifuge",),), (("diagnostic laborator", "medical laborator"),), ("B2B", "BOTH"), catalogue_terms=("lab", "medical", "diagnostic", "clinic")),
    TortureCase("S", "Promote thermal imaging cameras to electrical maintenance companies", (("thermal imaging", "infrared camera"),), (("electrical maintenance",),), ("B2B", "BOTH"), catalogue_terms=("electr", "maintenance", "engineer", "industrial")),
    TortureCase("T", "Promote solar panels to homeowners and factories", (("solar panel", "photovoltaic"),), (("homeowner", "household"), ("factor", "manufacturer")), ("BOTH",), catalogue_terms=("home", "industr", "electr", "energy")),
    TortureCase("U", "حملة لمنتجات العناية بالشعر", (("hair care", "الشعر"),), market_types=("B2C", "BOTH", "UNSPECIFIED"), catalogue_terms=("hair", "beauty", "cosmetic")),
    TortureCase("V", "حملة لألواح الطاقة الشمسية للمصانع والمنازل", (("solar", "شمس"),), (("factor", "مصانع"), ("home", "منازل")), ("BOTH",), catalogue_terms=("home", "industr", "electr", "energy")),
    TortureCase("W", "شركة جديدة اسمها Luna Market تريد الترويج لمجففات الشعر", (("hair dryer", "مجففات الشعر"),), market_types=("B2C", "B2B", "BOTH", "UNSPECIFIED"), advertiser="Luna Market", catalogue_terms=("hair", "beauty", "cosmetic")),
    TortureCase("X", "Not hair dryers - industrial dryers for factories.", (("industrial dryer",),), (("factor", "manufactur"),), ("B2B", "BOTH"), (("hair dryer", "beauty"),), catalogue_terms=("industr", "factor", "manufactur", "food"), forbidden_catalogue_terms=("hair saloon", "beauty - cosmetics")),
    TortureCase("Y", "We are NOT promoting iPhones. Promote Samsung refrigerators.", (("refrigerator", "fridge"),), market_types=("B2C", "BOTH", "UNSPECIFIED"), negative_groups=(("iphone", "smartphone", "apple"),), catalogue_terms=("appliance", "fridge", "electronics", "home"), forbidden_catalogue_terms=("iphone", "smartphone", "mobiles")),
    TortureCase("Z", "A company called Mobile House wants to promote refrigerators.", (("refrigerator", "fridge"),), market_types=("B2C", "BOTH", "UNSPECIFIED"), advertiser="Mobile House", catalogue_terms=("appliance", "fridge", "electronics", "home")),
)


def _blob(values: Iterable[object]) -> str:
    return json.dumps(list(values), ensure_ascii=False, default=str).lower()


def _groups_present(blob: str, groups: tuple[tuple[str, ...], ...]) -> bool:
    return all(any(term.lower() in blob for term in group) for group in groups)


def _safe_diagnostics(diagnostics: dict[str, object]) -> dict[str, object]:
    keys = (
        "ai_required", "ai_call_attempted", "ai_call_succeeded", "ai_intent_calls",
        "ai_review_calls", "intent_provider", "intent_model", "intent_latency_ms",
        "intent_error", "campaign_understanding_id", "intent_token_usage",
        "embedding_provider", "embedding_model", "query_embedding_generated",
        "query_embedding_calls", "query_embedding_tokens", "catalogue_embedding_cache_hit",
        "retrieval_mode", "allowed_profiles", "profiles_scored", "profiles_vector_scored",
        "profiles_lexically_scored", "qualified_profiles", "returned_profiles",
        "recommendation_execution", "rejected_leakage", "zero_evidence_leakage",
        "wrong_advertiser_substitution", "age_filter_active",
    )
    return {key: diagnostics.get(key) for key in keys}


def evaluate(case: TortureCase, result: dict[str, object]) -> dict[str, object]:
    raw_understanding = result.get("campaign_understanding")
    structural_valid = False
    understanding = None
    try:
        understanding = CampaignUnderstanding.model_validate(raw_understanding)
        structural_valid = True
    except Exception:
        pass
    diagnostics = dict(result.get("diagnostics") or {})
    plan_blob = _blob([raw_understanding])
    product_blob = _blob(understanding.products_services if understanding else [])
    target_blob = _blob([
        understanding.explicit_target_audiences if understanding else [],
        understanding.inferred_target_audiences if understanding else [],
        understanding.target_roles if understanding else [],
        understanding.target_industries if understanding else [],
        understanding.buyer_types if understanding else [],
        understanding.user_types if understanding else [],
    ])
    negative_blob = _blob([
        understanding.negative_concepts if understanding else [],
        understanding.false_friend_concepts if understanding else [],
    ])
    advertiser_ok = bool(understanding)
    if understanding:
        if case.advertiser:
            advertiser_ok = understanding.advertiser.explicitly_mentioned and case.advertiser.lower() in understanding.advertiser.name.lower()
        else:
            advertiser_ok = not understanding.advertiser.explicitly_mentioned
    rows = list(result.get("recommended") or [])
    evidence_supported = all(bool(row.get("Matched Evidence")) for row in rows)
    row_blob = _blob([
        [row.get("List Name"), row.get("Business Category Group"), row.get("Source Industry"), row.get("Audience")]
        for row in rows[:10]
    ])
    forbidden_clear = not any(term.lower() in row_blob for term in case.forbidden_catalogue_terms)
    catalogue_alignment = True
    if rows and case.catalogue_terms:
        catalogue_alignment = any(term.lower() in row_blob for term in case.catalogue_terms) and forbidden_clear
    criteria = {
        "openai_called_once": diagnostics.get("ai_call_succeeded") is True and diagnostics.get("ai_intent_calls") == 1,
        "understanding_structurally_valid": structural_valid,
        "product_interpreted": _groups_present(product_blob or plan_blob, case.product_groups),
        "advertiser_separated": advertiser_ok and diagnostics.get("wrong_advertiser_substitution", 0) == 0,
        "market_understood": bool(understanding and understanding.market_type in case.market_types),
        "explicit_audiences_preserved": _groups_present(target_blob, case.target_groups),
        "false_friends_recognized": _groups_present(negative_blob, case.negative_groups),
        "retrieval_executed": diagnostics.get("recommendation_execution") == "executed" and diagnostics.get("query_embedding_generated") is True and int(diagnostics.get("profiles_scored", 0) or 0) > 0,
        "rejected_rows_excluded": diagnostics.get("rejected_leakage", 0) == 0,
        "catalogue_evidence_supported": evidence_supported and catalogue_alignment,
        "zero_evidence_excluded": diagnostics.get("zero_evidence_leakage", 0) == 0,
        "taxonomy_not_required": diagnostics.get("recommendation_execution") == "executed" and diagnostics.get("retrieval_mode") in {"all_allowed_vectorized", "exhaustive"},
    }
    return {
        "case_id": case.case_id,
        "prompt": case.prompt,
        "passed": all(criteria.values()),
        "criteria": criteria,
        "campaign_understanding": raw_understanding,
        "diagnostics": _safe_diagnostics(diagnostics),
        "timings": result.get("timings", {}),
        "summary": result.get("summary", {}),
        "top_candidates": [
            {
                "list_id": row.get("List ID"),
                "list_name": row.get("List Name"),
                "category": row.get("Business Category Group"),
                "tier": row.get("Candidate Tier"),
                "similarities": row.get("Semantic Similarities"),
                "evidence": row.get("Matched Evidence"),
            }
            for row in rows[:10]
        ],
    }


def write_report(records: list[dict[str, object]], review_enabled: bool) -> None:
    records = sorted(records, key=lambda record: str(record["case_id"]))
    passed = sum(bool(record.get("passed")) for record in records)
    lines = [
        "# AI Torture Tests",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"Cases: {len(records)}; fully passed: {passed}; failed: {len(records) - passed}",
        f"Optional top-candidate review during matrix: {'enabled' if review_enabled else 'disabled to isolate planner/retrieval behavior and control cost'}.",
        "",
        "| Case | Result | Intent calls | Product | Market | Explicit target | False friend | Retrieval | Evidence/alignment | Returned | Intent ms | Total ms |",
        "|---|---|---:|---|---|---|---|---|---|---:|---:|---:|",
    ]
    for record in records:
        criteria = record["criteria"]
        diagnostics = record["diagnostics"]
        timings = record["timings"]
        lines.append(
            "| {case} | {result} | {calls} | {product} | {market} | {target} | {negative} | {retrieval} | {evidence} | {returned} | {intent_ms} | {total_ms} |".format(
                case=record["case_id"],
                result="PASS" if record["passed"] else "FAIL",
                calls=diagnostics.get("ai_intent_calls", 0),
                product="PASS" if criteria["product_interpreted"] else "FAIL",
                market="PASS" if criteria["market_understood"] else "FAIL",
                target="PASS" if criteria["explicit_audiences_preserved"] else "FAIL",
                negative="PASS" if criteria["false_friends_recognized"] else "FAIL",
                retrieval="PASS" if criteria["retrieval_executed"] else "FAIL",
                evidence="PASS" if criteria["catalogue_evidence_supported"] else "FAIL",
                returned=diagnostics.get("returned_profiles", 0),
                intent_ms=diagnostics.get("intent_latency_ms", 0),
                total_ms=timings.get("total_ms", 0),
            )
        )
    lines.extend(["", "## Failures", ""])
    failures = [record for record in records if not record["passed"]]
    if not failures:
        lines.append("None.")
    for record in failures:
        failed = [name for name, value in record["criteria"].items() if not value]
        error = record["diagnostics"].get("intent_error") or "none"
        lines.append(f"- **{record['case_id']}** `{record['prompt']}`: {', '.join(failed)}; API error: `{error}`.")
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--review", action="store_true", help="Enable the optional second LLM review call.")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--rerun-failed", action="store_true")
    parser.add_argument("--cases", default="", help="Comma-separated case IDs to run.")
    parser.add_argument("--replace-selected", action="store_true")
    args = parser.parse_args()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    existing: list[dict[str, object]] = []
    if (args.resume or args.rerun_failed or args.replace_selected) and RESULTS_PATH.exists():
        existing = [json.loads(line) for line in RESULTS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.rerun_failed:
        existing = [record for record in existing if record.get("passed")]
        RESULTS_PATH.write_text(
            "".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n" for record in existing),
            encoding="utf-8",
        )
    requested_ids = {value.strip().upper() for value in args.cases.split(",") if value.strip()}
    if args.replace_selected and requested_ids:
        existing = [record for record in existing if str(record.get("case_id")) not in requested_ids]
        RESULTS_PATH.write_text(
            "".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n" for record in existing),
            encoding="utf-8",
        )
    completed = {str(record["case_id"]) for record in existing}
    selected = tuple(case for case in CASES if not requested_ids or case.case_id in requested_ids)
    selected = selected[: args.limit or len(selected)]
    engine = HybridEngine()
    records = existing
    output_mode = "a" if existing else "w"
    with RESULTS_PATH.open(output_mode, encoding="utf-8", newline="\n") as handle:
        for case in selected:
            if case.case_id in completed:
                continue
            started = time.perf_counter()
            try:
                result = engine.recommend({
                    "campaign_prompt": case.prompt,
                    "max_lists": 10,
                    "candidate_scope": "direct_adjacent_contextual",
                    "age_filter_active": False,
                    "ai_review_top_results": args.review,
                })
                record = evaluate(case, result)
            except Exception as exc:
                record = {
                    "case_id": case.case_id,
                    "prompt": case.prompt,
                    "passed": False,
                    "criteria": {"unhandled_exception": False},
                    "campaign_understanding": None,
                    "diagnostics": {"intent_error": type(exc).__name__},
                    "timings": {"total_ms": int((time.perf_counter() - started) * 1000)},
                    "summary": {},
                    "top_candidates": [],
                }
            records.append(record)
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            handle.flush()
            print(json.dumps({
                "case": case.case_id,
                "passed": record["passed"],
                "failed_criteria": [key for key, value in record["criteria"].items() if not value],
                "intent_calls": record["diagnostics"].get("ai_intent_calls", 0),
                "returned": record["diagnostics"].get("returned_profiles", 0),
                "total_ms": record["timings"].get("total_ms", 0),
            }, ensure_ascii=True), flush=True)
            write_report(records, args.review)
    write_report(records, args.review)
    print(json.dumps({"cases": len(records), "passed": sum(bool(row["passed"]) for row in records), "report": str(REPORT_PATH)}, indent=2))


if __name__ == "__main__":
    main()
