from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, Sequence

import numpy as np

from config import DATA_DIR, SENTENCE_TRANSFORMER_MODEL
from .dense_provider_base import DenseProviderBase


class SentenceTransformerLocalProvider(DenseProviderBase):
    def __init__(self) -> None:
        model_path = Path(SENTENCE_TRANSFORMER_MODEL)
        if not SENTENCE_TRANSFORMER_MODEL or not model_path.exists():
            raise RuntimeError("SENTENCE_TRANSFORMER_MODEL must point to an existing local model; automatic downloads are disabled.")
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError("sentence-transformers is not installed locally.") from exc
        self.model_name = str(model_path.resolve())
        self.model = SentenceTransformer(self.model_name, local_files_only=True)
        key = hashlib.sha256(self.model_name.encode()).hexdigest()[:12]
        self.index_path = DATA_DIR / "indexes" / f"sentence_transformer_{key}.npz"
        self.metadata_path = DATA_DIR / "indexes" / f"sentence_transformer_{key}.json"
        self._data = None

    def build(self, documents: Sequence[Dict[str, object]], source_hash: str) -> Dict[str, object]:
        vectors = self.model.encode([str(row["text"]) for row in documents], normalize_embeddings=True, show_progress_bar=False)
        np.savez_compressed(self.index_path, document_vectors=np.asarray(vectors, dtype=np.float32), list_ids=np.asarray([str(row["list_id"]) for row in documents]))
        metadata = {"provider":"sentence_transformer_local","model":self.model_name,"source_hash":source_hash,"documents":len(documents)}
        self.metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        return metadata

    def encode_query(self, query: str) -> np.ndarray:
        return np.asarray(self.model.encode([query], normalize_embeddings=True, show_progress_bar=False)[0], dtype=np.float32)
