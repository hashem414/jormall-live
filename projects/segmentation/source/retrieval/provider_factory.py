from __future__ import annotations

from config import SEMANTIC_PROVIDER
from .semantic_provider import SemanticProvider


def create_semantic_provider() -> SemanticProvider:
    if SEMANTIC_PROVIDER == "lsa_local":
        from .local_lsa_provider import LocalLSAProvider
        return LocalLSAProvider()
    if SEMANTIC_PROVIDER == "sentence_transformer_local":
        from .sentence_transformer_provider import SentenceTransformerLocalProvider
        return SentenceTransformerLocalProvider()
    if SEMANTIC_PROVIDER == "openai_embeddings":
        from .openai_embedding_provider import OpenAIEmbeddingProvider
        return OpenAIEmbeddingProvider()
    raise ValueError(f"Unsupported SEMANTIC_PROVIDER: {SEMANTIC_PROVIDER}")
