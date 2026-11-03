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

DEFAULT_CLIENT_SLUG = "jormall"
HEX_COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")
SLUG_PATTERN = re.compile(r"[^a-z0-9]+")
SAFE_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
MARKAZIA_CLIENT_SLUG = "central-trade-auto-co-markazia-toyota-jordan"
MARKAZIA_COMPANY_NAME_EN = "Markazia Toyota"
MARKAZIA_COMPANY_NAME_AR = "المركزية تويوتا"
MARKAZIA_CAMPAIGN_NAME_EN = "2026 Toyota Corolla Hybrid - Smart Driving Campaign"
MARKAZIA_CAMPAIGN_NAME_AR = "حملة تويوتا كورولا هايبرد 2026 - القيادة الذكية"
MARKAZIA_AR_STARTERS = [
    "ما المواصفات الرئيسية لتويوتا كورولا هايبرد 2026؟",
    "ما الفئات والألوان والمزايا المتوفرة؟",
    "ما خيارات التمويل واستبدال المركبات المتوفرة؟",
    "أرغب أن يتصل بي فريق المبيعات.",
]
MARKAZIA_NOTES = (
    "The chatbot must respond in English or Arabic according to the customer's selected language and maintain the same "
    "language throughout the conversation unless the customer requests a change. Arabic responses must display correctly "
    "from right to left, while English responses must display from left to right.\n\n"
    "Canonical company identity:\n"
    "- In English responses, refer to the company as \"Markazia Toyota\".\n"
    "- In Arabic responses, refer to the company as \"المركزية تويوتا\".\n"
    "- Never write \"ماركازيا\" in Arabic.\n"
    "- Do not translate \"Markazia\" phonetically into Arabic.\n\n"
    "Language consistency:\n"
    "- When the user writes in Arabic, answer fully in Arabic unless a product name or technical term requires English.\n"
    "- Use the Arabic campaign title \"حملة تويوتا كورولا هايبرد 2026 - القيادة الذكية\" in Arabic responses.\n"
    "- Do not insert corrupted or untranslated campaign metadata into Arabic sentences.\n"
    "- Use valid UTF-8 text only.\n\n"
    "Use a professional, welcoming, concise, and sales-supportive tone. Give the direct answer first, followed by "
    "relevant supporting details and a clear next step.\n\n"
    "Explain that the Corolla Hybrid is a self-charging petrol-electric hybrid and does not require connection to an "
    "external charger. Avoid describing it as a fully electric or plug-in vehicle.\n\n"
    "When discussing the vehicle price, say: \"The published starting price is from JOD 23,500. The final price must be "
    "confirmed through a current official quotation.\"\n\n"
    "When discussing warranty, say: \"The published vehicle warranty is 3 years or 100,000 km, and the hybrid-battery "
    "warranty is 7 years or 120,000 km, whichever applicable limit is reached first. Final coverage is governed by the "
    "official warranty terms.\"\n\n"
    "When discussing financing, explain that financial facilities may be available but all conditions must be confirmed "
    "by an authorised Markazia Toyota financial consultant. Never calculate or estimate an instalment unless an approved "
    "calculation tool and current financing terms are provided.\n\n"
    "When customers ask about colours, equipment, grades, upholstery, stock, or delivery, explain that availability "
    "changes and offer to collect their contact information for live confirmation.\n\n"
    "When displaying campaign images, explain that images are illustrative and that the exact colour, upholstery, "
    "accessories, and equipment must be confirmed against the selected vehicle and current Jordan stock.\n\n"
    "The main conversion actions are: request a quotation, book a test drive, request financing assistance, request a "
    "trade-in valuation, call 06-550-8080, or visit the Markazia Toyota showroom on Mecca Street in Amman.\n\n"
    "Always include this qualification when appropriate: \"Prices, specifications, colours, promotions, financing, "
    "warranty application, and availability are subject to confirmation by Central Trade & Auto Co. Terms and conditions apply.\""
)
MARKAZIA_KNOWN_TEXT_REPLACEMENTS = {
    "2026 Toyota Corolla Hybrid ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“ Smart Driving Campaign": MARKAZIA_CAMPAIGN_NAME_EN,
    "2026 Toyota Corolla Hybrid Ã¢â‚¬â€œ Smart Driving Campaign": MARKAZIA_CAMPAIGN_NAME_EN,
    "2026 Toyota Corolla Hybrid – Smart Driving Campaign": MARKAZIA_CAMPAIGN_NAME_EN,
    "ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“": "-",
    "Ã¢â‚¬â€œ": "-",
    "Ã¢â‚¬â€": "-",
    "â€“": "-",
    "â€”": "-",
    "ماركازيا تويوتا": MARKAZIA_COMPANY_NAME_AR,
    "ماركازيا": "المركزية",
    "Ù…Ø§Ø±ÙƒØ§Ø²ÙŠØ§ ØªÙˆÙŠÙˆØªØ§": MARKAZIA_COMPANY_NAME_AR,
    "Ù…Ø§Ø±ÙƒØ§Ø²ÙŠØ§": "المركزية",
}


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
    contact_details: dict[str, str] = field(default_factory=dict)
    include_sales_callback_dashboard: bool = True
    include_chat_history_dashboard: bool = True
    do_not_answer_rules: str = ""
    notes: str = ""
    allowed_embed_origins: list[str] = field(default_factory=list)
    media_retrieval: dict[str, object] = field(default_factory=lambda: {"enabled": False})


