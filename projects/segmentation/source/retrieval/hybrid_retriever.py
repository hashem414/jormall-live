from __future__ import annotations

import time
from typing import Dict

from ai.query_builder import SemanticQueryBundle
from .lexical_index import LexicalIndex
from .provider_factory import create_semantic_provider


class HybridRetriever:
    def __init__(self) -> None:
        self.lexical = LexicalIndex()
        self.semantic = create_semantic_provider()

    def retrieve(self, query: SemanticQueryBundle | str, allowed_ids: set[str] | None = None, exhaustive: bool = False) -> Dict[str, object]:
        allowed = allowed_ids or set()
        if isinstance(query, str):
            query = SemanticQueryBundle(dimensions={"product": query, "audience": query, "use_case": query, "industry": query, "adjacent": query, "negative": ""}, lexical_query=query)

        lexical_started = time.perf_counter()
        lexical = self.lexical.search_exhaustive(query.lexical_query, allowed)
        lexical_by_id = {str(row["list_id"]): float(row["score"]) for row in lexical}
        lexical_ms = int((time.perf_counter() - lexical_started) * 1000)

        semantic_started = time.perf_counter()
        semantic = self.semantic.score_multi(query.dimensions, allowed)
        semantic_ms = int((time.perf_counter() - semantic_started) * 1000)

        candidates = []
        for row in semantic["rows"]:
            list_id = str(row["list_id"])
            lexical_score = lexical_by_id.get(list_id, 0.0)
            semantic_score = float(row.get("semantic_score", 0.0))
            candidates.append({
                **row,
                "lexical_score": lexical_score,
                "fused_score": semantic_score + min(0.10, lexical_score * 0.10),
            })
        candidates.sort(key=lambda item: (-float(item["fused_score"]), str(item["list_id"])))
        return {
            "candidates": candidates,
            "timings": {
                "lexical_retrieval_ms": lexical_ms,
                "semantic_retrieval_ms": semantic_ms,
                "fusion_ms": 0,
            },
            "counts": {"lexical": len(lexical), "semantic": len(candidates), "fused": len(candidates)},
            "mode": "exhaustive" if exhaustive else "all_allowed_vectorized",
            "profiles_scored": len(candidates),
            "profiles_vector_scored": len(candidates),
            "profiles_lexically_scored": len(allowed),
            "semantic_error": None,
            "query_embedding_generated": bool(semantic.get("query_embedding_generated")),
            "query_embedding_calls": int(semantic.get("query_embedding_calls", 0)),
            "query_embedding_tokens": int(semantic.get("query_embedding_tokens", 0)),
            "catalogue_embedding_cache_hit": bool(semantic.get("catalogue_embedding_cache_hit")),
            "embedding_model": str(semantic.get("embedding_model", "")),
        }
