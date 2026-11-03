from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from hashlib import sha1
from pathlib import Path
from typing import Any

from app.services.client_config_service import client_scraped_dir, load_client_config


MEDIA_CATALOG_FILENAME = "media_catalog.json"
IMAGE_MEDIA_TYPES = {"website_image", "website_screenshot", "document_image", "image", "screenshot"}
LOGO_CATEGORIES = {"logo", "client_logo", "partner_logo"}
NON_CONTENT_MEDIA_CATEGORIES = {
    "ui_asset",
    "payment_icon",
    "country_flag",
    "social_icon",
    "hidden_asset",
    "placeholder_image",
}
COUNTRY_NAMES = {
    "jordan",
    "kuwait",
    "qatar",
    "saudi arabia",
    "ksa",
    "uae",
    "united arab emirates",
    "bahrain",
    "oman",
    "iraq",
    "egypt",
    "lebanon",
}
STOPWORDS = {
    "a",
    "about",
    "an",
    "and",
    "approved",
    "evidence",
    "for",
    "from",
    "give",
    "image",
    "logo",
    "me",
    "of",
    "picture",
    "photo",
    "show",
    "proof",
    "source",
    "the",
    "to",
    "website",
    "with",
}

REQUEST_PHRASE_PATTERN = re.compile(
    r"(?i)\b(?:could\s+you|can\s+you|would\s+you|please|kindly|give\s+me|show\s+me|show|send\s+me|display|find|get|i\s+need|i\s+want)\b"
)

MEDIA_TARGET_PREFIX_PATTERN = re.compile(
    r"(?i)\b(?:image|photo|picture|logo)\s+(?:of|for)\s*[-:–—]*\s*(?P<target>.+)$"
)


@dataclass(frozen=True, slots=True)
class MediaSearchResult:
    item: dict[str, Any]
    score: int
    reason: str
    matched_text: str = ""

    def to_media_item(self) -> dict[str, Any]:
        media_type = clean_text(self.item.get("media_type"))
        is_video = media_type == "website_video"
        url = (
            self.item.get("video_url")
            if is_video
            else self.item.get("local_static_url")
            or self.item.get("url")
            or self.item.get("original_image_url")
            or ""
        )
        return {
            "type": "video" if is_video else "image",
            "url": url or "",
            "label": media_item_label(self.item),
            "source": "approved_media_catalog",
            "page_url": self.item.get("page_url") or "",
            "source_url": self.item.get("source_url") or "",
            "reason": self.reason,
            "local_static_url": self.item.get("local_static_url") or "",
            "original_image_url": self.item.get("original_image_url") or "",
            "entity_name": self.item.get("entity_name") or "",
            "alt_text": self.item.get("alt_text") or "",
            "category": self.item.get("category") or "",
        }


@dataclass(frozen=True, slots=True)
class SpecificMediaIntent:
    is_specific: bool
    target: str = ""
    wants_logo: bool = False
    wants_website: bool = False
    wants_all: bool = False
    raw_query: str = ""


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean_text(value).lower()).strip()


def tokens(value: Any) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9]+", clean_text(value).lower())
        if len(token) > 1 and token not in STOPWORDS
    }


def media_catalog_path(client_slug: str) -> Path:
    return client_scraped_dir(client_slug) / MEDIA_CATALOG_FILENAME


def stable_media_id(*parts: Any) -> str:
    payload = "|".join(clean_text(part) for part in parts)
    return sha1(payload.encode("utf-8", errors="ignore")).hexdigest()[:16]


def infer_entity_name(item: dict[str, Any]) -> str:
    for key in ["entity_name", "alt_text", "title_text", "aria_label"]:
        value = clean_text(item.get(key))
        if not value:
            continue

        if " - " in value:
            return value.split(" - ", 1)[0].strip()

        if "|" in value:
            return value.split("|", 1)[0].strip()

        if len(value.split()) <= 5:
            return value

    filename = Path(clean_text(item.get("original_image_url") or item.get("filename"))).stem
    filename = re.sub(r"[_-]?(?:logo|thumb|image|website|conversion|conversions)[_-]?", " ", filename, flags=re.I)
    filename = re.sub(r"^[a-f0-9]{6,}$", "", filename, flags=re.I)
    return clean_text(filename).title()


