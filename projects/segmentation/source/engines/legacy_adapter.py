from __future__ import annotations

from pathlib import Path
from typing import Dict

from segmentation_engine import build_filter_options, canonicalize_campaign_filters, filter_from_prompt_heuristic, load_cached_segments, recommend_lists


ROOT = Path(__file__).resolve().parents[1]


class LegacyAdapter:
    def __init__(self) -> None:
        self.catalogue = load_cached_segments(ROOT / "data" / "default_segments.tsv", ROOT / "data" / "processed_segments.csv")
        self.options = build_filter_options(self.catalogue)

    def recommend(self, payload: Dict[str, object]) -> Dict[str, object]:
        prompt = str(payload.get("campaign_prompt", "") or "")
        filters = canonicalize_campaign_filters(filter_from_prompt_heuristic(prompt, self.options), self.options) if prompt else {}
        for ui_key, filter_key in (("category", "desired_category"), ("gender", "desired_gender"), ("class", "desired_socioeconomic_class"), ("city", "desired_city"), ("area", "desired_area")):
            value = payload.get(ui_key)
            if value not in (None, "", [], "Any"):
                filters[filter_key] = value
        max_mode = str(payload.get("max_mode", "false")).lower() in {"true", "1", "yes"}
        result = recommend_lists(
            self.catalogue,
            filters,
            max_lists=9999 if max_mode else int(payload.get("max_lists", 30) or 30),
            min_quantity=int(payload.get("min_quantity", 0) or 0),
            target_quantity=int(payload.get("target_quantity", 0) or 0),
        )
        result["engine"] = "legacy"
        result["interpreted_filters"] = filters
        return result
