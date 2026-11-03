"""
طبقة الإمبيدنج — text-embedding-3-small.

ليش هذا الموديل: 1536 بُعد، رخيص جداً (~0.02$ لكل مليون توكن)، وأداؤه ممتاز
بالعربي والإنجليزي معاً — وهاد مهم لأن قاعدة المعرفة ثنائية اللغة.
لو احتجت دقة أعلى لاحقاً: text-embedding-3-large (3072 بُعد) — بس لازم
تعدّل VECTOR(1536) بالسكيما وتعيد بناء الإمبيدنجز.
"""

from __future__ import annotations

import logging

from tenacity import retry, stop_after_attempt, wait_exponential

from .clients import get_openai
from .config import get_settings

logger = logging.getLogger(__name__)

_BATCH_SIZE = 96          # حد آمن لكل طلب
_MAX_INPUT_CHARS = 8000   # حماية من تجاوز حد التوكنز للشانك الواحد


@retry(stop=stop_after_attempt(4), wait=wait_exponential(min=1, max=20))
def _embed_batch(texts: list[str], model: str) -> list[list[float]]:
    response = get_openai().embeddings.create(model=model, input=texts)
    return [item.embedding for item in response.data]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """إمبيدنج لقائمة نصوص، على دفعات، مع الحفاظ على الترتيب."""
    if not texts:
        return []

    settings = get_settings()
    cleaned = [(t or " ").strip()[:_MAX_INPUT_CHARS] or " " for t in texts]
    vectors: list[list[float]] = []

    for start in range(0, len(cleaned), _BATCH_SIZE):
        batch = cleaned[start : start + _BATCH_SIZE]
        vectors.extend(_embed_batch(batch, settings.embedding_model))
        logger.debug("embedded %d/%d", min(start + _BATCH_SIZE, len(cleaned)), len(cleaned))

    if vectors and len(vectors[0]) != settings.embedding_dim:
        raise ValueError(
            f"أبعاد الإمبيدنج ({len(vectors[0])}) ما بتطابق EMBEDDING_DIM "
            f"({settings.embedding_dim}) ولا عمود VECTOR بالسكيما."
        )
    return vectors


def embed_query(text: str) -> list[float]:
    """إمبيدنج لسؤال المستخدم. نفس الموديل المستخدم بالفهرسة — إلزامي."""
    return embed_texts([text])[0]
