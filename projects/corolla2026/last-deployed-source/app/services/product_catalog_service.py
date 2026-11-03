from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from urllib.parse import unquote, urlparse
from typing import Any

from app.services.client_config_service import PROJECT_ROOT, client_scraped_dir
from app.services.product_image_service import (
    is_placeholder_image_reference,
    known_non_product_image_hashes,
    validate_product_image,
)


PRODUCT_CATALOG_FILENAME = "product_catalog.json"
PRODUCT_SOURCE_TYPE = "website_product_catalog"

PRICE_QUERY_PATTERN = re.compile(
    r"\b(price|prices|pricing|package|packages|cost|costs|how much|range|"
    r"cheapest|least expensive|lowest|most expensive|highest|products under|"
    r"under\s+\d+|show me products|show me some|show me furniture|"
    r"see (?:your|the) products|list products)\b|"
    r"(كم سعر|ما سعر|سعر|أسعار|اسعار|نطاق الأسعار|نطاق الاسعار)",
    flags=re.IGNORECASE,
)

PRODUCT_IMAGE_QUERY_PATTERN = re.compile(
    r"\b(show|display|see|view|image|photo|picture)\b.*\b(product|chair|sofa|bed|table|desk|cabinet|recliner|furniture|ottoman)\b",
    flags=re.IGNORECASE,
)

PRODUCT_BROWSE_QUERY_PATTERN = re.compile(
    r"\b(?:show me|let me see|can i see|display|browse)\s+(?:some\s+)?"
    r"(?:of\s+the\s+)?(?:furniture|products?|chairs?|recliners?|sofas?|beds?|"
    r"tables?|bedroom furniture)\b",
    flags=re.IGNORECASE,
)

PRODUCT_OPTION_QUERY_PATTERN = re.compile(
    r"\b(are there|do you have|available|options?|any)\b",
    flags=re.IGNORECASE,
)

PRODUCT_NOUN_PATTERN = re.compile(
    r"\b(product|products|catalog|item|items|model|models|sku|style|"
    r"furniture|chair|chairs|sofa|sofas|recliner|recliners|bed|beds|"
    r"table|tables|desk|desks|cabinet|cabinets|ottoman|ottomans|"
    r"dresser|dressers|wardrobe|wardrobes|lamp|lamps)\b",
    flags=re.IGNORECASE,
)

DOCUMENT_PRICING_PATTERN = re.compile(
    r"\b(price list|pricing list|rate|rates|tariff|fee|fees|package|"
    r"packages|plan|plans|subscription|contract|invoice|invoiced|"
    r"validity|bonus|quantity|qty|per\s+\d+|per thousand|usage)\b",
    flags=re.IGNORECASE,
)

PRODUCT_CATEGORY_HINTS = {
    "ottoman",
    "ottomans",
    "sofa",
    "sofas",
    "recliner",
    "recliners",
    "chair",
    "chairs",
    "bed",
    "beds",
    "table",
    "tables",
    "dresser",
    "dressers",
    "wardrobe",
    "wardrobes",
    "lamp",
    "lamps",
    "cabinet",
    "cabinets",
    "dining",
    "sectional",
    "furniture",
}

CURRENCY_ALIASES = {
    "AED": ("AED", "د.إ", "د.إ"),
    "JOD": ("JOD", "JD", "د.أ", "د.ا", "د.إ"),
    "USD": ("USD", "$"),
    "SAR": ("SAR", "ر.س"),
}

STOPWORDS = {
    "what",
    "is",
    "the",
    "a",
    "an",
    "of",
    "for",
    "in",
    "available",
    "catalog",
    "product",
    "products",
    "price",
    "prices",
    "pricing",
    "cost",
    "costs",
    "how",
    "much",
    "range",
    "show",
    "me",
    "some",
    "list",
    "please",
    "image",
    "photo",
    "picture",
    "chair",
    "chairs",
    "piece",
    "pieces",
    "furniture",
    "option",
    "options",
    "it",
    "that",
    "this",
}

GENERIC_PRODUCT_NAMES = {
    "shop",
    "buy",
    "view",
    "add to cart",
    "تسوق",
    "غير متوفر للبيع",
    "اضافة الى السلة",
    "إضافة إلى السلة",
}


UI_NAME_BLOCKLIST = {
    *GENERIC_PRODUCT_NAMES,
    "add to compare",
    "add to compare list",
    "compare",
    "add to wishlist",
    "add to wish list",
    "skip to content",
    "quick view",
    "view details",
    "sale",
    "new",
    "special price",
    "regular price",
    "in stock",
    "out of stock",
    "notify when available",
    "change",
    "my wishlist",
    "my cart",
    "menu",
    "home",
    "main product photo",
}

UI_CATEGORY_BLOCKLIST = {
    "checkout",
    "checkout as a new customer",
    "customer login",
    "login",
    "menu",
    "my cart",
    "my wishlist",
    "shopping cart",
    "skip to content",
}

PERCENT_ONLY_PATTERN = re.compile(r"^\s*\d{1,3}\s*%\s*$")
ACTION_PHRASE_PATTERN = re.compile(
    r"\b(?:add to cart|add to wishlist|add to wish list|notify when available|"
    r"out of stock|in stock|quick view|add to compare(?: list)?|compare)\b.*$",
    flags=re.IGNORECASE,
)
INVALID_IMAGE_PATTERN = re.compile(
    r"(?:plp-loader|loader|loading|placeholder|spinner|preload|skeleton|blank|sprite|/flags/|flag-img|"
    r"visa|mastercard|payment|paypal|mada|applepay|logo/stores)",
    flags=re.IGNORECASE,
)
PRODUCT_URL_SUFFIX_WORDS = {
    "jordan",
    "jo",
    "en",
    "living",
    "rooms",
    "room",
    "home",
    "furniture",
    "accessories",
    "bedrooms",
    "bedroom",
    "dining",
    "office",
}

NAVIGATION_URL_PATTERN = re.compile(
    r"/(?:sitemap|catalogsearch|search|customer|wishlist|compare|cart|checkout|sendfriend)(?:/|\.|$)",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ProductSearchResult:
    item: dict[str, Any]
    score: float
    reason: str
    matched_text: str

    def media_item(self) -> dict[str, Any] | None:
        url = best_product_image_url(self.item)
        if not url:
            return None

        image_url = clean_text(self.item.get("image_url"))
        local_url = clean_text(self.item.get("local_image_url"))
        description = clean_text(self.item.get("description"))
        if not description:
            description = (
                f"{self.item.get('product_name')} from the available product catalog."
            )

        return {
            "type": "image",
            "url": url,
            "label": self.item.get("product_name") or "Product image",
            "description": description,
            "fallback_url": image_url if local_url and image_url and image_url != url else "",
            "product_url": clean_text(self.item.get("product_url")),
            "current_price": clean_text(self.item.get("current_price")),
            "old_price": clean_text(self.item.get("old_price")),
            "source": "product_catalog",
        }


def product_catalog_path(client_slug: str) -> Path:
    return client_scraped_dir(client_slug) / PRODUCT_CATALOG_FILENAME


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_text(value: object) -> str:
    value_text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^0-9A-Za-z\u0600-\u06FF]+", " ", value_text).strip()


