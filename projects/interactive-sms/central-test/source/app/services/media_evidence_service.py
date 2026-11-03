from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentChunk
from app.schemas.chat import ChatHistoryTurn
from app.services.client_config_service import client_scraped_dir


STOPWORDS = {
    "a",
    "about",
    "an",
    "and",
    "any",
    "are",
    "answer",
    "as",
    "at",
    "be",
    "by",
    "can",
    "did",
    "do",
    "does",
    "evidence",
    "for",
    "from",
    "give",
    "have",
    "how",
    "i",
    "image",
    "in",
    "is",
    "it",
    "listed",
    "me",
    "of",
    "on",
    "or",
    "proof",
    "show",
    "source",
    "that",
    "the",
    "this",
    "to",
    "website",
    "what",
    "which",
    "with",
    "you",
    "your",
}

CERTIFICATE_TERMS = {
    "certificate",
    "certification",
    "certified",
    "license",
    "licensed",
    "licence",
    "proof",
    "official",
}

CERTIFICATE_PHRASES = (
    "demo certificate",
    "official test document",
    "source evidence test",
    "test document image",
)

SERVICE_TERMS = {
    "advertising",
    "branding",
    "campaign",
    "consultancy",
    "content",
    "design",
    "development",
    "digital",
    "influencer",
    "it",
    "marketing",
    "media",
    "production",
    "public",
    "relations",
    "service",
    "services",
    "social",
    "strategy",
    "talent",
    "training",
}

SERVICE_PHRASES = (
    "our services",
    "digital marketing strategy",
    "training consultancy",
    "training & consultancy",
    "talent management",
    "design branding",
    "design & branding",
    "public relations",
    "it development",
    "it & development",
    "digital marketing",
)

LOCATION_TERMS = {
    "address",
    "branch",
    "directions",
    "location",
    "located",
    "map",
    "office",
}

CONTACT_TERMS = {
    "contact",
    "email",
    "mail",
    "mobile",
    "phone",
    "telephone",
    "whatsapp",
}

PRICING_TERMS = {
    "cost",
    "fee",
    "fees",
    "jod",
    "package",
    "packages",
    "plan",
    "price",
    "prices",
    "pricing",
    "usd",
}

LOGO_TERMS = (
    "brand mark",
    "brandmark",
    "logo",
    "logo-thumb",
    "logomark",
)

PARTNER_LOGO_TERMS = (
    "beloved clients",
    "client logo",
    "clients",
    "partner",
    "partners",
    "sponsor",
    "sponsors",
    "seeklogo",
)

STAFF_PHOTO_TERMS = (
    "account manager",
    "art director",
    "backend developer",
    "customer service",
    "employee",
    "employees",
    "event",
    "family",
    "frontend developer",
    "general manager",
    "headshot",
    "manager",
    "mobile developer",
    "our family",
    "people",
    "photographer",
    "portrait",
    "ramadan",
    "staff",
    "team",
)

SOCIAL_ICON_TERMS = (
    "facebook",
    "instagram",
    "linkedin",
    "tiktok",
    "twitter",
    "x.com",
    "whatsapp",
    "youtube",
    "social icon",
)

NON_CONTENT_CATEGORIES = {
    "country_flag",
    "payment_icon",
    "hidden_asset",
    "placeholder_image",
    "ui_asset",
}

NEGATIVE_CATEGORIES = {
    "client logo",
    "company logo",
    "decorative",
    "event_photo",
    "generic_marketing_image",
    "icon",
    "logo",
    "partner_logo",
    "social icon",
    "social_icon",
    "staff_photo",
    "team",
    *NON_CONTENT_CATEGORIES,
}

STRICT_INTENTS = {
    "certificate_evidence",
    "services_evidence",
    "location_evidence",
    "contact_evidence",
    "pricing_evidence",
}