DEFAULT_JORMALL_CONFIG = ClientConfig(
    company_name="JorMall",
    client_slug=DEFAULT_CLIENT_SLUG,
    chatbot_type="sales_assistant",
    assistant_name="JorMall Support Assistant",
    logo_url="/static/images/logo.png",
    favicon_url="/static/images/favicon.png",
    website_url="https://jormall-jo.com/",
    contact_info="the company directly",
    scrape_depth="shallow",
    primary_color="#2575b6",
    secondary_color="#4aa3df",
    button_color="#2575b6",
    background_color="#ffffff",
    scrape_website=True,
    website_scrape_active=True,
    website_scrape_status="active",
    website_scrape_error="",
    business_type="E-commerce and SMS services",
    chatbot_tone="Professional and helpful",
    chatbot_goal="Answer service, policy, and support questions",
    suggested_questions={
        "en": [
            "What is Smart Reach SMS?",
            "Does JorMall provide delivery reports?",
            "What are the free SMS bonus percentages?",
            "What are the contract approval requirements?",
        ],
        "ar": [
            "ما هي خدمة Smart Reach SMS؟",
            "هل توفر JorMall تقارير تسليم الرسائل؟",
            "ما هي نسب الرسائل المجانية؟",
            "ما هي متطلبات اعتماد العقود؟",
        ],
    },
    do_not_answer_rules=(
        "Do not answer outside uploaded or approved documents. "
        "Do not invent prices, discounts, policies, or legal claims."
    ),
    notes="Use a professional, helpful tone.",
)


def normalize_markazia_customer_visible_text(value: object) -> object:
    if not isinstance(value, str):
        return value

    normalized = value
    for bad, replacement in MARKAZIA_KNOWN_TEXT_REPLACEMENTS.items():
        normalized = normalized.replace(bad, replacement)
    return normalized


def normalize_markazia_customer_visible_object(value: object) -> object:
    if isinstance(value, str):
        return normalize_markazia_customer_visible_text(value)
    if isinstance(value, list):
        return [normalize_markazia_customer_visible_object(item) for item in value]
    if isinstance(value, dict):
        return {
            key: normalize_markazia_customer_visible_object(item)
            for key, item in value.items()
        }
    return value


