from __future__ import annotations

import base64
import hashlib
import json
import logging
import math
import re
import time
import unicodedata
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from openai import APIError, OpenAIError
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.document import MediaCollection, MediaImage
from app.schemas.media import MediaCollectionCreate, MediaCollectionUpdate, MediaImageMetadataUpdate
from app.services.client_config_service import client_data_dir, load_client_config, sanitize_filename
from app.services.embedding_service import create_embeddings
from app.services.openai_client import get_openai_client


logger = logging.getLogger(__name__)

MEDIA_HALFVEC_DISTANCE_INDEX_NAME = "ix_media_images_embedding_halfvec_cosine"

SUPPORTED_IMAGE_SIGNATURES = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
}
IMAGE_EXTENSIONS_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
PROMOTIONAL_ALT_TEXT_TERMS = {
    "warranty",
    "financing",
    "finance",
    "available",
    "availability",
    "offer",
    "discount",
    "price",
    "jod",
    "best value",
}
ARABIC_IMAGE_TERMS = {
    "صورة",
    "صور",
    "اعرض",
    "أعرض",
    "ارني",
    "أرني",
    "المقصورة",
    "داخلي",
    "داخلية",
    "خارجي",
    "خارجية",
    "لون",
    "أبيض",
    "ابيض",
    "أسود",
    "اسود",
    "أحمر",
    "احمر",
}
IMAGE_REQUEST_TERMS = {
    "image",
    "images",
    "photo",
    "photos",
    "picture",
    "pictures",
    "show",
    "display",
    "view",
    "interior",
    "exterior",
    "dashboard",
    "seats",
    "colour",
    "color",
    "white",
    "black",
    "red",
    "silver",
    "another",
    "more",
}
ARABIC_IMAGE_TERMS.update(
    {
        "\u0635\u0648\u0631\u0629",
        "\u0635\u0648\u0631",
        "\u0627\u0639\u0631\u0636",
        "\u0623\u0631\u0646\u064a",
        "\u0634\u0627\u0647\u062f",
        "\u0623\u0634\u0648\u0641",
        "\u0648\u0631\u064a\u0646\u064a",
        "\u0627\u0644\u0645\u0642\u0635\u0648\u0631\u0629",
        "\u062f\u0627\u062e\u0644\u064a",
        "\u062f\u0627\u062e\u0644\u064a\u0629",
        "\u0623\u0628\u064a\u0636",
        "\u0628\u064a\u0636\u0627\u0621",
        "\u0623\u0633\u0648\u062f",
        "\u0633\u0648\u062f\u0627\u0621",
    }
)
IMAGE_REQUEST_TERMS.update({"gallery", "look", "see"})

PROCESSING_STATUSES = {"validating", "processing", "analysing", "embedding"}
ANALYSIS_RETRY_STATUSES = PROCESSING_STATUSES | {"uploaded", "failed"}
READY_IMAGE_STATUSES = {"analysed", "needs_review", "approved"}
MISSING_ORIGINAL_ERROR = "Original image file is missing; please re-upload this image before retrying analysis."


class VisionMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title_en: str = ""
    title_ar: str = ""
    visual_description_en: str = ""
    visual_description_ar: str = ""
    alt_text_en: str = ""
    alt_text_ar: str = ""
    detected_category: str = ""
    detected_product_type: str = ""
    detected_brand: str = ""
    detected_model: str = ""
    detected_colour: str = ""
    detected_view: str = ""
    detected_image_type: str = ""
    detected_features: list[str] = Field(default_factory=list)
    detected_objects: list[str] = Field(default_factory=list)
    visible_text: list[str] = Field(default_factory=list)
    dominant_subject: str = ""
    suggested_group: str = ""
    keywords_en: list[str] = Field(default_factory=list)
    keywords_ar: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    needs_review: bool = True
    review_reasons: list[str] = Field(default_factory=list)

    @field_validator("*", mode="before")
    @classmethod
    def normalize_string_lists(cls, value: Any) -> Any:
        if isinstance(value, str):
            return re.sub(r"\s+", " ", value).strip()
        if isinstance(value, list):
            return [
                re.sub(r"\s+", " ", str(item)).strip()
                for item in value
                if str(item).strip()
            ][:80]
        return value


@dataclass(frozen=True, slots=True)
class MediaRetrievalResult:
    image: MediaImage
    score: float
    direct_score: float
    similarity: float

    def to_media_item(self) -> dict[str, Any]:
        return public_media_payload(self.image)


@dataclass(frozen=True, slots=True)
class MediaRequestIntent:
    is_media_request: bool
    requested_media_count: int
    quantity_intent: str
    explicit_visual_intent: bool = False
    media_request_type: str | None = None
    product: str | None = None
    requested_year: int | None = None
    approved_product: str | None = None
    approved_year: int | None = None
    year_mismatch: bool = False
    colour: str | None = None
    view: str | None = None
    group: str | None = None
    gallery_mode: str | None = None
    informational_intent: bool = False
    request_more: bool = False
    request_another: bool = False
    request_another_colour: bool = False
    available_colours: bool = False
    clamped: bool = False


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def contains_arabic(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", text or ""))


def clean_text(value: Any, *, max_length: int | None = None) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "")).strip()
    if max_length is not None:
        return cleaned[:max_length]
    return cleaned


def clean_list(values: Any, *, max_items: int = 80) -> list[str]:
    if isinstance(values, str):
        candidates = re.split(r"[,;\n]+", values)
    elif isinstance(values, list):
        candidates = values
    else:
        candidates = []
    output: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        cleaned = clean_text(item, max_length=120)
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            output.append(cleaned)
        if len(output) >= max_items:
            break
    return output


ARABIC_INDIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

ENGLISH_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
}
ARABIC_NUMBER_WORDS = {
    "واحد": 1,
    "واحدة": 1,
    "اثنين": 2,
    "إثنين": 2,
    "اثنتين": 2,
    "إثنتين": 2,
    "ثلاث": 3,
    "ثلاثة": 3,
    "اربع": 4,
    "أربع": 4,
    "اربعة": 4,
    "أربعة": 4,
    "خمس": 5,
    "خمسة": 5,
    "ست": 6,
    "ستة": 6,
    "سبع": 7,
    "سبعة": 7,
    "ثمان": 8,
    "ثمانية": 8,
}

COLOUR_SYNONYMS = {
    "white": ("white", "pearl white", "أبيض", "ابيض", "بيضاء", "بيضا"),
    "black": ("black", "أسود", "اسود", "سوداء", "سودا"),
    "red": ("red", "أحمر", "احمر", "حمراء", "حمرا"),
    "silver": ("silver", "فضي", "فضية", "فضى"),
    "grey": ("grey", "gray", "رمادي", "رمادية", "رصاصي"),
    "blue": ("blue", "أزرق", "ازرق", "زرقاء"),
    "beige": ("beige", "بيج", "عاجي"),
    "brown": ("brown", "بني", "بنية"),
    "green": ("green", "أخضر", "اخضر", "خضراء"),
    "yellow": ("yellow", "أصفر", "اصفر", "صفراء"),
    "orange": ("orange", "برتقالي", "برتقالية"),
}
COLOUR_LABELS_AR = {
    "white": "أبيض",
    "black": "أسود",
    "red": "أحمر",
    "silver": "فضي",
    "grey": "رمادي",
    "blue": "أزرق",
    "beige": "بيج",
    "brown": "بني",
    "green": "أخضر",
    "yellow": "أصفر",
    "orange": "برتقالي",
}

COLOUR_SYNONYMS = {
    **COLOUR_SYNONYMS,
    "white": (*COLOUR_SYNONYMS["white"], "\u0623\u0628\u064a\u0636", "\u0627\u0628\u064a\u0636", "\u0627\u0644\u0623\u0628\u064a\u0636", "\u0627\u0644\u0627\u0628\u064a\u0636", "\u0628\u064a\u0636\u0627\u0621", "\u0627\u0644\u0628\u064a\u0636\u0627\u0621", "\u0628\u064a\u0636\u0627", "\u0627\u0644\u0628\u064a\u0636\u0627"),
    "black": (*COLOUR_SYNONYMS["black"], "\u0623\u0633\u0648\u062f", "\u0627\u0633\u0648\u062f", "\u0627\u0644\u0623\u0633\u0648\u062f", "\u0627\u0644\u0627\u0633\u0648\u062f", "\u0633\u0648\u062f\u0627\u0621", "\u0627\u0644\u0633\u0648\u062f\u0627\u0621", "\u0633\u0648\u062f\u0627", "\u0627\u0644\u0633\u0648\u062f\u0627"),
    "red": (*COLOUR_SYNONYMS["red"], "\u0623\u062d\u0645\u0631", "\u0627\u062d\u0645\u0631", "\u0627\u0644\u0623\u062d\u0645\u0631", "\u0627\u0644\u0627\u062d\u0645\u0631", "\u062d\u0645\u0631\u0627\u0621", "\u0627\u0644\u062d\u0645\u0631\u0627\u0621", "\u062d\u0645\u0631\u0627", "\u0627\u0644\u062d\u0645\u0631\u0627"),
    "silver": (*COLOUR_SYNONYMS["silver"], "\u0641\u0636\u064a", "\u0627\u0644\u0641\u0636\u064a", "\u0641\u0636\u064a\u0629", "\u0627\u0644\u0641\u0636\u064a\u0629"),
    "grey": (*COLOUR_SYNONYMS["grey"], "\u0631\u0645\u0627\u062f\u064a", "\u0627\u0644\u0631\u0645\u0627\u062f\u064a", "\u0631\u0645\u0627\u062f\u064a\u0629", "\u0627\u0644\u0631\u0645\u0627\u062f\u064a\u0629", "\u0631\u0635\u0627\u0635\u064a", "\u0627\u0644\u0631\u0635\u0627\u0635\u064a"),
    "blue": (*COLOUR_SYNONYMS["blue"], "\u0623\u0632\u0631\u0642", "\u0627\u0632\u0631\u0642", "\u0627\u0644\u0623\u0632\u0631\u0642", "\u0627\u0644\u0627\u0632\u0631\u0642", "\u0632\u0631\u0642\u0627\u0621", "\u0627\u0644\u0632\u0631\u0642\u0627\u0621"),
    "beige": (*COLOUR_SYNONYMS["beige"], "\u0628\u064a\u062c", "\u0627\u0644\u0628\u064a\u062c", "\u0639\u0627\u062c\u064a", "\u0627\u0644\u0639\u0627\u062c\u064a"),
    "brown": (*COLOUR_SYNONYMS["brown"], "\u0628\u0646\u064a", "\u0627\u0644\u0628\u0646\u064a", "\u0628\u0646\u064a\u0629", "\u0627\u0644\u0628\u0646\u064a\u0629"),
    "green": (*COLOUR_SYNONYMS["green"], "\u0623\u062e\u0636\u0631", "\u0627\u062e\u0636\u0631", "\u0627\u0644\u0623\u062e\u0636\u0631", "\u0627\u0644\u0627\u062e\u0636\u0631", "\u062e\u0636\u0631\u0627\u0621", "\u0627\u0644\u062e\u0636\u0631\u0627\u0621"),
    "yellow": (*COLOUR_SYNONYMS["yellow"], "\u0623\u0635\u0641\u0631", "\u0627\u0635\u0641\u0631", "\u0627\u0644\u0623\u0635\u0641\u0631", "\u0627\u0644\u0627\u0635\u0641\u0631", "\u0635\u0641\u0631\u0627\u0621", "\u0627\u0644\u0635\u0641\u0631\u0627\u0621"),
    "orange": (*COLOUR_SYNONYMS["orange"], "\u0628\u0631\u062a\u0642\u0627\u0644\u064a", "\u0627\u0644\u0628\u0631\u062a\u0642\u0627\u0644\u064a", "\u0628\u0631\u062a\u0642\u0627\u0644\u064a\u0629", "\u0627\u0644\u0628\u0631\u062a\u0642\u0627\u0644\u064a\u0629"),
}

