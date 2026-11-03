from __future__ import annotations

from typing import Dict, List, Sequence


def reciprocal_rank_fusion(lexical: Sequence[Dict[str, object]], semantic: Sequence[Dict[str, object]], limit: int | None = 500, rank_constant: int = 60) -> List[Dict[str, object]]:
    fused: Dict[str, Dict[str, float | str]] = {}
    for provider, rows in (("lexical", lexical), ("semantic", semantic)):
        for rank, row in enumerate(rows, start=1):
            list_id = str(row["list_id"])
            item = fused.setdefault(list_id, {"list_id": list_id, "fused_score": 0.0, "lexical_score": 0.0, "semantic_score": 0.0})
            item["fused_score"] = float(item["fused_score"]) + 1.0 / (rank_constant + rank)
            item[f"{provider}_score"] = float(row["score"])
    ranked = sorted(fused.values(), key=lambda item: (-float(item["fused_score"]), str(item["list_id"])))
    return ranked if limit is None else ranked[:limit]