def tokens_for(value: object) -> list[str]:
    normalized = normalize_text(value)
    tokens: list[str] = []
    for token in normalized.split():
        if len(token) <= 1 or token in STOPWORDS:
            continue
        tokens.append(token)
        if len(token) > 3 and token.endswith("s"):
            singular = token[:-1]
            if singular not in STOPWORDS:
                tokens.append(singular)
    return tokens


def detect_currency(value: object) -> str:
    text = str(value or "").upper()
    original = str(value or "")

    for code, aliases in CURRENCY_ALIASES.items():
        if any(alias.upper() in text or alias in original for alias in aliases):
            return code

    if "$" in original:
        return "USD"

    return ""


def parse_price_number(value: object) -> float | None:
    text = str(value or "")
    match = re.search(r"\d[\d,]*(?:\.\d+)?", text)
    if not match:
        return None

    numeric = match.group(0).replace(",", "")
    try:
        return float(numeric)
    except ValueError:
        return None


def local_static_file_exists(url: object) -> bool:
    text = clean_text(url)
    if not text.startswith("/static/"):
        return False
    path = PROJECT_ROOT / "app" / "static" / text.removeprefix("/static/")
    return path.exists()


def is_invalid_product_image_url(url: object) -> bool:
    text = clean_text(url)
    return bool(
        text
        and (
            INVALID_IMAGE_PATTERN.search(text)
            or is_placeholder_image_reference(text)
        )
    )


def best_product_image_url(item: dict[str, Any]) -> str:
    local_url = clean_text(item.get("local_image_url"))
    image_url = clean_text(item.get("image_url"))
    if "image_local_valid" in item or "image_remote_valid" in item:
        validation = {
            "local_valid": bool(item.get("image_local_valid")),
            "remote_valid": bool(item.get("image_remote_valid")),
        }
    else:
        validation = validate_product_image(
            client_slug=clean_text(item.get("client_slug")) or "jormall",
            item=item,
        )

    if local_url and validation.get("local_valid"):
        return local_url
    if image_url and validation.get("remote_valid"):
        return image_url
    return ""


def extract_price_candidates(value: object) -> list[str]:
    text = str(value or "")
    currency_terms = r"(?:AED|JOD|JD|USD|SAR|د\.أ|د\.إ|د\.ا|ر\.س|\$)"
    patterns = [
        rf"\d[\d,]*(?:\.\d+)?\s*{currency_terms}",
        rf"{currency_terms}\s*\d[\d,]*(?:\.\d+)?",
        r"\b\d{1,3}(?:[,.]\d{3})+(?:\.\d+)?\b",
    ]
    candidates: list[str] = []

    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            candidate = clean_text(match.group(0))
            if candidate and candidate not in candidates:
                candidates.append(candidate)

    return candidates


def split_price_candidates(*values: object) -> list[str]:
    candidates: list[str] = []
    for value in values:
        for candidate in extract_price_candidates(value):
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


def format_price(value: object, currency: str = "") -> str:
    text = clean_text(value)
    if not text:
        return ""

    if currency and currency.upper() not in text.upper() and detect_currency(text) != currency:
        return f"{currency} {text}"

    return text


def build_product_search_text(item: dict[str, Any]) -> str:
    fields = [
        item.get("product_name"),
        item.get("category"),
        item.get("current_price"),
        item.get("old_price"),
        item.get("price_text"),
        item.get("discount_text"),
        item.get("availability"),
        item.get("description"),
        item.get("breadcrumbs"),
        item.get("product_url"),
        item.get("raw_text"),
    ]
    return clean_text(" ".join(str(field or "") for field in fields))


def is_polluted_product_name(value: object) -> bool:
    name = clean_text(value)
    normalized = normalize_text(name)
    if not name:
        return True
    if len(name) > 120:
        return True
    if PERCENT_ONLY_PATTERN.match(name):
        return True
    if re.fullmatch(r"(?:new|sale|special price|regular price)\s+\d{1,3}\s*%", name, flags=re.IGNORECASE):
        return True
    if normalized in {normalize_text(term) for term in UI_NAME_BLOCKLIST}:
        return True
    if any(
        normalize_text(term) in normalized
        for term in ["add to compare", "skip to content", "add to cart", "add to wishlist"]
    ):
        return True
    if len(name) <= 2:
        return True
    if re.fullmatch(r"[\W_]+", name):
        return True
    return False


def normalized_product_category(
    *,
    category: object,
    breadcrumbs: object,
    product_name: object,
) -> str:
    value = clean_text(category)
    normalized = normalize_text(value)
    normalized_name = normalize_text(product_name)
    category_is_ui = (
        not value
        or normalized in {normalize_text(term) for term in UI_CATEGORY_BLOCKLIST}
        or any(
            phrase in normalized
            for phrase in ("checkout as", "customer login", "skip to content")
        )
        or (
            normalized_name
            and (normalized_name in normalized or normalized in normalized_name)
        )
    )
    if not category_is_ui:
        return value

    breadcrumb_text = clean_text(breadcrumbs)
    breadcrumb_text = re.sub(r"^(?:home\s+)+", "", breadcrumb_text, flags=re.IGNORECASE)
    normalized_breadcrumb = normalize_text(breadcrumb_text)
    if (
        breadcrumb_text
        and normalized_breadcrumb != normalized_name
        and normalized_name not in normalized_breadcrumb
    ):
        return breadcrumb_text
    return "Uncategorized"


def title_case_product_name(value: str) -> str:
    words = clean_text(value).split()
    small_words = {"and", "or", "with", "for", "of", "the", "a", "an"}
    titled: list[str] = []
    for index, word in enumerate(words):
        lowered = word.lower()
        if index > 0 and lowered in small_words:
            titled.append(lowered)
        elif any(character.isdigit() for character in word):
            titled.append(word.upper() if len(word) <= 4 else word.capitalize())
        else:
            titled.append(lowered[:1].upper() + lowered[1:])
    return clean_text(" ".join(titled))


def product_name_from_url(product_url: object) -> str:
    url = clean_text(product_url)
    if not url:
        return ""
    path = unquote(urlparse(url).path)
    if re.search(r"/(?:sendfriend|wishlist|compare|cart|checkout|customer)/", path, flags=re.IGNORECASE):
        return ""
    slug = Path(path).stem
    slug = re.sub(r"[-_]+", " ", slug)
    words = [
        word
        for word in slug.split()
        if word.lower() not in PRODUCT_URL_SUFFIX_WORDS
    ]
    if len(words) < 2:
        return ""
    return title_case_product_name(" ".join(words))