VIEW_SYNONYMS = {
    "rear_seats": (
        "rear seats",
        "back seats",
        "rear seating",
        "المقاعد الخلفية",
        "مقاعد خلفية",
        "الكرسي الخلفي",
    ),
    "front_seats": (
        "front seats",
        "front seating",
        "المقاعد الأمامية",
        "المقاعد الامامية",
        "مقاعد أمامية",
        "مقاعد امامية",
    ),
    "dashboard": (
        "dashboard",
        "cockpit",
        "instrument panel",
        "لوحة القيادة",
        "تابلوه",
        "الطبلون",
        "طبلون",
    ),
    "panoramic_roof": (
        "panoramic roof",
        "sunroof",
        "سقف بانورامي",
        "السقف البانورامي",
        "فتحة سقف",
    ),
    "infotainment": (
        "infotainment",
        "touchscreen",
        "screen",
        "display",
        "شاشة",
        "شاشة المعلومات",
    ),
    "centre_console": (
        "center console",
        "centre console",
        "gear shift",
        "console",
        "الكونسول",
        "ناقل الحركة",
    ),
    "front_cabin": (
        "front cabin",
        "front interior",
        "driver perspective",
        "مقصورة أمامية",
        "مقصورة امامية",
        "المقصورة الأمامية",
    ),
    "interior": (
        "interior",
        "inside",
        "cabin",
        "داخلية",
        "داخلي",
        "مقصورة",
    ),
    "exterior": (
        "exterior",
        "outside",
        "front view",
        "side view",
        "rear view",
        "خارجي",
        "خارجية",
        "من الخارج",
    ),
    "packaging": ("packaging", "package", "box", "عبوة", "تغليف", "صندوق"),
}

VIEW_GROUP_ALIASES = {
    "dashboard": "dashboard",
    "rear_seats": "seats",
    "front_seats": "seats",
    "front_cabin": "interior",
    "panoramic_roof": "interior",
    "infotainment": "dashboard",
    "centre_console": "dashboard",
    "interior": "interior",
    "exterior": "exterior",
    "packaging": "packaging",
}

MEDIA_STOPWORDS = {
    "a",
    "an",
    "the",
    "me",
    "show",
    "give",
    "let",
    "see",
    "image",
    "images",
    "picture",
    "pictures",
    "photo",
    "photos",
    "of",
    "for",
    "to",
    "available",
    "colour",
    "colours",
    "color",
    "colors",
    "another",
    "more",
    "one",
    "two",
    "three",
    "four",
    "اعرض",
    "ارني",
    "أرني",
    "اعطيني",
    "أعطني",
    "صورة",
    "صور",
    "لون",
    "ألوان",
    "الوان",
    "المزيد",
    "اخرى",
    "أخرى",
}


