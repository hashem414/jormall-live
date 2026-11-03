from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Sequence


class SemanticProvider(ABC):
    @abstractmethod
    def build(self, documents: Sequence[Dict[str, object]], source_hash: str) -> Dict[str, object]:
        raise NotImplementedError

    @abstractmethod
    def search(self, query: str, top_k: int, allowed_ids: set[str] | None = None) -> List[Dict[str, object]]:
        raise NotImplementedError

    def score_multi(self, queries: Dict[str, str], allowed_ids: set[str]) -> Dict[str, object]:
        dimension_rows = {
            name: self.search_exhaustive(query, allowed_ids)
            for name, query in queries.items()
        }
        by_id: Dict[str, Dict[str, object]] = {}
        for name, rows in dimension_rows.items():
            for row in rows:
                item = by_id.setdefault(str(row["list_id"]), {"list_id": str(row["list_id"])})
                item[f"{name}_similarity"] = float(row["score"])
        return {
            "rows": list(by_id.values()),
            "query_embedding_generated": False,
            "query_embedding_calls": 0,
            "catalogue_embedding_cache_hit": True,
        }

    def search_exhaustive(self, query: str, allowed_ids: set[str]) -> List[Dict[str, object]]:
        return self.search(query, len(allowed_ids), allowed_ids)
