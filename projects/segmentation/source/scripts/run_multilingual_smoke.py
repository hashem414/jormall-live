from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engines.hybrid_engine import HybridEngine


PROMPTS = [
    "منتجات العناية بالشعر",
    "مجففات الشعر",
    "هواتف ذكية",
    "مكيفات",
    "ألواح شمسية",
    "معدات مصانع",
    "برامج محاسبة",
]


def main() -> None:
    engine = HybridEngine()
    rows = []
    for prompt in PROMPTS:
        result = engine.recommend({"campaign_prompt": prompt, "max_lists": 10})
        rows.append({
            "query": prompt,
            "recommendations": len(result["recommended"]),
            "latency_ms": result["timings"]["total_ms"],
            "normalized_concepts": result["interpreted_intent"]["normalized_product_concepts"],
        })
    output = ROOT / "reports" / "smart_rebuild" / "multilingual_smoke.json"
    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(rows, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