def normalize_for_match(value: Any) -> str:
    text = clean_text(value).translate(ARABIC_INDIC_DIGITS).casefold()
    text = "".join(
        character
        for character in unicodedata.normalize("NFKD", text)
        if unicodedata.category(character) != "Mn"
    )
    text = (
        text.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ى", "ي")
        .replace("ؤ", "و")
        .replace("ئ", "ي")
    )
    text = re.sub(r"[^a-z0-9\u0600-\u06FF]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalized_contains(text: str, phrase: str) -> bool:
    normalized_text = f" {normalize_for_match(text)} "
    normalized_phrase = normalize_for_match(phrase)
    if not normalized_phrase:
        return False
    if " " in normalized_phrase:
        return f" {normalized_phrase} " in normalized_text
    return bool(re.search(rf"(?<![\w\u0600-\u06FF]){re.escape(normalized_phrase)}(?![\w\u0600-\u06FF])", normalized_text))


def clamp_media_count(value: int, *, maximum: int | None = None) -> tuple[int, bool]:
    maximum = maximum or settings.media_max_results_per_answer
    clamped = max(1, min(int(value or 1), maximum))
    return clamped, clamped != value


def extract_explicit_number(text: str) -> int | None:
    normalized = normalize_for_match(text)
    number_match = re.search(r"(?<!\d)(\d{1,2})(?!\d)", normalized)
    if number_match:
        return int(number_match.group(1))
    for word, value in {**ENGLISH_NUMBER_WORDS, **ARABIC_NUMBER_WORDS}.items():
        if normalized_contains(normalized, word):
            return value
    if any(normalized_contains(normalized, term) for term in ["صورتين", "صورتان", "صوتين"]):
        return 2
    return None


def extract_canonical_colour(text: str) -> str | None:
    for colour, synonyms in COLOUR_SYNONYMS.items():
        if any(normalized_contains(text, synonym) for synonym in synonyms):
            return colour
    return None


def canonical_colours_for_image(image: MediaImage) -> set[str]:
    fields = [
        image.detected_colour,
        image.ai_title_en,
        image.ai_title_ar,
        image.dominant_subject,
        " ".join(clean_list(image.keywords_en)),
        " ".join(clean_list(image.keywords_ar)),
    ]
    combined = " ".join(fields)
    return {
        colour
        for colour, synonyms in COLOUR_SYNONYMS.items()
        if any(normalized_contains(combined, synonym) for synonym in synonyms)
    }


def extract_canonical_view(text: str) -> str | None:
    for view in [
        "rear_seats",
        "front_seats",
        "panoramic_roof",
        "centre_console",
        "infotainment",
        "dashboard",
        "front_cabin",
        "interior",
        "exterior",
        "packaging",
    ]:
        if any(normalized_contains(text, synonym) for synonym in VIEW_SYNONYMS[view]):
            return view
    return None


def canonical_views_for_image(image: MediaImage) -> set[str]:
    fields = [
        image.detected_view,
        image.detected_image_type,
        image.detected_product_type,
        image.detected_category,
        image.suggested_group,
        image.dominant_subject,
        image.ai_title_en,
        image.ai_title_ar,
        image.visual_description_en,
        image.visual_description_ar,
        " ".join(clean_list(image.detected_features)),
        " ".join(clean_list(image.detected_objects)),
        " ".join(clean_list(image.keywords_en)),
        " ".join(clean_list(image.keywords_ar)),
    ]
    combined = " ".join(fields)
    views = {
        view
        for view, synonyms in VIEW_SYNONYMS.items()
        if any(normalized_contains(combined, synonym) for synonym in synonyms)
    }
    if image.suggested_group:
        group = normalize_for_match(image.suggested_group)
        if group == "dashboard":
            views.add("dashboard")
        if group == "seats":
            views.add("rear_seats" if normalized_contains(combined, "rear") or normalized_contains(combined, "خلف") else "front_seats")
        if group in {"interior", "exterior", "packaging"}:
            views.add(group)
    if views & {"dashboard", "rear_seats", "front_seats", "front_cabin", "panoramic_roof", "infotainment", "centre_console"}:
        views.add("interior")
    return views


def image_matches_view(image: MediaImage, requested_view: str) -> bool:
    views = canonical_views_for_image(image)
    if requested_view == "interior":
        return bool(views & {"interior", "dashboard", "rear_seats", "front_seats", "front_cabin", "panoramic_roof", "infotainment", "centre_console"})
    if requested_view == "exterior":
        return "exterior" in views and not bool(views & {"dashboard", "rear_seats", "front_seats", "front_cabin", "panoramic_roof"})
    return requested_view in views


def media_query_tokens(text: str) -> set[str]:
    tokens = tokenize(normalize_for_match(text))
    ignored = set(MEDIA_STOPWORDS)
    for synonyms in [*COLOUR_SYNONYMS.values(), *VIEW_SYNONYMS.values()]:
        ignored.update(tokenize(" ".join(synonyms)))
    return {token for token in tokens if token not in ignored and not token.isdigit()}


VISUAL_INTENT_PHRASES = (
    "show me",
    "show the",
    "show available",
    "let me see",
    "can i see",
    "could i see",
    "display",
    "view",
    "image",
    "images",
    "picture",
    "pictures",
    "photo",
    "photos",
    "gallery",
    "look at",
    "browse",
    "\u0627\u0639\u0631\u0636",
    "\u0627\u0639\u0631\u0636 \u0644\u064a",
    "\u0623\u0639\u0631\u0636",
    "\u0623\u0631\u0646\u064a",
    "\u0627\u0631\u0646\u064a",
    "\u0648\u0631\u064a\u0646\u064a",
    "\u062e\u0644\u064a\u0646\u064a \u0627\u0634\u0648\u0641",
    "\u0623\u0631\u064a\u062f \u0623\u0646 \u0623\u0631\u0649",
    "\u0635\u0648\u0631\u0629",
    "\u0635\u0648\u0631",
    "\u0645\u0639\u0631\u0636",
    "\u0634\u0627\u0647\u062f",
    "\u0623\u0638\u0647\u0631",
)
INFORMATIONAL_ATTRIBUTE_PHRASES = (
    "what colours",
    "what colors",
    "which colours",
    "which colors",
    "what grades",
    "which grades",
    "what features",
    "which features",
    "tell me about",
    "specifications",
    "specification",
    "currently available",
    "are available",
    "are offered",
    "\u0645\u0627 \u0627\u0644\u0623\u0644\u0648\u0627\u0646",
    "\u0645\u0627 \u0627\u0644\u0627\u0644\u0648\u0627\u0646",
    "\u0645\u0627 \u0623\u0644\u0648\u0627\u0646",
    "\u0645\u0627 \u0627\u0644\u0641\u0626\u0627\u062a",
    "\u0645\u0627 \u0645\u0632\u0627\u064a\u0627",
    "\u0645\u0627 \u0645\u0648\u0627\u0635\u0641\u0627\u062a",
    "\u0627\u0644\u0645\u062a\u0648\u0641\u0631\u0629",
    "\u0627\u0644\u0645\u062a\u0627\u062d\u0629",
)
PRODUCT_STOPWORDS = MEDIA_STOPWORDS | {
    "show",
    "display",
    "view",
    "look",
    "browse",
    "can",
    "could",
    "i",
    "model",
    "year",
    "currently",
    "available",
    "offered",
    "grades",
    "grade",
    "features",
    "feature",
    "specifications",
    "specification",
    "car",
    "vehicle",
    "\u0633\u064a\u0627\u0631\u0629",
    "\u0645\u0648\u062f\u064a\u0644",
    "\u0627\u0644\u0645\u062a\u0648\u0641\u0631\u0629",
    "\u0627\u0644\u0645\u062a\u0627\u062d\u0629",
}
CAMPAIGN_TITLE_STOPWORDS = {
    "campaign",
    "collection",
    "images",
    "image",
    "launch",
    "gallery",
    "approved",
    "media",
    "model",
    "year",
    "car",
    "vehicle",
}
AUTOMOTIVE_YEAR_MIN = 1980
AUTOMOTIVE_YEAR_MAX = 2040


def has_explicit_visual_intent(text: str) -> bool:
    return any(normalized_contains(text, phrase) for phrase in VISUAL_INTENT_PHRASES)


def has_informational_attribute_intent(text: str) -> bool:
    if any(normalized_contains(text, phrase) for phrase in INFORMATIONAL_ATTRIBUTE_PHRASES):
        return True
    return bool(
        re.search(
            r"\b(?:what|which|tell me about)\b.*\b(?:colour|color|grade|feature|interior|exterior|dashboard|seat|specification)",
            normalize_for_match(text),
        )
    )


def extract_requested_year(text: str) -> int | None:
    normalized = normalize_for_match(text)
    for match in re.finditer(r"(?<!\d)((?:19|20)\d{2})(?!\d)", normalized):
        year = int(match.group(1))
        if AUTOMOTIVE_YEAR_MIN <= year <= AUTOMOTIVE_YEAR_MAX:
            return year
    return None


def extract_product_phrase_from_query(text: str) -> str | None:
    tokens = tokenize(normalize_for_match(text))
    ignored = set(PRODUCT_STOPWORDS)
    for synonyms in [*COLOUR_SYNONYMS.values(), *VIEW_SYNONYMS.values()]:
        ignored.update(tokenize(" ".join(synonyms)))
    product_tokens = [
        token
        for token in re.findall(r"[A-Za-z0-9\u0600-\u06FF]+", normalize_for_match(text))
        if token not in ignored and not token.isdigit()
    ]
    if not product_tokens:
        return None
    unique: list[str] = []
    seen: set[str] = set()
    for token in product_tokens:
        if token in seen:
            continue
        seen.add(token)
        unique.append(token)
    return " ".join(unique[:4]) or None


def extract_year_from_context_text(text: str) -> int | None:
    return extract_requested_year(text)


def product_label_from_text(text: str) -> str | None:
    cleaned = clean_text(re.sub(r"(?<!\d)(?:19|20)\d{2}(?!\d)", " ", text))
    words = [
        word
        for word in re.findall(r"[A-Za-z0-9\u0600-\u06FF]+", cleaned)
        if normalize_for_match(word) not in CAMPAIGN_TITLE_STOPWORDS
    ]
    if not words:
        return None
    return " ".join(words[:4])


def approved_media_context_from_images(
    images: list[MediaImage],
    *,
    product: str | None = None,
) -> dict[str, Any]:
    if not images:
        return {}
    collections = [
        collection
        for collection in {str(image.collection_id): getattr(image, "collection", None) for image in images}.values()
        if collection is not None
    ]
    year_sources: list[str] = []
    product_sources: list[str] = []
    for collection in collections:
        year_sources.extend(
            [
                getattr(collection, "shared_model_year", ""),
                getattr(collection, "title", ""),
                getattr(collection, "general_description_original", ""),
                getattr(collection, "general_description_en", ""),
                getattr(collection, "general_description_ar", ""),
            ]
        )
        product_sources.extend(
            [
                getattr(collection, "shared_product_family", ""),
                " ".join(
                    clean_text(value)
                    for value in [
                        getattr(collection, "shared_brand", ""),
                        getattr(collection, "shared_model", ""),
                    ]
                    if clean_text(value)
                ),
                getattr(collection, "title", ""),
            ]
        )
    year_sources.extend(
        clean_text(value)
        for image in images
        for value in [
            image.detected_model,
            image.dominant_subject,
            image.ai_title_en,
            image.ai_title_ar,
            image.visual_description_en,
            image.visual_description_ar,
        ]
    )
    approved_year = next(
        (
            year
            for year in (extract_year_from_context_text(source) for source in year_sources)
            if year is not None
        ),
        None,
    )
    approved_product = next(
        (
            clean_text(source)
            for source in product_sources
            if clean_text(source) and not re.fullmatch(r"(?:19|20)\d{2}", clean_text(source))
        ),
        None,
    )
    if approved_product and re.search(r"(?:19|20)\d{2}|campaign|collection|images|gallery", approved_product, re.I):
        approved_product = product_label_from_text(approved_product)
    if not approved_product:
        approved_product = product
    return {
        "approved_product": approved_product,
        "approved_year": approved_year,
    }


def approved_media_context_for_query(
    *,
    db: Session,
    client_slug: str,
    query: str,
) -> dict[str, Any]:
    if not media_retrieval_enabled(client_slug):
        return {}
    statement = (
        select(MediaImage)
        .join(MediaCollection, MediaCollection.id == MediaImage.collection_id)
        .where(
            MediaImage.client_slug == client_slug,
            MediaCollection.client_slug == client_slug,
            MediaCollection.is_enabled.is_(True),
            MediaCollection.is_approved.is_(True),
            MediaImage.is_approved.is_(True),
            MediaImage.is_active.is_(True),
            MediaImage.is_duplicate.is_(False),
        )
        .limit(200)
    )
    images = list(db.execute(statement).scalars())
    images, _duplicate_count = deduplicate_media_images(images)
    product = resolve_product_from_query(query, images) or extract_product_phrase_from_query(query)
    if product:
        matching = [image for image in images if product_matches_image(image, product)]
        if matching:
            images = matching
    context = approved_media_context_from_images(images, product=product)
    return {**context, "requested_product": product}


def format_year_mismatch_message(
    *,
    question: str,
    requested_year: int,
    approved_year: int,
    approved_product: str | None,
) -> str:
    product = clean_text(approved_product) or "this approved campaign"
    if contains_arabic(question):
        return (
            "\u0627\u0644\u062d\u0645\u0644\u0629 \u0648\u0627\u0644\u0635\u0648\u0631 "
            "\u0627\u0644\u0645\u0639\u062a\u0645\u062f\u0629 \u0627\u0644\u0645\u062a\u0648\u0641\u0631\u0629 "
            f"\u062a\u062e\u0635 {product} {approved_year}\u060c "
            f"\u0648\u0644\u0627 \u062a\u062a\u0648\u0641\u0631 \u062d\u0627\u0644\u064a\u0627\u064b "
            f"\u0635\u0648\u0631 \u0645\u0639\u062a\u0645\u062f\u0629 \u0644\u0645\u0648\u062f\u064a\u0644 {requested_year}."
        )
    return (
        f"The approved campaign and available images are for the {approved_year} {product}. "
        f"No approved {requested_year} images are currently available."
    )


def product_text_for_image(image: MediaImage) -> str:
    collection = getattr(image, "collection", None)
    collection_values = [
        getattr(collection, "title", ""),
        getattr(collection, "general_description_original", ""),
    ]
    return " ".join(
        clean_text(value)
        for value in [
            image.detected_brand,
            image.detected_model,
            image.detected_product_type,
            image.detected_category,
            image.dominant_subject,
            image.ai_title_en,
            image.ai_title_ar,
            " ".join(clean_list(image.keywords_en)),
            " ".join(clean_list(image.keywords_ar)),
            *collection_values,
        ]
        if clean_text(value)
    )


def product_matches_image(image: MediaImage, product: str | None) -> bool:
    if not product:
        return True
    return all(normalized_contains(product_text_for_image(image), token) for token in media_query_tokens(product))


def resolve_product_from_query(query: str, images: list[MediaImage]) -> str | None:
    tokens = media_query_tokens(query)
    if not tokens:
        return None
    matching_tokens = {
        token
        for token in tokens
        if any(normalized_contains(product_text_for_image(image), token) for image in images)
    }
    if not matching_tokens:
        return None
    return " ".join(sorted(matching_tokens))


def parse_media_request_intent(
    text: str,
    *,
    plural_default: int | None = None,
    maximum: int | None = None,
) -> MediaRequestIntent:
    plural_default = plural_default or settings.media_max_results_per_answer
    maximum = maximum or settings.media_max_results_per_answer
    is_media = looks_like_campaign_image_request(text)
    lowered = normalize_for_match(text)
    explicit_number = extract_explicit_number(text)
    request_another = any(
        normalized_contains(lowered, phrase)
        for phrase in [
            "another image",
            "another picture",
            "another photo",
            "one more",
            "next image",
            "different image",
            "صورة اخرى",
            "صورة اخري",
            "صورة ثانية",
            "صورا اخرى",
            "صور اخرى",
        ]
    )
    request_more = any(
        normalized_contains(lowered, phrase)
        for phrase in [
            "more images",
            "more pictures",
            "more photos",
            "show me more",
            "some images",
            "several images",
            "show options",
            "show available",
            "gallery",
            "المزيد من الصور",
            "صور اخرى",
            "عدة صور",
            "بعض الصور",
            "الصور المتوفرة",
        ]
    )
    request_another_colour = any(
        normalized_contains(lowered, phrase)
        for phrase in ["another colour", "another color", "different colour", "different color", "لون اخر", "لونا اخر"]
    )
    available_colours = any(
        normalized_contains(lowered, phrase)
        for phrase in [
            "available colours",
            "available colors",
            "what colours",
            "what colors",
            "show colours",
            "show colors",
            "الالوان المتوفرة",
            "الألوان المتوفرة",
            "ما الالوان",
            "ما الألوان",
            "اعرض الوان",
            "اعرض ألوان",
        ]
    )
    plural = any(
        normalized_contains(lowered, phrase)
        for phrase in ["images", "pictures", "photos", "options", "gallery", "صور", "الصور"]
    ) and not any(normalized_contains(lowered, phrase) for phrase in ["صورة", "one image", "one picture", "one photo"])
    singular = any(
        normalized_contains(lowered, phrase)
        for phrase in [
            "an image",
            "a picture",
            "a photo",
            "one image",
            "one picture",
            "one photo",
            "show me the",
            "let me see",
            "صورة",
            "صورة واحدة",
            "اعطيني صورة",
            "أعطني صورة",
            "ارني صورة",
            "أرني صورة",
            "وريني صورة",
        ]
    )

    quantity_intent = "singular"
    requested = 1
    if explicit_number is not None:
        requested = explicit_number
        quantity_intent = "explicit"
    elif available_colours or request_more or (plural and not request_another):
        requested = plural_default
        quantity_intent = "plural"
    elif request_another or singular:
        requested = 1
        quantity_intent = "singular"
    elif is_media:
        requested = 1
        quantity_intent = "singular"

    requested, clamped = clamp_media_count(requested, maximum=maximum)
    colour = None if request_another_colour or available_colours else extract_canonical_colour(text)
    view = extract_canonical_view(text)
    is_media = is_media or available_colours or bool(colour) or bool(view) or request_more or request_another or request_another_colour
    return MediaRequestIntent(
        is_media_request=is_media,
        requested_media_count=requested,
        quantity_intent=quantity_intent,
        colour=colour,
        view=view,
        group=VIEW_GROUP_ALIASES.get(view or "") if view else None,
        request_more=request_more,
        request_another=request_another,
        request_another_colour=request_another_colour,
        available_colours=available_colours,
        clamped=clamped,
    )


def parse_media_request_intent(
    text: str,
    *,
    plural_default: int | None = None,
    maximum: int | None = None,
) -> MediaRequestIntent:
    plural_default = plural_default or settings.media_max_results_per_answer
    maximum = maximum or settings.media_max_results_per_answer
    lowered = normalize_for_match(text)
    explicit_visual_intent = has_explicit_visual_intent(text)
    informational_intent = has_informational_attribute_intent(text)
    explicit_number = extract_explicit_number(text)
    requested_year = extract_requested_year(text)
    request_another = any(
        normalized_contains(lowered, phrase)
        for phrase in (
            "another image",
            "another picture",
            "another photo",
            "one more",
            "next image",
            "different image",
            "\u0635\u0648\u0631\u0629 \u0623\u062e\u0631\u0649",
            "\u0635\u0648\u0631\u0629 \u062b\u0627\u0646\u064a\u0629",
        )
    )
    request_more = any(
        normalized_contains(lowered, phrase)
        for phrase in (
            "more images",
            "more pictures",
            "more photos",
            "show me more",
            "some images",
            "several images",
            "show options",
            "show available",
            "gallery",
            "\u0627\u0644\u0645\u0632\u064a\u062f \u0645\u0646 \u0627\u0644\u0635\u0648\u0631",
            "\u0635\u0648\u0631 \u0623\u062e\u0631\u0649",
            "\u0639\u062f\u0629 \u0635\u0648\u0631",
            "\u0628\u0639\u0636 \u0627\u0644\u0635\u0648\u0631",
        )
    )
    request_another_colour = any(
        normalized_contains(lowered, phrase)
        for phrase in (
            "another colour",
            "another color",
            "different colour",
            "different color",
            "\u0644\u0648\u0646 \u0622\u062e\u0631",
        )
    )
    raw_available_colours = any(
        normalized_contains(lowered, phrase)
        for phrase in (
            "available colours",
            "available colors",
            "what colours",
            "what colors",
            "show colours",
            "show colors",
            "\u0627\u0644\u0623\u0644\u0648\u0627\u0646 \u0627\u0644\u0645\u062a\u0648\u0641\u0631\u0629",
            "\u0645\u0627 \u0627\u0644\u0623\u0644\u0648\u0627\u0646",
            "\u0627\u0639\u0631\u0636 \u0623\u0644\u0648\u0627\u0646",
        )
    )
    available_colours = raw_available_colours and explicit_visual_intent
    plural = any(
        normalized_contains(lowered, phrase)
        for phrase in (
            "images",
            "pictures",
            "photos",
            "options",
            "gallery",
            "\u0635\u0648\u0631",
        )
    ) and not any(
        normalized_contains(lowered, phrase)
        for phrase in (
            "\u0635\u0648\u0631\u0629",
            "one image",
            "one picture",
            "one photo",
            "an image",
            "a picture",
            "a photo",
        )
    )
    singular = any(
        normalized_contains(lowered, phrase)
        for phrase in (
            "an image",
            "a picture",
            "a photo",
            "one image",
            "one picture",
            "one photo",
            "\u0635\u0648\u0631\u0629",
            "\u0635\u0648\u0631\u0629 \u0648\u0627\u062d\u062f\u0629",
        )
    )
    colour = None if request_another_colour or available_colours else extract_canonical_colour(text)
    view = extract_canonical_view(text)
    attribute_specific = bool(colour or view)
    singular_attribute = bool(
        attribute_specific
        and re.search(r"\b(?:show me|display|view|let me see)\s+(?:a|an|the)\b", lowered)
    )
    is_media = bool(
        explicit_visual_intent
        or request_more
        or request_another
        or request_another_colour
    )
    if not is_media:
        return MediaRequestIntent(
            is_media_request=False,
            requested_media_count=0,
            quantity_intent="none",
            explicit_visual_intent=False,
            media_request_type=None,
            product=extract_product_phrase_from_query(text),
            requested_year=requested_year,
            colour=extract_canonical_colour(text),
            view=view,
            group=VIEW_GROUP_ALIASES.get(view or "") if view else None,
            informational_intent=informational_intent,
            request_more=request_more,
            request_another=request_another,
            request_another_colour=request_another_colour,
            available_colours=False,
        )

    media_request_type = "product_gallery"
    quantity_intent = "gallery"
    requested = plural_default
    if explicit_number is not None:
        requested = explicit_number
        quantity_intent = "explicit"
        media_request_type = "explicit_count"
    elif available_colours or request_more or (plural and not request_another):
        requested = plural_default
        quantity_intent = "plural"
        media_request_type = "available_colour_gallery" if available_colours else "plural_images"
    elif request_another or singular:
        requested = 1
        quantity_intent = "singular"
        media_request_type = "another_or_more" if request_another else "single_image"
    elif attribute_specific and singular_attribute:
        requested = 1
        quantity_intent = "singular"
        media_request_type = "attribute_image"
    elif attribute_specific:
        requested = 1
        quantity_intent = "singular"
        media_request_type = "attribute_image"

    requested, clamped = clamp_media_count(requested, maximum=maximum)
    gallery_mode = (
        "exterior"
        if media_request_type in {
            "product_gallery",
            "plural_images",
            "single_image",
            "explicit_count",
            "available_colour_gallery",
        }
        and not view
        else None
    )
    return MediaRequestIntent(
        is_media_request=True,
        requested_media_count=requested,
        quantity_intent=quantity_intent,
        explicit_visual_intent=explicit_visual_intent,
        media_request_type=media_request_type,
        product=extract_product_phrase_from_query(text),
        requested_year=requested_year,
        colour=colour,
        view=view,
        group=VIEW_GROUP_ALIASES.get(view or "") if view else None,
        gallery_mode=gallery_mode,
        informational_intent=informational_intent,
        request_more=request_more,
        request_another=request_another,
        request_another_colour=request_another_colour,
        available_colours=available_colours,
        clamped=clamped,
    )


def media_root(client_slug: str) -> Path:
    return client_data_dir(client_slug) / "media"


def collection_root(client_slug: str, collection_id: UUID | str) -> Path:
    return media_root(client_slug) / "collections" / str(collection_id)


def original_dir(client_slug: str, collection_id: UUID | str) -> Path:
    return collection_root(client_slug, collection_id) / "originals"


def approved_dir(client_slug: str, collection_id: UUID | str) -> Path:
    return collection_root(client_slug, collection_id) / "approved"


def thumbnail_dir(client_slug: str, collection_id: UUID | str) -> Path:
    return collection_root(client_slug, collection_id) / "thumbnails"


def public_media_url(client_slug: str, collection_id: UUID, image_id: UUID, variant: str = "approved") -> str:
    base_path = "/" + str(getattr(settings, "app_base_path", "") or "").strip().strip("/")
    base_path = "" if base_path == "/" else base_path.rstrip("/")
    return f"{base_path}/api/media/{image_id}/{variant}"


def client_relative_path(client_slug: str, relative_value: str) -> Path:
    root = client_data_dir(client_slug).resolve()
    candidate = (root / (relative_value or "")).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("Stored image path escapes the client data directory.")
    return candidate


def set_config_media_retrieval_enabled(*, client_slug: str, enabled: bool) -> None:
    config = load_client_config(client_slug)
    media_config = config.media_retrieval if isinstance(config.media_retrieval, dict) else {}
    config.media_retrieval = {
        **media_config,
        "enabled": bool(enabled),
        "max_results_per_answer": settings.media_max_results_per_answer,
    }
    from app.services.client_config_service import save_client_config

    save_client_config(config)


def sniff_image_mime(path: Path) -> str:
    header = path.read_bytes()[:16]
    if header.startswith(SUPPORTED_IMAGE_SIGNATURES["image/jpeg"][0]):
        return "image/jpeg"
    if header.startswith(SUPPORTED_IMAGE_SIGNATURES["image/png"][0]):
        return "image/png"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "image/webp"
    raise ValueError("Unsupported image type. Upload JPEG, PNG, or WebP images.")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_image_dimensions(width: int, height: int) -> None:
    if width <= 0 or height <= 0:
        raise ValueError("Image dimensions could not be read.")
    if max(width, height) > settings.media_max_pixel_dimension:
        raise ValueError(
            "Image dimensions exceed the configured "
            f"{settings.media_max_pixel_dimension}px limit."
        )


def write_optimized_versions(
    *,
    source_path: Path,
    approved_path: Path,
    thumbnail_path: Path,
    mime_type: str,
) -> tuple[int, int]:
    try:
        with Image.open(source_path) as image:
            image = ImageOps.exif_transpose(image)
            width, height = image.size
            validate_image_dimensions(width, height)
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA" if mime_type == "image/png" else "RGB")
            approved_path.parent.mkdir(parents=True, exist_ok=True)
            thumbnail_path.parent.mkdir(parents=True, exist_ok=True)

            display = image.copy()
            display.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            save_kwargs: dict[str, Any] = {"optimize": True}
            if mime_type == "image/png":
                display.save(approved_path, format="PNG", **save_kwargs)
            elif mime_type == "image/webp":
                display.save(approved_path, format="WEBP", quality=84, method=6)
            else:
                display.convert("RGB").save(approved_path, format="JPEG", quality=86, **save_kwargs)

            thumb = image.copy()
            thumb.thumbnail((420, 420), Image.Resampling.LANCZOS)
            thumb.convert("RGB").save(thumbnail_path, format="JPEG", quality=82, optimize=True)
            return width, height
    except UnidentifiedImageError as error:
        raise ValueError("The uploaded file is not a readable image.") from error


def validate_uploaded_image_file(
    *,
    path: Path,
    original_filename: str,
    content_type: str | None = None,
) -> str:
    size = path.stat().st_size
    if size <= 0:
        raise ValueError(f"{original_filename or 'Image'} is empty.")
    max_bytes = settings.media_max_file_size_mb * 1024 * 1024
    if size > max_bytes:
        raise ValueError(
            f"{original_filename or 'Image'} exceeds the "
            f"{settings.media_max_file_size_mb} MB per-image limit."
        )
    mime_type = sniff_image_mime(path)
    if content_type and content_type.lower() not in {mime_type, "application/octet-stream"}:
        raise ValueError("Image MIME type does not match the file signature.")
    return mime_type


def create_collection(
    *,
    db: Session,
    client_slug: str,
    payload: MediaCollectionCreate,
) -> MediaCollection:
    load_client_config(client_slug)
    collection = MediaCollection(
        client_slug=client_slug,
        campaign_id=client_slug,
        chatbot_id=client_slug,
        title=payload.title,
        general_description_original=payload.general_description,
        general_description_language=payload.general_description_language or (
            "ar" if contains_arabic(payload.general_description) else "en"
        ),
        general_description_en=payload.general_description if not contains_arabic(payload.general_description) else "",
        general_description_ar=payload.general_description if contains_arabic(payload.general_description) else "",
        is_enabled=payload.retrieval_enabled,
        analysis_status="draft",
    )
    db.add(collection)
    db.flush()
    set_config_media_retrieval_enabled(client_slug=client_slug, enabled=payload.retrieval_enabled)
    for directory in [
        original_dir(client_slug, collection.id),
        approved_dir(client_slug, collection.id),
        thumbnail_dir(client_slug, collection.id),
    ]:
        directory.mkdir(parents=True, exist_ok=True)
    return collection


def update_collection_from_payload(collection: MediaCollection, payload: MediaCollectionUpdate) -> None:
    data = payload.model_dump(exclude_unset=True)
    if "general_description" in data:
        description = clean_text(data.pop("general_description"), max_length=4000)
        collection.general_description_original = description
        collection.general_description_en = description if not contains_arabic(description) else ""
        collection.general_description_ar = description if contains_arabic(description) else ""
    if "retrieval_enabled" in data:
        collection.is_enabled = bool(data.pop("retrieval_enabled"))
    for key, value in data.items():
        if hasattr(collection, key):
            setattr(collection, key, value if not isinstance(value, str) else clean_text(value))


def get_collection_for_client(db: Session, client_slug: str, collection_id: UUID) -> MediaCollection:
    collection = db.scalar(
        select(MediaCollection).where(
            MediaCollection.id == collection_id,
            MediaCollection.client_slug == client_slug,
        )
    )
    if collection is None:
        raise ValueError("Media collection was not found for this client.")
    return collection


def refresh_collection_counts(db: Session, collection: MediaCollection) -> None:
    rows = db.execute(
        select(
            func.count(MediaImage.id),
            func.count(MediaImage.id).filter(MediaImage.analysis_status.in_(["analysed", "needs_review", "approved"])),
            func.count(MediaImage.id).filter(MediaImage.analysis_status == "failed"),
            func.count(MediaImage.id).filter(MediaImage.needs_review.is_(True)),
            func.count(MediaImage.id).filter(MediaImage.is_duplicate.is_(True)),
        ).where(
            MediaImage.collection_id == collection.id,
            MediaImage.client_slug == collection.client_slug,
        )
    ).one()
    collection.total_images = int(rows[0] or 0)
    collection.processed_images = int(rows[1] or 0)
    collection.failed_images = int(rows[2] or 0)
    collection.flagged_images = int(rows[3] or 0)
    collection.duplicate_images = int(rows[4] or 0)
    if collection.is_approved:
        collection.analysis_status = "approved"
    elif collection.failed_images and collection.processed_images:
        collection.analysis_status = "partially_failed"
    elif collection.failed_images and not collection.processed_images:
        collection.analysis_status = "failed"
    elif collection.flagged_images:
        collection.analysis_status = "review_required"
    elif collection.processed_images and collection.processed_images == collection.total_images:
        collection.analysis_status = "ready_for_approval"


def fail_media_image(image: MediaImage, reason: str, *, review_reason: str = "processing_failed") -> None:
    image.analysis_status = "failed"
    image.analysis_error = clean_text(reason, max_length=1000)
    image.needs_review = True
    image.is_approved = False
    image.is_active = False
    image.processing_error_at = utc_now()
    image.processing_started_at = None
    image.review_reasons = clean_list([*(image.review_reasons or []), review_reason], max_items=40)


def media_image_storage_paths(image: MediaImage) -> tuple[Path | None, Path | None, Path | None]:
    original = client_relative_path(image.client_slug, image.original_storage_path) if image.original_storage_path else None
    display = client_relative_path(image.client_slug, image.public_storage_path) if image.public_storage_path else None
    thumbnail = client_relative_path(image.client_slug, image.thumbnail_path) if image.thumbnail_path else None
    return original, display, thumbnail


def media_image_derivatives_ready(image: MediaImage) -> bool:
    try:
        _, display, thumbnail = media_image_storage_paths(image)
    except ValueError:
        return False
    return bool(display and thumbnail and display.is_file() and thumbnail.is_file())


def ensure_media_image_derivatives(collection: MediaCollection, image: MediaImage) -> bool:
    try:
        original, display, thumbnail = media_image_storage_paths(image)
    except ValueError as error:
        fail_media_image(image, str(error), review_reason="invalid_storage_path")
        return False

    if display and thumbnail and display.is_file() and thumbnail.is_file():
        return True

    if original is None or not original.is_file():
        fail_media_image(image, MISSING_ORIGINAL_ERROR, review_reason="missing_original_file")
        return False

    try:
        mime_type = validate_uploaded_image_file(
            path=original,
            original_filename=image.original_filename,
            content_type=image.mime_type,
        )
        extension = IMAGE_EXTENSIONS_BY_MIME[mime_type]
        image.mime_type = mime_type
        if not image.safe_filename or Path(image.safe_filename).suffix.lower() != extension:
            safe_stem = sanitize_filename(Path(image.original_filename or "campaign_image").stem)[:80]
            image.safe_filename = f"{safe_stem}-{image.sha256[:12]}{extension}"
        display = approved_dir(collection.client_slug, collection.id) / image.safe_filename
        thumbnail = thumbnail_dir(collection.client_slug, collection.id) / f"{image.id}.jpg"
        width, height = write_optimized_versions(
            source_path=original,
            approved_path=display,
            thumbnail_path=thumbnail,
            mime_type=mime_type,
        )
        image.public_storage_path = display.relative_to(client_data_dir(collection.client_slug)).as_posix()
        image.thumbnail_path = thumbnail.relative_to(client_data_dir(collection.client_slug)).as_posix()
        image.width = width
        image.height = height
        image.analysis_status = "uploaded"
        image.analysis_error = ""
        return True
    except Exception as error:
        fail_media_image(
            image,
            f"{type(error).__name__}: {error}",
            review_reason="derivative_generation_failed",
        )
        return False


def duplicate_reference(
    *,
    db: Session,
    client_slug: str,
    collection_id: UUID,
    sha256: str,
) -> MediaImage | None:
    return db.scalar(
        select(MediaImage)
        .where(
            MediaImage.client_slug == client_slug,
            MediaImage.sha256 == sha256,
            or_(
                MediaImage.collection_id == collection_id,
                MediaImage.collection.has(MediaCollection.client_slug == client_slug),
            ),
        )
        .order_by(MediaImage.created_at.asc())
        .limit(1)
    )


def existing_image_can_be_repaired(image: MediaImage, collection: MediaCollection) -> bool:
    return (
        image.collection_id == collection.id
        and image.client_slug == collection.client_slug
        and not image.is_approved
        and (
            image.analysis_status in ANALYSIS_RETRY_STATUSES
            or not image.original_storage_path
            or not image.public_storage_path
            or not image.thumbnail_path
            or image.embedding is None
        )
    )


def create_image_record(
    *,
    db: Session,
    collection: MediaCollection,
    source_path: Path,
    original_filename: str,
    content_type: str | None,
) -> MediaImage:
    mime_type = validate_uploaded_image_file(
        path=source_path,
        original_filename=original_filename,
        content_type=content_type,
    )
    extension = IMAGE_EXTENSIONS_BY_MIME[mime_type]
    digest = sha256_file(source_path)
    existing = duplicate_reference(
        db=db,
        client_slug=collection.client_slug,
        collection_id=collection.id,
        sha256=digest,
    )
    repairing_existing = existing is not None and existing_image_can_be_repaired(existing, collection)
    if repairing_existing:
        image = existing
        image.campaign_id = collection.campaign_id
        image.chatbot_id = collection.chatbot_id
        image.original_filename = Path(original_filename or image.original_filename or "campaign_image").name
        image.mime_type = mime_type
        image.file_size = source_path.stat().st_size
        image.sha256 = digest
        image.is_duplicate = False
        image.duplicate_of_image_id = None
        image.is_approved = False
        image.is_active = True
    else:
        image = MediaImage(
            collection_id=collection.id,
            client_slug=collection.client_slug,
            campaign_id=collection.campaign_id,
            chatbot_id=collection.chatbot_id,
            original_filename=Path(original_filename or "campaign_image").name,
            safe_filename=f"campaign-image-{digest[:12]}{extension}",
            original_storage_path="",
            public_storage_path="",
            thumbnail_path="",
            mime_type=mime_type,
            file_size=source_path.stat().st_size,
            sha256=digest,
            analysis_status="validating",
            needs_review=True,
            review_reasons=[],
        )
        db.add(image)

    if existing is not None and not repairing_existing:
        image.is_duplicate = True
        image.duplicate_of_image_id = existing.id
        image.analysis_status = "duplicate"
        image.review_reasons = ["exact_duplicate"]

    db.flush()
    image.safe_filename = f"{image.id}-{digest[:12]}{extension}"
    private_path = original_dir(collection.client_slug, collection.id) / f"{image.id}{extension}"
    approved_path = approved_dir(collection.client_slug, collection.id) / image.safe_filename
    thumbnail_path = thumbnail_dir(collection.client_slug, collection.id) / f"{image.id}.jpg"
    private_path.parent.mkdir(parents=True, exist_ok=True)
    moved_private_path = False
    try:
        source_path.replace(private_path)
        moved_private_path = True
        if not private_path.is_file() or private_path.stat().st_size <= 0:
            raise ValueError("Uploaded image could not be persisted to private storage.")
        width, height = write_optimized_versions(
            source_path=private_path,
            approved_path=approved_path,
            thumbnail_path=thumbnail_path,
            mime_type=mime_type,
        )
    except Exception:
        if moved_private_path:
            private_path.unlink(missing_ok=True)
        approved_path.unlink(missing_ok=True)
        thumbnail_path.unlink(missing_ok=True)
        raise
    image.original_storage_path = private_path.relative_to(client_data_dir(collection.client_slug)).as_posix()
    image.public_storage_path = approved_path.relative_to(client_data_dir(collection.client_slug)).as_posix()
    image.thumbnail_path = thumbnail_path.relative_to(client_data_dir(collection.client_slug)).as_posix()
    image.width = width
    image.height = height
    if not image.is_duplicate:
        image.analysis_status = "uploaded"
        image.processing_started_at = None
        image.processing_error_at = None
        image.analysis_error = ""
        image.needs_review = True
        image.review_reasons = []
    refresh_collection_counts(db, collection)
    return image


def collection_shared_context(collection: MediaCollection) -> str:
    return "\n".join(
        line
        for line in [
            f"Collection title: {collection.title}",
            f"General batch description: {collection.general_description_original}",
        ]
        if line.split(":", 1)[1].strip()
    )


def vision_prompt(collection: MediaCollection) -> str:
    return f"""
Analyze this single client-provided image for a campaign media catalogue.

Client-provided collection context:
{collection_shared_context(collection)}

Strict rules:
- Describe only what can reasonably be seen in this individual image.
- Use the general client description as context, not as proof of visual content.
- Never mark a shared fact as visually detected unless it is visible in the image.
- Do not assign every colour, model, feature, or group from the collection description to every image.
- Do not invent prices, availability, warranty, financing, technical specifications, model years, locations, or discounts.
- Do not identify an exact model unless supported by visible evidence; flag uncertainty.
- Flag conflicts between the general description and visible image evidence.
- Keep accessibility alt text concise and visual. Do not put promotional claims in alt text unless visibly printed in the image.
- Generate natural Arabic and English metadata.
""".strip()


def analyze_image_with_vision(
    *,
    collection: MediaCollection,
    image: MediaImage,
    image_path: Path,
) -> VisionMetadata:
    model_name = settings.openai_vision_model.strip()
    if not model_name:
        return fallback_metadata(
            collection=collection,
            image=image,
            reason="OPENAI_VISION_MODEL is not configured.",
        )

    data_url = (
        f"data:{image.mime_type};base64,"
        + base64.b64encode(image_path.read_bytes()).decode("ascii")
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = get_openai_client().responses.parse(
                model=model_name,
                instructions=vision_prompt(collection),
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "Return strict JSON for this one image."},
                            {"type": "input_image", "image_url": data_url},
                        ],
                    }
                ],
                text_format=VisionMetadata,
                store=False,
            )
            parsed = response.output_parsed
            if parsed is None:
                raise ValueError("Vision model returned no parsed metadata.")
            return parsed if isinstance(parsed, VisionMetadata) else VisionMetadata.model_validate(parsed)
        except (OpenAIError, APIError, ValidationError, ValueError) as error:
            last_error = error
            time.sleep(1.0 * (2 ** attempt))
    raise RuntimeError(f"Vision analysis failed: {last_error}") from last_error


