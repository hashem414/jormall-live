from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = PROJECT_ROOT / "app"
DATA_DIR = PROJECT_ROOT / "data"
CLIENTS_DIR = DATA_DIR / "clients"
STATIC_DIR = APP_DIR / "static"
CLIENT_ASSETS_DIR = STATIC_DIR / "client_assets"
SCRAPED_SOURCES_DIR = STATIC_DIR / "scraped_sources"

DEFAULT_CLIENT_SLUG = "central-e-commerce-co-ltd"
HEX_COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")
SLUG_PATTERN = re.compile(r"[^a-z0-9]+")
SAFE_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(slots=True)
class ClientConfig:
    company_name: str
    client_slug: str
    assistant_name: str
    logo_url: str | None
    favicon_url: str | None
    website_url: str
    primary_color: str
    secondary_color: str
    button_color: str
    background_color: str
    display_company_name: str = ""
    chatbot_type: str = "campaign"
    campaign_name: str = ""
    campaign_name_ar: str = ""
    campaign_description: str = ""
    campaign_objective: str = ""
    campaign_start_date: str = ""
    campaign_end_date: str = ""
    campaign_offer_details: str = ""
    campaign_creation_process_en: str = ""
    campaign_creation_process_ar: str = ""
    campaign_hosting_terms_en: str = ""
    campaign_hosting_terms_ar: str = ""
    campaign_gpt_coverage_en: str = ""
    campaign_gpt_coverage_ar: str = ""
    campaign_availability: str = ""
    campaign_call_to_action: str = ""
    campaign_language: str = ""
    opening_message_en: str = ""
    opening_message_ar: str = ""
    contact_info: str = ""
    scrape_website: bool = True
    scrape_depth: str = "shallow"
    website_scrape_active: bool = False
    website_scrape_status: str = "missing"
    website_scrape_error: str = ""
    business_type: str = "Not specified"
    chatbot_tone: str = "Professional and helpful"
    chatbot_goal: str = "Answer questions from approved sources"
    suggested_questions: dict[str, list[str]] = field(default_factory=dict)
    starter_question_items: list[dict[str, str]] = field(default_factory=list)
    starter_question_validation: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    footer_text_en: str = ""
    footer_text_ar: str = ""
    lead_consent_version: str = ""
    prechat_legal_mode: str = "explicit_consent"
    lead_notice_version: str = ""
    contact_details: dict[str, str] = field(default_factory=dict)
    do_not_answer_rules: str = ""
    notes: str = ""
    allowed_embed_origins: list[str] = field(default_factory=list)


def slugify_company_name(company_name: str) -> str:
    cleaned = company_name.strip().lower()
    cleaned = SLUG_PATTERN.sub("-", cleaned)
    cleaned = cleaned.strip("-")

    return cleaned[:80] or DEFAULT_CLIENT_SLUG


def sanitize_filename(filename: str) -> str:
    base_name = Path(filename).name.strip()
    safe_name = SAFE_FILENAME_PATTERN.sub("_", base_name)
    safe_name = safe_name.strip("._")

    return safe_name[:160] or "uploaded_file"


def validate_hex_color(value: str, field_name: str) -> str:
    cleaned = value.strip()

    if not HEX_COLOR_PATTERN.fullmatch(cleaned):
        raise ValueError(f"{field_name} must be a hex color like #2575b6.")

    return cleaned.lower()


def normalize_suggested_questions(
    values: dict[str, list[str]] | list[str] | str | None,
    *,
    company_name: str | None = None,
    fill_defaults: bool = True,
) -> dict[str, list[str]]:
    if values is None:
        if not fill_defaults:
            return {"en": [], "ar": []}

        return {
            "en": generic_suggested_questions(company_name or "this company"),
            "ar": [],
        }

    if isinstance(values, dict):
        english = values.get("en") or []
        arabic = values.get("ar") or []
    elif isinstance(values, str):
        english = values.splitlines()
        arabic = []
    else:
        english = values
        arabic = []

    english_questions = [value.strip() for value in english if value and value.strip()]
    arabic_questions = [value.strip() for value in arabic if value and value.strip()]

    if fill_defaults and not english_questions:
        english_questions = generic_suggested_questions(company_name or "this company")

    if fill_defaults and len(english_questions) < 4:
        english_questions = (
            english_questions
            + generic_suggested_questions(company_name or "this company")
        )

    english_questions = unique_keep_order(english_questions)[:4]
    arabic_questions = unique_keep_order(arabic_questions)[:4]

    return {
        "en": english_questions,
        "ar": arabic_questions,
    }


def parse_suggested_questions(values: list[str] | str | None) -> dict[str, list[str]]:
    return normalize_suggested_questions(values)