def classify_catalog_item(item: dict[str, Any]) -> str:
    existing = clean_text(item.get("category") or item.get("image_category") or item.get("image_role")).lower()
    existing = existing.replace("-", "_").replace(" ", "_")

    if existing in {
        "logo",
        "client_logo",
        "partner_logo",
        "service",
        "services",
        "pricing",
        "contact",
        "location",
        "certificate",
        "screenshot",
        "decorative",
        "staff_photo",
        "social_icon",
    }:
        return "service" if existing == "services" else existing

    combined = normalize_text(
        " ".join(
            clean_text(item.get(key))
            for key in [
                "alt_text",
                "title_text",
                "aria_label",
                "nearby_text",
                "parent_text",
                "section_heading",
                "original_image_url",
                "filename",
                "dom_class",
                "dom_id",
            ]
        )
    )
    width = int(item.get("width") or 0)
    height = int(item.get("height") or 0)

    if item.get("media_type") == "website_screenshot" or "/screenshots/" in clean_text(item.get("local_static_url")):
        return "screenshot"

    if item.get("visible") is False:
        return "hidden_asset"

    if any(term in combined for term in ["plp loader", "loader", "placeholder", "spinner", "sprite", "tracking pixel"]):
        return "placeholder_image"

    if (
        "flag img" in combined
        or "/flags/" in clean_text(item.get("original_image_url")).lower()
        or normalize_text(item.get("alt_text")) in COUNTRY_NAMES
        or normalize_text(item.get("entity_name")) in COUNTRY_NAMES
    ):
        return "country_flag"

    if any(term in combined for term in ["payment", "visa", "mastercard", "paypal", "applepay", "apple pay", "mada"]):
        return "payment_icon"

    if any(term in combined for term in ["certificate", "license", "licensed", "certification"]):
        return "certificate"

    if any(term in combined for term in ["facebook", "instagram", "linkedin", "tiktok", "whatsapp", "youtube"]):
        return "social_icon"

    if "logo" in combined:
        if any(term in combined for term in ["client", "clients", "partner", "partners", "sponsor", "beloved"]):
            return "partner_logo"
        if width and height and width <= 500 and height <= 300:
            return "client_logo"
        return "logo"

    if any(term in combined for term in ["client", "clients", "partner", "partners", "sponsor", "beloved"]):
        return "partner_logo"

    if item.get("entity_name") and width and height and width <= 500 and height <= 220:
        return "client_logo"

    if any(term in combined for term in ["service", "marketing", "branding", "production", "consultancy", "training", "development"]):
        return "service"

    if any(term in combined for term in ["price", "pricing", "package", "cost", "fee"]):
        return "pricing"

    if any(term in combined for term in ["contact", "phone", "email", "whatsapp"]):
        return "contact"

    if any(term in combined for term in ["location", "address", "map", "office"]):
        return "location"

    if any(term in combined for term in ["team", "staff", "manager", "employee", "portrait", "family"]):
        return "staff_photo"

    if width and height and width <= 64 and height <= 64:
        return "ui_asset"

    if "/static/" in clean_text(item.get("original_image_url")).lower() and not (
        item.get("alt_text") or item.get("title_text") or item.get("nearby_text")
    ):
        return "ui_asset"

    if item.get("kind") == "background" and not (
        item.get("alt_text") or item.get("title_text") or item.get("nearby_text")
    ):
        return "decorative"

    return "unknown"


def build_search_text(item: dict[str, Any]) -> str:
    return clean_text(
        " ".join(
            clean_text(item.get(key))
            for key in [
                "entity_name",
                "alt_text",
                "title_text",
                "aria_label",
                "nearby_text",
                "section_heading",
                "parent_text",
                "page_title",
                "page_url",
                "source_url",
                "original_image_url",
                "local_static_url",
                "filename",
                "category",
                "image_role",
                "ocr_text",
                "image_description",
                "vision_summary",
            ]
        )
    )