def fallback_metadata(*, collection: MediaCollection, image: MediaImage, reason: str) -> VisionMetadata:
    label = clean_text(Path(image.original_filename).stem.replace("_", " ").replace("-", " "))
    title = label or collection.title or "Campaign image"
    return VisionMetadata(
        title_en=title,
        title_ar=title,
        visual_description_en="Image uploaded for the campaign. Vision analysis requires review.",
        visual_description_ar="صورة مرفوعة للحملة وتحتاج إلى مراجعة تحليل الصور.",
        alt_text_en="Campaign image requiring visual review.",
        alt_text_ar="صورة حملة تحتاج إلى مراجعة بصرية.",
        detected_category="uncertain",
        detected_image_type="uncertain",
        dominant_subject=title,
        suggested_group="review_required",
        keywords_en=clean_list([title, collection.title]),
        keywords_ar=clean_list([title]),
        confidence=0.0,
        needs_review=True,
        review_reasons=["vision_unavailable", reason],
    )


def alt_text_has_promotional_claims(value: str) -> bool:
    lowered = value.casefold()
    return any(term in lowered for term in PROMOTIONAL_ALT_TEXT_TERMS)


def normalize_vision_metadata(metadata: VisionMetadata, collection: MediaCollection) -> VisionMetadata:
    reasons = clean_list(metadata.review_reasons, max_items=40)
    needs_review = metadata.needs_review
    if metadata.confidence < settings.media_vision_confidence_threshold:
        needs_review = True
        reasons.append("low_vision_confidence")
    if alt_text_has_promotional_claims(metadata.alt_text_en):
        needs_review = True
        reasons.append("english_alt_text_contains_promotional_claim")
    if any(term in metadata.alt_text_ar for term in ["ضمان", "تمويل", "عرض", "خصم", "سعر"]):
        needs_review = True
        reasons.append("arabic_alt_text_contains_promotional_claim")
    return metadata.model_copy(
        update={
            "needs_review": needs_review,
            "review_reasons": clean_list(reasons, max_items=40),
            "suggested_group": infer_group(metadata),
        }
    )