def unique_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []

    for value in values:
        cleaned = value.strip()
        key = cleaned.lower()

        if not cleaned or key in seen:
            continue

        seen.add(key)
        output.append(cleaned)

    return output


def normalize_origin(value: str) -> str | None:
    parsed = urlparse((value or "").strip())

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return None

    port = f":{parsed.port}" if parsed.port is not None else ""
    return f"{parsed.scheme.lower()}://{hostname}{port}"


def normalize_embed_origins(values: object) -> list[str]:
    if isinstance(values, str):
        candidates = re.split(r"[\s,]+", values)
    elif isinstance(values, list):
        candidates = [str(value) for value in values]
    else:
        candidates = []

    normalized = [
        origin
        for origin in (normalize_origin(value) for value in candidates)
        if origin
    ]
    return unique_keep_order(normalized)


def generic_suggested_questions(company_name: str) -> list[str]:
    return [
        f"What services does {company_name} provide?",
        f"What are {company_name}'s working hours?",
        f"How can I contact {company_name}?",
        f"Where is {company_name} located?",
    ]


def default_assistant_name(company_name: str) -> str:
    return f"{company_name.strip() or 'Client'} Assistant"


def normalize_chatbot_type(
    value: object,
    *,
    website_url: str = "",
    scrape_website: bool = False,
    website_scrape_active: bool = False,
) -> str:
    cleaned = str(value or "").strip().lower()

    if cleaned in {"campaign", "sales_assistant"}:
        return cleaned

    if website_scrape_active or scrape_website or website_url.strip():
        return "sales_assistant"

    return "campaign"


def normalize_campaign_language(value: object) -> str:
    cleaned = str(value or "").strip().lower()
    mapping = {
        "arabic": "ar",
        "ar": "ar",
        "english": "en",
        "en": "en",
        "arabic and english": "bilingual",
        "english and arabic": "bilingual",
        "bilingual": "bilingual",
    }
    return mapping.get(cleaned, cleaned if cleaned in {"ar", "en", "bilingual"} else "")


def campaign_language_label(value: object) -> str:
    return {
        "ar": "Arabic",
        "en": "English",
        "bilingual": "Arabic and English",
    }.get(normalize_campaign_language(value), "")


def client_data_dir(client_slug: str) -> Path:
    return CLIENTS_DIR / client_slug


def client_uploads_dir(client_slug: str) -> Path:
    return client_data_dir(client_slug) / "uploads"


def client_approved_dir(client_slug: str) -> Path:
    return client_data_dir(client_slug) / "approved"


def client_scraped_dir(client_slug: str) -> Path:
    return client_data_dir(client_slug) / "scraped"


def client_generated_dir(client_slug: str) -> Path:
    return client_data_dir(client_slug) / "generated"


def client_assets_dir(client_slug: str) -> Path:
    return CLIENT_ASSETS_DIR / client_slug


def client_scraped_sources_dir(client_slug: str) -> Path:
    return SCRAPED_SOURCES_DIR / client_slug


def ensure_client_directories(client_slug: str) -> None:
    for directory in [
        client_uploads_dir(client_slug),
        client_approved_dir(client_slug),
        client_scraped_dir(client_slug),
        client_generated_dir(client_slug),
        client_assets_dir(client_slug),
        client_scraped_sources_dir(client_slug) / "images",
        client_scraped_sources_dir(client_slug) / "screenshots",
        client_scraped_sources_dir(client_slug) / "videos",
        client_scraped_sources_dir(client_slug) / "document_images",
    ]:
        directory.mkdir(parents=True, exist_ok=True)


def static_url_for(path: Path) -> str:
    relative_path = path.relative_to(STATIC_DIR)
    return "/static/" + relative_path.as_posix()


def save_binary_file(stream: BinaryIO, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)

    with destination.open("wb") as output:
        shutil.copyfileobj(stream, output)


