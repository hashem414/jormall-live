from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, UnidentifiedImageError

from app.services.client_config_service import PROJECT_ROOT, client_scraped_dir


MIN_PRODUCT_IMAGE_SIDE = 120
MIN_PRODUCT_IMAGE_BYTES = 2_048
PLACEHOLDER_IMAGE_PATTERN = re.compile(
    r"(?:plp[-_]?loader|loader|loading|lazy[-_]?placeholder|placeholder|spinner|"
    r"preload|skeleton|blank(?:[-_.]|$)|transparent[-_]?pixel|tracking[-_]?pixel|"
    r"sprite|default[-_]?image|no[-_]?image|logo/stores|/flags/|flag-img|"
    r"visa|mastercard|payment|paypal|mada|applepay)",
    flags=re.IGNORECASE,
)
NON_PRODUCT_ROLE_PATTERN = re.compile(
    r"(?:hidden_asset|ui_asset|payment_icon|country_flag|social_icon|"
    r"placeholder_image|screenshot|loader|logo)",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ImageFileValidation:
    valid: bool
    reason: str
    width: int = 0
    height: int = 0
    sha256: str = ""
    format: str = ""


def local_static_path(url: object) -> Path | None:
    value = str(url or "").strip()
    if not value.startswith("/static/"):
        return None
    return PROJECT_ROOT / "app" / "static" / value.removeprefix("/static/")


def is_http_image_url(url: object) -> bool:
    value = str(url or "").strip()
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def is_placeholder_image_reference(*values: object) -> bool:
    return any(
        bool(PLACEHOLDER_IMAGE_PATTERN.search(str(value or "")))
        for value in values
        if str(value or "").strip()
    )


def has_non_product_media_role(item: dict) -> bool:
    role_text = " ".join(
        str(item.get(key) or "")
        for key in (
            "media_type",
            "image_role",
            "image_category",
            "category",
            "source_type",
            "dom_class",
        )
    )
    return bool(NON_PRODUCT_ROLE_PATTERN.search(role_text))


def validate_image_file(path: Path) -> ImageFileValidation:
    if not path.exists() or not path.is_file():
        return ImageFileValidation(False, "local file is missing")

    try:
        data = path.read_bytes()
    except OSError:
        return ImageFileValidation(False, "local file could not be read")

    digest = hashlib.sha256(data).hexdigest()
    if len(data) < MIN_PRODUCT_IMAGE_BYTES:
        return ImageFileValidation(False, "image file is too small", sha256=digest)

    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
            image_format = str(image.format or "")
    except (OSError, ValueError, UnidentifiedImageError):
        return ImageFileValidation(False, "image file is invalid or truncated", sha256=digest)

    if width < MIN_PRODUCT_IMAGE_SIDE or height < MIN_PRODUCT_IMAGE_SIDE:
        return ImageFileValidation(
            False,
            "image dimensions are too small for a product image",
            width,
            height,
            digest,
            image_format,
        )

    if max(width, height) / max(min(width, height), 1) > 8:
        return ImageFileValidation(
            False,
            "image aspect ratio indicates a banner or UI asset",
            width,
            height,
            digest,
            image_format,
        )

    return ImageFileValidation(True, "valid image file", width, height, digest, image_format)


def known_non_product_image_hashes(client_slug: str) -> set[str]:
    path = client_scraped_dir(client_slug) / "media_catalog.json"
    if not path.exists():
        return set()

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()

    media = payload.get("media") if isinstance(payload, dict) else payload
    if not isinstance(media, list):
        return set()

    hashes: set[str] = set()
    for item in media:
        if not isinstance(item, dict):
            continue
        placeholder_reference = is_placeholder_image_reference(
            item.get("original_image_url"),
            item.get("source_url"),
            item.get("entity_name"),
            item.get("filename"),
            item.get("dom_class"),
        )
        is_catalog_product_image = (
            "/media/catalog/product/"
            in str(item.get("original_image_url") or "").lower()
        )
        if is_catalog_product_image and not placeholder_reference:
            continue
        if not (
            placeholder_reference
            or has_non_product_media_role(item)
            or item.get("visible") is False
        ):
            continue
        local_path = local_static_path(item.get("local_static_url"))
        if local_path is None:
            continue
        validation = validate_image_file(local_path)
        if validation.sha256:
            hashes.add(validation.sha256)
    return hashes


def validate_product_image(
    *,
    client_slug: str,
    item: dict,
    known_invalid_hashes: set[str] | None = None,
) -> dict[str, object]:
    local_url = str(item.get("local_image_url") or "").strip()
    image_url = str(item.get("image_url") or "").strip()
    references = (
        image_url,
        local_url,
        item.get("image_alt"),
        item.get("image_source_field"),
        item.get("image_role"),
    )

    if has_non_product_media_role(item):
        return {
            "local_valid": False,
            "remote_valid": False,
            "reason": "media classification is not a product image",
            "placeholder": True,
        }

    placeholder = is_placeholder_image_reference(*references)
    remote_valid = bool(image_url and is_http_image_url(image_url) and not placeholder)
    local_validation = ImageFileValidation(False, "no local image")

    if local_url and not is_placeholder_image_reference(local_url):
        local_path = local_static_path(local_url)
        if local_path is not None:
            local_validation = validate_image_file(local_path)

    invalid_hashes = known_invalid_hashes
    if invalid_hashes is None:
        invalid_hashes = known_non_product_image_hashes(client_slug)

    local_valid = bool(
        local_validation.valid
        and local_validation.sha256 not in invalid_hashes
        and not placeholder
    )
    reason = local_validation.reason
    if local_validation.sha256 and local_validation.sha256 in invalid_hashes:
        reason = "image hash matches a known non-product asset"
        placeholder = True
    elif placeholder:
        reason = "image reference matches a loader, placeholder, or UI asset"
    elif not local_valid and remote_valid:
        reason = "local image is invalid; valid product image URL remains"

    return {
        "local_valid": local_valid,
        "remote_valid": remote_valid,
        "reason": reason,
        "placeholder": placeholder,
        "width": local_validation.width,
        "height": local_validation.height,
        "sha256": local_validation.sha256,
        "format": local_validation.format,
    }