def infer_group(metadata: VisionMetadata | MediaImage) -> str:
    fields = [
        getattr(metadata, "suggested_group", ""),
        getattr(metadata, "detected_image_type", ""),
        getattr(metadata, "detected_view", ""),
        getattr(metadata, "detected_product_type", ""),
        getattr(metadata, "detected_category", ""),
        getattr(metadata, "dominant_subject", ""),
        " ".join(clean_list(getattr(metadata, "detected_features", []))),
        " ".join(clean_list(getattr(metadata, "detected_objects", []))),
        " ".join(clean_list(getattr(metadata, "keywords_en", []))),
    ]
    combined = " ".join(clean_text(value).casefold() for value in fields)
    mapping = [
        (("dashboard", "instrument", "infotainment"), "dashboard"),
        (("seat", "sofa", "chair"), "seats"),
        (("interior", "inside", "داخل"), "interior"),
        (("exterior", "front", "rear", "side", "outside", "خار"), "exterior"),
        (("packaging", "package", "box"), "packaging"),
        (("offer", "banner", "poster", "promo"), "promotional_banners"),
        (("dining", "table"), "dining_rooms"),
        (("bed", "bedroom"), "bedrooms"),
        (("drink", "dessert", "dish", "food"), "food"),
    ]
    for terms, group in mapping:
        if any(term in combined for term in terms):
            return group
    return clean_text(getattr(metadata, "suggested_group", ""), max_length=120) or "general"


def searchable_text_for_image(collection: MediaCollection, image: MediaImage) -> tuple[str, str]:
    shared_en = [
        collection.title,
        collection.general_description_original,
    ]
    shared_ar = [
        collection.title,
        collection.general_description_original,
    ]
    visual = [
        image.ai_title_en,
        image.visual_description_en,
        image.detected_category,
        image.detected_product_type,
        image.detected_colour,
        image.detected_view,
        image.detected_image_type,
        image.dominant_subject,
        image.suggested_group,
        *clean_list(image.detected_features),
        *clean_list(image.keywords_en),
    ]
    visual_ar = [
        image.ai_title_ar,
        image.visual_description_ar,
        image.detected_category,
        image.detected_product_type,
        image.detected_colour,
        image.detected_view,
        image.detected_image_type,
        image.dominant_subject,
        image.suggested_group,
        *clean_list(image.keywords_ar),
    ]
    def join_clean(values: list[Any]) -> str:
        return clean_text(" ".join(clean_text(value) for value in values if clean_text(value)))

    return join_clean(shared_en + visual), join_clean(shared_ar + visual_ar)


def apply_metadata_to_image(image: MediaImage, metadata: VisionMetadata) -> None:
    image.ai_title_en = clean_text(metadata.title_en, max_length=255)
    image.ai_title_ar = clean_text(metadata.title_ar, max_length=255)
    image.visual_description_en = clean_text(metadata.visual_description_en, max_length=4000)
    image.visual_description_ar = clean_text(metadata.visual_description_ar, max_length=4000)
    image.alt_text_en = clean_text(metadata.alt_text_en, max_length=500)
    image.alt_text_ar = clean_text(metadata.alt_text_ar, max_length=500)
    image.detected_category = clean_text(metadata.detected_category, max_length=120)
    image.detected_product_type = clean_text(metadata.detected_product_type, max_length=120)
    image.detected_brand = clean_text(metadata.detected_brand, max_length=120)
    image.detected_model = clean_text(metadata.detected_model, max_length=120)
    image.detected_colour = clean_text(metadata.detected_colour, max_length=80)
    image.detected_view = clean_text(metadata.detected_view, max_length=80)
    image.detected_image_type = clean_text(metadata.detected_image_type, max_length=120)
    image.detected_features = clean_list(metadata.detected_features)
    image.detected_objects = clean_list(metadata.detected_objects)
    image.visible_text = clean_list(metadata.visible_text)
    image.dominant_subject = clean_text(metadata.dominant_subject, max_length=255)
    image.suggested_group = clean_text(metadata.suggested_group, max_length=120)
    image.keywords_en = clean_list(metadata.keywords_en)
    image.keywords_ar = clean_list(metadata.keywords_ar)
    image.vision_confidence = float(metadata.confidence)
    image.needs_review = bool(metadata.needs_review)
    image.review_reasons = clean_list(metadata.review_reasons, max_items=40)
    image.analysis_status = "needs_review" if image.needs_review else "analysed"
    image.analysis_error = ""
    image.processing_error_at = None


