from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.chat_service import (  # noqa: E402
    build_instructions,
    company_display_name,
    company_scope_fallback_ar,
    structured_config_answer,
    unavailable_information_message,
)
from app.services.client_config_service import (  # noqa: E402
    MARKAZIA_CAMPAIGN_NAME_AR,
    MARKAZIA_CAMPAIGN_NAME_EN,
    MARKAZIA_CLIENT_SLUG,
    MARKAZIA_COMPANY_NAME_AR,
    MARKAZIA_COMPANY_NAME_EN,
    load_client_config,
    normalize_markazia_customer_visible_text,
)
from app.standalone_db_seed import correct_standalone_metadata  # noqa: E402


CONFIG_PATH = ROOT / "data" / "clients" / MARKAZIA_CLIENT_SLUG / "config.json"
SEED_PATH = ROOT / "data" / "runtime" / "db_seed.json"
BAD_CUSTOMER_TOKENS = (
    "ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“",
    "Ã¢â‚¬â€œ",
    "Ã¢â‚¬â€",
    "2026 Toyota Corolla Hybrid ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“ Smart Driving Campaign",
    "2026 Toyota Corolla Hybrid Ã¢â‚¬â€œ Smart Driving Campaign",
)


def assert_clean_customer_text(text: str) -> None:
    for token in BAD_CUSTOMER_TOKENS:
        assert token not in text
    assert "ماركازيا تويوتا" not in text


def test_config_uses_canonical_branding_and_titles() -> None:
    config = load_client_config(MARKAZIA_CLIENT_SLUG)
    raw_config = CONFIG_PATH.read_text(encoding="utf-8")

    assert config.company_name == MARKAZIA_COMPANY_NAME_EN
    assert config.display_company_name == MARKAZIA_COMPANY_NAME_EN
    assert config.campaign_name == MARKAZIA_CAMPAIGN_NAME_EN
    assert config.campaign_name_ar == MARKAZIA_CAMPAIGN_NAME_AR
    assert MARKAZIA_COMPANY_NAME_AR in config.notes
    assert "Never write \"ماركازيا\" in Arabic." in config.notes
    assert_clean_customer_text(raw_config)
    assert "2026 Toyota Corolla Hybrid – Smart Driving Campaign" not in raw_config


def test_prompt_instructions_include_canonical_bilingual_rules() -> None:
    config = load_client_config(MARKAZIA_CLIENT_SLUG)
    instructions = build_instructions(config)

    assert MARKAZIA_COMPANY_NAME_EN in instructions
    assert MARKAZIA_COMPANY_NAME_AR in instructions
    assert MARKAZIA_CAMPAIGN_NAME_EN in instructions
    assert MARKAZIA_CAMPAIGN_NAME_AR in instructions
    assert "Never write \"ماركازيا\" in Arabic." in instructions
    assert_clean_customer_text(instructions)


def test_deterministic_arabic_responses_are_clean_and_canonical() -> None:
    config = load_client_config(MARKAZIA_CLIENT_SLUG)

    greeting = structured_config_answer(question="مرحبا", config=config)
    assert greeting is not None
    assert MARKAZIA_COMPANY_NAME_AR in greeting.answer
    assert "ماركازيا" not in greeting.answer
    assert_clean_customer_text(greeting.answer)

    fallback = unavailable_information_message(
        question="ما المشكلة",
        company_name=config.company_name,
        config=config,
    )
    assert MARKAZIA_CAMPAIGN_NAME_AR in fallback
    assert MARKAZIA_CAMPAIGN_NAME_EN not in fallback
    assert_clean_customer_text(fallback)

    company_fallback = company_scope_fallback_ar(company_display_name(config))
    assert MARKAZIA_COMPANY_NAME_AR in company_fallback
    assert "ماركازيا" not in company_fallback
    assert_clean_customer_text(company_fallback)


def test_seed_keeps_counts_and_corrected_campaign_title_without_vector_changes() -> None:
    seed_text = SEED_PATH.read_text(encoding="utf-8")
    payload = json.loads(seed_text)

    assert payload["client_slug"] == MARKAZIA_CLIENT_SLUG
    assert len(payload["chunks"]) == 246
    assert len(payload["media_images"]) == 10
    assert sum(1 for item in payload["chunks"] if item.get("embedding") is not None) == 246
    assert all(len(item["embedding"]) == 3072 for item in payload["chunks"] if item.get("embedding") is not None)
    assert MARKAZIA_CAMPAIGN_NAME_EN in seed_text
    assert "2026 Toyota Corolla Hybrid – Smart Driving Campaign" not in seed_text
    assert_clean_customer_text(seed_text)


def test_normalisation_and_startup_correction_are_narrow_and_idempotent() -> None:
    bad = "2026 Toyota Corolla Hybrid Ã¢â‚¬â€œ Smart Driving Campaign / ماركازيا تويوتا"
    once = normalize_markazia_customer_visible_text(bad)
    twice = normalize_markazia_customer_visible_text(once)
    source = inspect.getsource(correct_standalone_metadata).lower()

    assert once == f"{MARKAZIA_CAMPAIGN_NAME_EN} / {MARKAZIA_COMPANY_NAME_AR}"
    assert twice == once
    assert "embedding" not in source
    assert "delete" not in source
    assert "insert" not in source
    assert "sales_callback_requests" not in source
    assert "chat_conversations" not in source
    assert "chatbot_leads" not in source


def test_chat_js_image_loading_block_still_untouched() -> None:
    chat_js = (ROOT / "app" / "static" / "js" / "chat.js").read_text(encoding="utf-8")
    image_block = chat_js[
        chat_js.index("function createImageMediaCard"):
        chat_js.index("function renderMediaItems")
    ]

    assert "window.setTimeout" in image_block
    assert "Image unavailable" in image_block


if __name__ == "__main__":
    tests = [
        test_config_uses_canonical_branding_and_titles,
        test_prompt_instructions_include_canonical_bilingual_rules,
        test_deterministic_arabic_responses_are_clean_and_canonical,
        test_seed_keeps_counts_and_corrected_campaign_title_without_vector_changes,
        test_normalisation_and_startup_correction_are_narrow_and_idempotent,
        test_chat_js_image_loading_block_still_untouched,
    ]
    for test in tests:
        test()
    print(f"{len(tests)} focused Markazia branding/encoding checks passed.")
