from __future__ import annotations

import hashlib
import json
import math
import re
import time
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np

from config import SEMANTIC_HASH_DIM, SEMANTIC_INDEX_PATH, SEMANTIC_METADATA_PATH, SEMANTIC_VECTOR_DIM
from .semantic_provider import SemanticProvider


def _tokens(text: str) -> List[str]:
    return [token for token in re.findall(r"[\w]+", text.lower(), flags=re.UNICODE) if len(token) > 1]


def _bucket(token: str, dimensions: int) -> int:
    return int.from_bytes(hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest(), "little") % dimensions


def _tf_matrix(texts: Sequence[str], dimensions: int) -> Tuple[np.ndarray, np.ndarray]:
    matrix = np.zeros((len(texts), dimensions), dtype=np.float32)
    document_frequency = np.zeros(dimensions, dtype=np.int32)
    for row_index, text in enumerate(texts):
        counts: Dict[int, int] = {}
        for token in _tokens(text):
            bucket = _bucket(token, dimensions)
            counts[bucket] = counts.get(bucket, 0) + 1
        for bucket, count in counts.items():
            matrix[row_index, bucket] = 1.0 + math.log(count)
            document_frequency[bucket] += 1
    return matrix, document_frequency


def _normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


class LocalLSAProvider(SemanticProvider):
    def __init__(self, index_path: Path = SEMANTIC_INDEX_PATH, metadata_path: Path = SEMANTIC_METADATA_PATH):
        self.index_path = index_path
        self.metadata_path = metadata_path
        self._data: Dict[str, np.ndarray] | None = None

    def build(self, documents: Sequence[Dict[str, object]], source_hash: str) -> Dict[str, object]:
        started = time.perf_counter()
        texts = [str(document["text"]) for document in documents]
        matrix, df = _tf_matrix(texts, SEMANTIC_HASH_DIM)
        idf = np.log((len(texts) + 1) / (df + 1)).astype(np.float32) + 1.0
        matrix *= idf
        matrix = _normalize(matrix)
        requested = min(SEMANTIC_VECTOR_DIM, SEMANTIC_HASH_DIM, max(2, len(texts) - 1))
        oversample = min(12, max(4, requested // 4))
        rng = np.random.default_rng(20260806)
        omega = rng.standard_normal((SEMANTIC_HASH_DIM, requested + oversample), dtype=np.float32)
        projected = matrix @ omega
        projected = matrix @ (matrix.T @ projected)
        q, _ = np.linalg.qr(projected, mode="reduced")
        reduced = q.T @ matrix
        _u, _singular, vt = np.linalg.svd(reduced, full_matrices=False)
        components = vt[:requested].astype(np.float32)
        document_vectors = _normalize((matrix @ components.T).astype(np.float32))
        list_ids = np.asarray([str(document["list_id"]) for document in documents])
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(self.index_path, idf=idf, components=components, document_vectors=document_vectors, list_ids=list_ids)
        metadata = {
            "provider": "hashed_tfidf_truncated_svd_numpy",
            "source_hash": source_hash,
            "documents": len(documents),
            "hash_dimensions": SEMANTIC_HASH_DIM,
            "vector_dimensions": requested,
            "build_ms": int((time.perf_counter() - started) * 1000),
            "index_bytes": self.index_path.stat().st_size,
        }
        self.metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        self._data = None
        return metadata

    def _load(self) -> Dict[str, np.ndarray]:
        if self._data is None:
            loaded = np.load(self.index_path, allow_pickle=False)
            self._data = {name: loaded[name] for name in loaded.files}
        return self._data

    def _query_vector(self, query: str, idf: np.ndarray, components: np.ndarray) -> np.ndarray:
        vector = np.zeros((1, len(idf)), dtype=np.float32)
        counts: Dict[int, int] = {}
        for token in _tokens(query):
            bucket = _bucket(token, len(idf))
            counts[bucket] = counts.get(bucket, 0) + 1
        for bucket, count in counts.items():
            vector[0, bucket] = (1.0 + math.log(count)) * idf[bucket]
        vector = _normalize(vector) @ components.T
        return _normalize(vector)[0]

    def search(self, query: str, top_k: int = 300, allowed_ids: set[str] | None = None) -> List[Dict[str, object]]:
        data = self._load()
        query_vector = self._query_vector(query, data["idf"], data["components"])
        scores = data["document_vectors"] @ query_vector
        count = min(len(scores), max(top_k * 3, top_k))
        indices = np.argpartition(scores, -count)[-count:]
        indices = indices[np.argsort(scores[indices])[::-1]]
        results = []
        for index in indices:
            list_id = str(data["list_ids"][index])
            if allowed_ids is not None and list_id not in allowed_ids:
                continue
            results.append({"list_id": list_id, "score": float(scores[index])})
            if len(results) >= top_k:
                break
        return results

    def search_exhaustive(self, query: str, allowed_ids: set[str]) -> List[Dict[str, object]]:
        """Vector-score the complete allowed universe without a top-K pre-cap."""
        if not allowed_ids:
            return []
        data = self._load()
        query_vector = self._query_vector(query, data["idf"], data["components"])
        scores = data["document_vectors"] @ query_vector
        allowed_indices = [index for index, value in enumerate(data["list_ids"]) if str(value) in allowed_ids]
        allowed_indices.sort(key=lambda index: (-float(scores[index]), str(data["list_ids"][index])))
        return [
            {"list_id": str(data["list_ids"][index]), "score": float(scores[index])}
            for index in allowed_indices
        ]