def analyze_media_image(*, db: Session, collection: MediaCollection, image: MediaImage) -> None:
    if image.analysis_status in {"analysed", "needs_review", "approved"} and image.embedding is not None:
        return
    if image.is_duplicate:
        image.analysis_status = "duplicate"
        image.needs_review = True
        image.review_reasons = clean_list([*(image.review_reasons or []), "exact_duplicate"])
        return
    image.analysis_status = "processing"
    image.retry_count = int(image.retry_count or 0) + 1
    image.processing_started_at = utc_now()
    image.processing_error_at = None
    image.analysis_error = ""
    db.commit()
    try:
        if not ensure_media_image_derivatives(collection, image):
            return
        image_path = client_relative_path(image.client_slug, image.public_storage_path)
        image.analysis_status = "analysing"
        db.commit()
        metadata = normalize_vision_metadata(
            analyze_image_with_vision(
                collection=collection,
                image=image,
                image_path=image_path,
            ),
            collection,
        )
        apply_metadata_to_image(image, metadata)
        image.searchable_text_en, image.searchable_text_ar = searchable_text_for_image(collection, image)
        embedding_text = clean_text(f"{image.searchable_text_en}\n{image.searchable_text_ar}")
        if embedding_text:
            image.analysis_status = "embedding"
            db.commit()
            embedding = create_embeddings([embedding_text])
            image.embedding = embedding.embeddings[0]
            image.embedding_model = embedding.model
        image.is_active = True
        image.processing_started_at = None
        image.processing_error_at = None
        if image.analysis_status == "embedding":
            image.analysis_status = "needs_review" if image.needs_review else "analysed"
    except Exception as error:
        logger.exception(
            "Campaign media analysis failed",
            extra={
                "client_slug": image.client_slug,
                "collection_id": str(collection.id),
                "image_id": str(image.id),
                "stage": "analysis",
                "error_category": type(error).__name__,
            },
        )
        fail_media_image(image, f"{type(error).__name__}: {error}", review_reason="analysis_failed")
    finally:
        refresh_collection_counts(db, collection)
        db.commit()


def analyze_collection_task(client_slug: str, collection_id: str) -> None:
    with SessionLocal() as db:
        collection = get_collection_for_client(db, client_slug, UUID(collection_id))
        collection.analysis_status = "analysing"
        db.commit()
        images = list(
            db.execute(
                select(MediaImage)
                .where(
                    MediaImage.client_slug == client_slug,
                    MediaImage.collection_id == collection.id,
                    MediaImage.analysis_status.in_(list(ANALYSIS_RETRY_STATUSES)),
                )
                .order_by(MediaImage.display_order.asc(), MediaImage.created_at.asc())
            ).scalars()
        )
        for image in images:
            analyze_media_image(db=db, collection=collection, image=image)
        refresh_collection_counts(db, collection)
        db.commit()


def recover_stale_media_images(
    *,
    db: Session,
    client_slug: str,
    collection_id: UUID,
    force: bool = False,
    stale_minutes: int | None = None,
) -> dict[str, int | str]:
    collection = get_collection_for_client(db, client_slug, collection_id)
    cutoff = utc_now() - timedelta(minutes=stale_minutes or settings.media_stale_processing_minutes)
    statement = select(MediaImage).where(
        MediaImage.client_slug == client_slug,
        MediaImage.collection_id == collection.id,
        MediaImage.analysis_status.in_(list(ANALYSIS_RETRY_STATUSES)),
    )
    if not force:
        statement = statement.where(
            or_(
                MediaImage.analysis_status.in_(["uploaded", "failed"]),
                MediaImage.processing_started_at.is_(None),
                MediaImage.processing_started_at < cutoff,
            )
        )
    images = list(
        db.execute(statement.order_by(MediaImage.display_order.asc(), MediaImage.created_at.asc())).scalars()
    )
    processed = 0
    failed_before = sum(1 for image in images if image.analysis_status == "failed")
    for image in images:
        before = image.analysis_status
        analyze_media_image(db=db, collection=collection, image=image)
        if image.analysis_status in READY_IMAGE_STATUSES and image.embedding is not None:
            processed += 1
        elif before != "failed" and image.analysis_status == "failed":
            failed_before += 1
    refresh_collection_counts(db, collection)
    return {
        "client_slug": client_slug,
        "collection_id": str(collection.id),
        "queued_images": len(images),
        "processed_images": processed,
        "failed_images": failed_before,
        "analysis_status": collection.analysis_status,
    }


def retry_collection_media_task(client_slug: str, collection_id: str) -> None:
    with SessionLocal() as db:
        recover_stale_media_images(
            db=db,
            client_slug=client_slug,
            collection_id=UUID(collection_id),
            force=True,
        )
        db.commit()


def update_image_metadata(
    *,
    db: Session,
    client_slug: str,
    image_id: UUID,
    payload: MediaImageMetadataUpdate,
) -> MediaImage:
    image = db.scalar(
        select(MediaImage).where(
            MediaImage.id == image_id,
            MediaImage.client_slug == client_slug,
        )
    )
    if image is None:
        raise ValueError("Media image was not found for this client.")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        if key in {
            "detected_features",
            "detected_objects",
            "visible_text",
            "keywords_en",
            "keywords_ar",
            "review_reasons",
        }:
            setattr(image, key, clean_list(value))
        elif hasattr(image, key):
            setattr(image, key, value if not isinstance(value, str) else clean_text(value))
    collection = image.collection
    image.suggested_group = image.suggested_group or infer_group(image)
    image.searchable_text_en, image.searchable_text_ar = searchable_text_for_image(collection, image)
    try:
        image.analysis_status = "embedding"
        embedding = create_embeddings([clean_text(f"{image.searchable_text_en}\n{image.searchable_text_ar}")])
        image.embedding = embedding.embeddings[0]
        image.embedding_model = embedding.model
        image.analysis_status = "needs_review" if image.needs_review else "analysed"
        image.analysis_error = ""
        image.processing_error_at = None
    except Exception as error:
        fail_media_image(image, f"{type(error).__name__}: {error}", review_reason="embedding_refresh_failed")
    refresh_collection_counts(db, collection)
    return image


def media_image_ready_for_approval(image: MediaImage) -> bool:
    has_metadata = bool(
        clean_text(image.ai_title_en)
        or clean_text(image.ai_title_ar)
        or clean_text(image.visual_description_en)
        or clean_text(image.visual_description_ar)
        or clean_text(image.alt_text_en)
        or clean_text(image.alt_text_ar)
    )
    return (
        image.analysis_status in READY_IMAGE_STATUSES
        and not image.is_duplicate
        and image.analysis_status != "failed"
        and bool(image.public_storage_path)
        and bool(image.thumbnail_path)
        and has_metadata
        and image.embedding is not None
        and image.is_active
    )


def approve_image(image: MediaImage, approved: bool) -> None:
    if approved and not media_image_ready_for_approval(image):
        raise ValueError("Image must be analysed, have public image paths, metadata, and an embedding before approval.")
    image.is_approved = approved
    image.is_active = bool(approved)
    image.needs_review = False if approved else image.needs_review
    image.analysis_status = "approved" if approved else "rejected"


def approve_collection(collection: MediaCollection, approved: bool, approved_by: str) -> None:
    approved_count = 0
    for image in collection.images:
        if approved and not image.needs_review and media_image_ready_for_approval(image):
            approve_image(image, True)
            approved_count += 1
        elif not approved:
            image.is_active = False
            image.is_approved = False
            if image.analysis_status == "approved":
                image.analysis_status = "rejected"
    if approved and approved_count == 0:
        raise ValueError("No eligible analysed images are ready for collection approval.")
    collection.is_approved = approved
    collection.is_enabled = collection.is_enabled if approved else False
    collection.approved_by = clean_text(approved_by, max_length=120) if approved else None
    collection.approved_at = utc_now() if approved else None
    collection.analysis_status = "approved" if approved else "inactive"


def sync_config_media_flag(*, db: Session, client_slug: str) -> None:
    try:
        config = load_client_config(client_slug)
    except FileNotFoundError:
        return
    has_collections = bool(
        db.scalar(
            select(MediaCollection.id)
            .where(MediaCollection.client_slug == client_slug)
            .limit(1)
        )
    )
    explicit_enabled = bool(
        db.scalar(
            select(MediaCollection.id)
            .where(
                MediaCollection.client_slug == client_slug,
                MediaCollection.is_enabled.is_(True),
            )
            .limit(1)
        )
    )
    if not has_collections:
        media_config = config.media_retrieval if isinstance(config.media_retrieval, dict) else {}
        explicit_enabled = bool(media_config.get("enabled", settings.media_retrieval_enabled_default))
    has_approved_media = bool(
        db.scalar(
            select(MediaCollection.id)
            .where(
                MediaCollection.client_slug == client_slug,
                MediaCollection.is_enabled.is_(True),
                MediaCollection.is_approved.is_(True),
            )
            .limit(1)
        )
    )
    config.media_retrieval = {
        **(config.media_retrieval or {}),
        "enabled": explicit_enabled,
        "has_approved_media": has_approved_media,
        "max_results_per_answer": settings.media_max_results_per_answer,
    }
    from app.services.client_config_service import save_client_config

    save_client_config(config)


def serialize_collection(collection: MediaCollection, *, include_images: bool = False) -> dict[str, Any]:
    generated_groups = sorted(
        {
            clean_text(image.suggested_group)
            for image in getattr(collection, "images", [])
            if clean_text(image.suggested_group)
        }
    )
    payload = {
        "id": str(collection.id),
        "client_slug": collection.client_slug,
        "title": collection.title,
        "general_description": collection.general_description_original,
        "general_description_language": collection.general_description_language,
        "retrieval_enabled": collection.is_enabled,
        "analysis_status": collection.analysis_status,
        "total_images": collection.total_images,
        "processed_images": collection.processed_images,
        "failed_images": collection.failed_images,
        "flagged_images": collection.flagged_images,
        "duplicate_images": collection.duplicate_images,
        "generated_groups": generated_groups,
        "is_enabled": collection.is_enabled,
        "is_approved": collection.is_approved,
        "approved_by": collection.approved_by,
        "approved_at": collection.approved_at.isoformat() if collection.approved_at else None,
    }
    if include_images:
        payload["images"] = [serialize_image(image) for image in collection.images]
    return payload


def serialize_image(image: MediaImage) -> dict[str, Any]:
    return {
        "id": str(image.id),
        "collection_id": str(image.collection_id),
        "client_slug": image.client_slug,
        "original_filename": image.original_filename,
        "mime_type": image.mime_type,
        "file_size": image.file_size,
        "width": image.width,
        "height": image.height,
        "sha256": image.sha256,
        "thumbnail_url": public_media_url(image.client_slug, image.collection_id, image.id, "thumbnail"),
        "public_url": public_media_url(image.client_slug, image.collection_id, image.id, "approved"),
        "admin_thumbnail_url": "",
        "admin_image_url": "",
        "ai_title_en": image.ai_title_en,
        "ai_title_ar": image.ai_title_ar,
        "visual_description_en": image.visual_description_en,
        "visual_description_ar": image.visual_description_ar,
        "alt_text_en": image.alt_text_en,
        "alt_text_ar": image.alt_text_ar,
        "detected_category": image.detected_category,
        "detected_product_type": image.detected_product_type,
        "detected_brand": image.detected_brand,
        "detected_model": image.detected_model,
        "detected_colour": image.detected_colour,
        "detected_view": image.detected_view,
        "detected_image_type": image.detected_image_type,
        "detected_features": image.detected_features,
        "detected_objects": image.detected_objects,
        "visible_text": image.visible_text,
        "dominant_subject": image.dominant_subject,
        "suggested_group": image.suggested_group,
        "keywords_en": image.keywords_en,
        "keywords_ar": image.keywords_ar,
        "needs_review": image.needs_review,
        "review_reasons": image.review_reasons,
        "analysis_status": image.analysis_status,
        "analysis_error": image.analysis_error,
        "is_duplicate": image.is_duplicate,
        "duplicate_of_image_id": str(image.duplicate_of_image_id) if image.duplicate_of_image_id else None,
        "is_approved": image.is_approved,
        "is_active": image.is_active,
        "display_order": image.display_order,
    }


def public_media_payload(image: MediaImage) -> dict[str, Any]:
    label = image.ai_title_en or image.alt_text_en or image.dominant_subject or "Campaign image"
    caption = clean_text(image.visual_description_en, max_length=260)
    if normalize_for_match(caption) == normalize_for_match(label):
        caption = ""
    colours = sorted(canonical_colours_for_image(image))
    views = sorted(canonical_views_for_image(image))
    return {
        "id": str(image.id),
        "type": "image",
        "url": public_media_url(image.client_slug, image.collection_id, image.id, "approved"),
        "fallback_url": public_media_url(image.client_slug, image.collection_id, image.id, "thumbnail"),
        "thumbnail_url": public_media_url(image.client_slug, image.collection_id, image.id, "thumbnail"),
        "label": label,
        "title": label,
        "caption": caption,
        "alt_text": image.alt_text_en or label,
        "title_en": image.ai_title_en,
        "title_ar": image.ai_title_ar,
        "description": image.visual_description_en,
        "colour": colours[0] if colours else "",
        "colours": colours,
        "view": views[0] if views else "",
        "views": views,
        "group": image.suggested_group,
        "source": "approved_campaign_media",
    }


