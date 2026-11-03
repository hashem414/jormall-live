from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select, text

from app.core.database import SessionLocal, engine
from app.models.document import Document, DocumentChunk, MediaCollection, MediaImage
from app.services.client_config_service import DATA_DIR


SEED_PATH = DATA_DIR / "runtime" / "db_seed.json"


def parse_datetime(value: str | None):
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def parse_date(value: str | None):
    if not value:
        return None
    return date.fromisoformat(str(value))


def ensure_vector_extension() -> None:
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


def seed_standalone_database() -> dict[str, int | str]:
    if not SEED_PATH.exists():
        return {
            "status": "missing",
            "documents": 0,
            "chunks": 0,
            "embeddings": 0,
        }

    payload = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    client_slug = str(payload["client_slug"])
    documents = payload.get("documents") or []
    chunks = payload.get("chunks") or []
    media_collections = payload.get("media_collections") or []
    media_images = payload.get("media_images") or []

    with SessionLocal() as db:
        existing_chunks = int(
            db.scalar(
                select(func.count())
                .select_from(DocumentChunk)
                .where(DocumentChunk.client_slug == client_slug)
            )
            or 0
        )
        if existing_chunks > 0:
            existing_documents = int(
                db.scalar(
                    select(func.count())
                    .select_from(Document)
                    .where(Document.client_slug == client_slug)
                )
                or 0
            )
            existing_embeddings = int(
                db.scalar(
                    select(func.count(DocumentChunk.embedding))
                    .select_from(DocumentChunk)
                    .where(DocumentChunk.client_slug == client_slug)
                )
                or 0
            )
            return {
                "status": "already_seeded",
                "client_slug": client_slug,
                "documents": existing_documents,
                "chunks": existing_chunks,
                "media_collections": int(
                    db.execute(
                        select(text("count(*)"))
                        .select_from(MediaCollection)
                        .where(MediaCollection.client_slug == client_slug)
                    ).scalar_one()
                    or 0
                ),
                "media_images": int(
                    db.execute(
                        select(text("count(*)"))
                        .select_from(MediaImage)
                        .where(MediaImage.client_slug == client_slug)
                    ).scalar_one()
                    or 0
                ),
                "embeddings": existing_embeddings,
            }

        for item in documents:
            db.add(
                Document(
                    id=UUID(item["id"]),
                    title=item["title"],
                    client_slug=item["client_slug"],
                    original_filename=item["original_filename"],
                    source_path=item["source_path"],
                    language=item.get("language") or "en",
                    document_type=item.get("document_type") or "general",
                    status=item.get("status") or "active",
                    visibility=item.get("visibility") or "client",
                    issued_date=parse_date(item.get("issued_date")),
                    content_hash=item["content_hash"],
                    raw_text=item.get("raw_text"),
                    created_at=parse_datetime(item.get("created_at")),
                    updated_at=parse_datetime(item.get("updated_at")),
                )
            )
        db.flush()

        for item in chunks:
            db.add(
                DocumentChunk(
                    id=UUID(item["id"]),
                    document_id=UUID(item["document_id"]),
                    chunk_index=int(item["chunk_index"]),
                    content=item["content"],
                    section_title=item.get("section_title"),
                    source_reference=item.get("source_reference"),
                    token_count=item.get("token_count"),
                    chunk_metadata=item.get("chunk_metadata") or {},
                    embedding_model=item.get("embedding_model"),
                    embedding=item.get("embedding"),
                    created_at=parse_datetime(item.get("created_at")),
                    client_slug=item.get("client_slug") or client_slug,
                )
            )
        for item in media_collections:
            db.add(
                # Legacy shared_* values are still accepted from older packages,
                # but new packages use title + general description only.
                MediaCollection(
                    id=UUID(item["id"]),
                    client_slug=item["client_slug"],
                    title=item["title"],
                    general_description_original=item.get("general_description") or "Exported approved media collection",
                    general_description_language=item.get("general_description_language") or "en",
                    shared_brand=item.get("shared_brand") or "",
                    shared_product_family=item.get("shared_product_family") or "",
                    shared_campaign_name=item.get("shared_campaign_name") or "",
                    shared_model=item.get("shared_model") or "",
                    shared_model_year=item.get("shared_model_year") or "",
                    shared_cta_url=item.get("shared_cta_url") or "",
                    is_enabled=bool(item.get("is_enabled")),
                    is_approved=bool(item.get("is_approved")),
                    analysis_status="approved",
                )
            )
        db.flush()
        for item in media_images:
            db.add(
                MediaImage(
                    id=UUID(item["id"]),
                    collection_id=UUID(item["collection_id"]),
                    client_slug=item["client_slug"],
                    original_filename="approved_campaign_media",
                    safe_filename=Path(item.get("public_storage_path") or "").name,
                    original_storage_path="",
                    public_storage_path=item.get("public_storage_path") or "",
                    thumbnail_path=item.get("thumbnail_path") or "",
                    mime_type=item.get("mime_type") or "image/jpeg",
                    file_size=0,
                    width=int(item.get("width") or 0),
                    height=int(item.get("height") or 0),
                    sha256=str(item["id"]).replace("-", "")[:64],
                    ai_title_en=item.get("ai_title_en") or "",
                    ai_title_ar=item.get("ai_title_ar") or "",
                    visual_description_en=item.get("visual_description_en") or "",
                    visual_description_ar=item.get("visual_description_ar") or "",
                    alt_text_en=item.get("alt_text_en") or "",
                    alt_text_ar=item.get("alt_text_ar") or "",
                    detected_category=item.get("detected_category") or "",
                    detected_product_type=item.get("detected_product_type") or "",
                    detected_colour=item.get("detected_colour") or "",
                    detected_view=item.get("detected_view") or "",
                    detected_image_type=item.get("detected_image_type") or "",
                    suggested_group=item.get("suggested_group") or "",
                    keywords_en=item.get("keywords_en") or [],
                    keywords_ar=item.get("keywords_ar") or [],
                    searchable_text_en=item.get("searchable_text_en") or "",
                    searchable_text_ar=item.get("searchable_text_ar") or "",
                    embedding_model=item.get("embedding_model"),
                    embedding=item.get("embedding"),
                    is_approved=True,
                    is_active=True,
                    needs_review=False,
                    analysis_status="approved",
                    display_order=int(item.get("display_order") or 0),
                )
            )
        db.commit()

    return {
        "status": "seeded",
        "client_slug": client_slug,
        "documents": len(documents),
        "chunks": len(chunks),
        "media_collections": len(media_collections),
        "media_images": len(media_images),
        "embeddings": sum(1 for item in chunks if item.get("embedding") is not None),
    }
