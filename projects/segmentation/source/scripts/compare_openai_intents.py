from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import (
    BASE_DIR,
    DOTENV_LOADED,
    LLM_INTENT_ENABLED,
    OPENAI_CONFIGURED,
    OPENAI_INTENT_MODEL,
    SEMANTIC_PROVIDER,
)
from intent.llm_parser import LLMIntentResult, parse_optional_structured_intent
from intent.parser import parse_campaign_intent


PROMPTS = [
    "Promote pet grooming dryers to pet salons",
    "Promote solar panels to factories and homeowners",
    "AC Milan shirts for football fans",
    "حملة لمنتجات العناية بالشعر",
    "Promote mobile cranes to construction companies",
    "Promote industrial dryers to food factories",
]

COMMON_FIELDS = (
    "advertisers",
    "brands",
    "raw_product_phrases",
    "normalized_product_concepts",
    "open_product_terms",
    "use_cases",
    "audience_type",
    "target_entities",
    "target_roles",
    "target_industries",
    "explicit_filters",
    "offer",
    "product_positioning",
    "likely_class_affinity",
    "campaign_type",
    "clarification_needed",
    "ambiguity_notes",
    "confidence",
)


def _local_view(prompt: str) -> dict[str, Any]:
    intent = parse_campaign_intent(prompt, llm_intent_enabled=False)
    return {
        "advertisers": intent.advertisers,
        "brands": intent.brands,
        "raw_product_phrases": intent.raw_product_phrases,
        "normalized_product_concepts": intent.normalized_product_concepts,
        "open_product_terms": intent.open_product_terms,
        "use_cases": intent.use_cases,
        "audience_type": intent.audience_type,
        "target_entities": intent.target_entities,
        "target_roles": intent.target_roles,
        "target_industries": intent.target_industries,
        "explicit_filters": intent.explicit_filters.__dict__,
        "offer": intent.offer,
        "product_positioning": intent.product_attributes.positioning,
        "likely_class_affinity": intent.class_affinity,
        "campaign_type": intent.campaign_type,
        "clarification_needed": intent.clarification_needed,
        "ambiguity_notes": intent.ambiguity_notes,
        "confidence": intent.confidence,
    }


def _differences(local: dict[str, Any], remote: dict[str, Any]) -> list[str]:
    changed = [field for field in COMMON_FIELDS if local.get(field) != remote.get(field)]
    return changed or ["none"]


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def main() -> None:
    rows: list[tuple[str, dict[str, Any], LLMIntentResult, dict[str, Any]]] = []
    for prompt in PROMPTS:
        local = _local_view(prompt)
        result = parse_optional_structured_intent(prompt, enabled=True)
        openai_intent = result.payload if result.used else local
        rows.append((prompt, local, result, openai_intent))

    total_calls = sum(result.call_count for _, _, result, _ in rows)
    fallbacks = sum(not result.used for _, _, result, _ in rows)
    lines = [
        "# OpenAI Intent Comparison",
        "",
        "This report compares intent interpretation only. No catalogue, retrieval, ranking, candidate, profile, company, tier, or Max processing was invoked.",
        "",
        "## Run Diagnostics",
        "",
        f"- `.env` loaded: `{str(DOTENV_LOADED).lower()}`",
        f"- OpenAI key detected: `{str(OPENAI_CONFIGURED).lower()}`",
        f"- LLM intent enabled: `{str(LLM_INTENT_ENABLED).lower()}`",
        f"- Model: `{OPENAI_INTENT_MODEL}`",
        f"- OpenAI intent calls: `{total_calls}`",
        f"- Fallbacks/errors: `{fallbacks}`",
        f"- Embedding provider: `{SEMANTIC_PROVIDER}`",
        "- OpenAI embeddings used: `false`",
        "",
    ]
    for index, (prompt, local, result, openai_intent) in enumerate(rows, start=1):
        differences = _differences(local, openai_intent)
        lines.extend([
            f"## {index}. {prompt}",
            "",
            f"- Provider: `{result.provider}`",
            f"- Call count: `{result.call_count}`",
            f"- Intent latency: `{result.latency_ms} ms`",
            f"- Error/fallback: `{result.error or 'none'}`",
            f"- Differing fields: `{', '.join(differences)}`",
            "",
            "### LOCAL INTENT",
            "",
            "```json",
            _json(local),
            "```",
            "",
            "### OPENAI INTENT",
            "",
            "```json",
            _json(openai_intent),
            "```",
            "",
        ])

    report_path = BASE_DIR / "reports" / "openai_intent_comparison.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({
        "report": str(report_path),
        "dotenv_loaded": DOTENV_LOADED,
        "openai_configured": OPENAI_CONFIGURED,
        "model": OPENAI_INTENT_MODEL,
        "calls": total_calls,
        "fallbacks": fallbacks,
        "latencies_ms": [result.latency_ms for _, _, result, _ in rows],
        "errors": [result.error for _, _, result, _ in rows if result.error],
    }))


if __name__ == "__main__":
    main()