def media_retrieval_enabled(client_slug: str) -> bool:
    try:
        config = load_client_config(client_slug)
    except FileNotFoundError:
        return False
    media_config = config.media_retrieval if isinstance(config.media_retrieval, dict) else {}
    return bool(media_config.get("enabled", settings.media_retrieval_enabled_default))


def looks_like_campaign_image_request(text: str) -> bool:
    return has_explicit_visual_intent(text)


def tokenize(value: str) -> set[str]:
    return {
        token.casefold()
        for token in re.findall(r"[A-Za-z0-9\u0600-\u06FF]+", value or "")
        if len(token) > 1
    }


def direct_match_score(image: MediaImage, query: str) -> float:
    query_tokens = tokenize(query)
    if not query_tokens:
        return 0.0
    fields = [
        image.detected_product_type,
        image.detected_category,
        image.detected_model,
        image.detected_colour,
        image.detected_image_type,
        image.detected_view,
        image.suggested_group,
        image.dominant_subject,
        image.ai_title_en,
        image.ai_title_ar,
        " ".join(image.keywords_en or []),
        " ".join(image.keywords_ar or []),
    ]
    field_tokens = tokenize(" ".join(clean_text(field) for field in fields))
    overlap = query_tokens & field_tokens
    score = min(0.35, len(overlap) * 0.06)
    normalized_query = clean_text(query).casefold()
    for field in fields[:7]:
        normalized_field = clean_text(field).casefold()
        if normalized_field and normalized_field in normalized_query:
            score += settings.media_direct_match_boost
    return min(score, 0.75)


def media_context_terms(media_context: dict[str, Any] | None) -> str:
    if not isinstance(media_context, dict):
        return ""
    return " ".join(
        clean_text(media_context.get(key))
        for key in [
            "last_media_group",
            "last_product",
            "last_category",
            "last_model",
            "last_colour",
            "last_image_type",
            "last_view",
        ]
    )


def media_embedding_dimension() -> int:
    return settings.embedding_dimensions


def media_halfvec_distance_expression(dimension: int | None = None) -> str:
    dimension = dimension or media_embedding_dimension()
    return (
        f"media_images.embedding::halfvec({dimension}) "
        f"<=> CAST(:query_embedding AS halfvec({dimension}))"
    )


def vector_literal(values: list[float]) -> str:
    dimension = media_embedding_dimension()
    if len(values) != dimension:
        raise ValueError(
            "Media query embedding dimension mismatch. "
            f"Expected {dimension}, got {len(values)}."
        )
    parts: list[str] = []
    for value in values:
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError("Media query embedding contains a non-finite value.")
        parts.append(format(numeric, ".9g"))
    return f"[{','.join(parts)}]"