@dataclass(slots=True)
class MediaEvidenceCandidate:
    media_type: str
    url: str
    label: str
    source: str
    source_type: str
    page_url: str = ""
    source_url: str = ""
    document_title: str = ""
    original_filename: str = ""
    section_title: str = ""
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    score: int = 0
    reason: str = ""

    def to_media_item(self) -> dict[str, Any]:
        return {
            "type": self.media_type,
            "url": self.url,
            "label": self.label,
            "source": self.source,
            "page_url": self.page_url,
            "source_url": self.source_url,
            "reason": self.reason,
        }


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def text_blob(*values: Any) -> str:
    return clean_text(" ".join(str(value or "") for value in values))


def tokenize(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9]+", value.lower())
        if len(token) > 2 and token not in STOPWORDS
    }


def normalized_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def has_phrase(value: str, phrase: str) -> bool:
    return normalized_text(phrase) in normalized_text(value)


def phrase_matches(value: str, phrases: tuple[str, ...]) -> list[str]:
    return [
        phrase
        for phrase in phrases
        if has_phrase(value, phrase)
    ]


def matching_terms(value: str, terms: set[str]) -> set[str]:
    tokens = tokenize(value)

    return tokens & terms


def category_from_existing(value: Any) -> str:
    category = clean_text(value).lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "client_logo": "partner_logo",
        "company_logo": "logo",
        "service": "services",
        "social_icon": "social_icon",
        "team": "staff_photo",
        "country_flag": "country_flag",
        "payment_icon": "payment_icon",
        "hidden_asset": "hidden_asset",
        "placeholder_image": "placeholder_image",
        "ui_asset": "ui_asset",
    }

    return aliases.get(category, category)


def direct_metadata_text(metadata: dict[str, Any]) -> str:
    return text_blob(
        metadata.get("alt"),
        metadata.get("alt_text"),
        metadata.get("title"),
        metadata.get("title_text"),
        metadata.get("nearby_text"),
        metadata.get("section_heading"),
        metadata.get("ocr_text"),
        metadata.get("image_description"),
        metadata.get("vision_summary"),
        metadata.get("document_title"),
        metadata.get("original_filename"),
        metadata.get("source_reference"),
    )


def page_metadata_text(metadata: dict[str, Any]) -> str:
    return text_blob(
        metadata.get("page_title"),
        metadata.get("page_visible_text"),
    )


def full_metadata_text(metadata: dict[str, Any]) -> str:
    return text_blob(
        direct_metadata_text(metadata),
        page_metadata_text(metadata),
        metadata.get("url"),
        metadata.get("original_image_url"),
        metadata.get("local_static_url"),
        metadata.get("class_name"),
        metadata.get("element_id"),
        metadata.get("parent_class_name"),
    )


def evidence_intent_from_text(
    *,
    question: str,
    topic_text: str,
) -> str:
    question_text = clean_text(question).lower()
    combined = text_blob(question, topic_text).lower()

    if matching_terms(question_text, CERTIFICATE_TERMS) or phrase_matches(
        question_text,
        CERTIFICATE_PHRASES,
    ):
        return "certificate_evidence"

    if "website image" in question_text and not any(
        word in question_text
        for word in ["proof", "evidence", "source"]
    ):
        return "general_website_evidence"

    if (
        matching_terms(combined, LOCATION_TERMS)
        or re.search(r"\b(where|located|location|address)\b", combined)
    ):
        return "location_evidence"

    if matching_terms(combined, CONTACT_TERMS) or re.search(
        r"[\w.+-]+@[\w.-]+\.[a-z]{2,}",
        combined,
    ):
        return "contact_evidence"

    if matching_terms(combined, PRICING_TERMS):
        return "pricing_evidence"

    if (
        matching_terms(combined, SERVICE_TERMS)
        or phrase_matches(combined, SERVICE_PHRASES)
    ):
        return "services_evidence"

    if (
        matching_terms(combined, CERTIFICATE_TERMS)
        or phrase_matches(combined, CERTIFICATE_PHRASES)
    ):
        return "certificate_evidence"

    return "general_website_evidence"


def last_history_text(
    history: list[ChatHistoryTurn],
    role: str,
) -> str:
    for turn in reversed(history):
        if turn.role == role:
            return turn.content

    return ""


