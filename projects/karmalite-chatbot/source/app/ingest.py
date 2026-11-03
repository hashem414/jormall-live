"""
خط أنابيب الفهرسة: ملف → شانكس → إمبيدنج → PostgreSQL.

مميزات:
  • idempotent: لو محتوى الملف ما تغيّر (نفس sha256) بيتخطّاه
  • إعادة الفهرسة بتمسح شانكس الملف القديمة وتكتب الجديدة داخل ترانزاكشن وحدة
  • بيدعم مجلد كامل: data/*.md
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from psycopg.types.json import Jsonb

from .chunking import Chunk, chunk_markdown
from .config import get_settings
from .db import get_conn, to_pgvector
from .embeddings import embed_texts

logger = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt"}


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ingest_file(path: str | Path, *, force: bool = False) -> dict:
    settings = get_settings()
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    source = path.as_posix()
    content_hash = _hash(text)

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id, content_hash FROM documents WHERE source = %s", (source,)
        ).fetchone()

        if existing and existing["content_hash"] == content_hash and not force:
            logger.info("skip %s (بدون تغيير)", source)
            return {"source": source, "status": "unchanged", "chunks": 0}

    chunks: list[Chunk] = chunk_markdown(
        text,
        source=source,
        max_chars=settings.chunk_max_chars,
        min_chars=settings.chunk_min_chars,
        overlap=settings.chunk_overlap_chars,
    )
    if not chunks:
        return {"source": source, "status": "empty", "chunks": 0}

    logger.info("embedding %d chunks من %s ...", len(chunks), source)
    vectors = embed_texts([c.content for c in chunks])

    title = next(
        (ln.lstrip("# ").strip() for ln in text.splitlines() if ln.startswith("# ")),
        path.stem,
    )

    with get_conn() as conn, conn.transaction():
        row = conn.execute(
            """
            INSERT INTO documents (source, title, content_hash, updated_at)
            VALUES (%s, %s, %s, now())
            ON CONFLICT (source) DO UPDATE
                SET content_hash = EXCLUDED.content_hash,
                    title        = EXCLUDED.title,
                    updated_at   = now()
            RETURNING id
            """,
            (source, title, content_hash),
        ).fetchone()
        document_id = row["id"]

        conn.execute("DELETE FROM chunks WHERE document_id = %s", (document_id,))

        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO chunks (document_id, chunk_index, breadcrumb, content,
                                    search_text, chunk_type, metadata, token_count, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
                """,
                [
                    (
                        document_id,
                        index,
                        chunk.breadcrumb,
                        chunk.content,
                        chunk.search_text,
                        chunk.chunk_type,
                        Jsonb(chunk.metadata),
                        chunk.token_count,
                        to_pgvector(vector),
                    )
                    for index, (chunk, vector) in enumerate(zip(chunks, vectors))
                ],
            )

    by_type: dict[str, int] = {}
    for chunk in chunks:
        by_type[chunk.chunk_type] = by_type.get(chunk.chunk_type, 0) + 1

    logger.info("✔ %s → %d chunks %s", source, len(chunks), by_type)
    return {
        "source": source,
        "status": "indexed",
        "chunks": len(chunks),
        "by_type": by_type,
        "avg_tokens": round(sum(c.token_count for c in chunks) / len(chunks), 1),
    }


def ingest_path(path: str | Path = "data", *, force: bool = False) -> list[dict]:
    """يفهرس ملف واحد أو كل الملفات المدعومة داخل مجلد."""
    path = Path(path)
    if path.is_file():
        return [ingest_file(path, force=force)]

    files = sorted(p for p in path.rglob("*") if p.suffix.lower() in SUPPORTED_SUFFIXES)
    if not files:
        raise FileNotFoundError(f"ما في ملفات مدعومة داخل {path}")
    return [ingest_file(f, force=force) for f in files]
