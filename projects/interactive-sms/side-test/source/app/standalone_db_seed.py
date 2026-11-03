from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, engine
from app.models.document import Document, DocumentChunk, KnowledgeSeedState
from app.services.embedding_service import create_embeddings
from app.services.client_config_service import DATA_DIR
from app.source_seed_builder import apply_authoritative_sources


SEED_PATH = DATA_DIR / "runtime" / "db_seed.json"


def parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")) if value else None


def parse_date(value: str | None) -> date | None:
    return date.fromisoformat(str(value)) if value else None


def seed_payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def ensure_vector_extension() -> None:
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


def _tracked_rows_are_complete(db: Session, state: KnowledgeSeedState) -> bool:
    document_ids = [UUID(value) for value in state.document_ids]
    chunk_ids = [UUID(value) for value in state.chunk_ids]
    documents_found = (
        db.scalar(
            select(func.count()).select_from(Document).where(
                Document.client_slug == state.client_slug,
                Document.id.in_(document_ids),
            )
        )
        if document_ids
        else 0
    )
    chunks_found = (
        db.scalar(
            select(func.count()).select_from(DocumentChunk).where(
                DocumentChunk.client_slug == state.client_slug,
                DocumentChunk.id.in_(chunk_ids),
            )
        )
        if chunk_ids
        else 0
    )
    embeddings_found = (
        db.scalar(
            select(func.count()).select_from(DocumentChunk).where(
                DocumentChunk.client_slug == state.client_slug,
                DocumentChunk.id.in_(chunk_ids),
                DocumentChunk.embedding.is_not(None),
            )
        )
        if chunk_ids
        else 0
    )
    return int(documents_found or 0) == len(document_ids) and int(
        chunks_found or 0
    ) == len(chunk_ids) and int(embeddings_found or 0) == state.embedding_count


def _apply_document(document: Document, item: dict[str, Any], client_slug: str) -> None:
    document.title = str(item["title"])
    document.client_slug = client_slug
    document.original_filename = str(item["original_filename"])
    document.source_path = str(item["source_path"])
    document.language = str(item.get("language") or "en")
    document.document_type = str(item.get("document_type") or "general")
    document.status = str(item.get("status") or "active")
    document.visibility = str(item.get("visibility") or "client")
    document.issued_date = parse_date(item.get("issued_date"))
    document.content_hash = str(item["content_hash"])
    document.raw_text = item.get("raw_text")
    if created_at := parse_datetime(item.get("created_at")):
        document.created_at = created_at
    if updated_at := parse_datetime(item.get("updated_at")):
        document.updated_at = updated_at


def _apply_chunk(
    chunk: DocumentChunk,
    item: dict[str, Any],
    client_slug: str,
    document_id: UUID,
) -> None:
    chunk.document_id = document_id
    chunk.chunk_index = int(item["chunk_index"])
    chunk.content = str(item["content"])
    chunk.section_title = item.get("section_title")
    chunk.source_reference = item.get("source_reference")
    chunk.token_count = item.get("token_count")
    chunk.chunk_metadata = item.get("chunk_metadata") or {}
    chunk.embedding_model = item.get("embedding_model")
    chunk.embedding = item.get("embedding")
    chunk.client_slug = client_slug
    if created_at := parse_datetime(item.get("created_at")):
        chunk.created_at = created_at