def apply_markazia_canonical_payload(payload: dict[str, object]) -> dict[str, object]:
    if payload.get("client_slug") != MARKAZIA_CLIENT_SLUG:
        return payload

    payload = {
        key: normalize_markazia_customer_visible_object(value)
        for key, value in payload.items()
    }
    payload["company_name"] = MARKAZIA_COMPANY_NAME_EN
    payload["display_company_name"] = MARKAZIA_COMPANY_NAME_EN
    payload["campaign_name"] = MARKAZIA_CAMPAIGN_NAME_EN
    payload["campaign_name_ar"] = MARKAZIA_CAMPAIGN_NAME_AR
    payload["notes"] = MARKAZIA_NOTES

    suggested = payload.get("suggested_questions")
    if isinstance(suggested, dict):
        suggested["ar"] = MARKAZIA_AR_STARTERS[:]

    starter_items = payload.get("starter_question_items")
    if isinstance(starter_items, list):
        for index, label in enumerate(MARKAZIA_AR_STARTERS):
            if index < len(starter_items) and isinstance(starter_items[index], dict):
                starter_items[index]["label_ar"] = label

    contact_details = payload.get("contact_details")
    if isinstance(contact_details, dict):
        contact_details["location_ar"] = "معرض المركزية تويوتا، شارع مكة، عمّان، الأردن"

    return payload


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
            language: questions.copy()
            for language, questions in DEFAULT_JORMALL_CONFIG.suggested_questions.items()
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


def contains_arabic(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06ff]", text or ""))


def starter_intent_key(question: str) -> str:
    text = (question or "").strip().lower()
    if not text:
        return ""
    if re.search(r"\b(show|display|see|image|photo|picture|gallery)\b", text) or any(
        term in question
        for term in (
            "\u0627\u0639\u0631\u0636",
            "\u0623\u0631\u0646\u064a",
            "\u0635\u0648\u0631\u0629",
            "\u0635\u0648\u0631",
        )
    ):
        return "image_gallery"
    if re.search(r"\b(spec|specification|specifications|engine|battery|hybrid|charging|transmission)\b", text) or any(
        term in question
        for term in (
            "\u0645\u0648\u0627\u0635\u0641\u0627\u062a",
            "\u0645\u062d\u0631\u0643",
            "\u0628\u0637\u0627\u0631\u064a\u0629",
            "\u0647\u0627\u064a\u0628\u0631\u062f",
            "\u0634\u062d\u0646",
        )
    ):
        return "specifications"
    if (
        re.search(r"\b(grade|grades|trim|trims|colour|colours|color|colors|feature|features)\b", text)
        or any(
            term in question
            for term in (
                "\u0641\u0626\u0627\u062a",
                "\u0623\u0644\u0648\u0627\u0646",
                "\u0645\u0632\u0627\u064a\u0627",
                "\u0645\u064a\u0632\u0627\u062a",
            )
        )
    ):
        has_grade = re.search(r"\b(grade|grades|trim|trims)\b", text) or any(term in question for term in ("\u0641\u0626\u0627\u062a", "\u0641\u0626\u0629"))
        has_colour = re.search(r"\b(colour|colours|color|colors)\b", text) or "\u0623\u0644\u0648\u0627\u0646" in question
        has_feature = re.search(r"\b(feature|features)\b", text) or any(term in question for term in ("\u0645\u0632\u0627\u064a\u0627", "\u0645\u064a\u0632\u0627\u062a"))
        if sum(bool(value) for value in (has_grade, has_colour, has_feature)) >= 2:
            return "grades_colours_features"
        if has_grade:
            return "grades"
        if has_colour:
            return "colours"
        return "features"
    if re.search(r"\b(finance|financing|instalment|installment|trade-in|trade in)\b", text) or any(
        term in question
        for term in (
            "\u062a\u0645\u0648\u064a\u0644",
            "\u0623\u0642\u0633\u0627\u0637",
            "\u0627\u0633\u062a\u0628\u062f\u0627\u0644",
        )
    ):
        return "financing_trade_in"
    if re.search(r"\b(quotation|quote|test drive|book)\b", text) or any(
        term in question
        for term in (
            "\u0639\u0631\u0636 \u0633\u0639\u0631",
            "\u062a\u062c\u0631\u0628\u0629 \u0642\u064a\u0627\u062f\u0629",
            "\u062d\u062c\u0632",
        )
    ):
        return "quotation_test_drive"
    if re.search(r"\b(price|starting|cost|jod)\b", text) or "\u0633\u0639\u0631" in question:
        return "price"
    if re.search(r"\b(warranty|guarantee)\b", text) or any(term in question for term in ("\u0643\u0641\u0627\u0644\u0629", "\u0636\u0645\u0627\u0646")):
        return "warranty"
    if re.search(r"\b(safety|airbag|airbags)\b", text) or any(term in question for term in ("\u0633\u0644\u0627\u0645\u0629", "\u0648\u0633\u0627\u0626\u062f")):
        return "safety"
    if re.search(r"\b(contact|phone|telephone|location|showroom|where)\b", text) or any(
        term in question
        for term in (
            "\u062a\u0648\u0627\u0635\u0644",
            "\u0647\u0627\u062a\u0641",
            "\u0645\u0639\u0631\u0636",
            "\u0645\u0648\u0642\u0639",
        )
    ):
        return "contact"
    if re.search(r"\b(service|services|process|how it works|packages?)\b", text) or any(
        term in question
        for term in (
            "\u062e\u062f\u0645\u0627\u062a",
            "\u0622\u0644\u064a\u0629",
            "\u0628\u0627\u0642\u0627\u062a",
        )
    ):
        return "generic_business"
    return "general"