def topic_text_from_history(
    *,
    question: str,
    history: list[ChatHistoryTurn],
) -> str:
    return text_blob(
        question,
        last_history_text(history, "user"),
        last_history_text(history, "assistant"),
    )


def classify_image(metadata: dict[str, Any]) -> str:
    existing_category = category_from_existing(
        metadata.get("category")
        or metadata.get("image_category")
        or metadata.get("image_role")
    )

    if existing_category in {
        "certificate",
        "services",
        "pricing",
        "location",
        "contact",
        "screenshot",
        "decorative",
        "staff_photo",
        "partner_logo",
        "logo",
        "social_icon",
        "icon",
        "generic_marketing_image",
    }:
        return existing_category

    url = clean_text(metadata.get("url") or metadata.get("original_image_url"))
    local_static_url = clean_text(metadata.get("local_static_url"))
    direct_text = direct_metadata_text(metadata).lower()
    kind = clean_text(metadata.get("kind"))
    filename = Path(url or local_static_url).name.lower()
    width = int(metadata.get("width") or 0)
    height = int(metadata.get("height") or 0)
    combined = full_metadata_text(metadata).lower()

    if "/screenshots/" in local_static_url:
        return "screenshot"

    if metadata.get("visible") is False:
        return "hidden_asset"

    if any(term in combined for term in ["plp-loader", "loader", "placeholder", "spinner", "sprite"]):
        return "placeholder_image"

    if "flag-img" in combined or "/flags/" in combined:
        return "country_flag"

    if any(term in combined for term in ["payment", "visa", "mastercard", "paypal", "applepay", "apple pay", "mada"]):
        return "payment_icon"

    if (
        matching_terms(direct_text, CERTIFICATE_TERMS)
        or phrase_matches(direct_text, CERTIFICATE_PHRASES)
    ):
        return "certificate"

    if any(term in combined for term in SOCIAL_ICON_TERMS):
        return "social_icon"

    if any(term in combined for term in PARTNER_LOGO_TERMS):
        return "partner_logo"

    if any(term in combined for term in LOGO_TERMS):
        return "logo"

    if width and height and (width < 90 or height < 60):
        return "icon"

    if kind == "background" and not direct_text:
        return "decorative"

    if any(term in combined for term in STAFF_PHOTO_TERMS):
        return "staff_photo"

    if matching_terms(direct_text, PRICING_TERMS):
        return "pricing"

    if matching_terms(direct_text, LOCATION_TERMS):
        return "location"

    if matching_terms(direct_text, CONTACT_TERMS):
        return "contact"

    if matching_terms(direct_text, SERVICE_TERMS) or phrase_matches(
        direct_text,
        SERVICE_PHRASES,
    ):
        return "services"

    if width >= 700 or height >= 350:
        return "generic_marketing_image"

    return "unknown"


def category_matches_intent(category: str, intent: str) -> bool:
    return (
        (intent == "certificate_evidence" and category == "certificate")
        or (intent == "services_evidence" and category == "services")
        or (intent == "location_evidence" and category == "location")
        or (intent == "contact_evidence" and category == "contact")
        or (intent == "pricing_evidence" and category == "pricing")
    )


def source_type_preference(
    *,
    source_type: str,
    category: str,
    intent: str,
    is_screenshot: bool,
) -> tuple[int, str | None]:
    if intent == "certificate_evidence":
        if source_type == "document_image":
            return 80, "direct embedded document image"
        if source_type == "pdf_page_image":
            return 35, "document page image"
        if is_screenshot:
            return 15, "screenshot fallback"
        if source_type == "website_auto_scrape":
            return 20, "website image"

    if is_screenshot:
        return 30, "screenshot"

    if source_type == "website_auto_scrape":
        return 20, "website image"

    if source_type in {"document_image", "pdf_page_image"}:
        return 20, "uploaded document image"

    return 0, None


