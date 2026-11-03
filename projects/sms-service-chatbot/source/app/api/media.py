from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.document import MediaCollection, MediaImage
from app.services.client_config_service import client_data_dir, load_client_config, slugify_company_name


router = APIRouter(tags=["Campaign Media"])


def validate_client_slug(client_slug: str) -> str:
    cleaned = (client_slug or "").strip()
    if not cleaned or cleaned != slugify_company_name(cleaned):
        raise HTTPException(status_code=404, detail="Client not found.")
    try:
        load_client_config(cleaned)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="Client not found.") from error
    return cleaned


@router.get(
    "/api/media/{client_slug}/{collection_id}/{image_id}/{variant}",
    summary="Serve an approved public campaign image safely",
)
def serve_public_media_image(
    client_slug: str,
    collection_id: UUID,
    image_id: UUID,
    variant: str,
    db: Session = Depends(get_db),
):
    slug = validate_client_slug(client_slug)
    if variant not in {"approved", "thumbnail"}:
        raise HTTPException(status_code=404, detail="Image not found.")
    image = db.scalar(
        select(MediaImage)
        .join(MediaCollection, MediaCollection.id == MediaImage.collection_id)
        .where(
            MediaImage.client_slug == slug,
            MediaImage.collection_id == collection_id,
            MediaImage.id == image_id,
            MediaImage.is_approved.is_(True),
            MediaImage.is_active.is_(True),
            MediaImage.is_duplicate.is_(False),
            MediaCollection.client_slug == slug,
            MediaCollection.is_enabled.is_(True),
            MediaCollection.is_approved.is_(True),
        )
    )
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found.")
    relative_path = image.thumbnail_path if variant == "thumbnail" else image.public_storage_path
    root = client_data_dir(slug).resolve()
    path = (root / relative_path).resolve()
    try:
        if not path.is_file() or not path.is_relative_to(root):
            raise HTTPException(status_code=404, detail="Image not found.")
    except OSError as error:
        raise HTTPException(status_code=404, detail="Image not found.") from error
    media_type = "image/jpeg" if variant == "thumbnail" else image.mime_type
    return FileResponse(
        path,
        media_type=media_type,
        headers={"Cache-Control": f"public, max-age={settings.media_public_cache_seconds}"},
    )