def starter_id_for_question(question: str, index: int) -> str:
    intent = starter_intent_key(question)
    if intent and intent not in {"general", "generic_business"}:
        return intent
    cleaned = SLUG_PATTERN.sub("_", (question or "").strip().lower()).strip("_")
    return (cleaned[:48] or f"starter_{index + 1}").strip("_")


def derive_arabic_starter_question(english_question: str, config: "ClientConfig | None" = None) -> str:
    intent = starter_intent_key(english_question)
    text = (english_question or "").lower()
    campaign_name = (getattr(config, "campaign_name", "") or "").lower() if config else ""
    is_corolla_campaign = "corolla" in text or "corolla" in campaign_name

    if intent == "specifications":
        return (
            "\u0645\u0627 \u0627\u0644\u0645\u0648\u0627\u0635\u0641\u0627\u062a "
            "\u0627\u0644\u0631\u0626\u064a\u0633\u064a\u0629 \u0644\u062a\u0648\u064a\u0648\u062a\u0627 "
            "\u0643\u0648\u0631\u0648\u0644\u0627 \u0647\u0627\u064a\u0628\u0631\u062f 2026\u061f"
            if is_corolla_campaign
            else "\u0645\u0627 \u0627\u0644\u0645\u0648\u0627\u0635\u0641\u0627\u062a \u0627\u0644\u0631\u0626\u064a\u0633\u064a\u0629\u061f"
        )
    if intent == "grades_colours_features":
        return (
            "\u0645\u0627 \u0627\u0644\u0641\u0626\u0627\u062a \u0648\u0627\u0644\u0623\u0644\u0648\u0627\u0646 "
            "\u0648\u0627\u0644\u0645\u0632\u0627\u064a\u0627 \u0627\u0644\u0645\u062a\u0648\u0641\u0631\u0629\u061f"
        )
    if intent == "grades":
        return "\u0645\u0627 \u0627\u0644\u0641\u0626\u0627\u062a \u0627\u0644\u0645\u062a\u0648\u0641\u0631\u0629\u061f"
    if intent == "colours":
        return "\u0645\u0627 \u0627\u0644\u0623\u0644\u0648\u0627\u0646 \u0627\u0644\u062e\u0627\u0631\u062c\u064a\u0629 \u0627\u0644\u0645\u062a\u0627\u062d\u0629\u061f"
    if intent == "features":
        return "\u0645\u0627 \u0645\u0632\u0627\u064a\u0627 \u0627\u0644\u0645\u0642\u0635\u0648\u0631\u0629 \u0648\u0627\u0644\u062a\u0642\u0646\u064a\u0627\u062a \u0627\u0644\u0645\u062a\u0648\u0641\u0631\u0629\u061f"
    if intent == "financing_trade_in":
        return (
            "\u0645\u0627 \u062e\u064a\u0627\u0631\u0627\u062a \u0627\u0644\u062a\u0645\u0648\u064a\u0644 "
            "\u0648\u0627\u0633\u062a\u0628\u062f\u0627\u0644 \u0627\u0644\u0645\u0631\u0643\u0628\u0627\u062a "
            "\u0627\u0644\u0645\u062a\u0648\u0641\u0631\u0629\u061f"
        )
    if intent == "quotation_test_drive":
        return (
            "\u0647\u0644 \u064a\u0645\u0643\u0646\u0646\u064a \u0637\u0644\u0628 "
            "\u0639\u0631\u0636 \u0633\u0639\u0631 \u0623\u0648 \u062d\u062c\u0632 "
            "\u062a\u062c\u0631\u0628\u0629 \u0642\u064a\u0627\u062f\u0629\u061f"
        )
    if intent == "image_gallery":
        return (
            "\u0627\u0639\u0631\u0636 \u0644\u064a \u062a\u0648\u064a\u0648\u062a\u0627 \u0643\u0648\u0631\u0648\u0644\u0627."
            if is_corolla_campaign
            else "\u0627\u0639\u0631\u0636 \u0644\u064a \u0627\u0644\u0635\u0648\u0631."
        )
    if intent == "price":
        return "\u0643\u0645 \u064a\u0628\u062f\u0623 \u0627\u0644\u0633\u0639\u0631\u061f"
    if intent == "warranty":
        return "\u0645\u0627 \u0627\u0644\u0643\u0641\u0627\u0644\u0629 \u0627\u0644\u0645\u062a\u0648\u0641\u0631\u0629\u061f"
    if intent == "safety":
        return "\u0645\u0627 \u0623\u0646\u0638\u0645\u0629 \u0627\u0644\u0633\u0644\u0627\u0645\u0629 \u0627\u0644\u0645\u062a\u0648\u0641\u0631\u0629\u061f"
    if intent == "contact":
        return "\u0643\u064a\u0641 \u064a\u0645\u0643\u0646\u0646\u064a \u0627\u0644\u062a\u0648\u0627\u0635\u0644 \u0645\u0639\u0643\u0645\u061f"
    return f"\u0645\u0627 \u0627\u0644\u0645\u0639\u0644\u0648\u0645\u0627\u062a \u0627\u0644\u0645\u062a\u0627\u062d\u0629 \u0639\u0646 {english_question.strip()}\u061f"


