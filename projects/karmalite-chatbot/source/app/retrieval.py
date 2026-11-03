"""
الاسترجاع الهجين (Hybrid Retrieval).

ليش هجين مش دلالي بس؟
  • البحث الدلالي (cosine) ممتاز للمعنى: «بدي أشيل شعر رجلي» → ليزر إزالة الشعر
  • البحث بالكلمات المفتاحية ممتاز للأسماء الحرفية: «بروفايلو»، «Vivace»، «KarmaFemme»
    ولا الإمبيدنج ولا غيره بيضمن يجيبها بدقة.
الدمج بيتم بـ Reciprocal Rank Fusion (RRF) — ما بيحتاج معايرة درجات بين الطريقتين.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from .clients import get_openai
from .config import get_settings
from .db import get_conn, to_pgvector
from .embeddings import embed_query
from .text_utils import build_search_text

logger = logging.getLogger(__name__)

_RRF_K = 60  # ثابت التخميد القياسي بـ RRF


@dataclass
class RetrievedChunk:
    id: int
    content: str
    breadcrumb: str
    chunk_type: str
    source: str
    vector_score: float   # تشابه cosine (0..1)
    rrf_score: float
    metadata: dict

    def as_context(self, index: int) -> str:
        return f"[{index}] ({self.breadcrumb})\n{self.content}"


_HYBRID_SQL = """
WITH vector_hits AS (
    SELECT id,
           1 - (embedding <=> %(qvec)s::vector)                        AS vscore,
           ROW_NUMBER() OVER (ORDER BY embedding <=> %(qvec)s::vector) AS vrank
    FROM chunks
    WHERE embedding IS NOT NULL
    ORDER BY embedding <=> %(qvec)s::vector
    LIMIT %(candidates)s
),
lexical_hits AS (
    SELECT id,
           ts_rank_cd(to_tsvector('simple', search_text), q)                        AS lscore,
           ROW_NUMBER() OVER (ORDER BY ts_rank_cd(to_tsvector('simple', search_text), q) DESC) AS lrank
    FROM chunks, websearch_to_tsquery('simple', %(qtext)s) AS q
    WHERE to_tsvector('simple', search_text) @@ q
    ORDER BY lscore DESC
    LIMIT %(candidates)s
)
SELECT c.id,
       c.content,
       c.breadcrumb,
       c.chunk_type,
       c.metadata,
       d.source,
       COALESCE(v.vscore, 0)                                AS vector_score,
       COALESCE(1.0 / (%(rrf_k)s + v.vrank), 0)
     + COALESCE(1.0 / (%(rrf_k)s + l.lrank), 0)             AS rrf_score
FROM chunks c
JOIN documents d       ON d.id = c.document_id
LEFT JOIN vector_hits v  ON v.id = c.id
LEFT JOIN lexical_hits l ON l.id = c.id
WHERE v.id IS NOT NULL OR l.id IS NOT NULL
ORDER BY rrf_score DESC, vector_score DESC
LIMIT %(top_k)s
"""


def hybrid_search(
    query: str,
    *,
    top_k: int | None = None,
    candidates: int | None = None,
) -> list[RetrievedChunk]:
    settings = get_settings()
    top_k = top_k or settings.retrieve_top_k
    candidates = candidates or settings.retrieve_candidates

    query_vector = embed_query(query)
    query_text = build_search_text(query)

    # ef_search بينضبط مرة وحدة لكل اتصال بـ db._configure — مش هون —
    # عشان ما ندفع BEGIN/COMMIT زيادة مع كل بحث على قاعدة بعيدة.
    with get_conn() as conn:
        rows = conn.execute(
            _HYBRID_SQL,
            {
                "qvec": to_pgvector(query_vector),
                "qtext": query_text,
                "candidates": candidates,
                "top_k": top_k,
                "rrf_k": _RRF_K,
            },
        ).fetchall()

    results = [
        RetrievedChunk(
            id=r["id"],
            content=r["content"],
            breadcrumb=r["breadcrumb"] or "",
            chunk_type=r["chunk_type"],
            source=r["source"],
            vector_score=float(r["vector_score"]),
            rrf_score=float(r["rrf_score"]),
            metadata=r["metadata"] if isinstance(r["metadata"], dict) else json.loads(r["metadata"] or "{}"),
        )
        for r in rows
    ]
    logger.debug("hybrid_search('%s') → %d نتيجة", query[:60], len(results))
    return results


_RERANK_PROMPT = """أنت مُقيّم استرجاع. قيّم كل مقطع من 0 إلى 10 حسب مدى فائدته للإجابة على سؤال العميل.
10 = يحتوي الإجابة مباشرة، 0 = لا علاقة له.
أعد JSON فقط بالشكل: {"scores": [{"id": <رقم المقطع>, "score": <0-10>}]}

سؤال العميل: {query}

المقاطع:
{passages}"""


def rerank(query: str, chunks: list[RetrievedChunk], keep: int) -> list[RetrievedChunk]:
    """إعادة ترتيب اختيارية بموديل خفيف — بتزيد الدقة وبتكلّف استدعاء إضافي."""
    if len(chunks) <= 1:
        return chunks

    settings = get_settings()
    passages = "\n\n".join(
        f"[{c.id}] {c.content[:600]}" for c in chunks
    )
    try:
        response = get_openai().chat.completions.create(
            model=settings.utility_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "user",
                    "content": _RERANK_PROMPT.replace("{query}", query).replace(
                        "{passages}", passages
                    ),
                }
            ],
        )
        scores = {
            int(item["id"]): float(item["score"])
            for item in json.loads(response.choices[0].message.content or "{}").get("scores", [])
        }
    except Exception as exc:  # الترتيب تحسين اختياري — ما بنكسر الطلب لو فشل
        logger.warning("rerank فشل، بنكمل بترتيب RRF: %s", exc)
        return chunks[:keep]

    ranked = sorted(chunks, key=lambda c: scores.get(c.id, 0.0), reverse=True)
    return [c for c in ranked if scores.get(c.id, 0.0) >= 3][:keep] or ranked[:keep]


def retrieve(query: str) -> list[RetrievedChunk]:
    """نقطة الدخول: بحث هجين → (اختياري) إعادة ترتيب → فلترة العتبة."""
    settings = get_settings()
    hits = hybrid_search(
        query,
        top_k=settings.retrieve_top_k * 2 if settings.rerank_enabled else settings.retrieve_top_k,
    )
    if not hits:
        return []

    if settings.rerank_enabled:
        hits = rerank(query, hits, keep=settings.retrieve_top_k)

    # لو أفضل نتيجة ضعيفة جداً دلالياً، غالباً السؤال خارج نطاق قاعدة المعرفة
    best = max(h.vector_score for h in hits)
    if best < settings.min_relevance_score:
        logger.info("أعلى تشابه %.3f < العتبة — سؤال خارج النطاق", best)
        return []

    return hits


def build_context(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return "لا توجد معلومات مطابقة في قاعدة المعرفة."
    return "\n\n---\n\n".join(c.as_context(i + 1) for i, c in enumerate(chunks))
