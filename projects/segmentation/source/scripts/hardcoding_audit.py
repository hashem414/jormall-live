from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import PRODUCT_TAXONOMY_PATH, RAW_CATALOGUE_PATH, RELATIONSHIP_RULES_PATH
from profiles.raw_parser import read_raw_catalogue


ACTIVE_ROOTS = [ROOT / name for name in ("ai", "domain", "explanations", "profiles", "ranking", "retrieval")]
ACTIVE_INTENT_FILES = [
    ROOT / "intent" / name
    for name in ("advertiser_parser.py", "class_affinity.py", "product_disambiguation.py", "product_taxonomy.py")
]
ACTIVE_FILES = [
    ROOT / "app.py",
    ROOT / "config.py",
    ROOT / "engines" / "hybrid_engine.py",
    *ACTIVE_INTENT_FILES,
    *[path for base in ACTIVE_ROOTS for path in base.rglob("*.py")],
]
LEGACY_FILES = [
    ROOT / "segmentation_engine.py",
    ROOT / "engines" / "legacy_adapter.py",
    ROOT / "engines" / "shadow_engine.py",
    *[
        path
        for path in (ROOT / "intent").glob("*.py")
        if path not in ACTIVE_INTENT_FILES and path.name != "__init__.py"
    ],
]


def literals(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        (getattr(node, "lineno", 0), node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def scan(
    files: list[Path],
    companies: set[str],
    benchmark_queries: set[str],
    product_terms: set[str],
) -> dict[str, list[tuple[object, ...]]]:
    result: dict[str, list[tuple[object, ...]]] = {
        "company": [], "prompt": [], "product": [], "large_branch": [], "prompt_branch": [],
    }
    for path in sorted(set(files)):
        relative = str(path.relative_to(ROOT))
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for line, value in literals(path):
            normalized = " ".join(value.lower().split())
            if normalized in companies:
                result["company"].append((relative, line, value))
            if normalized in benchmark_queries:
                result["prompt"].append((relative, line, value))
            if normalized in product_terms and not relative.endswith("product_taxonomy.py"):
                result["product"].append((relative, line, value))
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            chain = 1
            cursor = node
            while len(cursor.orelse) == 1 and isinstance(cursor.orelse[0], ast.If):
                chain += 1
                cursor = cursor.orelse[0]
            if chain >= 8:
                result["large_branch"].append((relative, node.lineno, chain))
            names = {item.id.lower() for item in ast.walk(node.test) if isinstance(item, ast.Name)}
            constants = [
                item.value
                for item in ast.walk(node.test)
                if isinstance(item, ast.Constant) and isinstance(item.value, str) and len(item.value.strip()) >= 3
            ]
            if names & {"prompt", "raw_prompt", "campaign_prompt", "query"} and constants:
                result["prompt_branch"].append((relative, node.lineno, " | ".join(constants[:5])))
    return result


def section(lines: list[str], title: str, values: list[tuple[object, ...]]) -> None:
    lines.extend([f"## {title}", ""])
    if values:
        lines.extend(f"- `{path}:{line}`: `{value}`" for path, line, value, *_rest in values[:100])
    else:
        lines.append("None.")
    lines.append("")


def main() -> None:
    companies = {
        str(row["source_owner"]).lower()
        for row in read_raw_catalogue(RAW_CATALOGUE_PATH)
        if len(str(row["source_owner"])) >= 5 and len(str(row["source_owner"]).split()) >= 2
    }
    benchmark_queries = {
        json.loads(line)["query"].lower()
        for benchmark in (ROOT / "benchmarks" / "campaigns.jsonl", ROOT / "benchmarks_v2" / "challenge_set.jsonl")
        for line in benchmark.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    taxonomy = json.loads(PRODUCT_TAXONOMY_PATH.read_text(encoding="utf-8"))
    relationships = json.loads(RELATIONSHIP_RULES_PATH.read_text(encoding="utf-8"))
    product_terms = {
        str(alias).lower()
        for item in taxonomy["products"]
        for alias in item.get("aliases", [])
        if len(str(alias)) >= 5
    }
    product_terms.update(
        str(term).lower()
        for group in relationships["concept_groups"]
        for term in group.get("seed_terms", [])
        if len(str(term)) >= 5
    )

    active = scan(ACTIVE_FILES, companies, benchmark_queries, product_terms)
    legacy = scan(LEGACY_FILES, companies, benchmark_queries, product_terms)
    active_blocking = [*active["company"], *active["prompt"], *active["large_branch"], *active["prompt_branch"]]
    status = "PASS" if not active_blocking else "FAIL"
    lines = [
        "# Production Hardcoding Audit", "", f"Status: {status}", "",
        "The mandatory AI path and isolated legacy compatibility code are reported separately. With `AI_REQUIRED=true`, every recommendation endpoint forces `HybridEngine`; legacy and shadow engines cannot be selected.", "",
        f"- Active AI-path Python files scanned: {len(set(ACTIVE_FILES))}",
        f"- Active company literals: {len(active['company'])}",
        f"- Active exact benchmark prompts: {len(active['prompt'])}",
        f"- Active prompt-dependent literal branches: {len(active['prompt_branch'])}",
        f"- Active branch chains (8+): {len(active['large_branch'])}",
        f"- Active product literals outside taxonomy: {len(active['product'])} (informational; planner guidance may name false-friend examples)", "",
    ]
    section(lines, "Active Company Literals", active["company"])
    section(lines, "Active Exact Prompt Literals", active["prompt"])
    section(lines, "Active Prompt Branches", active["prompt_branch"])
    section(lines, "Active Large Branches", active["large_branch"])
    section(lines, "Active Product Literals", active["product"])
    lines.extend([
        "## Isolated Legacy Findings", "",
        f"- Legacy/dormant files scanned: {len(set(LEGACY_FILES))}",
        f"- Company literals: {len(legacy['company'])}",
        f"- Exact prompts: {len(legacy['prompt'])}",
        f"- Prompt-dependent literal branches: {len(legacy['prompt_branch'])}",
        f"- Large branches: {len(legacy['large_branch'])}",
        f"- Product literals: {len(legacy['product'])}", "",
        "These findings remain for development comparison and old catalogue utilities. They are not reachable as campaign reasoning while `AI_REQUIRED=true`; tests verify that the public recommendation routes force the hybrid engine.", "",
    ])
    section(lines, "Legacy Company Literals", legacy["company"])
    section(lines, "Legacy Prompt Branches", legacy["prompt_branch"])
    section(lines, "Legacy Large Branches", legacy["large_branch"])
    section(lines, "Legacy Product Literals", legacy["product"])
    output = ROOT / "reports" / "ai_rebuild" / "hardcoding_audit.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({
        "status": status,
        "active_company_literals": len(active["company"]),
        "active_exact_prompts": len(active["prompt"]),
        "active_prompt_branches": len(active["prompt_branch"]),
        "active_large_branches": len(active["large_branch"]),
        "active_product_literals": len(active["product"]),
        "legacy_product_literals": len(legacy["product"]),
    }, indent=2))


if __name__ == "__main__":
    main()