def normalize_starter_question_items(
    *,
    suggested_questions: dict[str, list[str]] | None,
    starter_question_items: list[dict[str, str]] | None,
    config: "ClientConfig | None" = None,
) -> list[dict[str, str]]:
    existing_items = [
        item for item in (starter_question_items or []) if isinstance(item, dict)
    ]
    normalized_items: list[dict[str, str]] = []
    used_ids: set[str] = set()

    def unique_id(base: str, index: int) -> str:
        candidate = SLUG_PATTERN.sub("_", base.strip().lower()).strip("_") or f"starter_{index + 1}"
        original = candidate
        suffix = 2
        while candidate in used_ids:
            candidate = f"{original}_{suffix}"
            suffix += 1
        used_ids.add(candidate)
        return candidate

    if existing_items:
        for index, item in enumerate(existing_items[:4]):
            label_en = str(item.get("label_en") or item.get("en") or item.get("label") or "").strip()
            label_ar = str(item.get("label_ar") or item.get("ar") or "").strip()
            if not label_en and not label_ar:
                continue
            if label_en and (not label_ar or starter_intent_key(label_en) != starter_intent_key(label_ar)):
                label_ar = derive_arabic_starter_question(label_en, config)
            starter_id = unique_id(
                str(item.get("id") or starter_id_for_question(label_en or label_ar, index)),
                index,
            )
            normalized_items.append(
                {
                    "id": starter_id,
                    "type": str(item.get("type") or ("image" if starter_intent_key(label_en or label_ar) == "image_gallery" else "question")),
                    "label_en": label_en,
                    "label_ar": label_ar,
                }
            )
        if normalized_items:
            return normalized_items

    questions = suggested_questions or {"en": [], "ar": []}
    english = [value.strip() for value in questions.get("en", []) if value and value.strip()]
    arabic = [value.strip() for value in questions.get("ar", []) if value and value.strip()]

    for index, label_en in enumerate(english[:4]):
        intent = starter_intent_key(label_en)
        label_ar = arabic[index] if index < len(arabic) else ""
        if not label_ar or starter_intent_key(label_ar) != intent:
            label_ar = derive_arabic_starter_question(label_en, config)
        starter_id = unique_id(starter_id_for_question(label_en, index), index)
        normalized_items.append(
            {
                "id": starter_id,
                "type": "image" if intent == "image_gallery" else "question",
                "label_en": label_en,
                "label_ar": label_ar,
            }
        )

    if normalized_items:
        return normalized_items

    for index, label_ar in enumerate(arabic[:4]):
        starter_id = unique_id(starter_id_for_question(label_ar, index), index)
        normalized_items.append(
            {
                "id": starter_id,
                "type": "image" if starter_intent_key(label_ar) == "image_gallery" else "question",
                "label_en": "",
                "label_ar": label_ar,
            }
        )

    return normalized_items


