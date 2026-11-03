from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch

from app.answers.orchestration import (
    encode_event as encode_chat_event,
    website_not_scraped_message,
)
from app.answers.policy import ChatResult, ChatSource, build_chat_result, get_no_answer_message
from app.api.public_chat import (
    canonicalize_stream_line,
    encode_event as encode_public_event,
)
from app.services.client_config_service import load_client_config
from app.services.public_branding_service import (
    PublicBrandingStreamGuard,
    canonicalize_public_branding,
)
from app.source_seed_builder import apply_authoritative_sources
from app.standalone_db_seed import SEED_PATH


ROOT = Path(__file__).resolve().parents[1]
FORMER_ENGLISH_NAME = "Central E-Commerce Co. Ltd."
FORMER_ARABIC_NAME = "الشركة المركزية للتجارة الإلكترونية"


def test_client_config_uses_only_the_public_company_name() -> None:
    config = load_client_config("central-e-commerce-co-ltd")

    assert config.company_name == "JorMall"
    assert "JorMall" in config.footer_text_en
    assert FORMER_ENGLISH_NAME not in config.footer_text_en
    assert "جورمول" in config.footer_text_ar
    assert "JorMall" not in config.footer_text_ar
    assert FORMER_ARABIC_NAME not in config.footer_text_ar


def test_english_opening_message_lists_the_three_key_benefits() -> None:
    config = load_client_config("central-e-commerce-co-ltd")

    assert config.opening_message_en == (
        "**JorMall Interactive Campaign Chatbot – Key Benefits**\n\n"
        "**1. Turn campaigns into interactive experiences**\n"
        "Transform promotional campaigns from one-way messages into interactive customer experiences.\n\n"
        "**2. Give customers instant access to campaign information**\n"
        "Customers can open the chatbot link from an SMS, social media post, digital advertisement, "
        "or other promotion to learn about the offer, product, service, event, prices, validity, terms, "
        "locations, and next steps.\n\n"
        "**3. Answer questions and guide customer action**\n"
        "The chatbot answers common questions, directs customers to the appropriate contact or "
        "registration channel, and helps increase campaign engagement."
    )


def test_ui_fallbacks_do_not_expose_the_former_company_name() -> None:
    template = (ROOT / "app/templates/chat.html").read_text(encoding="utf-8")
    javascript = (ROOT / "app/static/js/chat.js").read_text(encoding="utf-8-sig")

    for text in (template, javascript):
        assert FORMER_ENGLISH_NAME not in text
        assert FORMER_ARABIC_NAME not in text

    assert template.count('data-i18n-alt="companyLogoAlt"') == 2
    assert template.count('data-i18n-title=') == 2
    assert "document.title = translations[language].pageTitle" in javascript

    arabic_lines = "\n".join(
        line for line in javascript.splitlines()
        if re.search(r"[\u0600-\u06FF]", line)
    )
    assert "JorMall" not in arabic_lines


def test_public_branding_guard_canonicalizes_aliases_and_preserves_addresses() -> None:
    english = canonicalize_public_branding(
        f"Jormall ({FORMER_ENGLISH_NAME}) can help. Contact info@jormall.com.",
        language="en",
    )
    arabic = canonicalize_public_branding(
        f"مصادر {FORMER_ARABIC_NAME} وفريق JorMall. info@jormall.com",
        language="ar",
    )

    assert english == "JorMall can help. Contact info@jormall.com."
    assert arabic == "مصادر جورمول وفريق جورمول. info@jormall.com"
    assert canonicalize_public_branding(FORMER_ARABIC_NAME, language="en-US") == "JorMall"
    assert canonicalize_public_branding("JorMall", language="ar-JO") == "جورمول"
    assert canonicalize_public_branding(
        f"JorMall, operated by {FORMER_ENGLISH_NAME}, can help.",
        language="en",
    ) == "JorMall can help."
    assert canonicalize_public_branding(
        f"جورمول، التابعة لـ {FORMER_ARABIC_NAME}، تساعدكم.",
        language="ar",
    ) == "جورمول تساعدكم."