def is_non_content_media(item: dict[str, Any]) -> bool:
    category = clean_text(item.get("category")).lower()
    image_role = clean_text(item.get("image_role")).lower()
    return category in NON_CONTENT_MEDIA_CATEGORIES or image_role in NON_CONTENT_MEDIA_CATEGORIES


def normalize_catalog_item(
    *,
    client_slug: str,
    source_url: str,
    page: dict[str, Any],
    item: dict[str, Any],
    media_type: str,
    index: int,
) -> dict[str, Any]:
    local_static_url = clean_text(item.get("local_static_url"))
    original_image_url = clean_text(item.get("original_image_url") or item.get("url"))
    video_url = clean_text(item.get("video_url") or item.get("url"))
    filename = Path(local_static_url or original_image_url or video_url).name
    normalized = {
        "media_id": stable_media_id(client_slug, media_type, local_static_url, original_image_url, video_url, index),
        "client_slug": client_slug,
        "source_type": "website_auto_scrape",
        "media_type": media_type,
        "category": clean_text(item.get("category") or item.get("image_category") or item.get("image_role")),
        "image_role": clean_text(item.get("image_role") or item.get("image_category") or item.get("category")),
        "entity_name": clean_text(item.get("entity_name")),
        "alt_text": clean_text(item.get("alt_text") or item.get("alt")),
        "title_text": clean_text(item.get("title_text") or item.get("title")),
        "aria_label": clean_text(item.get("aria_label")),
        "nearby_text": clean_text(item.get("nearby_text")),
        "section_heading": clean_text(item.get("section_heading")),
        "parent_text": clean_text(item.get("parent_text") or item.get("parent_container_text")),
        "page_title": clean_text(item.get("page_title") or page.get("title")),
        "page_url": clean_text(item.get("page_url") or page.get("page_url")),
        "source_url": source_url,
        "original_image_url": original_image_url,
        "video_url": video_url,
        "local_static_url": local_static_url,
        "local_path": clean_text(item.get("local_path")),
        "filename": filename,
        "width": int(item.get("width") or 0),
        "height": int(item.get("height") or 0),
        "visible": bool(item.get("visible", True)),
        "dom_class": clean_text(item.get("dom_class") or item.get("class_name")),
        "dom_id": clean_text(item.get("dom_id") or item.get("element_id")),
        "ocr_text": clean_text(item.get("ocr_text")),
        "image_description": clean_text(item.get("image_description")),
        "vision_summary": clean_text(item.get("vision_summary") or item.get("image_description")),
        "kind": clean_text(item.get("kind")),
        "image_index": item.get("image_index") or index,
    }
    normalized["entity_name"] = normalized["entity_name"] or infer_entity_name(normalized)
    normalized["category"] = classify_catalog_item(normalized)
    normalized["image_role"] = normalized["image_role"] or normalized["category"]
    normalized["search_text"] = build_search_text(normalized)
    return normalized


def build_media_catalog_from_pages(
    *,
    client_slug: str,
    source_url: str,
    pages: list[Any],
) -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    seen_media_keys: set[str] = set()

    for page in pages:
        page_payload = page if isinstance(page, dict) else {
            "page_url": getattr(page, "page_url", ""),
            "title": getattr(page, "title", ""),
            "images": getattr(page, "images", []),
            "screenshots": getattr(page, "screenshots", []),
            "videos": getattr(page, "videos", []),
        }

        for index, image in enumerate(page_payload.get("images", []), start=1):
            if image.get("local_static_url"):
                item = normalize_catalog_item(
                    client_slug=client_slug,
                    source_url=source_url,
                    page=page_payload,
                    item=image,
                    media_type="website_image",
                    index=index,
                )
                key = item.get("local_static_url") or item.get("original_image_url") or item["media_id"]
                if key not in seen_media_keys:
                    catalog.append(item)
                    seen_media_keys.add(key)

        for index, screenshot in enumerate(page_payload.get("screenshots", []), start=1):
            if screenshot.get("local_static_url"):
                item = normalize_catalog_item(
                    client_slug=client_slug,
                    source_url=source_url,
                    page=page_payload,
                    item=screenshot,
                    media_type="website_screenshot",
                    index=index,
                )
                key = item.get("local_static_url") or item["media_id"]
                if key not in seen_media_keys:
                    catalog.append(item)
                    seen_media_keys.add(key)

        for index, video in enumerate(page_payload.get("videos", []), start=1):
            if video.get("video_url") or video.get("url"):
                item = normalize_catalog_item(
                    client_slug=client_slug,
                    source_url=source_url,
                    page=page_payload,
                    item=video,
                    media_type="website_video",
                    index=index,
                )
                key = item.get("video_url") or item["media_id"]
                if key not in seen_media_keys:
                    catalog.append(item)
                    seen_media_keys.add(key)

    return catalog