def suggested_questions_from_starter_items(
    starter_question_items: list[dict[str, str]],
) -> dict[str, list[str]]:
    return {
        "en": [
            item["label_en"]
            for item in starter_question_items
            if item.get("label_en")
        ][:4],
        "ar": [
            item["label_ar"]
            for item in starter_question_items
            if item.get("label_ar")
        ][:4],
    }


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
        if slug == DEFAULT_CLIENT_SLUG:
            return DEFAULT_JORMALL_CONFIG

        raise FileNotFoundError(f"Client config not found for '{slug}'.")

    payload = apply_markazia_canonical_payload(
        json.loads(config_path.read_text(encoding="utf-8-sig"))
    )

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

    config = ClientConfig(
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
        contact_details={
            str(key): str(value)
            for key, value in (payload.get("contact_details") or {}).items()
            if value is not None
        }
        if isinstance(payload.get("contact_details"), dict)
        else {},
        include_sales_callback_dashboard=bool(
            payload.get("include_sales_callback_dashboard", True)
        ),
        include_chat_history_dashboard=bool(
            payload.get("include_chat_history_dashboard", True)
        ),
        do_not_answer_rules=payload.get("do_not_answer_rules") or "",
        notes=payload.get("notes") or "",
        allowed_embed_origins=normalize_embed_origins(
            payload.get("allowed_embed_origins")
        ),
        media_retrieval=(
            payload.get("media_retrieval")
            if isinstance(payload.get("media_retrieval"), dict)
            else {"enabled": False}
        ),
    )
    config.starter_question_items = normalize_starter_question_items(
        suggested_questions=config.suggested_questions,
        starter_question_items=config.starter_question_items,
        config=config,
    )
    if config.starter_question_items:
        config.suggested_questions = suggested_questions_from_starter_items(
            config.starter_question_items
        )
    return config


def ensure_default_jormall_config() -> None:
    ensure_client_directories(DEFAULT_CLIENT_SLUG)
    config_path = client_data_dir(DEFAULT_CLIENT_SLUG) / "config.json"

    if config_path.exists():
        return

    save_client_config(DEFAULT_JORMALL_CONFIG)