def save_client_config(config: ClientConfig) -> Path:
    ensure_client_directories(config.client_slug)
    config_path = client_data_dir(config.client_slug) / "config.json"
    config_path.write_text(
        json.dumps(asdict(config), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return config_path


def load_client_config(client_slug: str | None = None) -> ClientConfig:
    slug = client_slug or DEFAULT_CLIENT_SLUG
    config_path = client_data_dir(slug) / "config.json"

    if not config_path.exists():
        raise FileNotFoundError(f"Client config not found for '{slug}'.")

    payload = json.loads(config_path.read_text(encoding="utf-8"))

    company_name = payload["company_name"]
    assistant_name = payload.get("assistant_name")
    if isinstance(assistant_name, dict):
        assistant_name = assistant_name.get("en") or assistant_name.get("ar")
    assistant_name = str(assistant_name or default_assistant_name(company_name)).strip()
    suggested_questions = normalize_suggested_questions(
        payload.get("suggested_questions"),
        company_name=company_name,
        fill_defaults=False,
    )

    if not suggested_questions.get("ar"):
        suggested_questions["ar"] = []

    chatbot_type = normalize_chatbot_type(
        payload.get("chatbot_type"),
        website_url=payload.get("website_url") or "",
        scrape_website=bool(
            payload.get(
                "scrape_website",
                bool(payload.get("website_url")),
            )
        ),
        website_scrape_active=bool(payload.get("website_scrape_active", False)),
    )

    return ClientConfig(
        company_name=company_name,
        client_slug=payload["client_slug"],
        chatbot_type=chatbot_type,
        campaign_name=payload.get("campaign_name") or "",
        campaign_name_ar=payload.get("campaign_name_ar") or "",
        campaign_description=payload.get("campaign_description") or "",
        campaign_objective=payload.get("campaign_objective") or "",
        campaign_start_date=payload.get("campaign_start_date") or "",
        campaign_end_date=payload.get("campaign_end_date") or "",
        campaign_offer_details=payload.get("campaign_offer_details") or "",
        campaign_creation_process_en=payload.get("campaign_creation_process_en") or "",
        campaign_creation_process_ar=payload.get("campaign_creation_process_ar") or "",
        campaign_hosting_terms_en=payload.get("campaign_hosting_terms_en") or "",
        campaign_hosting_terms_ar=payload.get("campaign_hosting_terms_ar") or "",
        campaign_gpt_coverage_en=payload.get("campaign_gpt_coverage_en") or "",
        campaign_gpt_coverage_ar=payload.get("campaign_gpt_coverage_ar") or "",
        campaign_availability=payload.get("campaign_availability") or "",
        campaign_call_to_action=payload.get("campaign_call_to_action") or "",
        campaign_language=normalize_campaign_language(payload.get("campaign_language")),
        opening_message_en=payload.get("opening_message_en") or "",
        opening_message_ar=payload.get("opening_message_ar") or "",
        assistant_name=assistant_name,
        logo_url=payload.get("logo_url"),
        favicon_url=payload.get("favicon_url") or "/static/images/favicon.png",
        website_url=payload.get("website_url") or "",
        contact_info=payload.get("contact_info") or "",
        primary_color=payload.get("primary_color") or "#2575b6",
        secondary_color=payload.get("secondary_color") or "#4aa3df",
        button_color=payload.get("button_color") or "#2575b6",
        background_color=payload.get("background_color") or "#ffffff",
        display_company_name=payload.get("display_company_name") or "",
        scrape_website=bool(
            payload.get(
                "scrape_website",
                bool(payload.get("website_url")),
            )
        ),
        scrape_depth=payload.get("scrape_depth") or "shallow",
        website_scrape_active=bool(payload.get("website_scrape_active", False)),
        website_scrape_status=payload.get("website_scrape_status") or (
            "active"
            if payload.get("website_scrape_active")
            else ("disabled" if not payload.get("scrape_website", bool(payload.get("website_url"))) else "missing")
        ),
        website_scrape_error=payload.get("website_scrape_error") or "",
        business_type=payload.get("business_type") or payload.get("industry") or "Not specified",
        chatbot_tone=payload.get("chatbot_tone") or "Professional and helpful",
        chatbot_goal=payload.get("chatbot_goal") or "Answer questions from approved sources",
        suggested_questions=suggested_questions,
        starter_question_items=[
            {
                str(key): str(value)
                for key, value in item.items()
                if value is not None
            }
            for item in (payload.get("starter_question_items") or [])
            if isinstance(item, dict)
        ],
        starter_question_validation={
            language: [
                item
                for item in items
                if isinstance(item, dict)
            ]
            for language, items in (payload.get("starter_question_validation") or {}).items()
            if isinstance(items, list)
        },
        footer_text_en=str(payload.get("footer_text_en") or ""),
        footer_text_ar=str(payload.get("footer_text_ar") or ""),
        lead_consent_version=str(payload.get("lead_consent_version") or ""),
        prechat_legal_mode=str(payload.get("prechat_legal_mode") or "explicit_consent"),
        lead_notice_version=str(payload.get("lead_notice_version") or ""),
        contact_details={
            str(key): str(value)
            for key, value in (payload.get("contact_details") or {}).items()
            if value is not None
        }
        if isinstance(payload.get("contact_details"), dict)
        else {},
        do_not_answer_rules=payload.get("do_not_answer_rules") or "",
        notes=payload.get("notes") or "",
        allowed_embed_origins=normalize_embed_origins(
            payload.get("allowed_embed_origins")
        ),
    )
