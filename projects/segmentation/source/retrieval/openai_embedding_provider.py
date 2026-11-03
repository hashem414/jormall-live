from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Dict, Sequence

import numpy as np

from ai.openai_client import create_openai_client
from config import (
    EMBEDDING_CACHE_DIR,
    OPENAI_EMBEDDING_BATCH_SIZE,
    OPENAI_EMBEDDING_MODEL,
    OPENAI_EMBEDDING_TIMEOUT_SECONDS,
    OPENAI_EMBEDDINGS_ENABLED,
)
from .dense_provider_base import DenseProviderBase


def _normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.maximum(norms, 1e-12)


class OpenAIEmbeddingProvider(DenseProviderBase):
    def __init__(self) -> None:
        if not OPENAI_EMBEDDINGS_ENABLED:
            raise RuntimeError("OpenAI embeddings are disabled by configuration.")
        key = hashlib.sha256(OPENAI_EMBEDDING_MODEL.encode("utf-8")).hexdigest()[:12]
        self.index_path = EMBEDDING_CACHE_DIR / f"{key}.npz"
        self.metadata_path = EMBEDDING_CACHE_DIR / f"{key}.json"
        self.model_name = OPENAI_EMBEDDING_MODEL
        self._data = None

    def _client(self):
        return create_openai_client(timeout=OPENAI_EMBEDDING_TIMEOUT_SECONDS, max_retries=0)

    def _embed(self, texts: Sequence[str]) -> tuple[np.ndarray, int, int]:
        if not texts:
            return np.empty((0, 0), dtype=np.float32), 0, 0
        client = self._client()
        vectors = []
        calls = 0
        tokens = 0
        for offset in range(0, len(texts), OPENAI_EMBEDDING_BATCH_SIZE):
            batch = list(texts[offset:offset + OPENAI_EMBEDDING_BATCH_SIZE])
            response = client.embeddings.create(model=self.model_name, input=batch)
            calls += 1
            usage = getattr(response, "usage", None)
            tokens += int(getattr(usage, "total_tokens", 0) or 0)
            vectors.extend(item.embedding for item in response.data)
        return _normalize(np.asarray(vectors, dtype=np.float32)), calls, tokens

    def build(self, documents: Sequence[Dict[str, object]], source_hash: str) -> Dict[str, object]:
        started = time.perf_counter()
        documents = sorted(documents, key=lambda item: str(item["list_id"]))
        current_hashes = {
            str(item["list_id"]): str(item.get("document_hash") or hashlib.sha256(str(item["text"]).encode("utf-8")).hexdigest())
            for item in documents
        }
        old_hashes: Dict[str, str] = {}
        old_vectors: Dict[str, np.ndarray] = {}
        if self.metadata_path.exists() and self.index_path.exists():
            try:
                metadata = json.loads(self.metadata_path.read_text(encoding="utf-8"))
                if metadata.get("provider") == "openai_embeddings" and metadata.get("model") == self.model_name:
                    old_hashes = {str(key): str(value) for key, value in metadata.get("document_hashes", {}).items()}
                    if old_hashes == current_hashes:
                        return {
                            "provider": "openai_embeddings",
                            "model": self.model_name,
                            "source_hash": source_hash,
                            "documents": len(documents),
                            "dimensions": int(metadata.get("dimensions", 0)),
                            "cache_hits": len(documents),
                            "cache_misses": 0,
                            "embedding_calls": 0,
                            "embedding_tokens": 0,
                            "build_ms": int((time.perf_counter() - started) * 1000),
                            "index_bytes": self.index_path.stat().st_size,
                        }
                    loaded = np.load(self.index_path, allow_pickle=False)
                    loaded_ids = loaded["list_ids"]
                    loaded_vectors = loaded["document_vectors"]
                    old_vectors = {str(list_id): loaded_vectors[index] for index, list_id in enumerate(loaded_ids)}
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                old_hashes = {}
                old_vectors = {}

        reused: Dict[str, np.ndarray] = {}
        missing = []
        for document in documents:
            list_id = str(document["list_id"])
            if list_id in old_vectors and old_hashes.get(list_id) == current_hashes[list_id]:
                reused[list_id] = old_vectors[list_id]
            else:
                missing.append(document)

        new_matrix, calls, tokens = self._embed([str(item["text"]) for item in missing])
        generated = {str(item["list_id"]): new_matrix[index] for index, item in enumerate(missing)}
        vector_by_id = {**reused, **generated}
        list_ids = [str(item["list_id"]) for item in documents]
        if not list_ids:
            raise ValueError("No eligible retrieval documents were supplied.")
        matrix = _normalize(np.asarray([vector_by_id[list_id] for list_id in list_ids], dtype=np.float32))
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(self.index_path, document_vectors=matrix, list_ids=np.asarray(list_ids))
        metadata = {
            "provider": "openai_embeddings",
            "model": self.model_name,
            "source_hash": source_hash,
            "documents": len(documents),
            "dimensions": int(matrix.shape[1]),
            "document_hashes": current_hashes,
            "cache_hits": len(reused),
            "cache_misses": len(missing),
            "embedding_calls": calls,
            "embedding_tokens": tokens,
            "build_ms": int((time.perf_counter() - started) * 1000),
            "index_bytes": self.index_path.stat().st_size,
        }
        self.metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self._data = None
        return {key: value for key, value in metadata.items() if key != "document_hashes"}

    def encode_query(self, query: str) -> np.ndarray:
        matrix, _calls, _tokens = self._embed([query])
        return matrix[0]

    def score_multi(self, queries: Dict[str, str], allowed_ids: set[str]) -> Dict[str, object]:
        started = time.perf_counter()
        names = [name for name, value in queries.items() if value.strip()]
        query_vectors, calls, tokens = self._embed([queries[name] for name in names])
        data = self._load()
        document_vectors = data["document_vectors"]
        score_matrix = document_vectors @ query_vectors.T
        rows = []
        for index, raw_id in enumerate(data["list_ids"]):
            list_id = str(raw_id)
            if list_id not in allowed_ids:
                continue
            row: Dict[str, object] = {"list_id": list_id}
            for name in queries:
                row[f"{name}_similarity"] = 0.0
            for dimension, name in enumerate(names):
                row[f"{name}_similarity"] = float(score_matrix[index, dimension])
            positive = (
                0.30 * float(row.get("product_similarity", 0.0))
                + 0.28 * float(row.get("audience_similarity", 0.0))
                + 0.16 * float(row.get("use_case_similarity", 0.0))
                + 0.14 * float(row.get("industry_similarity", 0.0))
                + 0.12 * float(row.get("adjacent_similarity", 0.0))
            )
            negative = max(0.0, float(row.get("negative_similarity", 0.0)))
            row["semantic_score"] = positive - 0.24 * negative
            rows.append(row)
        rows.sort(key=lambda item: (-float(item["semantic_score"]), str(item["list_id"])))
        return {
            "rows": rows,
            "query_embedding_generated": True,
            "query_embedding_calls": calls,
            "query_embedding_tokens": tokens,
            "catalogue_embedding_cache_hit": self.index_path.exists(),
            "embedding_model": self.model_name,
            "embedding_ms": int((time.perf_counter() - started) * 1000),
        }
