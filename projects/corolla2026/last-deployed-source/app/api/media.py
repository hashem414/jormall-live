from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.document import MediaCollection, MediaImage
from app.services.client_config_service import client_data_dir


router = APIRouter(tags=["Campaign Media"])
CLIENT_SLUG = os.getenv("CLIENT_SLUG", os.getenv("STANDALONE_CLIENT_SLUG", "central-trade-auto-co-markazia-toyota-jordan")).strip() or "central-trade-auto-co-markazia-toyota-jordan"


if CLIENT_SLUG != "central-trade-auto-co-markazia-toyota-jordan":
    raise RuntimeError("CLIENT_SLUG/STANDALONE_CLIENT_SLUG does not match this exported chatbot package.")


@router.get(
    "/api/media/{image_id}/{variant}",
    summary="Serve an approved public campaign image safely",
)
def serve_public_media_image(
    image_id: UUID,
    variant: str,
    db: Session = Depends(get_db),
):
    if variant not in {"approved", "thumbnail"}:
        raise HTTPException(status_code=404, detail="Image not found.")
    image = db.scalar(
        select(MediaImage)
        .join(MediaCollection, MediaCollection.id == MediaImage.collection_id)
        .where(
            MediaImage.client_slug == CLIENT_SLUG,
            MediaImage.id == image_id,
            MediaImage.is_approved.is_(True),
            MediaImage.is_active.is_(True),
            MediaImage.is_duplicate.is_(False),
            MediaCollection.client_slug == CLIENT_SLUG,
            MediaCollection.is_enabled.is_(True),
            MediaCollection.is_approved.is_(True),
        )
    )
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found.")
    relative_path = image.thumbnail_path if variant == "thumbnail" else image.public_storage_path
    root = client_data_dir(CLIENT_SLUG).resolve()
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