def save_media_catalog(
    *,
    client_slug: str,
    source_url: str,
    pages: list[Any],
) -> tuple[Path, list[dict[str, Any]]]:
    catalog = build_media_catalog_from_pages(
        client_slug=client_slug,
        source_url=source_url,
        pages=pages,
    )
    path = media_catalog_path(client_slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "client_slug": client_slug,
                "source_url": source_url,
                "total_media": len(catalog),
                "media": catalog,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path, catalog


def load_media_catalog(client_slug: str) -> list[dict[str, Any]]:
    config = load_client_config(client_slug)

    if not config.website_scrape_active:
        return []

    path = media_catalog_path(client_slug)

    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            media = payload.get("media")
            if isinstance(media, list):
                normalized_media = [
                    item
                    for item in media
                    if isinstance(item, dict) and item.get("client_slug") == client_slug
                ]
                for item in normalized_media:
                    item["category"] = classify_catalog_item(item)
                    item["image_role"] = item.get("image_role") or item["category"]
                    item["search_text"] = build_search_text(item)
                return normalized_media
        except Exception:
            pass

    return build_active_media_catalog(client_slug)


def build_active_media_catalog(client_slug: str) -> list[dict[str, Any]]:
    scraped_dir = client_scraped_dir(client_slug)
    if not scraped_dir.exists():
        return []

    for json_path in sorted(scraped_dir.glob("*Website_Scrape.json"), reverse=True):
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        catalog = build_media_catalog_from_pages(
            client_slug=client_slug,
            source_url=clean_text(payload.get("base_url")),
            pages=payload.get("pages", []),
        )
        catalog_path = media_catalog_path(client_slug)
        catalog_path.write_text(
            json.dumps(
                {
                    "client_slug": client_slug,
                    "source_url": clean_text(payload.get("base_url")),
                    "total_media": len(catalog),
                    "media": catalog,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        payload["media_catalog_path"] = catalog_path.as_posix()
        payload["media_catalog"] = catalog
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return catalog

    return []


def extract_specific_media_target(message: str) -> SpecificMediaIntent:
    raw = clean_text(message)
    lowered = raw.lower()
    wants_logo = bool(re.search(r"\b(logo|brandmark|logomark)\b", lowered)) or "شعار" in raw
    wants_all = bool(re.search(r"\b(all|more|multiple|every)\b", lowered))
    wants_website = "website" in lowered or "site" in lowered
    image_phrase = bool(
        re.search(r"\b(show|give|find|get|display|send)\b.*\b(image|logo|photo|picture)\b", lowered)
        or re.search(r"\b(image|logo|photo|picture)\b.*\b(for|of|with)\b", lowered)
        or any(phrase in raw for phrase in ["أرني", "اعرض", "أعطني", "صورة", "شعار"])
    )

    if not image_phrase and not wants_logo:
        return SpecificMediaIntent(is_specific=False, raw_query=raw)

    target = raw
    quoted = re.search(r"['\"]([^'\"]{2,})['\"]", raw)
    if quoted:
        target = quoted.group(1)
    else:
        cleaned_request = REQUEST_PHRASE_PATTERN.sub(" ", raw)
        prefix_match = MEDIA_TARGET_PREFIX_PATTERN.search(cleaned_request)

        if prefix_match:
            target = prefix_match.group("target")
        else:
            target = re.sub(
                r"(?i)\b(?:image|logo|photo|picture|website|site|for|of|with|alt|text|evidence|proof|source|the|a|an)\b",
                " ",
                cleaned_request,
            )

        target = re.sub(r"\s+", " ", target)
        target = target.strip(" \t\r\n-:–—")

    target_tokens = tokens(target)
    is_specific = bool(target_tokens or re.search(r"[\u0600-\u06ff]{2,}", target))

    return SpecificMediaIntent(
        is_specific=is_specific,
        target=target or raw,
        wants_logo=wants_logo,
        wants_website=wants_website,
        wants_all=wants_all,
        raw_query=raw,
    )


def field_match_score(value: str, query: str, *, exact_bonus: int, partial_bonus: int) -> tuple[int, str]:
    value_norm = normalize_text(value)
    query_norm = normalize_text(query)

    if not value_norm or not query_norm:
        return 0, ""

    if value_norm == query_norm:
        return exact_bonus, value

    if query_norm in value_norm:
        return partial_bonus, value

    query_tokens = tokens(query)
    value_tokens = tokens(value)

    if query_tokens and value_tokens and query_tokens == value_tokens:
        return exact_bonus - 20, value

    overlap = query_tokens & value_tokens

    if overlap:
        return min(len(overlap) * 35, partial_bonus - 20), value

    return 0, ""


def score_media_candidate(
    candidate: dict[str, Any],
    query: str,
    *,
    wants_logo: bool,
) -> MediaSearchResult:
    score = 0
    direct_score = 0
    reasons: list[str] = []
    matched_text = ""
    media_type = clean_text(candidate.get("media_type"))
    category = clean_text(candidate.get("category")).lower()

    if media_type not in IMAGE_MEDIA_TYPES:
        score -= 500

    for key, exact_bonus, partial_bonus, label in [
        ("alt_text", 320, 260, "image alt text matches"),
        ("title_text", 280, 230, "image title matches"),
        ("entity_name", 300, 250, "entity name matches"),
        ("aria_label", 230, 190, "aria label matches"),
        ("original_image_url", 180, 140, "image URL matches"),
        ("filename", 170, 130, "filename matches"),
        ("nearby_text", 150, 110, "nearby text matches"),
        ("section_heading", 140, 100, "section heading matches"),
        ("search_text", 100, 75, "metadata matches"),
    ]:
        field_score, field_text = field_match_score(
            clean_text(candidate.get(key)),
            query,
            exact_bonus=exact_bonus,
            partial_bonus=partial_bonus,
        )
        if field_score:
            score += field_score
            if key in {"alt_text", "title_text", "entity_name", "aria_label", "original_image_url", "filename"}:
                direct_score += field_score
            reasons.append(label)
            matched_text = matched_text or field_text

    query_tokens = tokens(query)
    candidate_tokens = tokens(candidate.get("search_text"))
    missing_tokens = query_tokens - candidate_tokens

    if query_tokens and missing_tokens == query_tokens:
        score -= 250
        reasons.append("no target token match")
    elif missing_tokens:
        score -= min(len(missing_tokens) * 45, 120)

    if wants_logo:
        if category in LOGO_CATEGORIES:
            score += 130
            reasons.append(f"{category} category")
        if "logo" in normalize_text(candidate.get("original_image_url") or candidate.get("filename")):
            score += 90
            reasons.append("logo filename")
        if category in {"decorative", "staff_photo", "service", "screenshot"}:
            score -= 130
    elif category == "screenshot":
        score -= 100

    if category in {"social_icon", "decorative", "staff_photo"}:
        score -= 120

    if direct_score < 100:
        score -= 300
        reasons.append("no strong direct metadata match")

    width = int(candidate.get("width") or 0)
    height = int(candidate.get("height") or 0)
    if wants_logo and width and height and width <= 700 and height <= 400:
        score += 25

    return MediaSearchResult(
        item=candidate,
        score=score,
        reason=", ".join(list(dict.fromkeys(reasons))[:3]) or "metadata match",
        matched_text=matched_text,
    )


def search_media_catalog(
    *,
    client_slug: str,
    query: str,
    wants_logo: bool = False,
    limit: int = 1,
) -> list[MediaSearchResult]:
    catalog = load_media_catalog(client_slug)
    results: list[MediaSearchResult] = []
    seen_urls: set[str] = set()

    for candidate in catalog:
        url = clean_text(candidate.get("local_static_url"))
        if not url or url in seen_urls:
            continue

        if clean_text(candidate.get("media_type")) not in IMAGE_MEDIA_TYPES:
            continue

        if is_non_content_media(candidate):
            continue

        results.append(score_media_candidate(candidate, query, wants_logo=wants_logo))
        seen_urls.add(url)
    results.sort(key=lambda result: result.score, reverse=True)

    return [
        result
        for result in results
        if result.score >= 170
    ][:limit]


def browse_media_catalog(
    *,
    client_slug: str,
    limit: int = 1,
    prefer_screenshots: bool = False,
) -> list[MediaSearchResult]:
    catalog = load_media_catalog(client_slug)
    results: list[MediaSearchResult] = []
    seen_urls: set[str] = set()

    for candidate in catalog:
        media_type = clean_text(candidate.get("media_type"))
        if media_type not in {"website_image", "website_screenshot"}:
            continue

        url = clean_text(candidate.get("local_static_url"))
        if not url or url in seen_urls:
            continue

        category = clean_text(candidate.get("category")).lower()
        if is_non_content_media(candidate):
            continue
        score = 100
        reasons = ["approved website media"]

        if media_type == "website_screenshot":
            score += 70 if prefer_screenshots else 15
            reasons.append("screenshot")
        else:
            score += 70 if not prefer_screenshots else 15
            reasons.append("website image")

        if candidate.get("visible") is True:
            score += 15

        if category in {"service", "pricing", "contact", "location", "certificate"}:
            score += 35
            reasons.append(f"{category} category")
        elif category in LOGO_CATEGORIES:
            score += 10
            reasons.append(f"{category} category")
        elif category in {"decorative", "social_icon"}:
            score -= 60
            reasons.append(f"{category} category")

        matched_text = clean_text(
            candidate.get("alt_text")
            or candidate.get("section_heading")
            or candidate.get("page_title")
            or candidate.get("filename")
        )
        results.append(
            MediaSearchResult(
                item=candidate,
                score=score,
                reason=", ".join(reasons),
                matched_text=matched_text,
            )
        )
        seen_urls.add(url)

    results.sort(key=lambda result: result.score, reverse=True)
    return results[: max(1, limit)]


def media_item_label(item: dict[str, Any]) -> str:
    entity = clean_text(item.get("entity_name"))
    category = clean_text(item.get("category")).replace("_", " ")

    if entity and category:
        return f"{entity} {category}"

    return (
        entity
        or clean_text(item.get("alt_text"))
        or clean_text(item.get("image_description"))
        or clean_text(item.get("section_heading"))
        or clean_text(item.get("page_title"))
        or "Company image"
    )


def format_specific_media_answer(
    *,
    result: MediaSearchResult | None,
    intent: SpecificMediaIntent,
    company_name: str,
) -> tuple[str, list[dict[str, Any]]]:
    target = clean_text(intent.target or intent.raw_query)

    if result is None:
        return (
            f"I could not find a related company image matching '{target}'.",
            [],
        )

    item = result.item
    entity = clean_text(item.get("entity_name")) or target
    answer = f"Here is {entity}."
    media = [result.to_media_item()]
    return answer, media


def media_catalog_summary(client_slug: str, *, sample_size: int = 8) -> dict[str, Any]:
    catalog = load_media_catalog(client_slug)
    categories = Counter(clean_text(item.get("category")) or "unknown" for item in catalog)
    media_types = Counter(clean_text(item.get("media_type")) or "unknown" for item in catalog)

    return {
        "client_slug": client_slug,
        "total_media": len(catalog),
        "media_types": dict(media_types),
        "categories": dict(categories),
        "sample_items": catalog[:sample_size],
    }
