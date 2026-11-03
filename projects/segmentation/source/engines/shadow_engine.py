from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict

from .hybrid_engine import HybridEngine
from .legacy_adapter import LegacyAdapter


class ShadowEngine:
    def __init__(self, report_dir: Path):
        self.legacy = LegacyAdapter()
        self.hybrid = HybridEngine()
        self.report_dir = report_dir
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def recommend(self, payload: Dict[str, object]) -> Dict[str, object]:
        legacy = self.legacy.recommend(payload)
        hybrid = self.hybrid.recommend(payload)
        comparison = {
            "created_at_unix": time.time(),
            "prompt": payload.get("campaign_prompt", ""),
            "legacy_ids": [row.get("List ID") for row in legacy.get("recommended", [])],
            "hybrid_ids": [row.get("List ID") for row in hybrid.get("recommended", [])],
            "hybrid_diagnostics": hybrid.get("diagnostics", {}),
        }
        path = self.report_dir / f"shadow_{int(time.time() * 1000)}.json"
        path.write_text(json.dumps(comparison, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        legacy["shadow_comparison_file"] = str(path)
        return legacy