def usefulness_score(
    metadata: dict[str, Any],
    *,
    topic_text: str,
    intent: str,
    require_screenshot: bool,
    require_certificate: bool,
) -> tuple[int, str]:
    category = classify_image(metadata)
    metadata["category"] = category
    metadata["image_category"] = category
    metadata["image_role"] = category
    local_static_url = clean_text(metadata.get("local_static_url"))
    source_type = clean_text(metadata.get("source_type"))
    width = int(metadata.get("width") or 0)
    height = int(metadata.get("height") or 0)
    is_screenshot = category == "screenshot" or "/screenshots/" in local_static_url
    direct_text = direct_metadata_text(metadata)
    page_text = page_metadata_text(metadata)
    has_visual_text = any(
        [
            metadata.get("ocr_text"),
            metadata.get("alt"),
            metadata.get("alt_text"),
            metadata.get("nearby_text"),
            metadata.get("section_heading"),
            metadata.get("image_description"),
            metadata.get("vision_summary"),
            metadata.get("title"),
            metadata.get("title_text"),
        ]
    )
    proof_text = text_blob(
        direct_text,
        page_text if is_screenshot and not has_visual_text else "",
    )
    evidence_text = text_blob(proof_text, category)
    topic_tokens = tokenize(topic_text)
    direct_tokens = tokenize(direct_text)
    page_tokens = tokenize(page_text) if is_screenshot else set()
    evidence_tokens = direct_tokens | page_tokens
    overlap = len(topic_tokens & evidence_tokens)
    score = 0
    reasons: list[str] = []

    if require_screenshot and not is_screenshot:
        score -= 250
        reasons.append("not a screenshot")

    if require_certificate and category != "certificate":
        score -= 250
        reasons.append("not certificate evidence")

    source_bonus, source_reason = source_type_preference(
        source_type=source_type,
        category=category,
        intent=intent,
        is_screenshot=is_screenshot,
    )
    score += source_bonus

    if source_reason:
        reasons.append(source_reason)

    if category_matches_intent(category, intent):
        score += 160
        reasons.append(f"exact {category} match")

    if intent == "certificate_evidence":
        certificate_terms = matching_terms(proof_text, CERTIFICATE_TERMS)
        certificate_phrases = phrase_matches(proof_text, CERTIFICATE_PHRASES)

        if certificate_terms:
            score += min(len(certificate_terms) * 35, 140)
            reasons.append("certificate OCR/text match")

        if certificate_phrases:
            score += 100
            reasons.append("exact certificate phrase")

    elif intent == "services_evidence":
        service_terms = matching_terms(proof_text, SERVICE_TERMS)
        service_phrases = phrase_matches(proof_text, SERVICE_PHRASES)

        if service_terms:
            score += min(len(service_terms) * 25, 150)
            reasons.append("service text match")

        if service_phrases:
            score += min(len(service_phrases) * 55, 165)
            reasons.append("service section text match")

    elif intent == "location_evidence":
        location_terms = matching_terms(proof_text, LOCATION_TERMS | topic_tokens)

        if location_terms:
            score += min(len(location_terms) * 35, 160)
            reasons.append("address/location text match")

    elif intent == "contact_evidence":
        contact_terms = matching_terms(proof_text, CONTACT_TERMS | topic_tokens)
        has_email = bool(re.search(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", proof_text.lower()))
        has_phone = bool(re.search(r"(?:\+?\d[\d\s().-]{6,}\d)", proof_text))

        if contact_terms:
            score += min(len(contact_terms) * 35, 150)
            reasons.append("contact text match")

        if has_email or has_phone:
            score += 90
            reasons.append("email/phone OCR match")

    elif intent == "pricing_evidence":
        pricing_terms = matching_terms(proof_text, PRICING_TERMS | topic_tokens)
        has_money = bool(
            re.search(
                r"(?:[$]|jod|usd|\b\d+(?:\.\d+)?\s*(?:jd|jod|usd)\b)",
                proof_text.lower(),
            )
        )

        if pricing_terms:
            score += min(len(pricing_terms) * 35, 160)
            reasons.append("pricing text match")

        if has_money:
            score += 80
            reasons.append("price OCR match")

    elif intent == "general_website_evidence":
        if direct_tokens:
            score += min(len(direct_tokens & topic_tokens) * 15, 70)

        if category not in NEGATIVE_CATEGORIES:
            score += 35
            reasons.append("approved website media")

    if overlap:
        score += min(overlap * 8, 50)

        if "topic match" not in reasons:
            reasons.append("topic match")

    if metadata.get("ocr_text"):
        score += 25

        if not any("OCR" in reason for reason in reasons):
            reasons.append("OCR text")

    if metadata.get("alt") or metadata.get("alt_text"):
        score += 10

    if metadata.get("nearby_text") and category not in NEGATIVE_CATEGORIES:
        score += 15

    if is_screenshot and not has_visual_text:
        score -= 120
        reasons.append("page-wide screenshot fallback")

    if width and height:
        area = width * height

        if width < 90 or height < 60:
            score -= 60
        elif area < 12_000:
            score -= 35
        elif area > 70_000:
            score += 15

    if category in NEGATIVE_CATEGORIES:
        penalty = 260 if intent in STRICT_INTENTS else 120
        score -= penalty
        reasons.append(f"penalized {category}")

    if intent in STRICT_INTENTS and not category_matches_intent(category, intent):
        direct_match = False

        if intent == "certificate_evidence":
            direct_match = bool(
                matching_terms(proof_text, CERTIFICATE_TERMS)
                or phrase_matches(proof_text, CERTIFICATE_PHRASES)
            )
        elif intent == "services_evidence":
            direct_match = bool(
                matching_terms(proof_text, SERVICE_TERMS)
                or phrase_matches(proof_text, SERVICE_PHRASES)
            )
        elif intent == "location_evidence":
            direct_match = bool(matching_terms(proof_text, LOCATION_TERMS | topic_tokens))
        elif intent == "contact_evidence":
            direct_match = bool(
                matching_terms(proof_text, CONTACT_TERMS | topic_tokens)
                or re.search(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", proof_text.lower())
                or re.search(r"(?:\+?\d[\d\s().-]{6,}\d)", proof_text)
            )
        elif intent == "pricing_evidence":
            direct_match = bool(matching_terms(proof_text, PRICING_TERMS | topic_tokens))

        if not direct_match:
            score -= 170
            reasons.append("no strict intent match")

    if not direct_text and not (is_screenshot and page_text):
        score -= 80
        reasons.append("low semantic signal")

    concise_reasons = list(dict.fromkeys(reason for reason in reasons if reason))

    return score, ", ".join(concise_reasons[:3]) or "approved media evidence"


def load_latest_scrape_media(client_slug: str) -> dict[str, dict[str, Any]]:
    scraped_dir = client_scraped_dir(client_slug)

    if not scraped_dir.exists():
        return {}

    media_by_url: dict[str, dict[str, Any]] = {}

    for json_path in sorted(scraped_dir.glob("*Website_Scrape.json"), reverse=True):
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        for page in payload.get("pages", []):
            page_url = clean_text(page.get("page_url"))
            page_title = clean_text(page.get("title"))
            page_text = "\n".join(page.get("visible_text", [])[:40])

            for image_index, image in enumerate(page.get("images", []), start=1):
                local_static_url = clean_text(image.get("local_static_url"))

                if not local_static_url:
                    continue

                enriched = {
                    **image,
                    "source_type": "website_auto_scrape",
                    "media_type": "image",
                    "page_url": page_url,
                    "page_title": page_title,
                    "page_visible_text": page_text,
                    "image_index": image.get("image_index") or image_index,
                    "alt_text": image.get("alt") or image.get("alt_text") or "",
                }
                enriched["image_role"] = image.get("image_role") or classify_image(enriched)
                enriched["image_category"] = image.get("image_category") or enriched["image_role"]
                enriched["category"] = enriched["image_category"]
                media_by_url[local_static_url] = enriched

            for screenshot_index, screenshot in enumerate(page.get("screenshots", []), start=1):
                local_static_url = clean_text(screenshot.get("local_static_url"))

                if not local_static_url:
                    continue

                media_by_url[local_static_url] = {
                    **screenshot,
                    "source_type": "website_auto_scrape",
                    "media_type": "screenshot",
                    "page_url": page_url,
                    "page_title": page_title,
                    "page_visible_text": page_text,
                    "image_index": screenshot_index,
                    "image_role": "screenshot",
                    "image_category": "screenshot",
                    "category": "screenshot",
                }

        break

    return media_by_url


def db_media_rows(
    *,
    db: Session,
    client_slug: str,
) -> list[tuple[DocumentChunk, Document]]:
    return db.execute(
        select(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            DocumentChunk.client_slug == client_slug,
            Document.client_slug == client_slug,
            Document.status == "active",
            Document.visibility == "client",
            DocumentChunk.chunk_metadata.has_key("local_static_url"),
        )
        .order_by(Document.created_at.desc(), DocumentChunk.chunk_index.asc())
    ).all()


def candidate_label(
    *,
    metadata: dict[str, Any],
    document: Document,
    reason: str,
) -> str:
    role = classify_image(metadata)
    meaningful = clean_text(
        metadata.get("entity_name")
        or metadata.get("alt_text")
        or metadata.get("image_label")
        or metadata.get("image_description")
        or metadata.get("section_heading")
        or metadata.get("page_title")
    )

    if role == "screenshot":
        return f"{meaningful} screenshot" if meaningful else "Website screenshot"

    if role == "certificate":
        return meaningful or "Certificate image"

    if metadata.get("source_type") == "website_auto_scrape":
        return meaningful or "Website image"

    return meaningful or "Company image"


def build_candidates(
    *,
    db: Session,
    client_slug: str,
    topic_text: str,
    intent: str,
    require_website: bool,
    require_screenshot: bool,
    require_certificate: bool,
) -> list[MediaEvidenceCandidate]:
    scrape_media = load_latest_scrape_media(client_slug)
    candidates: list[MediaEvidenceCandidate] = []
    seen_urls: set[str] = set()

    for chunk, document in db_media_rows(db=db, client_slug=client_slug):
        metadata = {
            **(chunk.chunk_metadata or {}),
        }
        local_static_url = clean_text(metadata.get("local_static_url"))

        if not local_static_url or local_static_url in seen_urls:
            continue

        metadata.update(scrape_media.get(local_static_url, {}))
        source_type = clean_text(metadata.get("source_type"))
        role = classify_image(metadata)
        metadata["image_role"] = role
        metadata["image_category"] = role
        metadata["category"] = role

        if require_website and source_type != "website_auto_scrape":
            continue

        if require_screenshot and role != "screenshot":
            continue

        if require_certificate and role != "certificate":
            continue

        if role in NON_CONTENT_CATEGORIES:
            continue

        score, reason = usefulness_score(
            metadata,
            topic_text=topic_text,
            intent=intent,
            require_screenshot=require_screenshot,
            require_certificate=require_certificate,
        )

        if require_website and role in NEGATIVE_CATEGORIES:
            continue

        candidates.append(
            MediaEvidenceCandidate(
                media_type="image",
                url=local_static_url,
                label=candidate_label(
                    metadata=metadata,
                    document=document,
                    reason=reason,
                ),
                source="approved_client_evidence",
                source_type=source_type,
                page_url=clean_text(metadata.get("page_url")),
                source_url=clean_text(metadata.get("source_url")),
                document_title=document.title,
                original_filename=document.original_filename,
                section_title=chunk.section_title or "",
                content=chunk.content,
                metadata=metadata,
                score=score,
                reason=reason,
            )
        )
        seen_urls.add(local_static_url)

    candidates.sort(key=lambda candidate: candidate.score, reverse=True)
    return candidates


def bundle_items(evidence_bundle: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(evidence_bundle, dict):
        return []

    items = evidence_bundle.get("items")

    if not isinstance(items, list):
        return []

    return [
        item
        for item in items
        if isinstance(item, dict)
    ]


def topic_text_from_bundle(
    *,
    question: str,
    history: list[ChatHistoryTurn],
    evidence_bundle: dict[str, Any] | None,
) -> str:
    items = bundle_items(evidence_bundle)

    return text_blob(
        question,
        last_history_text(history, "assistant"),
        evidence_bundle.get("question") if isinstance(evidence_bundle, dict) else "",
        evidence_bundle.get("answer_preview") if isinstance(evidence_bundle, dict) else "",
        " ".join(clean_text(item.get("content_preview")) for item in items),
    )


def candidate_from_bundle_media(
    *,
    url: str,
    item: dict[str, Any],
    scrape_media: dict[str, dict[str, Any]],
    topic_text: str,
    intent: str,
    require_screenshot: bool,
    require_certificate: bool,
) -> MediaEvidenceCandidate | None:
    metadata = {
        **item,
        **scrape_media.get(url, {}),
        "local_static_url": url,
    }
    source_type = clean_text(metadata.get("source_type"))
    role = classify_image(metadata)
    metadata["image_role"] = role
    metadata["image_category"] = role
    metadata["category"] = role

    if require_screenshot and role != "screenshot":
        return None

    if require_certificate and role != "certificate":
        return None

    if role in NON_CONTENT_CATEGORIES:
        return None

    score, reason = usefulness_score(
        metadata,
        topic_text=topic_text,
        intent=intent,
        require_screenshot=require_screenshot,
        require_certificate=require_certificate,
    )
    score += 80

    return MediaEvidenceCandidate(
        media_type="image",
        url=url,
        label=candidate_label(
            metadata=metadata,
            document=type(
                "EvidenceDocument",
                (),
                {"original_filename": clean_text(item.get("original_filename"))},
            )(),
            reason=reason,
        ),
        source="approved_client_evidence",
        source_type=source_type,
        page_url=clean_text(metadata.get("page_url")),
        source_url=clean_text(metadata.get("source_url")),
        document_title=clean_text(item.get("document_title")),
        original_filename=clean_text(item.get("original_filename")),
        section_title=clean_text(item.get("section_title")),
        content=clean_text(item.get("content_preview")),
        metadata=metadata,
        score=score,
        reason=f"directly linked source; {reason}",
    )


def candidate_from_related_scrape_media(
    *,
    url: str,
    metadata: dict[str, Any],
    source_item: dict[str, Any],
    topic_text: str,
    intent: str,
    require_screenshot: bool,
    require_certificate: bool,
) -> MediaEvidenceCandidate | None:
    role = classify_image(metadata)
    metadata = {
        **metadata,
        "image_role": role,
        "image_category": role,
        "category": role,
    }

    if require_screenshot and role != "screenshot":
        return None

    if require_certificate and role != "certificate":
        return None

    if role in NEGATIVE_CATEGORIES and intent in STRICT_INTENTS:
        return None

    if role in NON_CONTENT_CATEGORIES:
        return None

    score, reason = usefulness_score(
        metadata,
        topic_text=topic_text,
        intent=intent,
        require_screenshot=require_screenshot,
        require_certificate=require_certificate,
    )
    score += 45

    return MediaEvidenceCandidate(
        media_type="image",
        url=url,
        label=candidate_label(
            metadata=metadata,
            document=type(
                "EvidenceDocument",
                (),
                {"original_filename": clean_text(source_item.get("original_filename"))},
            )(),
            reason=reason,
        ),
        source="approved_client_evidence",
        source_type=clean_text(metadata.get("source_type")),
        page_url=clean_text(metadata.get("page_url")),
        source_url=clean_text(metadata.get("source_url") or source_item.get("source_url")),
        document_title=clean_text(source_item.get("document_title")),
        original_filename=clean_text(source_item.get("original_filename")),
        section_title=clean_text(source_item.get("section_title")),
        content=clean_text(source_item.get("content_preview")),
        metadata=metadata,
        score=score,
        reason=f"same source page; {reason}",
    )


def minimum_score_for_intent(
    *,
    intent: str,
    require_website: bool,
    require_screenshot: bool,
    require_certificate: bool,
) -> int:
    if require_certificate or intent == "certificate_evidence":
        return 170

    if require_screenshot:
        return 150

    if intent in {
        "services_evidence",
        "location_evidence",
        "contact_evidence",
        "pricing_evidence",
    }:
        return 150

    if require_website:
        return 80

    return 90


def select_media_evidence_for_bundle(
    *,
    db: Session,
    client_slug: str,
    question: str,
    history: list[ChatHistoryTurn],
    evidence_bundle: dict[str, Any] | None,
    require_website: bool = False,
    require_screenshot: bool = False,
    require_certificate: bool = False,
    limit: int = 3,
) -> list[MediaEvidenceCandidate]:
    items = bundle_items(evidence_bundle)

    if not items:
        return []

    scrape_media = load_latest_scrape_media(client_slug)
    topic_text = topic_text_from_bundle(
        question=question,
        history=history,
        evidence_bundle=evidence_bundle,
    )
    intent = evidence_intent_from_text(
        question=question,
        topic_text=topic_text,
    )

    if require_certificate:
        intent = "certificate_evidence"

    candidates: list[MediaEvidenceCandidate] = []
    seen_urls: set[str] = set()
    source_page_urls = {
        clean_text(item.get("page_url"))
        for item in items
        if clean_text(item.get("page_url"))
    }

    for item in items:
        if require_website and item.get("source_type") != "website_auto_scrape":
            continue

        for key in ["local_static_url", "screenshot_url"]:
            url = clean_text(item.get(key))

            if not url or url in seen_urls:
                continue

            candidate = candidate_from_bundle_media(
                url=url,
                item=item,
                scrape_media=scrape_media,
                topic_text=topic_text,
                intent=intent,
                require_screenshot=require_screenshot,
                require_certificate=require_certificate,
            )

            if candidate is not None:
                candidates.append(candidate)
                seen_urls.add(url)

    if source_page_urls:
        source_item_by_page = {
            clean_text(item.get("page_url")): item
            for item in items
            if clean_text(item.get("page_url"))
        }

        for url, metadata in scrape_media.items():
            if url in seen_urls:
                continue

            page_url = clean_text(metadata.get("page_url"))

            if page_url not in source_page_urls:
                continue

            if require_website and metadata.get("source_type") != "website_auto_scrape":
                continue

            candidate = candidate_from_related_scrape_media(
                url=url,
                metadata=metadata,
                source_item=source_item_by_page.get(page_url, {}),
                topic_text=topic_text,
                intent=intent,
                require_screenshot=require_screenshot,
                require_certificate=require_certificate,
            )

            if candidate is not None:
                candidates.append(candidate)
                seen_urls.add(url)

    candidates.sort(key=lambda candidate: candidate.score, reverse=True)

    threshold = minimum_score_for_intent(
        intent=intent,
        require_website=require_website,
        require_screenshot=require_screenshot,
        require_certificate=require_certificate,
    )

    return [
        candidate
        for candidate in candidates
        if candidate.score >= threshold
    ][:limit]


def select_media_evidence(
    *,
    db: Session,
    client_slug: str,
    question: str,
    history: list[ChatHistoryTurn],
    require_website: bool = False,
    require_screenshot: bool = False,
    require_certificate: bool = False,
    limit: int = 3,
) -> list[MediaEvidenceCandidate]:
    topic_text = topic_text_from_history(
        question=question,
        history=history,
    )
    intent = evidence_intent_from_text(
        question=question,
        topic_text=topic_text,
    )

    if require_certificate:
        intent = "certificate_evidence"

    candidates = build_candidates(
        db=db,
        client_slug=client_slug,
        topic_text=topic_text,
        intent=intent,
        require_website=require_website,
        require_screenshot=require_screenshot,
        require_certificate=require_certificate,
    )

    threshold = minimum_score_for_intent(
        intent=intent,
        require_website=require_website,
        require_screenshot=require_screenshot,
        require_certificate=require_certificate,
    )

    selected = [
        candidate
        for candidate in candidates
        if candidate.score >= threshold
    ][:limit]

    if selected or require_screenshot or require_certificate:
        return selected

    screenshot_candidates = build_candidates(
        db=db,
        client_slug=client_slug,
        topic_text=topic_text,
        intent=intent,
        require_website=True,
        require_screenshot=True,
        require_certificate=False,
    )

    return [
        candidate
        for candidate in screenshot_candidates
        if candidate.score >= 55
    ][: min(limit, 2)]