def test_every_public_stream_event_applies_the_branding_guard() -> None:
    old_answer = f"Jormall ({FORMER_ENGLISH_NAME})"
    old_arabic_status = f"مصادر {FORMER_ARABIC_NAME}"

    for encoder in (encode_chat_event, encode_public_event):
        answer_event = json.loads(encoder({"type": "replace", "answer": old_answer}))
        status_event = json.loads(encoder({"type": "status", "message": old_arabic_status}))
        assert answer_event["answer"] == "JorMall"
        assert status_event["message"] == "مصادر جورمول"

    nested_event = json.loads(
        encode_public_event(
            {
                "type": "replace",
                "answer": "تفاصيل JorMall",
                "media": [{"label": f"صورة {FORMER_ENGLISH_NAME}"}],
            },
            language="ar",
        )
    )
    assert nested_event["answer"] == "تفاصيل جورمول"
    assert nested_event["media"][0]["label"] == "صورة جورمول"


def test_public_api_applies_the_question_language_to_stream_lines() -> None:
    line = json.dumps(
        {
            "type": "replace",
            "answer": "Thank you for reaching JorMall.",
            "sources": [{"title": FORMER_ENGLISH_NAME}],
        }
    )
    event = json.loads(canonicalize_stream_line(line, question="أرني الشعار"))

    assert event["answer"] == "Thank you for reaching جورمول."
    assert event["sources"][0]["title"] == "جورمول"


def test_stream_guard_handles_names_split_across_deltas() -> None:
    english_guard = PublicBrandingStreamGuard(language="en", tail_token_count=2)
    english_parts = [
        english_guard.feed("JorMall is licensed as Central E-"),
        english_guard.feed("Commerce Co. Ltd. in Jordan."),
        english_guard.flush(),
    ]
    arabic_guard = PublicBrandingStreamGuard(language="ar", tail_token_count=2)
    arabic_parts = [
        arabic_guard.feed("مرحبًا من Jor"),
        arabic_guard.feed("Mall وفريق الشركة المركزية "),
        arabic_guard.feed("للتجارة الإلكترونية."),
        arabic_guard.flush(),
    ]

    english = "".join(english_parts)
    arabic = "".join(arabic_parts)
    assert english == "JorMall is licensed as JorMall in Jordan."
    assert FORMER_ENGLISH_NAME not in "".join(english_parts)
    assert arabic == "مرحبًا من جورمول وفريق جورمول."
    assert "JorMall" not in "".join(arabic_parts)
    assert FORMER_ARABIC_NAME not in "".join(arabic_parts)


def test_arabic_media_fallback_uses_the_arabic_company_name() -> None:
    config = load_client_config("central-e-commerce-co-ltd")

    unavailable = website_not_scraped_message(
        question="أرني صورة الشعار",
        client_config=config,
    )
    no_answer = get_no_answer_message(
        "اعرض صورة من الموقع",
        config.company_name,
        assistant_name=config.assistant_name,
        contact_info=config.contact_info,
    )

    for answer in (unavailable, no_answer):
        assert "جورمول" in answer
        assert "JorMall" not in answer
        assert FORMER_ARABIC_NAME not in answer


def test_nonstream_result_guard_covers_direct_answers_and_sources() -> None:
    old_result = ChatResult(
        answer=f"تفاصيل {FORMER_ENGLISH_NAME}",
        grounded=True,
        disclaimer=None,
        model_called=False,
        sources=[
            ChatSource(
                document_title=FORMER_ENGLISH_NAME,
                section_title="JorMall overview",
                source_reference=FORMER_ARABIC_NAME,
                similarity=0.9,
            )
        ],
    )
    with patch("app.answers.policy._build_chat_result", return_value=old_result):
        result = build_chat_result(question="ما التفاصيل؟", db=object())

    assert result.answer == "تفاصيل جورمول"
    assert result.sources[0].document_title == "جورمول"
    assert result.sources[0].section_title == "جورمول overview"
    assert result.sources[0].source_reference == "جورمول"


def test_effective_knowledge_cannot_reintroduce_the_former_name() -> None:
    effective = apply_authoritative_sources(
        json.loads(SEED_PATH.read_text(encoding="utf-8"))
    )
    text = "\n".join(
        [item["raw_text"] for item in effective["documents"]]
        + [item["content"] for item in effective["chunks"]]
    )

    assert FORMER_ENGLISH_NAME not in text
    assert FORMER_ARABIC_NAME not in text
