from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import numpy as np
from .semantic_provider import SemanticProvider


class DenseProviderBase(SemanticProvider):
    index_path: Path
    _data: Dict[str, np.ndarray] | None = None

    def _load(self) -> Dict[str, np.ndarray]:
        if self._data is None:
            loaded = np.load(self.index_path, allow_pickle=False)
            self._data = {name: loaded[name] for name in loaded.files}
        return self._data

    def encode_query(self, query: str) -> np.ndarray:
        raise NotImplementedError

    def search(self, query: str, top_k: int = 300, allowed_ids: set[str] | None = None) -> List[Dict[str, object]]:
        data = self._load()
        scores = data["document_vectors"] @ self.encode_query(query)
        indices = np.argsort(scores)[::-1]
        rows = []
        for index in indices:
            list_id = str(data["list_ids"][index])
            if allowed_ids is not None and list_id not in allowed_ids:
                continue
            rows.append({"list_id": list_id, "score": float(scores[index])})
            if len(rows) >= top_k:
                break
        return rows

    def search_exhaustive(self, query: str, allowed_ids: set[str]) -> List[Dict[str, object]]:
        if not allowed_ids:
            return []
        data = self._load()
        scores = data["document_vectors"] @ self.encode_query(query)
        rows = [
            {"list_id": str(data["list_ids"][index]), "score": float(scores[index])}
            for index in range(len(scores)) if str(data["list_ids"][index]) in allowed_ids
        ]
        rows.sort(key=lambda row: (-float(row["score"]), str(row["list_id"])))
        return rows