def product_name_from_raw_text(raw_text: object) -> str:
    text = clean_text(raw_text)
    if not text:
        return ""
    first_price = re.search(
        r"(?:AED|JOD|JD|USD|SAR|\$)?\s*\d[\d,]*(?:\.\d+)?\s*(?:AED|JOD|JD|USD|SAR|\$)?",
        text,
        flags=re.IGNORECASE,
    )
    if first_price:
        text = text[: first_price.start()]
    text = re.sub(r"^\s*\d{1,3}\s*%\s*", "", text)
    text = re.sub(r"^\s*(special price|regular price|sale|new)\s+", "", text, flags=re.IGNORECASE)
    text = ACTION_PHRASE_PATTERN.sub("", text)
    text = clean_text(text.strip(" -:|"))
    if len(text) > 120:
        return ""
    if is_polluted_product_name(text):
        return ""
    return title_case_product_name(text)


def repair_product_name(item: dict[str, Any], product_name: str) -> str:
    url_name = product_name_from_url(item.get("product_url")) or product_name_from_url(
        item.get("page_url")
    )
    supporting_text = normalize_text(
        f"{item.get('description') or ''} {item.get('raw_text') or ''}"
    )
    if url_name:
        url_tokens = {
            token
            for token in canonical_product_tokens(url_name)
            if token not in {"and", "for", "from", "the", "with"}
        }
        supporting_tokens = set(canonical_product_tokens(supporting_text))
        current_tokens = canonical_product_tokens(product_name)
        identity_conflict = bool(
            current_tokens
            and url_tokens
            and current_tokens[0] not in url_tokens
        )
        if (
            identity_conflict
            and (
                normalize_text(url_name) in supporting_text
                or (
                    len(url_tokens) >= 2
                    and len(url_tokens & supporting_tokens) / len(url_tokens) >= 0.8
                )
            )
        ):
            return title_case_product_name(url_name)

    candidates = [
        product_name,
        clean_text(item.get("image_alt") or item.get("alt_text")),
        clean_text(item.get("title_text")),
        url_name,
        product_name_from_raw_text(item.get("raw_text")),
    ]
    for candidate in candidates:
        if candidate and not is_polluted_product_name(candidate):
            return title_case_product_name(candidate)
    return ""


def product_id_for(item: dict[str, Any]) -> str:
    key = "|".join(
        [
            str(item.get("product_url") or ""),
            str(item.get("product_name") or ""),
            str(item.get("current_price") or ""),
            str(item.get("page_url") or ""),
        ]
    )
    return sha1(key.encode("utf-8", errors="ignore")).hexdigest()[:16]


def is_navigation_url(url: object) -> bool:
    return bool(NAVIGATION_URL_PATTERN.search(clean_text(urlparse(clean_text(url)).path)))


def is_product_detail_url(url: object) -> bool:
    path = clean_text(urlparse(clean_text(url)).path)
    return bool(path.lower().endswith(".html") and not is_navigation_url(url))


def canonical_product_url(item: dict[str, Any]) -> str:
    candidates = [
        clean_text(item.get("product_url")).split("#", 1)[0],
        clean_text(item.get("page_url")).split("#", 1)[0],
    ]
    for candidate in candidates:
        if is_product_detail_url(candidate):
            return candidate
    for candidate in candidates:
        if candidate and not is_navigation_url(candidate):
            return candidate
    return candidates[0] if candidates else ""


def product_key_for_dedupe(item: dict[str, Any]) -> str:
    page_url = clean_text(item.get("page_url")).split("#", 1)[0]
    product_url = clean_text(item.get("product_url")).split("#", 1)[0]
    if product_url and not is_navigation_url(product_url):
        return product_url
    if is_product_detail_url(page_url):
        return page_url
    return f"{normalize_text(item.get('product_name'))}|{item.get('current_price')}"


def normalize_product_item(
    *,
    client_slug: str,
    item: dict[str, Any],
    known_invalid_hashes: set[str] | None = None,
) -> dict[str, Any] | None:
    product_name = repair_product_name(item, clean_text(item.get("product_name")))
    current_price = clean_text(item.get("current_price"))
    price_text = clean_text(item.get("price_text"))
    raw_text = clean_text(item.get("raw_text"))
    page_url = clean_text(item.get("page_url"))
    product_url = canonical_product_url(item)
    breadcrumbs = clean_text(item.get("breadcrumbs"))
    if is_product_detail_url(page_url):
        category = "Uncategorized"
        if product_url != page_url:
            breadcrumbs = ""
    else:
        category = normalized_product_category(
            category=item.get("category"),
            breadcrumbs=breadcrumbs,
            product_name=product_name,
        )

    if is_polluted_product_name(product_name):
        return None

    price_candidate_count = len(split_price_candidates(current_price, price_text, raw_text))
    if is_navigation_url(product_url) and not clean_text(item.get("description")) and price_candidate_count > 3:
        return None

    preferred_candidates = split_price_candidates(current_price, price_text, raw_text)

    current_price_candidates = extract_price_candidates(current_price)
    if len(current_price_candidates) > 1:
        current_price = current_price_candidates[0]
    elif len(current_price) > 80 or len(current_price.split()) > 8:
        current_price = preferred_candidates[0] if preferred_candidates else current_price
    elif not current_price and preferred_candidates:
        current_price = preferred_candidates[0]

    old_price = clean_text(item.get("old_price"))
    if preferred_candidates and (
        not old_price or old_price == current_price or old_price not in preferred_candidates
    ):
        old_price = (
            preferred_candidates[1]
            if len(preferred_candidates) > 1
            else old_price
        )
    elif len(old_price) > 80 or not old_price:
        old_price = (
            preferred_candidates[1]
            if len(preferred_candidates) > 1
            else old_price
        )

    if not product_name or not (current_price or price_text or raw_text):
        return None

    currency = clean_text(item.get("currency")) or detect_currency(
        f"{current_price} {price_text} {raw_text}"
    )
    image_url = clean_text(item.get("image_url"))
    local_image_url = clean_text(item.get("local_image_url"))
    image_probe = {
        **item,
        "client_slug": client_slug,
        "image_url": image_url,
        "local_image_url": local_image_url,
    }
    image_validation = validate_product_image(
        client_slug=client_slug,
        item=image_probe,
        known_invalid_hashes=known_invalid_hashes,
    )
    if not image_validation.get("remote_valid"):
        image_url = ""
    if not image_validation.get("local_valid"):
        local_image_url = ""

    normalized = {
        "client_slug": client_slug,
        "source_type": PRODUCT_SOURCE_TYPE,
        "product_id": "",
        "product_name": product_name,
        "category": category,
        "current_price": current_price or price_text,
        "old_price": old_price,
        "currency": currency,
        "price_text": price_text or current_price,
        "numeric_current_price": parse_price_number(current_price),
        "numeric_old_price": parse_price_number(old_price),
        "discount_text": clean_text(item.get("discount_text")),
        "product_url": product_url,
        "image_url": image_url,
        "local_image_url": local_image_url,
        "image_alt": clean_text(item.get("image_alt") or item.get("alt_text")),
        "image_width": int(image_validation.get("width") or item.get("image_width") or item.get("width") or 0),
        "image_height": int(image_validation.get("height") or item.get("image_height") or item.get("height") or 0),
        "image_source_field": clean_text(item.get("image_source_field")),
        "image_local_valid": bool(local_image_url),
        "image_remote_valid": bool(image_url),
        "image_validation_reason": clean_text(image_validation.get("reason")),
        "video_url": clean_text(item.get("video_url")),
        "availability": clean_text(item.get("availability")),
        "description": clean_text(item.get("description")),
        "page_url": page_url,
        "breadcrumbs": breadcrumbs,
        "raw_text": raw_text,
        "search_text": "",
    }
    normalized["product_id"] = product_id_for(normalized)
    normalized["search_text"] = build_product_search_text(normalized)
    return normalized