def media_halfvec_search_supported(db: Session) -> bool:
    try:
        return bool(
            db.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM pg_indexes
                        WHERE indexname = :index_name
                          AND tablename = 'media_images'
                    )
                    """
                ),
                {"index_name": MEDIA_HALFVEC_DISTANCE_INDEX_NAME},
            ).scalar()
        )
    except SQLAlchemyError:
        db.rollback()
        return False


def exact_media_vector_rows(
    *,
    db: Session,
    base_statement,
    embedding: list[float],
    limit: int,
) -> list[tuple[MediaImage, float]]:
    distance = MediaImage.embedding.cosine_distance(embedding).label("cosine_distance")
    return list(
        db.execute(
            base_statement.with_only_columns(MediaImage, distance)
            .where(MediaImage.embedding.is_not(None))
            .order_by(distance.asc())
            .limit(limit)
        ).all()
    )


def indexed_media_vector_rows(
    *,
    db: Session,
    client_slug: str,
    embedding: list[float],
    limit: int,
) -> list[tuple[MediaImage, float]]:
    distance_expression = media_halfvec_distance_expression()
    rows = db.execute(
        text(
            f"""
            SELECT media_images.id, {distance_expression} AS cosine_distance
            FROM media_images
            JOIN media_collections ON media_collections.id = media_images.collection_id
            WHERE media_images.client_slug = :client_slug
              AND media_collections.client_slug = :client_slug
              AND media_collections.is_enabled IS TRUE
              AND media_collections.is_approved IS TRUE
              AND media_images.is_approved IS TRUE
              AND media_images.is_active IS TRUE
              AND media_images.is_duplicate IS FALSE
              AND media_images.embedding IS NOT NULL
            ORDER BY cosine_distance ASC
            LIMIT :limit
            """
        ),
        {
            "client_slug": client_slug,
            "query_embedding": vector_literal(embedding),
            "limit": limit,
        },
    ).all()
    if not rows:
        return []
    image_ids = [row.id for row in rows]
    images_by_id = {
        str(image.id): image
        for image in db.execute(select(MediaImage).where(MediaImage.id.in_(image_ids))).scalars()
    }
    return [
        (images_by_id[str(row.id)], float(row.cosine_distance))
        for row in rows
        if str(row.id) in images_by_id and row.cosine_distance is not None
    ]


def deduplicate_media_images(images: list[MediaImage]) -> tuple[list[MediaImage], int]:
    seen: set[str] = set()
    output: list[MediaImage] = []
    duplicates = 0
    for image in images:
        identities = [
            f"id:{image.id}",
            f"sha:{image.sha256}" if image.sha256 else "",
            f"duplicate:{image.duplicate_of_image_id}" if image.duplicate_of_image_id else "",
            f"path:{normalize_for_match(image.public_storage_path)}" if image.public_storage_path else "",
        ]
        if any(identity and identity in seen for identity in identities):
            duplicates += 1
            continue
        for identity in identities:
            if identity:
                seen.add(identity)
        output.append(image)
    return output, duplicates


def representative_colour_results(
    *,
    images: list[MediaImage],
    intent: MediaRequestIntent,
    vector_scores: dict[str, float],
    retrieval_text: str,
    avoid: set[str],
) -> list[MediaRetrievalResult]:
    representatives: dict[str, MediaImage] = {}
    product_images = [image for image in images if product_matches_image(image, intent.product)]
    if product_images:
        images = product_images
    ranked = rank_media_candidates(
        images=[image for image in images if str(image.id) not in avoid and image_matches_view(image, "exterior")],
        intent=intent,
        vector_scores=vector_scores,
        retrieval_text=retrieval_text,
    )
    for result in ranked:
        colours = sorted(canonical_colours_for_image(result.image))
        for colour in colours:
            if colour in representatives:
                continue
            representatives[colour] = result.image
            break
    colour_results = [
        MediaRetrievalResult(
            image=image,
            score=ranked_score_for_image(ranked, image),
            direct_score=direct_match_score(image, retrieval_text),
            similarity=vector_scores.get(str(image.id), 0.0),
        )
        for colour, image in sorted(representatives.items())
    ]
    colour_results.sort(
        key=lambda result: (
            -result.image.display_order,
            result.image.created_at or datetime.min.replace(tzinfo=timezone.utc),
            str(result.image.id),
        )
    )
    return colour_results


def exterior_diverse_gallery_results(
    *,
    images: list[MediaImage],
    intent: MediaRequestIntent,
    vector_scores: dict[str, float],
    retrieval_text: str,
    avoid: set[str],
) -> list[MediaRetrievalResult]:
    candidates = [
        image
        for image in images
        if str(image.id) not in avoid and image_matches_view(image, "exterior")
    ]
    if intent.colour:
        candidates = [
            image
            for image in candidates
            if intent.colour in canonical_colours_for_image(image)
        ]
    product_candidates = [
        image for image in candidates if product_matches_image(image, intent.product)
    ]
    candidate_colours = {
        colour
        for image in candidates
        for colour in canonical_colours_for_image(image)
    }
    product_candidate_colours = {
        colour
        for image in product_candidates
        for colour in canonical_colours_for_image(image)
    }
    if product_candidates and (
        intent.colour
        or len(product_candidate_colours) >= min(
            intent.requested_media_count,
            len(candidate_colours) or len(product_candidate_colours),
        )
    ):
        candidates = product_candidates
    ranked = rank_media_candidates(
        images=candidates,
        intent=intent,
        vector_scores=vector_scores,
        retrieval_text=retrieval_text,
    )
    selected: list[MediaRetrievalResult] = []
    used_ids: set[str] = set()
    used_hashes: set[str] = set()
    used_colours: set[str] = set()

    def can_add(result: MediaRetrievalResult) -> bool:
        image_id = str(result.image.id)
        image_hash = clean_text(result.image.sha256)
        return image_id not in used_ids and (not image_hash or image_hash not in used_hashes)

    def add(result: MediaRetrievalResult) -> None:
        used_ids.add(str(result.image.id))
        if result.image.sha256:
            used_hashes.add(result.image.sha256)
        used_colours.update(canonical_colours_for_image(result.image))
        selected.append(result)

    for result in ranked:
        colours = canonical_colours_for_image(result.image)
        if can_add(result) and (not colours or not (colours & used_colours)):
            add(result)
    for result in ranked:
        if can_add(result):
            add(result)
    return selected


def ranked_score_for_image(results: list[MediaRetrievalResult], image: MediaImage) -> float:
    for result in results:
        if result.image.id == image.id:
            return result.score
    return 0.0


def strict_filter_candidates(
    *,
    images: list[MediaImage],
    intent: MediaRequestIntent,
    product: str | None,
    avoid: set[str],
) -> tuple[list[MediaImage], bool]:
    candidates = [image for image in images if str(image.id) not in avoid]
    strict = False
    if intent.request_another_colour:
        previous_colour = intent.colour
        if previous_colour:
            candidates = [image for image in candidates if previous_colour not in canonical_colours_for_image(image)]
    if intent.colour:
        strict = True
        candidates = [image for image in candidates if intent.colour in canonical_colours_for_image(image)]
    if intent.view:
        strict = True
        candidates = [image for image in candidates if image_matches_view(image, intent.view)]
    if product:
        product_candidates = [image for image in candidates if product_matches_image(image, product)]
        if product_candidates:
            candidates = product_candidates
            strict = True
    return candidates, strict


def rank_media_candidates(
    *,
    images: list[MediaImage],
    intent: MediaRequestIntent,
    vector_scores: dict[str, float],
    retrieval_text: str,
) -> list[MediaRetrievalResult]:
    ranked: list[MediaRetrievalResult] = []
    product = intent.product
    for image in images:
        direct = direct_match_score(image, retrieval_text)
        similarity = vector_scores.get(str(image.id), 0.0)
        colour_match = 1.0 if intent.colour and intent.colour in canonical_colours_for_image(image) else 0.0
        view_match = 1.0 if intent.view and image_matches_view(image, intent.view) else 0.0
        product_match = 1.0 if product and product_matches_image(image, product) else 0.0
        confidence_boost = min(max(float(image.vision_confidence or 0.0), 0.0), 1.0) * 0.04
        display_boost = max(0.0, 0.04 - min(image.display_order or 0, 20) * 0.002)
        score = (
            max(similarity, 0.0)
            + direct
            + colour_match * 2.0
            + view_match * 1.2
            + product_match * 0.8
            + confidence_boost
            + display_boost
        )
        ranked.append(
            MediaRetrievalResult(
                image=image,
                score=score,
                direct_score=direct,
                similarity=similarity,
            )
        )
    ranked.sort(
        key=lambda result: (
            result.score,
            result.direct_score,
            result.similarity,
            float(result.image.vision_confidence or 0.0),
            -int(result.image.display_order or 0),
            -(result.image.created_at.timestamp() if result.image.created_at else 0.0),
            str(result.image.id),
        ),
        reverse=True,
    )
    return ranked


def log_media_retrieval_diagnostics(
    *,
    query: str,
    client_slug: str,
    intent: MediaRequestIntent,
    eligible_count: int,
    exact_count: int,
    semantic_count: int,
    duplicate_count: int,
    previous_ids: set[str],
    final: list[MediaRetrievalResult],
    fallback: str,
) -> None:
    logger.debug(
        "Campaign media retrieval diagnostics",
        extra={
            "raw_query": clean_text(query, max_length=300),
            "normalised_query": normalize_for_match(query)[:300],
            "language": "ar" if contains_arabic(query) else "en",
            "media_intent": intent.is_media_request,
            "explicit_visual_intent": intent.explicit_visual_intent,
            "informational_intent": intent.informational_intent,
            "media_request_type": intent.media_request_type,
            "quantity_intent": intent.quantity_intent,
            "requested_count": intent.requested_media_count,
            "explicit_product": intent.product,
            "requested_year": intent.requested_year,
            "approved_product": intent.approved_product,
            "approved_year": intent.approved_year,
            "year_mismatch": intent.year_mismatch,
            "explicit_colour": intent.colour,
            "explicit_view": intent.view,
            "explicit_group": intent.group,
            "gallery_mode": intent.gallery_mode,
            "client_slug": client_slug,
            "eligible_item_count": eligible_count,
            "exterior_candidate_count": sum(1 for result in final if image_matches_view(result.image, "exterior")),
            "interior_candidate_count": sum(1 for result in final if image_matches_view(result.image, "interior")),
            "exact_filter_candidate_count": exact_count,
            "semantic_candidate_count": semantic_count,
            "merged_candidate_count": eligible_count,
            "duplicate_count_removed": duplicate_count,
            "previous_ids_excluded": len(previous_ids),
            "final_item_ids": [str(result.image.id) for result in final],
            "final_result_count": len(final),
            "final_colours": [sorted(canonical_colours_for_image(result.image)) for result in final],
            "final_groups": [result.image.suggested_group for result in final],
            "selected_fallback": fallback,
        },
    )


def retrieve_campaign_media(
    *,
    db: Session,
    client_slug: str,
    query: str,
    media_context: dict[str, Any] | None = None,
    avoid_image_ids: list[str] | None = None,
    limit: int | None = None,
    intent: MediaRequestIntent | None = None,
) -> list[MediaRetrievalResult]:
    intent = intent or parse_media_request_intent(query, maximum=settings.media_max_results_per_answer)
    if not media_retrieval_enabled(client_slug) or not intent.is_media_request:
        return []
    requested_count = min(
        limit or intent.requested_media_count,
        intent.requested_media_count,
        settings.media_max_results_per_answer,
    )
    context_text = media_context_terms(media_context)
    retrieval_text = clean_text(f"{context_text} {query}")
    avoid = {str(value) for value in avoid_image_ids or [] if value}
    base_statement = (
        select(MediaImage)
        .join(MediaCollection, MediaCollection.id == MediaImage.collection_id)
        .where(
            MediaImage.client_slug == client_slug,
            MediaCollection.client_slug == client_slug,
            MediaCollection.is_enabled.is_(True),
            MediaCollection.is_approved.is_(True),
            MediaImage.is_approved.is_(True),
            MediaImage.is_active.is_(True),
            MediaImage.is_duplicate.is_(False),
        )
    )
    images = list(db.execute(base_statement.limit(200)).scalars())
    if not images:
        return []
    images, duplicate_count = deduplicate_media_images(images)
    product = resolve_product_from_query(query, images) or intent.product
    approved_context = approved_media_context_from_images(images, product=product)
    approved_year = approved_context.get("approved_year")
    approved_product = approved_context.get("approved_product")
    intent = replace(
        intent,
        product=product,
        approved_product=approved_product,
        approved_year=approved_year,
        year_mismatch=bool(
            intent.requested_year
            and approved_year
            and int(intent.requested_year) != int(approved_year)
        ),
    )
    if intent.request_another_colour and isinstance(media_context, dict):
        previous_colour = extract_canonical_colour(str(media_context.get("last_colour") or ""))
        if previous_colour:
            images = [image for image in images if previous_colour not in canonical_colours_for_image(image)]
    vector_scores: dict[str, float] = {}
    try:
        embedding = create_embeddings([retrieval_text]).embeddings[0]
        vector_literal(embedding)
        if media_halfvec_search_supported(db):
            try:
                rows = indexed_media_vector_rows(
                    db=db,
                    client_slug=client_slug,
                    embedding=embedding,
                    limit=60,
                )
            except SQLAlchemyError as error:
                db.rollback()
                logger.warning(
                    "Campaign media halfvec vector retrieval failed; falling back to exact vector search",
                    extra={
                        "client_slug": client_slug,
                        "index_name": MEDIA_HALFVEC_DISTANCE_INDEX_NAME,
                        "embedding_dimension": media_embedding_dimension(),
                        "error_category": type(error).__name__,
                    },
                )
                rows = exact_media_vector_rows(
                    db=db,
                    base_statement=base_statement,
                    embedding=embedding,
                    limit=60,
                )
        else:
            rows = exact_media_vector_rows(
                db=db,
                base_statement=base_statement,
                embedding=embedding,
                limit=60,
            )
        images = list({str(image.id): image for image in [*images, *[row[0] for row in rows]]}.values())
        vector_scores = {
            str(image.id): max(-1.0, min(1.0, 1.0 - float(distance_value)))
            for image, distance_value in rows
            if distance_value is not None
        }
    except Exception as error:
        if isinstance(error, SQLAlchemyError):
            db.rollback()
        logger.info(
            "Campaign media vector retrieval skipped",
            extra={
                "client_slug": client_slug,
                "stage": "media_retrieval_embedding",
                "error_category": type(error).__name__,
            },
        )

    if intent.available_colours:
        ranked = representative_colour_results(
            images=images,
            intent=intent,
            vector_scores=vector_scores,
            retrieval_text=retrieval_text,
            avoid=avoid,
        )
        final = ranked[:requested_count]
        log_media_retrieval_diagnostics(
            query=query,
            client_slug=client_slug,
            intent=intent,
            eligible_count=len(images),
            exact_count=len(ranked),
            semantic_count=len(vector_scores),
            duplicate_count=duplicate_count,
            previous_ids=avoid,
            final=final,
            fallback="available_colours",
        )
        return final

    if intent.gallery_mode == "exterior" and not intent.view:
        ranked = exterior_diverse_gallery_results(
            images=images,
            intent=intent,
            vector_scores=vector_scores,
            retrieval_text=retrieval_text,
            avoid=avoid,
        )
        final = ranked[:requested_count]
        log_media_retrieval_diagnostics(
            query=query,
            client_slug=client_slug,
            intent=intent,
            eligible_count=len(images),
            exact_count=len(ranked),
            semantic_count=len(vector_scores),
            duplicate_count=duplicate_count,
            previous_ids=avoid,
            final=final,
            fallback="default_exterior_gallery",
        )
        return final

    strict_candidates, strict = strict_filter_candidates(
        images=images,
        intent=intent,
        product=product,
        avoid=avoid,
    )
    if strict:
        ranked = rank_media_candidates(
            images=strict_candidates,
            intent=intent,
            vector_scores=vector_scores,
            retrieval_text=retrieval_text,
        )
        final = ranked[:requested_count]
        log_media_retrieval_diagnostics(
            query=query,
            client_slug=client_slug,
            intent=intent,
            eligible_count=len(images),
            exact_count=len(strict_candidates),
            semantic_count=len(vector_scores),
            duplicate_count=duplicate_count,
            previous_ids=avoid,
            final=final,
            fallback="strict_filters",
        )
        return final

    ranked = rank_media_candidates(
        images=[image for image in images if str(image.id) not in avoid],
        intent=intent,
        vector_scores=vector_scores,
        retrieval_text=retrieval_text,
    )
    ranked = [
        result
        for result in ranked
        if result.score >= settings.media_min_similarity or result.direct_score >= 0.18
    ]
    final = ranked[:requested_count]
    log_media_retrieval_diagnostics(
        query=query,
        client_slug=client_slug,
        intent=intent,
        eligible_count=len(images),
        exact_count=0,
        semantic_count=len(vector_scores),
        duplicate_count=duplicate_count,
        previous_ids=avoid,
        final=final,
        fallback="hybrid",
    )
    return final


def no_media_result_message(question: str, intent: MediaRequestIntent | None = None) -> str:
    if intent and (intent.colour or intent.view):
        if contains_arabic(question):
            return "لا تتوفر حالياً صورة معتمدة مطابقة لهذا اللون أو النوع المطلوب."
        return "I don't currently have an approved image matching that colour or view."
    if contains_arabic(question):
        return "لا تتوفر حالياً صورة معتمدة مطابقة لهذا الطلب."
    if intent and (intent.colour or intent.view):
        if contains_arabic(question):
            return "لا تتوفر حالياً صورة معتمدة مطابقة لهذا اللون أو النوع المطلوب."
        return "I don't currently have an approved image matching that colour or view."
    return "I do not currently have an approved image matching that request."


def media_answer(
    results: list[MediaRetrievalResult],
    question: str,
    intent: MediaRequestIntent | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    intent = intent or parse_media_request_intent(question)
    if not results:
        return no_media_result_message(question, intent), []
    media = [result.to_media_item() for result in results]
    if intent.available_colours:
        colours = [str(item.get("colour") or "").strip() for item in media if item.get("colour")]
        if contains_arabic(question):
            labels = [COLOUR_LABELS_AR.get(colour, colour) for colour in colours]
            return "الألوان المعتمدة المتوفرة حالياً: " + "، ".join(labels) + ".", media
        return "The approved available colours are: " + ", ".join(colours) + ".", media
    if contains_arabic(question):
        answer = "هذه صور معتمدة مرتبطة بطلبك." if len(media) > 1 else "هذه صورة معتمدة مرتبطة بطلبك."
    else:
        answer = "Here are approved images related to your request." if len(media) > 1 else "Here is an approved image related to your request."
    return answer, media


def media_answer(
    results: list[MediaRetrievalResult],
    question: str,
    intent: MediaRequestIntent | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    intent = intent or parse_media_request_intent(question)
    if not results:
        return no_media_result_message(question, intent), []
    media = [result.to_media_item() for result in results]
    approved_context = approved_media_context_from_images(
        [result.image for result in results],
        product=intent.product,
    )
    approved_year = intent.approved_year or approved_context.get("approved_year")
    approved_product = intent.approved_product or approved_context.get("approved_product")
    if intent.requested_year and approved_year and int(intent.requested_year) != int(approved_year):
        return (
            format_year_mismatch_message(
                question=question,
                requested_year=int(intent.requested_year),
                approved_year=int(approved_year),
                approved_product=approved_product,
            ),
            media,
        )
    if intent.available_colours and intent.informational_intent:
        colours = [str(item.get("colour") or "").strip() for item in media if item.get("colour")]
        if contains_arabic(question):
            labels = [COLOUR_LABELS_AR.get(colour, colour) for colour in colours]
            return (
                "\u0627\u0644\u0623\u0644\u0648\u0627\u0646 "
                "\u0627\u0644\u0645\u0639\u062a\u0645\u062f\u0629 "
                "\u0627\u0644\u0645\u062a\u0648\u0641\u0631\u0629 "
                "\u062d\u0627\u0644\u064a\u0627\u064b: "
                + "\u060c ".join(labels)
                + "."
            ), media
        return "The approved available colours are: " + ", ".join(colours) + ".", media
    return "", media


def media_context_from_results(results: list[MediaRetrievalResult]) -> dict[str, Any]:
    if not results:
        return {}
    first = results[0].image
    return {
        "last_media_collection_id": str(first.collection_id),
        "last_media_group": first.suggested_group,
        "last_product": first.detected_product_type or first.dominant_subject,
        "last_category": first.detected_category,
        "last_model": first.detected_model,
        "last_colour": first.detected_colour,
        "last_image_type": first.detected_image_type,
        "last_view": first.detected_view,
        "last_image_result_ids": [str(result.image.id) for result in results],
    }


def export_approved_media_catalog(client_slug: str) -> dict[str, Any]:
    with SessionLocal() as db:
        collections = list(
            db.execute(
                select(MediaCollection)
                .where(
                    MediaCollection.client_slug == client_slug,
                    MediaCollection.is_enabled.is_(True),
                    MediaCollection.is_approved.is_(True),
                )
                .order_by(MediaCollection.created_at.asc())
            ).scalars()
        )
        return {
            "client_slug": client_slug,
            "exported_at": utc_now().isoformat(),
            "collections": [
                {
                    **serialize_collection(collection),
                    "images": [
                        public_media_payload(image)
                        | {
                            "id": str(image.id),
                            "metadata": {
                                "detected_category": image.detected_category,
                                "detected_product_type": image.detected_product_type,
                                "detected_colour": image.detected_colour,
                                "detected_view": image.detected_view,
                                "detected_image_type": image.detected_image_type,
                                "suggested_group": image.suggested_group,
                            },
                        }
                        for image in collection.images
                        if image.is_approved and image.is_active and not image.is_duplicate
                    ],
                }
                for collection in collections
            ],
        }


def write_media_export(client_slug: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(export_approved_media_catalog(client_slug), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