def sync_seed_payload(
    payload: dict[str, Any],
    db: Session,
    *,
    seed_hash: str | None = None,
) -> dict[str, int | str]:
    """Upsert packaged knowledge and remove only stale rows tracked by its prior seed."""

    client_slug = str(payload.get("client_slug") or "").strip()
    if not client_slug:
        raise ValueError("Seed client_slug cannot be empty.")
    documents = list(payload.get("documents") or [])
    chunks = list(payload.get("chunks") or [])
    effective_hash = seed_hash or seed_payload_hash(payload)
    version = str(
        payload.get("source_version") or payload.get("generated_at") or effective_hash[:16]
    )
    state = db.get(KnowledgeSeedState, client_slug)

    if state and state.seed_hash == effective_hash and _tracked_rows_are_complete(db, state):
        return {
            "status": "unchanged",
            "client_slug": client_slug,
            "seed_version": state.seed_version,
            "seed_hash": state.seed_hash,
            "documents": state.document_count,
            "chunks": state.chunk_count,
            "embeddings": state.embedding_count,
        }

    missing_embeddings = [item for item in chunks if item.get("embedding") is None]
    if missing_embeddings:
        embedding_result = create_embeddings(
            [str(item["content"]) for item in missing_embeddings]
        )
        for item, embedding in zip(missing_embeddings, embedding_result.embeddings, strict=True):
            item["embedding"] = embedding
            item["embedding_model"] = embedding_result.model

    previous_document_ids = {UUID(value) for value in (state.document_ids if state else [])}
    previous_chunk_ids = {UUID(value) for value in (state.chunk_ids if state else [])}
    existing_documents = db.scalars(
        select(Document).where(Document.client_slug == client_slug)
    ).all()
    by_document_id = {item.id: item for item in existing_documents}
    by_content_hash = {item.content_hash: item for item in existing_documents}
    document_id_map: dict[UUID, UUID] = {}
    managed_document_ids: set[UUID] = set()

    for item in documents:
        payload_id = UUID(str(item["id"]))
        content_hash = str(item["content_hash"])
        document = by_document_id.get(payload_id) or by_content_hash.get(content_hash)
        if document is None:
            document = Document(id=payload_id)
            db.add(document)
        _apply_document(document, item, client_slug)
        db.flush()
        document_id_map[payload_id] = document.id
        managed_document_ids.add(document.id)
        by_document_id[document.id] = document
        by_content_hash[content_hash] = document

    existing_chunks = db.scalars(
        select(DocumentChunk).where(DocumentChunk.client_slug == client_slug)
    ).all()
    by_chunk_id = {item.id: item for item in existing_chunks}
    by_position = {(item.document_id, item.chunk_index): item for item in existing_chunks}
    managed_chunk_ids: set[UUID] = set()

    for item in chunks:
        payload_id = UUID(str(item["id"]))
        payload_document_id = UUID(str(item["document_id"]))
        document_id = document_id_map.get(payload_document_id)
        if document_id is None:
            raise ValueError(f"Chunk {payload_id} references an unknown seed document.")
        position = (document_id, int(item["chunk_index"]))
        chunk = by_chunk_id.get(payload_id) or by_position.get(position)
        if chunk is None:
            chunk = DocumentChunk(id=payload_id)
            db.add(chunk)
        _apply_chunk(chunk, item, client_slug, document_id)
        db.flush()
        managed_chunk_ids.add(chunk.id)
        by_chunk_id[chunk.id] = chunk
        by_position[position] = chunk

    stale_chunk_ids = previous_chunk_ids - managed_chunk_ids
    if stale_chunk_ids:
        db.execute(
            delete(DocumentChunk).where(
                DocumentChunk.client_slug == client_slug,
                DocumentChunk.id.in_(stale_chunk_ids),
            )
        )
    stale_document_ids = previous_document_ids - managed_document_ids
    if stale_document_ids:
        db.execute(
            delete(Document).where(
                Document.client_slug == client_slug,
                Document.id.in_(stale_document_ids),
            )
        )

    embedding_count = sum(item.get("embedding") is not None for item in chunks)
    if state is None:
        state = KnowledgeSeedState(
            client_slug=client_slug,
            seed_hash=effective_hash,
            seed_version=version,
        )
        db.add(state)
    state.seed_hash = effective_hash
    state.seed_version = version
    state.document_ids = sorted(map(str, managed_document_ids))
    state.chunk_ids = sorted(map(str, managed_chunk_ids))
    state.document_count = len(documents)
    state.chunk_count = len(chunks)
    state.embedding_count = int(embedding_count)
    state.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "status": "upserted",
        "client_slug": client_slug,
        "seed_version": version,
        "seed_hash": effective_hash,
        "documents": len(documents),
        "chunks": len(chunks),
        "embeddings": int(embedding_count),
        "stale_documents_removed": len(stale_document_ids),
        "stale_chunks_removed": len(stale_chunk_ids),
    }


def seed_standalone_database() -> dict[str, int | str]:
    if not SEED_PATH.exists():
        return {"status": "missing", "documents": 0, "chunks": 0, "embeddings": 0}
    payload = apply_authoritative_sources(
        json.loads(SEED_PATH.read_text(encoding="utf-8"))
    )
    with SessionLocal() as db:
        return sync_seed_payload(payload, db, seed_hash=seed_payload_hash(payload))