def dedupe_products(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}

    for item in products:
        key = product_key_for_dedupe(item)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = item
            continue

        existing_quality = int(bool(best_product_image_url(existing))) + int(
            existing.get("product_name") != existing.get("category")
        ) + int(existing.get("numeric_current_price") is not None) + int(
            bool(clean_text(existing.get("description")))
        )
        item_quality = int(bool(best_product_image_url(item))) + int(
            item.get("product_name") != item.get("category")
        ) + int(item.get("numeric_current_price") is not None) + int(
            bool(clean_text(item.get("description")))
        )
        if item_quality > existing_quality:
            by_key[key] = item

    return list(by_key.values())


def save_product_catalog(
    *,
    client_slug: str,
    source_url: str,
    products: list[dict[str, Any]],
) -> tuple[Path, dict[str, Any]]:
    path = product_catalog_path(client_slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    previous_products: list[dict[str, Any]] = []
    previous_payload: dict[str, Any] = {}
    if path.exists():
        try:
            loaded_previous_payload = json.loads(path.read_text(encoding="utf-8"))
            previous_payload = (
                loaded_previous_payload
                if isinstance(loaded_previous_payload, dict)
                else {}
            )
            previous_rows = (
                previous_payload.get("products", [])
                if previous_payload
                else loaded_previous_payload
            )
            if isinstance(previous_rows, list):
                previous_products = [
                    item for item in previous_rows if isinstance(item, dict)
                ]
        except (OSError, ValueError):
            previous_products = []

    candidate_products = [*products, *previous_products]
    previous_raw_total = int(previous_payload.get("total_raw_products") or 0)
    incremental_update = bool(
        previous_products
        and len(products) < max(5, len(previous_products) // 4)
    )
    reported_raw_total = (
        max(previous_raw_total, len(candidate_products))
        if incremental_update
        else len(products)
    )
    reported_scraped_total = (
        int(previous_payload.get("total_scraped_products") or 0)
        if incremental_update
        else len(products)
    )
    invalid_hashes = known_non_product_image_hashes(client_slug)
    normalization_rows = [
        (
            item,
            normalize_product_item(
                client_slug=client_slug,
                item=item,
                known_invalid_hashes=invalid_hashes,
            ),
        )
        for item in candidate_products
    ]
    normalized_products = [normalized for _item, normalized in normalization_rows if normalized]
    normalized_products = dedupe_products(normalized_products)
    sample_removed_products = [
        {
            "product_name": clean_text(item.get("product_name")),
            "product_url": clean_text(item.get("product_url")),
            "raw_text": clean_text(item.get("raw_text"))[:300],
        }
        for item, normalized in normalization_rows
        if normalized is None
    ][:10]
    removed_polluted_names = sum(
        1
        for item, normalized in normalization_rows
        if normalized is None
        and is_polluted_product_name(
            repair_product_name(item, clean_text(item.get("product_name")))
        )
    )
    invalid_product_images_removed = sum(
        1
        for item, normalized in normalization_rows
        if normalized is not None
        and bool(item.get("local_image_url") or item.get("image_url"))
        and not bool(normalized.get("local_image_url") or normalized.get("image_url"))
    )
    placeholders_removed = sum(
        1
        for item, normalized in normalization_rows
        if normalized is not None
        and bool(item.get("local_image_url") or item.get("image_url"))
        and is_placeholder_image_reference(
            item.get("image_url"),
            item.get("local_image_url"),
            item.get("image_alt"),
            normalized.get("image_validation_reason"),
        )
    )
    categories = sorted(
        {
            str(item.get("category") or "").strip()
            for item in normalized_products
            if str(item.get("category") or "").strip()
        }
    )
    currencies = sorted(
        {
            str(item.get("currency") or "").strip()
            for item in normalized_products
            if str(item.get("currency") or "").strip()
        }
    )
    payload = {
        "client_slug": client_slug,
        "source_type": PRODUCT_SOURCE_TYPE,
        "source_url": source_url,
        "generated_at": utc_now_iso(),
        "total_raw_products": reported_raw_total,
        "total_scraped_products": reported_scraped_total,
        "total_previous_products_considered": len(previous_products),
        "total_products": len(normalized_products),
        "total_clean_products": len(normalized_products),
        "removed_polluted_products": max(
            int(previous_payload.get("removed_polluted_products") or 0)
            if incremental_update
            else 0,
            reported_raw_total - len(normalized_products),
        ),
        "removed_polluted_names": removed_polluted_names,
        "invalid_product_images_removed": invalid_product_images_removed,
        "placeholders_removed": placeholders_removed,
        "products_with_valid_local_images": sum(bool(item.get("local_image_url")) for item in normalized_products),
        "products_with_valid_remote_only_images": sum(
            bool(item.get("image_url")) and not bool(item.get("local_image_url"))
            for item in normalized_products
        ),
        "products_without_images": sum(
            not bool(item.get("image_url") or item.get("local_image_url"))
            for item in normalized_products
        ),
        "sample_removed_products": sample_removed_products,
        "categories": categories,
        "currencies": currencies,
        "products": normalized_products,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path, payload


def load_product_catalog(client_slug: str) -> dict[str, Any]:
    path = product_catalog_path(client_slug)
    if not path.exists():
        return {
            "client_slug": client_slug,
            "source_type": PRODUCT_SOURCE_TYPE,
            "total_products": 0,
            "categories": [],
            "currencies": [],
            "products": [],
            "path": path.as_posix(),
            "exists": False,
        }

    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        products = payload
        payload = {
            "client_slug": client_slug,
            "source_type": PRODUCT_SOURCE_TYPE,
            "products": products,
        }

    raw_products = payload.get("products") or []
    invalid_hashes = known_non_product_image_hashes(client_slug)
    products = [
        normalized
        for item in raw_products
        if isinstance(item, dict)
        if (
            normalized := normalize_product_item(
                client_slug=client_slug,
                item=item,
                known_invalid_hashes=invalid_hashes,
            )
        )
    ]
    products = dedupe_products(products)
    sample_removed_products = payload.get("sample_removed_products") or [
        {
            "product_name": clean_text(item.get("product_name")),
            "product_url": clean_text(item.get("product_url")),
            "raw_text": clean_text(item.get("raw_text"))[:300],
        }
        for item in raw_products
        if isinstance(item, dict)
        and normalize_product_item(
            client_slug=client_slug,
            item=item,
            known_invalid_hashes=invalid_hashes,
        ) is None
    ][:10]
    payload["products"] = products
    payload["total_raw_products"] = int(payload.get("total_raw_products") or len(raw_products))
    payload["total_products"] = len(products)
    payload["total_clean_products"] = len(products)
    payload["removed_polluted_products"] = int(
        payload.get("removed_polluted_products")
        or max(0, len(raw_products) - len(products))
    )
    payload["sample_removed_products"] = sample_removed_products
    payload["removed_polluted_names"] = int(payload.get("removed_polluted_names") or 0)
    payload["invalid_product_images_removed"] = int(payload.get("invalid_product_images_removed") or 0)
    payload["placeholders_removed"] = int(payload.get("placeholders_removed") or 0)
    payload["products_with_valid_local_images"] = sum(bool(item.get("local_image_url")) for item in products)
    payload["products_with_valid_remote_only_images"] = sum(
        bool(item.get("image_url")) and not bool(item.get("local_image_url"))
        for item in products
    )
    payload["products_without_images"] = sum(
        not bool(item.get("image_url") or item.get("local_image_url"))
        for item in products
    )
    payload["path"] = path.as_posix()
    payload["exists"] = True
    return payload


def looks_like_product_query(query: str) -> bool:
    cleaned_tokens = set(tokens_for(cleaned_product_query(query or "")))
    return bool(
        PRICE_QUERY_PATTERN.search(query or "")
        or PRODUCT_IMAGE_QUERY_PATTERN.search(query or "")
        or PRODUCT_BROWSE_QUERY_PATTERN.search(query or "")
        or looks_like_product_image_followup(query or "")
        or looks_like_product_link_followup(query or "")
        or looks_like_budget_category_query(query or "")
        or (
            PRODUCT_OPTION_QUERY_PATTERN.search(query or "")
            and bool(cleaned_tokens & PRODUCT_CATEGORY_HINTS)
        )
    )


def product_catalog_has_products(client_slug: str) -> bool:
    catalog = load_product_catalog(client_slug)
    return bool(catalog.get("products") or [])


def looks_like_document_pricing_query(query: str) -> bool:
    normalized = query or ""
    if not PRICE_QUERY_PATTERN.search(normalized):
        return False

    if PRODUCT_IMAGE_QUERY_PATTERN.search(normalized) or PRODUCT_BROWSE_QUERY_PATTERN.search(normalized):
        return False

    if PRODUCT_NOUN_PATTERN.search(normalized):
        return False

    return bool(
        DOCUMENT_PRICING_PATTERN.search(normalized)
        or re.search(r"\b\d[\d,]*(?:\.\d+)?\b", normalized)
        or re.search(r"\b(?:jod|jd|usd|aed|sar)\b", normalized, flags=re.IGNORECASE)
    )


def should_return_product_no_match(
    *,
    client_slug: str,
    query: str,
) -> bool:
    if not looks_like_product_query(query):
        return bool(
            PRODUCT_NOUN_PATTERN.search(query or "")
            and re.search(
                r"\b(show|find|list|under|over|below|above|cheapest|"
                r"lowest|most expensive|highest|price|cost|how much)\b",
                query or "",
                flags=re.IGNORECASE,
            )
        )

    if looks_like_document_pricing_query(query):
        return False

    if (
        PRODUCT_IMAGE_QUERY_PATTERN.search(query or "")
        or PRODUCT_BROWSE_QUERY_PATTERN.search(query or "")
        or looks_like_product_image_followup(query or "")
        or looks_like_product_link_followup(query or "")
        or looks_like_cheapest_query(query or "")
        or looks_like_most_expensive_query(query or "")
        or PRODUCT_NOUN_PATTERN.search(query or "")
    ):
        return True

    cleaned_tokens = tokens_for(cleaned_product_query(query or ""))
    return product_catalog_has_products(client_slug) and len(cleaned_tokens) >= 2


def cleaned_product_query(query: str) -> str:
    cleaned = re.sub(
        r"\b(what|is|are|there|do|you|have|any|the|available|catalog|price|prices|pricing|cost|costs|"
        r"how much|range|of|for|show me|show|some|list|products|product|"
        r"cheapest|least expensive|lowest|most expensive|highest|image|photo|picture|"
        r"furniture|piece|pieces|options|option|it|that|this)\b",
        " ",
        query,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"(كم سعر|ما سعر|سعر|أسعار|اسعار|نطاق الأسعار|نطاق الاسعار)", " ", cleaned)
    return clean_text(cleaned).strip(" ?!.،؛")


PRODUCT_SEARCH_FILLERS = {
    "available",
    "catalog",
    "company",
    "give",
    "item",
    "items",
    "option",
    "options",
    "please",
    "product",
    "products",
}


def canonical_product_tokens(value: object) -> list[str]:
    tokens: list[str] = []
    for token in normalize_text(value).split():
        if len(token) <= 1 or token in PRODUCT_SEARCH_FILLERS:
            continue
        if len(token) > 4 and token.endswith("ies"):
            token = f"{token[:-3]}y"
        elif len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
            token = token[:-1]
        tokens.append(token)
    return tokens


def product_score(item: dict[str, Any], query: str) -> ProductSearchResult:
    product_name = str(item.get("product_name") or "")
    category = str(item.get("category") or "")
    search_text = str(item.get("search_text") or build_product_search_text(item))
    normalized_query = normalize_text(query)
    normalized_name = normalize_text(product_name)
    normalized_search = normalize_text(search_text)
    query_tokens = set(canonical_product_tokens(query))
    searchable_tokens = set(canonical_product_tokens(search_text))
    name_tokens = set(canonical_product_tokens(product_name))
    category_tokens = set(canonical_product_tokens(category))
    score = 0.0
    reasons: list[str] = []

    if normalized_query and normalized_query == normalized_name:
        score = 1000
        reasons.append("exact normalized product name match")
    elif normalized_query and normalized_query in normalized_name:
        score = 850
        reasons.append("full query phrase contained in product name")
    elif query_tokens and query_tokens.issubset(name_tokens):
        score = 700
        reasons.append("all important query tokens matched product name")

    if query_tokens:
        overlap = query_tokens & searchable_tokens
        name_overlap = query_tokens & name_tokens
        category_overlap = query_tokens & category_tokens
        query_count = max(len(query_tokens), 1)
        name_coverage = len(name_overlap) / query_count
        name_precision = len(name_overlap) / max(len(name_tokens), 1)
        search_coverage = len(overlap) / query_count
        category_coverage = len(category_overlap) / query_count

        if score < 700:
            score += 360 * name_coverage
            score += 140 * name_precision
            score += 90 * search_coverage
            score += 35 * category_coverage

        if normalized_query and normalized_query in normalized_search:
            score += 70
            reasons.append("full phrase matched catalog text")

        if name_overlap:
            reasons.append("tokens matched product name")
        elif category_overlap:
            reasons.append("tokens matched category")
        elif overlap:
            reasons.append("tokens matched searchable catalog text")

    return ProductSearchResult(
        item=item,
        score=round(score, 3),
        reason=", ".join(reasons) or "weak text match",
        matched_text=search_text[:500],
    )


def search_product_catalog(
    *,
    client_slug: str,
    query: str,
    limit: int = 10,
) -> list[ProductSearchResult]:
    catalog = load_product_catalog(client_slug)
    products = list(catalog.get("products") or [])
    if not products:
        return []

    target = cleaned_product_query(query) or query
    scored = [
        product_score(item, target)
        for item in products
        if not is_polluted_product_name(item.get("product_name"))
    ]
    scored.sort(key=lambda result: result.score, reverse=True)
    if not scored:
        return []

    best_score = scored[0].score
    minimum_score = 180.0
    if best_score >= 700:
        minimum_score = max(minimum_score, best_score * 0.45)
    return [
        result
        for result in scored
        if result.score >= minimum_score
    ][: max(1, limit)]


def products_for_category_query(
    *,
    client_slug: str,
    query: str,
) -> list[ProductSearchResult]:
    results = search_product_catalog(client_slug=client_slug, query=query, limit=50)
    if not results:
        return []

    best_score = results[0].score
    return [
        result
        for result in results
        if result.score >= max(20, best_score * 0.45)
    ]


def format_product_line(item: dict[str, Any]) -> str:
    name = item.get("product_name") or "Product"
    current = format_price(item.get("current_price"), item.get("currency") or "")
    old = format_price(item.get("old_price"), item.get("currency") or "")
    if old and old != current:
        return f"{name}: {current} (old price: {old})"
    return f"{name}: {current}"


def item_numeric_price(item: dict[str, Any]) -> float | None:
    numeric = item.get("numeric_current_price")
    if isinstance(numeric, (int, float)):
        return float(numeric)
    return parse_price_number(item.get("current_price"))


def priced_products(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item
        for item in products
        if not is_polluted_product_name(item.get("product_name"))
        and item_numeric_price(item) is not None
    ]


def looks_like_most_expensive_query(query: str) -> bool:
    return bool(re.search(r"\b(most expensive|highest|priciest|max(?:imum)? price)\b", query, re.I))


def looks_like_cheapest_query(query: str) -> bool:
    return bool(re.search(r"\b(cheapest|least expensive|lowest|min(?:imum)? price)\b", query, re.I))


def looks_like_budget_category_query(query: str) -> bool:
    return bool(
        re.search(r"\b(cheap|cheaper|affordable|budget|lower priced|lower-priced)\b", query, re.I)
        and (set(canonical_product_tokens(query)) & PRODUCT_CATEGORY_HINTS)
    )


def price_threshold_filter(query: str) -> tuple[str, float] | None:
    match = re.search(
        r"\b(?P<direction>under|below|less than|over|above|more than)\s+(?P<amount>\d[\d,]*(?:\.\d+)?)",
        query,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return match.group("direction").lower(), float(match.group("amount").replace(",", ""))


def looks_like_product_image_followup(query: str) -> bool:
    lowered = query.lower().strip()
    return bool(
        re.search(r"\b(show|display|see|view)\s+(?:me\s+)?(it|that|this|them)(?:\s+to\s+me)?\b", lowered)
        or re.search(r"\b(image|images|photo|photos|picture|pictures)\s+(?:of\s+)?(it|that|this|them)\b", lowered)
        or re.search(r"\b(show|display)\s+me\s+(?:the\s+)?(?:image|images|photo|photos|picture|pictures)\s+of\s+(it|them)\b", lowered)
        or re.search(r"\bcan\s+i\s+see\s+(it|that|them|those)\b", lowered)
        or re.search(r"\bshow\s+(?:me\s+)?that\s+one\b", lowered)
    )


def looks_like_product_link_followup(query: str) -> bool:
    lowered = query.lower().strip()
    return bool(
        re.search(r"\b(link|url|page|product page)\b", lowered)
        and re.search(r"\b(it|its|that|this|them|their|product|item)\b", lowered)
    )


def looks_like_multiple_product_followup(query: str) -> bool:
    lowered = query.lower().strip()
    return bool(
        re.search(r"\b(show|display|see|view)\s+(?:me\s+)?them\b", lowered)
        or re.search(r"\b(?:their|those)\s+(?:images|photos|pictures)\b", lowered)
        or re.search(r"\bcan\s+i\s+see\s+(?:them|those)\b", lowered)
    )


def product_reference(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "product_id": clean_text(item.get("product_id")),
        "product_name": clean_text(item.get("product_name")),
        "product_url": clean_text(item.get("product_url")),
        "current_price": clean_text(item.get("current_price")),
        "old_price": clean_text(item.get("old_price")),
        "currency": clean_text(item.get("currency")),
        "image_url": clean_text(item.get("image_url")),
        "local_image_url": clean_text(item.get("local_image_url")),
        "image_alt": clean_text(item.get("image_alt")),
        "description": clean_text(item.get("description")),
    }


def result_from_product_reference(
    *,
    products: list[dict[str, Any]],
    reference: dict[str, Any] | None,
) -> ProductSearchResult | None:
    if not reference:
        return None
    reference_id = clean_text(reference.get("product_id"))
    reference_url = clean_text(reference.get("product_url"))
    reference_name = normalize_text(reference.get("product_name"))
    for item in products:
        if reference_id and reference_id == clean_text(item.get("product_id")):
            return ProductSearchResult(item=item, score=1000, reason="saved session product reference", matched_text="")
        if reference_url and reference_url == clean_text(item.get("product_url")):
            return ProductSearchResult(item=item, score=1000, reason="saved session product reference", matched_text="")
        if reference_name and reference_name == normalize_text(item.get("product_name")):
            return ProductSearchResult(item=item, score=1000, reason="saved session product reference", matched_text="")
    return None


def history_content(turn: Any) -> str:
    if isinstance(turn, dict):
        return clean_text(turn.get("content"))
    return clean_text(getattr(turn, "content", ""))


def history_role(turn: Any) -> str:
    if isinstance(turn, dict):
        return clean_text(turn.get("role"))
    return clean_text(getattr(turn, "role", ""))


def recent_product_from_history(
    *,
    client_slug: str,
    history: list[Any] | None,
) -> ProductSearchResult | None:
    if not history:
        return None

    products = list(load_product_catalog(client_slug).get("products") or [])
    for turn in reversed(history):
        if history_role(turn) != "assistant":
            continue
        content = history_content(turn)
        if not content:
            continue
        scored = [product_score(item, content) for item in products]
        scored.sort(key=lambda result: result.score, reverse=True)
        if scored and scored[0].score >= 45:
            return scored[0]
    return None


def format_exact_product_answer(
    *,
    results: list[ProductSearchResult],
    contact_info: str = "",
) -> str | None:
    if not results:
        return None

    best = results[0]
    if best.score < 35:
        return None

    close_results = [
        result
        for result in results[:3]
        if result.score >= max(35, best.score * 0.72)
    ]

    if len(close_results) > 1 and best.score < 95:
        lines = ["I found several possible matches in the available catalog:"]
        lines.extend(
            f"{index}. {format_product_line(result.item)}"
            for index, result in enumerate(close_results, start=1)
        )
        if contact_info:
            lines.append(f"For more details contact {contact_info}.")
        return "\n".join(lines)

    item = best.item
    current = format_price(item.get("current_price"), item.get("currency") or "")
    answer = (
        f"The available catalog lists {item.get('product_name')} at {current}."
    )
    old = format_price(item.get("old_price"), item.get("currency") or "")
    if old and old != current:
        answer += f" The previous/listed old price is {old}."
    if contact_info:
        answer += f" For more details contact {contact_info}."
    return answer


def format_price_range_answer(
    *,
    query: str,
    results: list[ProductSearchResult],
    company_name: str,
    contact_info: str = "",
) -> str | None:
    priced: list[tuple[float, ProductSearchResult]] = []
    for result in results:
        price = parse_price_number(result.item.get("current_price"))
        if price is not None:
            priced.append((price, result))

    if not priced:
        return None

    by_currency: dict[str, list[tuple[float, ProductSearchResult]]] = {}
    for price, result in priced:
        currency = result.item.get("currency") or detect_currency(
            result.item.get("current_price")
        ) or "price"
        by_currency.setdefault(currency, []).append((price, result))

    topic = cleaned_product_query(query) or "matching products"
    lines: list[str] = []
    for currency, currency_results in by_currency.items():
        currency_results.sort(key=lambda pair: pair[0])
        low_price, low_result = currency_results[0]
        high_price, high_result = currency_results[-1]
        low_display = format_price(low_result.item.get("current_price"), currency)
        high_display = format_price(high_result.item.get("current_price"), currency)
        lines.append(
            f"{topic} prices in the available {company_name} catalog range "
            f"from {low_display} to {high_display}."
        )
        if low_result.item.get("product_name") != high_result.item.get("product_name"):
            lines.append(
                "For example, "
                f"{low_result.item.get('product_name')} is {low_display} and "
                f"{high_result.item.get('product_name')} is {high_display}."
            )

    if contact_info:
        lines.append(f"For more details contact {contact_info}.")
    return " ".join(lines)


def format_product_list_answer(
    *,
    results: list[ProductSearchResult],
    contact_info: str = "",
) -> str | None:
    if not results:
        return None

    strong = [
        result
        for result in results[:5]
        if result.score >= max(20, results[0].score * 0.45)
    ]
    if not strong:
        return None

    lines = ["Here are matching products from the available catalog:"]
    lines.extend(
        f"{index}. {format_product_line(result.item)}"
        for index, result in enumerate(strong, start=1)
    )
    if contact_info:
        lines.append(f"For more details contact {contact_info}.")
    return "\n".join(lines)


def product_answer_for_query(
    *,
    client_slug: str,
    query: str,
    company_name: str,
    contact_info: str = "",
    history: list[Any] | None = None,
    last_product_reference: dict[str, Any] | None = None,
    last_product_references: list[dict[str, Any]] | None = None,
) -> tuple[str, list[dict[str, Any]], list[ProductSearchResult]] | None:
    catalog = load_product_catalog(client_slug)
    products = list(catalog.get("products") or [])
    if not products:
        return None

    explicit_product_intent = looks_like_product_query(query)
    precomputed_results: list[ProductSearchResult] = []
    if not explicit_product_intent:
        precomputed_results = search_product_catalog(
            client_slug=client_slug,
            query=query,
            limit=10,
        )
        if not precomputed_results or precomputed_results[0].score < 700:
            return None

    lowered = query.lower()

    if looks_like_product_image_followup(query):
        if looks_like_multiple_product_followup(query):
            saved_results = [
                result
                for reference in (last_product_references or [])[:5]
                if (
                    result := result_from_product_reference(
                        products=products,
                        reference=reference,
                    )
                ) is not None
            ]
            if saved_results:
                media = [
                    media_item
                    for result in saved_results
                    if (media_item := result.media_item()) is not None
                ]
                if media:
                    return (
                        "Here are the product images from the previous catalog results.",
                        media,
                        saved_results,
                    )
                return (
                    "The previous catalog products do not have available product images.",
                    [],
                    saved_results,
                )

        recent_result = result_from_product_reference(
            products=products,
            reference=last_product_reference,
        )
        if recent_result is None and last_product_references:
            recent_result = result_from_product_reference(
                products=products,
                reference=last_product_references[0],
            )
        if recent_result is None:
            recent_result = recent_product_from_history(
                client_slug=client_slug,
                history=history,
            )
        if recent_result is not None:
            media_item = recent_result.media_item()
            if media_item is not None:
                return (
                    f"Here is {recent_result.item.get('product_name')} from the available catalog.",
                    [media_item],
                    [recent_result],
                )
            return (
                f"I found {recent_result.item.get('product_name')}, but I do not have an available product image for it.",
                [],
                [recent_result],
            )

        return (
            "I do not have a product reference from this chat to show yet.",
            [], 
            [],
        )

    if looks_like_product_link_followup(query):
        recent_result = result_from_product_reference(
            products=products,
            reference=last_product_reference,
        )
        if recent_result is None and last_product_references:
            recent_result = result_from_product_reference(
                products=products,
                reference=last_product_references[0],
            )
        if recent_result is None:
            recent_result = recent_product_from_history(
                client_slug=client_slug,
                history=history,
            )
        if recent_result is not None:
            product_name = clean_text(recent_result.item.get("product_name"))
            product_url = canonical_product_url(recent_result.item)
            if product_url:
                return (
                    f"Product page for {product_name}: {product_url}",
                    [],
                    [recent_result],
                )
            return (
                f"I found {product_name}, but I do not have an available product page link for it.",
                [],
                [recent_result],
            )

        return (
            "I do not have a product reference from this chat to link to yet.",
            [],
            [],
        )

    is_general_product_browse = bool(
        PRODUCT_BROWSE_QUERY_PATTERN.search(query)
        and not canonical_product_tokens(cleaned_product_query(query))
    )
    if is_general_product_browse:
        browse_items = [item for item in products if best_product_image_url(item)][:5]
        if not browse_items:
            return (
                "I found products in the available catalog, but their product images are unavailable.",
                [],
                [],
            )
        browse_results = [
            ProductSearchResult(item=item, score=100, reason="product catalog browse", matched_text="")
            for item in browse_items
        ]
        answer = (
            "Here are some furniture products from the available catalog:\n"
            + "\n".join(
                f"{index}. {format_product_line(result.item)}"
                for index, result in enumerate(browse_results, start=1)
            )
        )
        media = [
            media_item
            for result in browse_results
            if (media_item := result.media_item()) is not None
        ]
        return answer, media, browse_results

    results = precomputed_results or search_product_catalog(
        client_slug=client_slug,
        query=query,
        limit=10,
    )
    all_priced = priced_products(products)

    if looks_like_most_expensive_query(query) and all_priced:
        item = max(all_priced, key=lambda product: item_numeric_price(product) or -1)
        result = ProductSearchResult(
            item=item,
            score=100,
            reason="highest numeric catalog price",
            matched_text="",
        )
        media_item = result.media_item()
        return (
            "The most expensive item found in the available catalog is "
            f"{format_product_line(item)}.",
            [media_item] if media_item else [],
            [result],
        )

    if looks_like_cheapest_query(query) and all_priced:
        item = min(all_priced, key=lambda product: item_numeric_price(product) or float("inf"))
        result = ProductSearchResult(
            item=item,
            score=100,
            reason="lowest numeric catalog price",
            matched_text="",
        )
        media_item = result.media_item()
        return (
            "The cheapest item found in the available catalog is "
            f"{format_product_line(item)}.",
            [media_item] if media_item else [],
            [result],
        )

    if looks_like_budget_category_query(query):
        category_results = products_for_category_query(client_slug=client_slug, query=query)
        priced_category_results = [
            result
            for result in category_results
            if item_numeric_price(result.item) is not None
        ]
        priced_category_results.sort(key=lambda result: item_numeric_price(result.item) or 0)
        answer = format_product_list_answer(
            results=priced_category_results[:5],
            contact_info=contact_info,
        )
        if answer:
            media = [
                media
                for result in priced_category_results[:3]
                if (media := result.media_item()) is not None
            ]
            return answer, media, priced_category_results

    threshold_filter = price_threshold_filter(query)
    if threshold_filter and all_priced:
        direction, amount = threshold_filter
        if direction in {"under", "below", "less than"}:
            filtered_items = [
                item
                for item in all_priced
                if (item_numeric_price(item) or float("inf")) <= amount
            ]
        else:
            filtered_items = [
                item
                for item in all_priced
                if (item_numeric_price(item) or 0) >= amount
            ]
        filtered_items.sort(key=lambda item: item_numeric_price(item) or 0)
        threshold_results = [
            ProductSearchResult(item=item, score=100, reason="numeric price filter", matched_text="")
            for item in filtered_items[:5]
        ]
        answer = format_product_list_answer(
            results=threshold_results,
            contact_info=contact_info,
        )
        if answer:
            media = [
                media
                for result in threshold_results[:3]
                if (media := result.media_item()) is not None
            ]
            return answer, media, threshold_results

    is_range = bool(
        re.search(
            r"\b(range|between|price range|range of prices)\b|"
            r"(نطاق الأسعار|نطاق الاسعار)",
            lowered,
            flags=re.IGNORECASE,
        )
    )
    is_list = bool(
        re.search(
            r"\b(show|list|some|products|available|under\s+\d+|over\s+\d+|below\s+\d+|above\s+\d+)\b",
            lowered,
            flags=re.IGNORECASE,
        )
        and not re.search(r"\b(image|photo|picture)\b", lowered, flags=re.IGNORECASE)
    )
    generic_price_overview = bool(
        re.search(r"\b(prices|pricing|packages|package)\b", lowered)
        and len(tokens_for(cleaned_product_query(query))) <= 2
    )
    is_option_query = bool(
        PRODUCT_OPTION_QUERY_PATTERN.search(query)
        and (set(tokens_for(cleaned_product_query(query))) & PRODUCT_CATEGORY_HINTS)
    )

    if is_range:
        category_results = products_for_category_query(client_slug=client_slug, query=query)
        answer = format_price_range_answer(
            query=query,
            results=category_results,
            company_name=company_name,
            contact_info=contact_info,
        )
        if answer:
            return answer, [], category_results

    if generic_price_overview:
        sample_results = [
            ProductSearchResult(item=item, score=1, reason="catalog sample", matched_text="")
            for item in priced_products(products)[:5]
        ]
        answer = (
            f"Here are some products from the available {company_name} catalog:\n"
            + "\n".join(
                f"{index}. {format_product_line(result.item)}"
                for index, result in enumerate(sample_results[:5], start=1)
            )
        )
        if contact_info:
            answer += f"\nFor more details contact {contact_info}."
        media = [
            media
            for result in sample_results[:3]
            if (media := result.media_item()) is not None
        ]
        return answer, media, sample_results

    if is_option_query:
        category_results = products_for_category_query(client_slug=client_slug, query=query)
        answer = format_product_list_answer(
            results=category_results,
            contact_info=contact_info,
        )
        if answer:
            media = [
                media
                for result in category_results[:3]
                if (media := result.media_item()) is not None
            ]
            return answer, media, category_results

    if is_list:
        answer = format_product_list_answer(
            results=results,
            contact_info=contact_info,
        )
        if answer:
            strong_results = [
                result
                for result in results[:5]
                if result.score >= max(20, results[0].score * 0.45)
            ]
            media = [
                media
                for result in strong_results[:3]
                if (media := result.media_item()) is not None
            ]
            return answer, media, results

    answer = format_exact_product_answer(results=results, contact_info=contact_info)
    if not answer:
        return None

    media = []
    if results:
        media_item = results[0].media_item()
        if media_item is not None:
            media.append(media_item)
    return answer, media, results


def product_catalog_summary(client_slug: str) -> dict[str, Any]:
    catalog = load_product_catalog(client_slug)
    products = list(catalog.get("products") or [])
    categories: dict[str, int] = {}
    currencies: set[str] = set()

    for item in products:
        category = str(item.get("category") or "Uncategorized").strip() or "Uncategorized"
        categories[category] = categories.get(category, 0) + 1
        currency = str(item.get("currency") or "").strip()
        if currency:
            currencies.add(currency)

    return {
        "client_slug": client_slug,
        "total_raw_products": catalog.get("total_raw_products", len(products)),
        "total_products": len(products),
        "total_clean_products": len(products),
        "removed_polluted_products": catalog.get("removed_polluted_products", 0),
        "removed_polluted_names": catalog.get("removed_polluted_names", 0),
        "invalid_product_images_removed": catalog.get("invalid_product_images_removed", 0),
        "placeholders_removed": catalog.get("placeholders_removed", 0),
        "products_with_valid_local_images": catalog.get("products_with_valid_local_images", 0),
        "products_with_valid_remote_only_images": catalog.get("products_with_valid_remote_only_images", 0),
        "products_without_images": catalog.get("products_without_images", 0),
        "categories_count": len(categories),
        "categories": dict(sorted(categories.items())),
        "currencies": sorted(currencies),
        "product_catalog": {
            "exists": bool(catalog.get("exists")),
            "path": catalog.get("path"),
            "source_url": catalog.get("source_url"),
            "generated_at": catalog.get("generated_at"),
        },
        "sample_products": products[:10],
        "sample_removed_products": catalog.get("sample_removed_products", []),
    }
