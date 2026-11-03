from __future__ import annotations

import json
import re
import traceback
from dataclasses import dataclass
from typing import Any, Generator

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document, DocumentChunk
from app.schemas.chat import ChatHistoryTurn
from app.services.client_config_service import (
    DEFAULT_CLIENT_SLUG,
    ClientConfig,
    client_scraped_dir,
    load_client_config,
)
from app.services.chat_service import (
    GroundedModelOutput,
    build_context,
    build_instructions,
    direct_custom_calculation_answer,
    direct_document_sequence_answer,
    direct_table_answer,
    expand_contract_requirement_context,
    expand_document_sequence_context,
    format_generic_contact_info_answer,
    get_no_answer_message,
    get_question_language,
    looks_like_live_data_request,
    structured_config_answer,
    unavailable_information_message,
)
from app.services.conversation_intent_service import (
    ConversationBrainDecision,
    resolve_conversation_intent,
)
from app.services.openai_client import get_openai_client
from app.services.retrieval_service import (
    RetrievedChunk,
    is_metadata_only_chunk,
    retrieve_client_chunks,
)
from app.services.media_evidence_service import (
    MediaEvidenceCandidate,
    select_media_evidence,
    select_media_evidence_for_bundle,
)
from app.services.media_catalog_service import (
    browse_media_catalog,
    extract_specific_media_target,
    format_specific_media_answer,
    search_media_catalog,
)
from app.services.campaign_media_service import (
    approved_media_context_for_query,
    extract_requested_year,
    format_year_mismatch_message,
    media_answer,
    media_context_from_results,
    parse_media_request_intent,
    retrieve_campaign_media,
)
from app.services.product_catalog_service import (
    looks_like_document_pricing_query,
    product_answer_for_query,
    product_reference,
    should_return_product_no_match,
)
from app.services.retrieval_threshold_service import (
    has_strong_context_overlap,
    is_similarity_allowed,
    required_similarity_for_client,
)
from app.services.session_memory_store import format_history_answer


SERVICE_ERROR_EN = (
    "The JorMall assistant is temporarily unavailable. "
    "Please try again later."
)

SERVICE_ERROR_AR = (
    "مساعد JorMall غير متاح مؤقتًا. "
    "يرجى المحاولة مرة أخرى لاحقًا."
)


STATIC_IMAGE_URL_PATTERN = re.compile(
    r"(/static/scraped_sources/(?:[a-z0-9-]+/)?(?:images|screenshots|document_images)/[^\s\"'<>]+?\.(?:png|jpg|jpeg|webp|gif))",
    flags=re.IGNORECASE,
)

STATIC_SCREENSHOT_URL_PATTERN = re.compile(
    r"(/static/scraped_sources/(?:[a-z0-9-]+/)?screenshots/[^\s\"'<>]+?\.(?:png|jpg|jpeg|webp|gif))",
    flags=re.IGNORECASE,
)

VIDEO_URL_PATTERN = re.compile(
    r"(https?://[^\s\"'<>]+?\.(?:mp4|webm|mov|m4v)(?:\?[^\s\"'<>]*)?)",
    flags=re.IGNORECASE,
)

HTTP_URL_PATTERN = re.compile(
    r"(https?://[^\s\"'<>]+)",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class StreamingPlan:
    context: str
    source_map: dict[str, RetrievedChunk]
    chunks: list[RetrievedChunk]


@dataclass(frozen=True, slots=True)
class ResolvedQuestionPlan:
    """
    answer_question:
        The complete standalone question given to the answering model.

    retrieval_question:
        The optimized query used for pgvector retrieval.
    """

    answer_question: str
    retrieval_question: str


class IncrementalAnswerExtractor:
    def __init__(self) -> None:
        self.raw_output = ""
        self.can_answer: bool | None = None
        self.answer_started = False
        self.answer_finished = False
        self.read_position = 0
        self.escape_pending = False
        self.unicode_escape: str | None = None

    def feed(self, delta: str) -> str:
        self.raw_output += delta

        if self.can_answer is None:
            match = re.search(
                r'"can_answer"\s*:\s*(true|false)',
                self.raw_output,
            )

            if match:
                self.can_answer = match.group(1) == "true"

        if self.can_answer is not True:
            return ""

        if not self.answer_started:
            answer_match = re.search(
                r'"answer"\s*:\s*"',
                self.raw_output,
            )

            if answer_match is None:
                return ""

            self.answer_started = True
            self.read_position = answer_match.end()

        if self.answer_finished:
            return ""

        output_parts: list[str] = []

        while self.read_position < len(self.raw_output):
            character = self.raw_output[self.read_position]
            self.read_position += 1

            if self.unicode_escape is not None:
                self.unicode_escape += character

                if len(self.unicode_escape) == 4:
                    try:
                        output_parts.append(
                            chr(int(self.unicode_escape, 16))
                        )
                    except ValueError:
                        pass

                    self.unicode_escape = None

                continue

            if self.escape_pending:
                escape_map = {
                    '"': '"',
                    "\\": "\\",
                    "/": "/",
                    "b": "\b",
                    "f": "\f",
                    "n": "\n",
                    "r": "\r",
                    "t": "\t",
                }

                if character == "u":
                    self.unicode_escape = ""
                else:
                    output_parts.append(
                        escape_map.get(character, character)
                    )

                self.escape_pending = False
                continue

            if character == "\\":
                self.escape_pending = True
                continue

            if character == '"':
                self.answer_finished = True
                break

            output_parts.append(character)

        return "".join(output_parts)


def contains_arabic(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", text))


def get_required_answer_language(question: str) -> str:
    return "Arabic" if contains_arabic(question) else "English"


def get_service_error_message(question: str) -> str:
    if contains_arabic(question):
        return "مساعد JorMall غير متاح مؤقتًا. يرجى المحاولة مرة أخرى لاحقًا."

    return SERVICE_ERROR_EN


def get_client_service_error_message(
    question: str,
    client_config: ClientConfig,
) -> str:
    if client_config.client_slug == DEFAULT_CLIENT_SLUG:
        return get_service_error_message(question)

    if contains_arabic(question):
        return (
            f"مساعد {client_config.company_name} غير متاح مؤقتًا. "
            "يرجى المحاولة لاحقًا."
        )

    return (
        f"The {client_config.company_name} assistant is temporarily unavailable. "
        "Please try again later."
    )


def looks_like_contact_request(text: str) -> bool:
    normalized = text.lower()
    english_match = bool(
        re.search(
            r"\b(contact(?: info| information| details)?|phone(?: number)?|telephone|email|"
            r"call (?:you|markazia|us)|reach (?:you|markazia|you at|us)|whatsapp|"
            r"customer service number|where are you located|where is (?:the )?(?:showroom|branch|office)|"
            r"showroom(?: location)?|branch(?: location)?|office(?: location)?|location)\b",
            normalized,
        )
    )
    arabic_match = any(
        term in text
        for term in [
            "\u062a\u0648\u0627\u0635\u0644",
            "\u0627\u0644\u062a\u0648\u0627\u0635\u0644",
            "\u0627\u062a\u0635\u0644",
            "\u0627\u0644\u0647\u0627\u062a\u0641",
            "\u0631\u0642\u0645",
            "\u0627\u0644\u0631\u0642\u0645",
            "\u0627\u0644\u0645\u0648\u0642\u0639",
            "\u0645\u0648\u0642\u0639\u0643\u0645",
            "\u0627\u0644\u0645\u0639\u0631\u0636",
        ]
    )
    return english_match or arabic_match


def looks_like_callback_request(text: str) -> bool:
    normalized = text.lower()
    return bool(
        re.search(
            r"\b(?:call me|contact me|sales (?:team|representative).*(?:call|contact) me|"
            r"ask sales to (?:call|contact) me|representative to contact me)\b",
            normalized,
        )
    ) or any(
        term in text
        for term in (
            "\u064a\u062a\u0635\u0644 \u0628\u064a",
            "\u064a\u062a\u0635\u0644\u0648\u0627 \u0641\u064a",
            "\u0627\u062a\u0635\u0644\u0648\u0627 \u0628\u064a",
            "\u0645\u0646\u062f\u0648\u0628 \u0645\u0628\u064a\u0639\u0627\u062a",
        )
    )


def format_trusted_contact_answer(
    client_config: ClientConfig,
    question: str = "",
) -> str:
    contact_answer = format_generic_contact_info_answer(
        question=question,
        config=client_config,
    )
    if contact_answer:
        return contact_answer
    return (
        f"I do not have validated contact details for {client_config.company_name} "
        "in the configured company profile."
    )


def encode_event(payload: dict) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
    ) + "\n"


def safe_log_text(value: object) -> str:
    return str(value).encode(
        "ascii",
        errors="backslashreplace",
    ).decode("ascii")


def build_streaming_instructions(client_config: ClientConfig) -> str:
    return (
        build_instructions(client_config)
        + "\n11. Recent conversation context may only help you understand "
        "follow-up references such as 'it', 'that', 'the second one', or "
        "'explain it more'. It is never factual evidence."
        + f"\n12. Approved {client_config.company_name} document excerpts remain the only "
        "factual source of truth."
        + "\n13. If the approved excerpts contain partial but relevant "
        "information, answer using the available approved information. "
        "Do not refuse only because the document may contain more details "
        "outside the provided excerpts."
        + "\n14. For contract approval questions, if the excerpts include "
        "contract requirements, customer contract procedures, signatures, "
        "official stamps, authorization, or approval rules, treat them as "
        "sufficient evidence and summarize the requirements found."
        + "\n15. For broad questions asking for requirements, rules, or procedures, "
        "summarize all relevant requirements found in the approved excerpts."
        + "\n16. When can_answer is true, used_source_ids must contain one or more "
        "valid source IDs exactly as shown in the approved excerpts/context. "
        "Do not invent source IDs."
        + "\n17. If the user asks for proof, source, image evidence, screenshot, "
        "or video, answer naturally from the approved excerpts. Do not invent "
        "image URLs or video URLs. The backend will attach approved media "
        "evidence when available."
        + "\n18. For normal answers, do not expose internal file names, "
        "document titles, source types, DOCX/PDF/XLSX labels, or phrases like "
        "'according to the file' unless the user explicitly asks for source, "
        "proof, evidence, page URL, or file source."
        + "\n19. Return structured fields in this exact order: "
        "can_answer, answer, used_source_ids."
    )


def trim_history_text(
    text: str,
    max_characters: int = 800,
) -> str:
    clean_text = text.strip()

    if len(clean_text) <= max_characters:
        return clean_text

    return clean_text[: max_characters - 20].rstrip() + " ...[trimmed]"


def format_recent_history(
    history: list[ChatHistoryTurn],
) -> str:
    if not history:
        return ""

    lines: list[str] = []
    summary_turn = (
        history[0]
        if history
        and history[0].role == "assistant"
        and history[0].content.startswith("Earlier conversation summary:")
        else None
    )

    if summary_turn is not None:
        lines.append(trim_history_text(summary_turn.content, max_characters=900))

    recent_history = history[1:] if summary_turn is not None else history

    for turn in recent_history[-10:]:
        speaker = "User" if turn.role == "user" else "Assistant"
        lines.append(
            f"{speaker}: {trim_history_text(turn.content)}"
        )

    return "\n".join(lines)


def format_available_source_ids(
    source_map: dict[str, RetrievedChunk],
) -> str:
    if not source_map:
        return "No source IDs available."

    lines: list[str] = []

    for source_id, chunk in source_map.items():
        lines.append(
            "- "
            f"{source_id}: "
            f"{chunk.document_title} · "
            f"{chunk.section_title} "
            f"(similarity={chunk.similarity:.3f})"
        )

    return "\n".join(lines)


def build_model_input(
    *,
    original_question: str,
    answer_question: str,
    context: str,
    source_map: dict[str, RetrievedChunk],
    history: list[ChatHistoryTurn],
    client_config: ClientConfig,
) -> str:
    history_text = format_recent_history(history)

    required_answer_language = get_required_answer_language(
        original_question
    )

    language_instruction = (
        f"REQUIRED ANSWER LANGUAGE: {required_answer_language}\n"
        "Write the complete answer in that language, even if the approved "
        "document excerpts are written in another language.\n"
        "Do not switch answer languages because of the document language."
    )

    question_section = (
        f"Original user question:\n{original_question}\n\n"
        f"Resolved standalone question:\n{answer_question}"
    )

    source_id_section = (
        "Available approved source IDs that may be used in used_source_ids:\n"
        f"{format_available_source_ids(source_map)}"
    )

    if history_text:
        return (
            f"{language_instruction}\n\n"
            "Recent conversation context "
            "(for reference resolution only; not factual evidence):\n"
            f"{history_text}\n\n"
            f"{question_section}\n\n"
            f"{source_id_section}\n\n"
            f"Approved {client_config.company_name} document excerpts:\n{context}"
        )

    return (
        f"{language_instruction}\n\n"
        f"{question_section}\n\n"
        f"{source_id_section}\n\n"
        f"Approved {client_config.company_name} document excerpts:\n{context}"
    )


def looks_like_contract_approval_question(text: str) -> bool:
    normalized = text.lower()

    english_match = (
        "contract" in normalized
        and (
            "approval" in normalized
            or "requirements" in normalized
            or "procedure" in normalized
            or "signature" in normalized
            or "stamp" in normalized
        )
    )

    arabic_match = any(
        phrase in text
        for phrase in [
            "اعتماد العقود",
            "متطلبات العقد",
            "إجراءات العقد",
            "توقيع العقد",
            "ختم الشركة",
            "المدير العام",
        ]
    )

    return english_match or arabic_match


def expand_contract_approval_query(query: str) -> str:
    if not looks_like_contract_approval_question(query):
        return query

    expansion = (
        "contract approval requirements procedures with customers "
        "customer contract approval signature general manager official stamp "
        "authorized representative customer signer commercial register "
        "إجراءات اعتماد العقود مع الزبائن متطلبات اعتماد العقد "
        "توقيع المدير العام ختم الشركة توقيع الزبون المفوض بالتوقيع "
        "السجل التجاري البريد الإلكتروني رقم الهاتف"
    )

    return f"{query} {expansion}"


def expand_document_pricing_query(query: str) -> str:
    if not looks_like_document_pricing_query(query):
        return query

    expansion = (
        "price list pricing rates fees packages plans contract pricing "
        "quantity qty table value total per unit per 1000 invoice validity "
        "bonus usage fee service package current dated latest"
    )

    return f"{query} {expansion}"


def expand_arabic_table_query(query: str) -> str:
    if not contains_arabic(query):
        return query

    arabic_table_terms = (
        "\u062c\u0627\u0626\u0632\u0629",
        "\u062c\u0648\u0627\u0626\u0632",
        "\u0645\u0643\u0627\u0641\u0623\u0629",
        "\u0645\u0643\u0627\u0641\u0622\u062a",
        "\u0628\u0627\u0642\u0629",
        "\u0628\u0627\u0642\u0627\u062a",
        "\u062d\u0632\u0645\u0629",
        "\u062d\u0632\u0645",
        "\u0643\u0645\u064a\u0629",
        "\u0639\u062f\u062f",
        "\u0641\u0626\u0629",
        "\u0641\u0626\u0627\u062a",
        "\u0645\u062a\u0648\u0633\u0637\u0629",
        "\u0643\u0628\u0631\u0649",
        "\u062c\u062f\u0648\u0644",
        "\u0642\u0627\u0631\u0646",
    )
    if not any(term in query for term in arabic_table_terms):
        return query

    expansions = [
        "table rows columns row prize reward rewards bundle package quantity count positioning position tier",
    ]

    if any(term in query for term in ("\u0645\u062a\u0648\u0633\u0637\u0629", "\u0627\u0644\u0645\u062a\u0648\u0633\u0637\u0629")):
        expansions.append("mid tier mid-tier")

    if any(term in query for term in ("\u0643\u0628\u0631\u0649", "\u0627\u0644\u0643\u0628\u0631\u0649", "\u0645\u0644\u064a\u0648\u0646")):
        expansions.append("grand prize headline attraction 1M 1000000")

    for match in re.finditer(r"(\d[\d,]*)\s*\u0623\u0644\u0641", query):
        number = match.group(1).replace(",", "")
        expansions.append(f"{number}K {int(number) * 1000 if number.isdigit() else number}")

    for match in re.finditer(r"(\d[\d,]*)\s*(?:\u0645\u0644\u064a\u0648\u0646|\u0645\u0644\u0627\u064a\u064a\u0646)", query):
        number = match.group(1).replace(",", "")
        expansions.append(f"{number}M {int(number) * 1000000 if number.isdigit() else number}")

    return f"{query} {' '.join(expansions)}"


def looks_like_visual_or_source_request(text: str) -> bool:
    normalized = text.lower()

    english_match = any(
        phrase in normalized
        for phrase in [
            "source",
            "proof",
            "prove",
            "evidence",
            "image",
            "photo",
            "picture",
            "screenshot",
            "show me",
            "where did it come from",
            "where did this come from",
            "from where",
        ]
    )

    arabic_match = any(
        phrase in text
        for phrase in [
            "المصدر",
            "مصدر",
            "دليل",
            "إثبات",
            "يثبت",
            "صورة",
            "لقطة",
            "سكرين",
            "اعرض",
            "ورجيني",
            "من وين",
        ]
    )

    return english_match or arabic_match


def looks_like_video_request(text: str) -> bool:
    normalized = text.lower()

    english_match = any(
        phrase in normalized
        for phrase in [
            "video",
            "watch video",
            "mp4",
            "clip",
            "film",
        ]
    )

    arabic_match = any(
        phrase in text
        for phrase in [
            "فيديو",
            "مقطع",
            "شاهد",
        ]
    )

    return english_match or arabic_match


def looks_like_conversation_memory_question(text: str) -> bool:
    normalized = text.lower()

    english_match = any(
        phrase in normalized
        for phrase in [
            "what was my name",
            "what did i say",
            "what did i ask",
            "what was i interested in",
            "what service was i interested",
            "what did we discuss",
            "summarize our chat",
            "summarize this chat",
            "full chat history",
            "repeat your answer",
            "previous answer",
            "last question",
            "last answer",
            "my name",
        ]
    )

    arabic_match = any(
        phrase in text
        for phrase in [
            "اسمي",
            "ماذا قلت",
            "ماذا سألت",
            "لخص المحادثة",
            "آخر سؤال",
            "آخر إجابة",
        ]
    )

    return english_match or arabic_match


def looks_like_license_question(text: str) -> bool:
    normalized = text.lower()

    english_match = any(
        phrase in normalized
        for phrase in [
            "license",
            "licensed",
            "licence",
            "trc",
            "telecommunications regulatory commission",
            "telecommunications commission",
            "category c",
            "class c",
            "bulk sms",
            "sms vendor",
        ]
    )

    arabic_match = any(
        phrase in text
        for phrase in [
            "رخصة",
            "مرخص",
            "مرخصة",
            "هيئة تنظيم قطاع الاتصالات",
            "هيئة تنظيم الاتصالات",
            "فئة ج",
            "رسائل الجملة",
        ]
    )

    return english_match or arabic_match


def expand_visual_evidence_query(query: str) -> str:
    if not (
        looks_like_visual_or_source_request(query)
        or looks_like_video_request(query)
        or looks_like_license_question(query)
    ):
        return query

    generic_evidence_terms = (
        " website image evidence local static URL original image URL "
        "website screenshot evidence extracted image text OCR source proof "
        "Website Image Evidence Website Screenshot Evidence "
        "Local static URL Original image URL Extracted image text "
        "دليل صورة مصدر لقطة شاشة"
    )

    video_terms = ""
    if looks_like_video_request(query):
        video_terms = (
            " website video evidence video URL MP4 Watch a video "
            "Website Video Evidence Video URL "
            "فيديو رابط الفيديو"
        )

    license_terms = ""
    if looks_like_license_question(query):
        license_terms = (
            " JorMall license licensed Telecommunications Regulatory Commission "
            "TRC General Category Telecommunications License Category C Class C "
            "licensed bulk SMS vendor "
            "هيئة تنظيم قطاع الاتصالات مرخص رخصة الاتصالات الفئوية العامة "
            "فئة ج الشركة المركزية للتجارة الإلكترونية رسائل الجملة"
        )

    return f"{query}{generic_evidence_terms}{video_terms}{license_terms}"


def expand_retrieval_query(query: str) -> str:
    expanded_query = expand_contract_approval_query(query)
    expanded_query = expand_document_pricing_query(expanded_query)
    expanded_query = expand_arabic_table_query(expanded_query)
    expanded_query = expand_campaign_vehicle_query(expanded_query)
    expanded_query = expand_visual_evidence_query(expanded_query)

    return expanded_query


def expand_campaign_vehicle_query(query: str) -> str:
    normalized = query.lower()
    expansions: list[str] = []

    domain_terms = (
        "grade", "grades", "trim", "trims", "variant", "variants",
        "colour", "colours", "color", "colors", "spec", "specs",
        "specification", "specifications", "feature", "features",
        "engine", "battery", "hybrid", "charging", "transmission",
        "wheel drive", "airbag", "airbags", "safety", "warranty",
        "finance", "financing", "instalment", "installment",
        "trade-in", "trade in", "quotation", "quote", "test drive",
        "moonroof", "touchscreen", "carplay", "android auto",
    )
    arabic_domain_terms = (
        "\u0641\u0626\u0627\u062a", "\u0641\u0626\u0629", "\u0627\u0644\u0641\u0626\u0627\u062a",
        "\u0645\u0648\u0627\u0635\u0641\u0627\u062a", "\u0627\u0644\u0645\u0648\u0627\u0635\u0641\u0627\u062a",
        "\u0623\u0644\u0648\u0627\u0646", "\u0627\u0644\u0623\u0644\u0648\u0627\u0646",
        "\u0645\u0632\u0627\u064a\u0627", "\u0627\u0644\u0645\u0632\u0627\u064a\u0627",
        "\u0645\u062d\u0631\u0643", "\u0628\u0637\u0627\u0631\u064a\u0629", "\u0647\u0627\u064a\u0628\u0631\u062f",
        "\u0634\u062d\u0646", "\u0646\u0627\u0642\u0644", "\u0633\u0644\u0627\u0645\u0629",
        "\u0643\u0641\u0627\u0644\u0629", "\u0636\u0645\u0627\u0646", "\u062a\u0645\u0648\u064a\u0644",
        "\u0623\u0642\u0633\u0627\u0637", "\u0627\u0633\u062a\u0628\u062f\u0627\u0644",
        "\u0639\u0631\u0636 \u0633\u0639\u0631", "\u062a\u062c\u0631\u0628\u0629 \u0642\u064a\u0627\u062f\u0629",
    )
    if not (
        any(term in normalized for term in domain_terms)
        or any(term in query for term in arabic_domain_terms)
    ):
        return query

    if any(term in normalized for term in ("grade", "grades", "trim", "trims", "variant", "variants")) or any(term in query for term in ("\u0641\u0626\u0627\u062a", "\u0627\u0644\u0641\u0626\u0627\u062a")):
        expansions.append("Models Grades Price Positioning Toyota Corolla HEV Mid-Grade HEV High-Grade final equipment availability")
    if any(term in normalized for term in ("colour", "colours", "color", "colors")) or any(term in query for term in ("\u0623\u0644\u0648\u0627\u0646", "\u0627\u0644\u0623\u0644\u0648\u0627\u0646")):
        expansions.append("Exterior Design Colours Pearl White Metallic Silver Black Red Dark Grey Blue illustrative colour families official colour names current availability confirm stock")
    if any(term in normalized for term in ("spec", "specs", "specification", "specifications", "engine", "battery", "hybrid", "charging", "transmission", "wheel drive")) or any(term in query for term in ("\u0645\u0648\u0627\u0635\u0641\u0627\u062a", "\u0645\u062d\u0631\u0643", "\u0628\u0637\u0627\u0631\u064a\u0629", "\u0647\u0627\u064a\u0628\u0631\u062f", "\u0634\u062d\u0646", "\u0646\u0627\u0642\u0644")):
        expansions.append("Main Technical Specifications compact hybrid sedan self-charging petrol-electric 1.8-litre four-cylinder 97 hp 142 Nm 71 hp 163 Nm lithium-ion CVT front-wheel drive Normal Eco Sport Electric no external charging")
    if any(term in normalized for term in ("feature", "features", "touchscreen", "carplay", "android auto", "moonroof", "parking", "usb", "bluetooth")) or any(term in query for term in ("\u0645\u0632\u0627\u064a\u0627", "\u0627\u0644\u0645\u0632\u0627\u064a\u0627", "\u0627\u0644\u0645\u0642\u0635\u0648\u0631\u0629")):
        expansions.append("Interior Comfort Technology 8-inch touchscreen Apple CarPlay Android Auto Bluetooth USB speakers parking sensors smart keyless entry push-button start moonroof High-Grade")
    if any(term in normalized for term in ("safety", "airbag", "airbags", "abs", "isofix", "stability")) or any(term in query for term in ("\u0633\u0644\u0627\u0645\u0629", "\u0648\u0633\u0627\u0626\u062f")):
        expansions.append("Safety Driver Confidence eight airbags ABS EBD HAC VSC traction control tyre pressure warning ISOFIX responsible attentive driving")
    if any(term in normalized for term in ("warranty", "guarantee")) or any(term in query for term in ("\u0643\u0641\u0627\u0644\u0629", "\u0636\u0645\u0627\u0646")):
        expansions.append("Warranty Ownership Support 3 years 100,000 km hybrid-battery warranty 7 years 120,000 km official warranty terms exclusions maintenance final sales agreement")
    if any(term in normalized for term in ("finance", "financing", "instalment", "installment", "monthly", "down payment", "trade-in", "trade in")) or any(term in query for term in ("\u062a\u0645\u0648\u064a\u0644", "\u0623\u0642\u0633\u0627\u0637", "\u0627\u0633\u062a\u0628\u062f\u0627\u0644")):
        expansions.append("Financial Facilities Trade-In flexible monthly instalments in-house financing interest-free promotions when available down-payment up to 24 months selected campaigns subject to approval inspection valuation final acceptance financial team")
    if any(term in normalized for term in ("quotation", "quote", "test drive", "call", "contact", "showroom")) or any(term in query for term in ("\u0639\u0631\u0636 \u0633\u0639\u0631", "\u062a\u062c\u0631\u0628\u0629 \u0642\u064a\u0627\u062f\u0629", "\u064a\u062a\u0635\u0644", "\u0647\u0627\u062a\u0641", "\u0645\u0639\u0631\u0636")):
        expansions.append("quotation test drive financing assistance trade-in valuation sales representative Telephone 06-550-8080 Markazia Toyota showroom Mecca Street Amman appointments hours availability confirmed")

    if not expansions:
        return query
    return f"{query} {' '.join(expansions)}"


def looks_like_campaign_vehicle_text_query(query: str) -> bool:
    normalized = query.lower()
    return any(
        term in normalized
        for term in (
            "grade", "grades", "trim", "colour", "colours", "color", "colors",
            "spec", "specs", "specification", "specifications", "feature",
            "features", "engine", "battery", "hybrid", "charging",
            "transmission", "safety", "airbag", "warranty", "finance",
            "financing", "trade-in", "trade in", "quotation", "quote",
            "test drive", "moonroof", "touchscreen", "carplay", "android auto",
        )
    ) or any(
        term in query
        for term in (
            "\u0641\u0626\u0627\u062a", "\u0627\u0644\u0641\u0626\u0627\u062a",
            "\u0645\u0648\u0627\u0635\u0641\u0627\u062a", "\u0623\u0644\u0648\u0627\u0646",
            "\u0627\u0644\u0623\u0644\u0648\u0627\u0646", "\u0645\u0632\u0627\u064a\u0627",
            "\u0645\u062d\u0631\u0643", "\u0628\u0637\u0627\u0631\u064a\u0629",
            "\u0647\u0627\u064a\u0628\u0631\u062f", "\u0634\u062d\u0646",
            "\u0646\u0627\u0642\u0644", "\u0633\u0644\u0627\u0645\u0629",
            "\u0648\u0633\u0627\u0626\u062f", "\u0643\u0641\u0627\u0644\u0629",
            "\u0636\u0645\u0627\u0646", "\u062a\u0645\u0648\u064a\u0644",
            "\u0623\u0642\u0633\u0627\u0637", "\u0627\u0633\u062a\u0628\u062f\u0627\u0644",
            "\u0639\u0631\u0636 \u0633\u0639\u0631", "\u062a\u062c\u0631\u0628\u0629 \u0642\u064a\u0627\u062f\u0629",
        )
    )


def prefers_website_scrape_sources(question: str) -> bool:
    return has_any_phrase(
        question,
        (
            "website",
            "web page",
            "page url",
            "source url",
            "website scrape",
            "scraped website",
            "on your site",
            "from your site",
        ),
    )


def prioritize_website_scrape_chunks(
    *,
    question: str,
    chunks: list[RetrievedChunk],
) -> list[RetrievedChunk]:
    if not prefers_website_scrape_sources(question):
        return chunks

    website_chunks = [
        chunk
        for chunk in chunks
        if chunk.metadata.get("source_type") == "website_auto_scrape"
    ]

    if not website_chunks:
        return chunks

    ordered_chunks = website_chunks + [
        chunk
        for chunk in chunks
        if chunk.metadata.get("source_type") != "website_auto_scrape"
    ]
    seen_chunk_ids: set[str] = set()
    unique_chunks: list[RetrievedChunk] = []

    for chunk in ordered_chunks:
        chunk_id = str(chunk.chunk_id)

        if chunk_id in seen_chunk_ids:
            continue

        seen_chunk_ids.add(chunk_id)
        unique_chunks.append(chunk)

    return unique_chunks


def prepare_streaming_plan(
    *,
    retrieval_question: str,
    db: Session,
    client_slug: str = DEFAULT_CLIENT_SLUG,
) -> StreamingPlan | None:
    client_config = load_client_config(client_slug)
    expanded_retrieval_question = expand_retrieval_query(
        retrieval_question
    )

    retrieval = retrieve_client_chunks(
        question=expanded_retrieval_question,
        db=db,
        top_k=(
            min(max(settings.retrieval_top_k, 10), 10)
            if prefers_website_scrape_sources(retrieval_question)
            else min(max(settings.retrieval_top_k, 8), 10)
            if looks_like_campaign_vehicle_text_query(retrieval_question)
            else settings.retrieval_top_k
        ),
        client_slug=client_slug,
    )

    retrieval_results = retrieval.results

    if not client_config.website_scrape_active:
        retrieval_results = [
            chunk
            for chunk in retrieval_results
            if chunk.metadata.get("source_type") != "website_auto_scrape"
        ]

    if not retrieval_results:
        print(f"[{client_slug} retrieval] No results.")
        return None

    best_result = retrieval_results[0]
    required_similarity = required_similarity_for_client(
        question=retrieval_question,
        chunk_language=best_result.language,
        client_slug=client_slug,
    )

    print(
        f"[{client_slug} retrieval] "
        f"query={safe_log_text(repr(expanded_retrieval_question))}, "
        f"best_title={safe_log_text(repr(best_result.document_title))}, "
        f"best_section={safe_log_text(repr(best_result.section_title))}, "
        f"best_language={safe_log_text(repr(best_result.language))}, "
        f"best_similarity={best_result.similarity:.4f}, "
        f"required_similarity={required_similarity:.4f}"
    )

    if not is_similarity_allowed(
        similarity=best_result.similarity,
        question=retrieval_question,
        chunk_language=best_result.language,
        client_slug=client_slug,
    ):
        print(f"[{client_slug} retrieval] Rejected because similarity is too low.")
        return None

    if not (
        has_strong_context_overlap(
            question=retrieval_question,
            chunks=retrieval_results,
            client_config=client_config,
        )
        or (
            expanded_retrieval_question != retrieval_question
            and has_strong_context_overlap(
                question=expanded_retrieval_question,
                chunks=retrieval_results,
                client_config=client_config,
            )
        )
    ):
        print(f"[{client_slug} retrieval] Rejected by strict RAG relevance gate.")
        return None

    context_chunks = expand_contract_requirement_context(
        retrieved_chunks=retrieval_results,
        db=db,
        client_slug=client_slug,
    )
    context_chunks = expand_document_sequence_context(
        question=retrieval_question,
        retrieved_chunks=context_chunks,
        db=db,
        client_slug=client_slug,
    )
    context_chunks = prioritize_website_scrape_chunks(
        question=retrieval_question,
        chunks=context_chunks,
    )

    context, source_map = build_context(context_chunks)

    print(
        f"[{client_slug} retrieval] "
        f"context_chunks={len(context_chunks)}, "
        f"source_ids={list(source_map.keys())}"
    )

    return StreamingPlan(
        context=context,
        source_map=source_map,
        chunks=context_chunks,
    )


def has_active_website_chunks(*, db: Session, client_slug: str) -> bool:
    return bool(
        db.scalar(
            select(DocumentChunk.id)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                DocumentChunk.client_slug == client_slug,
                Document.client_slug == client_slug,
                Document.status == "active",
                Document.visibility == "client",
                DocumentChunk.chunk_metadata["source_type"].astext == "website_auto_scrape",
            )
            .limit(1)
        )
    )


def has_active_client_chunks(*, db: Session, client_slug: str) -> bool:
    return bool(
        db.scalar(
            select(DocumentChunk.id)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                DocumentChunk.client_slug == client_slug,
                Document.client_slug == client_slug,
                Document.status == "active",
                Document.visibility == "client",
            )
            .limit(1)
        )
    )


def website_not_scraped_message(client_config: ClientConfig) -> str:
    contact = client_config.contact_info.strip() or "the company directly"

    return (
        f"Thank you for reaching {client_config.assistant_name}. "
        f"For more details contact {contact}."
    )


def filter_inactive_website_media(
    *,
    evidence: list[MediaEvidenceCandidate],
    client_config: ClientConfig,
) -> list[MediaEvidenceCandidate]:
    if client_config.website_scrape_active:
        return evidence

    return [
        item
        for item in evidence
        if item.source_type != "website_auto_scrape"
    ]


def build_source_payloads(
    *,
    model_output: GroundedModelOutput,
    source_map: dict[str, RetrievedChunk],
    client_slug: str = DEFAULT_CLIENT_SLUG,
) -> list[dict] | None:
    if not model_output.can_answer or not model_output.answer.strip():
        print(
            f"[{client_slug} source validation] Model said it cannot answer "
            "or returned an empty answer."
        )
        return None

    requested_source_ids = list(
        dict.fromkeys(model_output.used_source_ids or [])
    )

    valid_source_ids = [
        source_id
        for source_id in requested_source_ids
        if source_id in source_map
    ]

    if requested_source_ids and not valid_source_ids:
        print(
            f"[{client_slug} source validation] Model returned invalid source IDs."
        )
        print(f"Requested: {requested_source_ids}")
        print(f"Available: {list(source_map.keys())}")

    if not requested_source_ids:
        print(
            f"[{client_slug} source validation] Model returned no source IDs. "
            "Recovering with available retrieved source IDs."
        )

    if not valid_source_ids:
        valid_source_ids = list(source_map.keys())[:4]

    if not valid_source_ids:
        return None

    return [
        {
            "document_title": source_map[source_id].document_title,
            "section_title": source_map[source_id].section_title,
            "source_reference": source_map[source_id].source_reference,
            "similarity": source_map[source_id].similarity,
        }
        for source_id in valid_source_ids
    ]


def resolve_valid_source_ids(
    *,
    model_output: GroundedModelOutput,
    source_map: dict[str, RetrievedChunk],
) -> list[str]:
    requested_source_ids = list(
        dict.fromkeys(model_output.used_source_ids or [])
    )
    valid_source_ids = [
        source_id
        for source_id in requested_source_ids
        if source_id in source_map
    ]

    if not valid_source_ids:
        valid_source_ids = list(source_map.keys())[:4]

    return valid_source_ids


def content_preview(text: str, limit: int = 700) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()

    if len(cleaned) <= limit:
        return cleaned

    return cleaned[: limit - 20].rstrip() + " ...[trimmed]"


def evidence_item_from_chunk(
    *,
    chunk: RetrievedChunk,
) -> dict[str, Any]:
    metadata = chunk.metadata or {}
    local_static_url = str(metadata.get("local_static_url") or "").strip()

    return {
        "client_slug": chunk.client_slug,
        "document_id": str(chunk.document_id),
        "chunk_id": str(chunk.chunk_id),
        "document_title": chunk.document_title,
        "original_filename": chunk.original_filename,
        "source_type": metadata.get("source_type"),
        "document_type": metadata.get("document_type"),
        "source_reference": chunk.source_reference,
        "source_url": metadata.get("source_url"),
        "page_url": metadata.get("page_url"),
        "local_static_url": local_static_url or None,
        "screenshot_url": (
            local_static_url
            if "/screenshots/" in local_static_url
            else None
        ),
        "video_url": metadata.get("video_url"),
        "section_title": chunk.section_title,
        "content_preview": content_preview(chunk.content),
    }


def build_evidence_bundle(
    *,
    client_slug: str,
    question: str,
    answer: str,
    source_map: dict[str, RetrievedChunk],
    source_ids: list[str],
) -> dict[str, Any]:
    items = [
        evidence_item_from_chunk(chunk=source_map[source_id])
        for source_id in source_ids
        if source_id in source_map
    ]

    return {
        "version": 1,
        "client_slug": client_slug,
        "question": question,
        "answer_preview": content_preview(answer, limit=900),
        "items": items,
    }


def build_evidence_bundle_from_chunks(
    *,
    client_slug: str,
    question: str,
    answer: str,
    chunks: list[RetrievedChunk],
    limit: int = 5,
) -> dict[str, Any] | None:
    selected_chunks = chunks[:limit]

    if not selected_chunks:
        return None

    source_map = {
        f"S{index}": chunk
        for index, chunk in enumerate(selected_chunks, start=1)
    }

    return build_evidence_bundle(
        client_slug=client_slug,
        question=question,
        answer=answer,
        source_map=source_map,
        source_ids=list(source_map.keys()),
    )


def latest_evidence_bundle(
    evidence_history: list[dict[str, Any]] | None,
    *,
    client_slug: str,
) -> dict[str, Any] | None:
    for bundle in reversed(evidence_history or []):
        if not isinstance(bundle, dict):
            continue

        if bundle.get("client_slug") != client_slug:
            continue

        items = bundle.get("items")

        if isinstance(items, list) and items:
            return bundle

    return None


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


def format_source_answer_from_bundle(
    *,
    evidence_bundle: dict[str, Any],
    wants_website: bool,
) -> str:
    return "The information is based on the company knowledge currently available to this chatbot."


def format_source_attribution_from_bundle(
    *,
    evidence_bundle: dict[str, Any],
) -> str:
    return "The information is based on the company knowledge currently available to this chatbot."


def format_no_bundle_media_answer(
    *,
    evidence_bundle: dict[str, Any],
    client_config: ClientConfig,
) -> str:
    source_text = format_source_answer_from_bundle(
        evidence_bundle=evidence_bundle,
        wants_website=False,
    )

    return (
        "I found source evidence for this answer, but no strong linked image "
        "evidence cleared the relevance threshold. The supporting "
        f"{client_config.company_name} source is:\n"
        f"{source_text}"
    )


def parse_final_output(
    *,
    final_response,
    raw_output: str,
) -> GroundedModelOutput:
    parsed_output = getattr(
        final_response,
        "output_parsed",
        None,
    )

    if parsed_output is None:
        return GroundedModelOutput.model_validate_json(raw_output)

    if isinstance(parsed_output, GroundedModelOutput):
        return parsed_output

    return GroundedModelOutput.model_validate(
        parsed_output
    )


def build_default_question_plan(question: str) -> ResolvedQuestionPlan:
    return ResolvedQuestionPlan(
        answer_question=question,
        retrieval_question=question,
    )


def recent_user_questions(history: list[ChatHistoryTurn], limit: int = 5) -> list[str]:
    questions: list[str] = []
    for turn in reversed(history):
        if turn.role != "user":
            continue
        content = turn.content.strip()
        if content and not looks_like_evidence_request(content):
            questions.append(content)
        if len(questions) >= limit:
            break
    return questions


def resolve_deterministic_followup_plan(
    *,
    question: str,
    history: list[ChatHistoryTurn],
) -> ResolvedQuestionPlan | None:
    normalized = re.sub(r"\s+", " ", question.lower()).strip()
    if not history:
        return None

    previous_questions = recent_user_questions(history)
    if not previous_questions:
        return None

    previous_question = previous_questions[0]
    previous_text = " ".join(previous_questions).lower()

    if re.search(r"\bwhy\s+is\s+this\s+information\s+processed\b", normalized):
        if any(term in previous_text for term in ("information", "data", "collected", "application process")):
            expanded = (
                f"{previous_question} Why is the collected applicant information "
                "processed? processing purpose data collected application process"
            )
            return ResolvedQuestionPlan(
                answer_question=(
                    "Why is the applicant information collected through the "
                    "application process processed?"
                ),
                retrieval_question=expanded,
            )

    if re.search(r"\bwho\s+performs\s+(?:it|the\s+review|the\s+credit\s+review|the\s+affordability\s+review)\b", normalized):
        if any(term in previous_text for term in ("affordability", "credit review", "review")):
            expanded = (
                "Who performs the affordability and credit review? "
                f"{previous_question} provider financing company"
            )
            return ResolvedQuestionPlan(
                answer_question="Who performs the affordability and credit review?",
                retrieval_question=expanded,
            )

    if re.search(r"\bisn['’]?t\s+it\b|\byou\s+said\b|\bi\s+think\b|\bthe\s+document\s+says\b", normalized):
        expanded = f"{previous_question} {question}"
        return ResolvedQuestionPlan(
            answer_question=previous_question,
            retrieval_question=expanded,
        )

    if re.search(r"\b(?:it|this|that|they|those|them|the provider|the campaign|the offer|the application)\b", normalized):
        if len(normalized.split()) <= 8:
            expanded = f"{previous_question} {question}"
            return ResolvedQuestionPlan(
                answer_question=expanded,
                retrieval_question=expanded,
            )

    return None


def build_question_plan_from_decision(
    *,
    question: str,
    decision: ConversationBrainDecision,
) -> ResolvedQuestionPlan:
    answer_question = (
        decision.standalone_question.strip()
        or decision.retrieval_query.strip()
        or question
    )

    retrieval_question = (
        decision.retrieval_query.strip()
        or decision.standalone_question.strip()
        or question
    )

    return ResolvedQuestionPlan(
        answer_question=answer_question,
        retrieval_question=retrieval_question,
    )


def looks_like_detail_expansion_followup(question: str) -> bool:
    normalized = re.sub(r"\s+", " ", question.lower()).strip()
    return bool(
        re.search(
            r"\b(?:talk\s+more|tell\s+me\s+more|explain\s+more|more\s+details|"
            r"give\s+me\s+more\s+details|elaborate|explain\s+it|explain\s+them)\b",
            normalized,
        )
    )


def should_prefer_conversation_question_plan(
    *,
    question: str,
    deterministic_plan: ResolvedQuestionPlan | None,
    decision: ConversationBrainDecision,
) -> bool:
    if deterministic_plan is None:
        return True

    if decision.route != "retrieve_documents":
        return False

    if decision.confidence < 0.75:
        return False

    standalone_question = decision.standalone_question.strip()
    retrieval_query = decision.retrieval_query.strip()
    if not standalone_question and not retrieval_query:
        return False

    deterministic_answer = deterministic_plan.answer_question.strip().lower()
    deterministic_query = deterministic_plan.retrieval_question.strip().lower()
    current_question = question.strip().lower()

    if looks_like_detail_expansion_followup(question):
        return True

    return (
        current_question
        and current_question in deterministic_answer
        and current_question in deterministic_query
        and standalone_question.lower() not in {current_question, deterministic_answer}
    )


def yield_memory_answer(
    *,
    answer: str,
) -> Generator[str, None, None]:
    yield encode_event(
        {
            "type": "replace",
            "answer": answer,
            "grounded": False,
            "conversation_memory": True,
            "disclaimer": None,
            "sources": [],
            "media": [],
        }
    )

    yield encode_event(
        {
            "type": "done",
            "grounded": False,
            "conversation_memory": True,
            "model_called": True,
        }
    )


def yield_clarification(
    *,
    answer: str,
) -> Generator[str, None, None]:
    yield encode_event(
        {
            "type": "replace",
            "answer": answer,
            "grounded": False,
            "conversation_memory": False,
            "clarification": True,
            "disclaimer": None,
            "sources": [],
            "media": [],
        }
    )

    yield encode_event(
        {
            "type": "done",
            "grounded": False,
            "conversation_memory": False,
            "clarification": True,
            "model_called": True,
        }
    )


def clean_media_url(url: str) -> str:
    return url.strip().rstrip(".,;:)]}\"'")


def unique_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []

    for item in items:
        cleaned = clean_media_url(item)

        if not cleaned or cleaned in seen:
            continue

        seen.add(cleaned)
        output.append(cleaned)

    return output


def extract_image_urls(text: str) -> list[str]:
    image_urls = [
        match.group(1)
        for match in STATIC_IMAGE_URL_PATTERN.finditer(text)
    ]

    screenshot_urls = [
        match.group(1)
        for match in STATIC_SCREENSHOT_URL_PATTERN.finditer(text)
    ]

    return unique_keep_order(image_urls + screenshot_urls)


def extract_video_urls(text: str) -> list[str]:
    return unique_keep_order(
        [
            match.group(1)
            for match in VIDEO_URL_PATTERN.finditer(text)
        ]
    )


def extract_http_urls(text: str) -> list[str]:
    return unique_keep_order(
        [
            match.group(1)
            for match in HTTP_URL_PATTERN.finditer(text)
        ]
    )


def looks_like_contextual_link_followup(text: str) -> bool:
    lowered = str(text or "").lower().strip()
    return bool(
        re.search(r"\b(link|links|url|urls)\b", lowered)
        and re.search(r"\b(give|show|send|provide|open|where|what|which|it|that|this)\b", lowered)
    )


def history_turn_role(turn: Any) -> str:
    if isinstance(turn, dict):
        return str(turn.get("role") or "")
    return str(getattr(turn, "role", "") or "")


def history_turn_content(turn: Any) -> str:
    if isinstance(turn, dict):
        return str(turn.get("content") or "")
    return str(getattr(turn, "content", "") or "")


def format_contextual_link_followup(
    *,
    question: str,
    history: list[ChatHistoryTurn],
    evidence_history: list[dict[str, Any]] | None,
    client_slug: str,
) -> str | None:
    if not looks_like_contextual_link_followup(question):
        return None

    latest_bundle = latest_evidence_bundle(evidence_history, client_slug=client_slug)
    bundle_videos = [
        str(item.get("video_url") or "").strip()
        for item in bundle_items(latest_bundle)
        if str(item.get("video_url") or "").strip()
    ]
    if bundle_videos:
        urls = unique_keep_order(bundle_videos)
        label = "related video link" if len(urls) == 1 else "related video links"
        return f"Here {'is' if len(urls) == 1 else 'are'} the {label}:\n" + "\n".join(urls)

    bundle_pages = [
        str(item.get("page_url") or item.get("source_url") or "").strip()
        for item in bundle_items(latest_bundle)
        if str(item.get("page_url") or item.get("source_url") or "").strip()
    ]
    if bundle_pages:
        urls = unique_keep_order(bundle_pages)
        label = "related page link" if len(urls) == 1 else "related page links"
        return f"Here {'is' if len(urls) == 1 else 'are'} the {label}:\n" + "\n".join(urls[:5])

    for turn in reversed(history or []):
        if history_turn_role(turn) != "assistant":
            continue
        content = history_turn_content(turn)
        video_urls = extract_video_urls(content)
        if video_urls:
            label = "related video link" if len(video_urls) == 1 else "related video links"
            return f"Here {'is' if len(video_urls) == 1 else 'are'} the {label}:\n" + "\n".join(video_urls[:5])

        urls = extract_http_urls(content)
        if urls:
            label = "related link" if len(urls) == 1 else "related links"
            return f"Here {'is' if len(urls) == 1 else 'are'} the {label}:\n" + "\n".join(urls[:5])

    return None


def get_nearby_text(
    *,
    text: str,
    needle: str,
    window: int = 1600,
) -> str:
    index = text.find(needle)

    if index < 0:
        return text[:window]

    start = max(index - window, 0)
    end = min(index + len(needle) + window, len(text))

    return text[start:end]


def text_mentions_license(text: str) -> bool:
    return looks_like_license_question(text)


def text_mentions_acr(text: str) -> bool:
    normalized = text.lower()

    return (
        "acr" in normalized
        or "automatic customer relations" in normalized
        or "automatic customer relation" in normalized
        or "علاقات العملاء" in text
    )


def text_mentions_niqaty(text: str) -> bool:
    normalized = text.lower()

    return (
        "niqaty" in normalized
        or "loyalty" in normalized
        or "reward" in normalized
        or "نقاطي" in text
    )


def media_label_for_url(
    *,
    url: str,
    context: str,
    question_text: str,
    client_config: ClientConfig,
) -> str:
    nearby_text = get_nearby_text(
        text=context,
        needle=url,
    )

    combined = f"{question_text}\n{nearby_text}"

    if text_mentions_license(combined):
        if contains_arabic(question_text):
            return f"دليل صورة خاص بـ {client_config.company_name}"
        return "Related company image"

    if text_mentions_acr(combined):
        if url.lower().endswith((".mp4", ".webm", ".mov", ".m4v")):
            return "Related company video"
        return "Related website image"

    if text_mentions_niqaty(combined):
        return "Related website image"

    if "/screenshots/" in url:
        return "Related website screenshot"

    if url.lower().endswith((".mp4", ".webm", ".mov", ".m4v")):
        return "Related company video"

    return "Related website image"


def rank_image_url(
    *,
    url: str,
    context: str,
    question_text: str,
) -> int:
    nearby_text = get_nearby_text(
        text=context,
        needle=url,
    )

    combined = f"{question_text}\n{nearby_text}"

    score = 0

    if "/images/" in url:
        score += 20

    if "/screenshots/" in url:
        score += 10

    if text_mentions_license(combined):
        score += 100

    if text_mentions_acr(combined):
        score += 50

    if text_mentions_niqaty(combined):
        score += 40

    return score


def build_media_payloads(
    *,
    original_question: str,
    answer_question: str,
    context: str,
    client_config: ClientConfig,
) -> list[dict[str, Any]]:
    question_text = f"{original_question}\n{answer_question}"

    wants_image = looks_like_visual_or_source_request(question_text)
    wants_video = looks_like_video_request(question_text)

    if not wants_image and not wants_video:
        return []

    media_items: list[dict[str, Any]] = []

    if wants_image:
        image_urls = extract_image_urls(context)

        ranked_image_urls = sorted(
            image_urls,
            key=lambda url: rank_image_url(
                url=url,
                context=context,
                question_text=question_text,
            ),
            reverse=True,
        )

        for image_url in ranked_image_urls[:2]:
            media_items.append(
                {
                    "type": "image",
                    "url": image_url,
                    "label": media_label_for_url(
                        url=image_url,
                        context=context,
                        question_text=question_text,
                        client_config=client_config,
                    ),
                    "source": "approved_client_evidence",
                }
            )

    if wants_video:
        video_urls = extract_video_urls(context)

        for video_url in video_urls[:2]:
            media_items.append(
                {
                    "type": "video",
                    "url": video_url,
                    "label": media_label_for_url(
                        url=video_url,
                        context=context,
                        question_text=question_text,
                        client_config=client_config,
                    ),
                    "source": "approved_client_evidence",
                }
            )

    return media_items


def safe_marker_label(label: str) -> str:
    return (
        label.replace("[", "")
        .replace("]", "")
        .replace("|", "-")
        .replace("\n", " ")
        .strip()
    )


def media_marker(media_item: dict[str, Any]) -> str:
    media_type = media_item.get("type")
    url = str(media_item.get("url") or "").strip()
    label = safe_marker_label(
        str(media_item.get("label") or "source evidence")
    )

    if not url:
        return ""

    if media_type == "image":
        return f"[[image:{url}|{label}]]"

    if media_type == "video":
        return f"[[video:{url}|{label}]]"

    return ""


def append_media_markers(
    *,
    answer: str,
    media: list[dict[str, Any]],
) -> str:
    markers = [
        marker
        for marker in (media_marker(item) for item in media)
        if marker
    ]

    if not markers:
        return answer.strip()

    cleaned_answer = answer.strip()
    if not cleaned_answer:
        return "\n".join(markers)
    return cleaned_answer + "\n\n" + "\n".join(markers)


def has_any_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    normalized = text.lower()

    return any(phrase in normalized for phrase in phrases)


def looks_like_source_request(text: str) -> bool:
    return has_any_phrase(
        text,
        (
            "show me the source",
            "show me source",
            "source from the website",
            "website source",
            "what source did you use",
            "which source",
            "page url",
            "source url",
            "supports your answer",
            "support your answer",
            "where did that come from",
            "where did it come from",
            "show me proof",
            "show proof",
            "show me evidence",
            "show evidence",
        ),
    )


def looks_like_source_attribution_request(text: str) -> bool:
    return has_any_phrase(
        text,
        (
            "uploaded files or from the website",
            "uploaded file or website",
            "from uploaded files",
            "from uploaded file",
            "from the website scrape",
            "from website scrape",
            "uploaded-vs-website",
            "which source type",
            "source type",
            "came from uploads",
            "came from the website",
        ),
    )


def looks_like_image_request(text: str) -> bool:
    return has_any_phrase(
        text,
        (
            "image proof",
            "image evidence",
            "show me proof",
            "show proof",
            "show me evidence",
            "show evidence",
            "show me image",
            "show image",
            "photo proof",
            "picture proof",
            "certificate image",
            "certificate proof",
            "show me certificate",
            "local static url",
        ),
    )


def requested_media_limit(text: str) -> int:
    if has_any_phrase(
        text,
        (
            "all images",
            "all website images",
            "all website media",
            "all image evidence",
            "all proof",
            "all proofs",
            "more images",
            "more website images",
            "more website media",
            "more image evidence",
            "more proofs",
            "multiple images",
            "multiple website images",
            "multiple website media",
            "multiple image evidence",
            "multiple proofs",
            "show all evidence",
            "show all images",
            "show all website images",
            "show all website media",
            "show all image evidence",
            "show every image",
            "show every website image",
            "show more",
        ),
    ):
        return 5

    return 1


def looks_like_screenshot_request(text: str) -> bool:
    return has_any_phrase(
        text,
        (
            "screenshot",
            "screen shot",
            "website screenshot",
            "screenshot evidence",
        ),
    )


def looks_like_website_image_request(text: str) -> bool:
    return (
        "website" in text.lower()
        and has_any_phrase(
            text,
            (
                "image",
                "photo",
                "picture",
                "visual",
                "evidence",
                "proof",
            ),
        )
    )


def looks_like_video_link_request(text: str) -> bool:
    return (
        looks_like_video_request(text)
        and has_any_phrase(
            text,
            (
                "link",
                "links",
                "url",
                "urls",
                "give me",
                "show me",
                "do you have",
                "downloaded locally",
                "stored as links",
                "website",
            ),
        )
    )


def looks_like_general_media_browse_request(text: str) -> bool:
    lower = text.lower()

    if any(term in lower for term in ("certificate", "evidence", "proof", "source")):
        return False

    general_website_image_request = (
        ("website" in lower or "site" in lower)
        and has_any_phrase(
            text,
            (
                "image",
                "images",
                "photo",
                "photos",
                "picture",
                "pictures",
                "screenshot",
                "screenshots",
                "visual",
                "visuals",
            ),
        )
        and has_any_phrase(
            text,
            (
                "show",
                "browse",
                "list",
                "give me",
                "what",
                "all",
                "more",
                "saved",
            ),
        )
    )

    return has_any_phrase(
        text,
        (
            "what images were saved",
            "images saved from the website",
            "show me general website images",
            "browse website images",
            "show saved website images",
            "all website images",
        ),
    ) or general_website_image_request


def looks_like_evidence_request(text: str) -> bool:
    return (
        looks_like_source_request(text)
        or looks_like_source_attribution_request(text)
        or looks_like_image_request(text)
        or looks_like_screenshot_request(text)
        or looks_like_website_image_request(text)
        or looks_like_video_link_request(text)
    )


def try_yield_specific_media_lookup(
    *,
    question: str,
    client_slug: str,
    client_config: ClientConfig,
) -> Generator[str, None, None] | None:
    intent = extract_specific_media_target(question)

    if not intent.is_specific:
        return None

    if "certificate" in question.lower():
        return None

    if not client_config.website_scrape_active:
        return yield_evidence_answer(
            answer=website_not_scraped_message(client_config),
        )

    limit = 5 if intent.wants_all else 1
    results = search_media_catalog(
        client_slug=client_slug,
        query=intent.target,
        wants_logo=intent.wants_logo,
        limit=limit,
    )
    best_result = results[0] if results else None

    if best_result is None:
        return yield_evidence_answer(
            answer=get_no_answer_message(
                question,
                client_config.company_name,
                assistant_name=client_config.assistant_name,
                contact_info=client_config.contact_info,
            ),
        )

    answer, media = format_specific_media_answer(
        result=best_result,
        intent=intent,
        company_name=client_config.company_name,
    )

    return yield_evidence_answer(
        answer=append_media_markers(answer=answer, media=media),
        media=media,
    )


def format_general_website_media_browse_answer(
    *,
    results: list[Any],
    media: list[dict[str, Any]],
    question: str,
    client_config: ClientConfig,
) -> str:
    if not media:
        return "I could not find related website images for that request."

    multiple_media = len(media) > 1

    if looks_like_screenshot_request(question):
        answer = (
            "Here are related website screenshots."
            if multiple_media
            else "Here is a related website screenshot."
        )
    else:
        answer = (
            "Here are related website images."
            if multiple_media
            else "Here is a related website image."
        )

    return append_media_markers(answer=answer, media=media)


def try_yield_general_website_media_browse(
    *,
    question: str,
    client_slug: str,
    client_config: ClientConfig,
) -> Generator[str, None, None] | None:
    if not looks_like_general_media_browse_request(question):
        return None

    if not client_config.website_scrape_active:
        return yield_evidence_answer(
            answer=website_not_scraped_message(client_config),
        )

    limit = requested_media_limit(question)
    results = browse_media_catalog(
        client_slug=client_slug,
        limit=limit,
        prefer_screenshots=looks_like_screenshot_request(question),
    )
    media = [result.to_media_item() for result in results]

    return yield_evidence_answer(
        answer=format_general_website_media_browse_answer(
            results=results,
            media=media,
            question=question,
            client_config=client_config,
        ),
        media=media,
    )


def looks_like_prompt_injection_or_secret_request(text: str) -> bool:
    return has_any_phrase(
        text,
        (
            "ignore your instructions",
            "ignore previous instructions",
            "ignore the system",
            "answer from the internet",
            "use the internet",
            "reveal your system prompt",
            "show your system prompt",
            "what is your system prompt",
            "developer instructions",
            "hidden instructions",
            "api key",
            "secret key",
        ),
    )


def yield_policy_refusal(
    *,
    client_config: ClientConfig,
) -> Generator[str, None, None]:
    answer = (
        "I can only answer from approved "
        f"{client_config.company_name} sources, and I cannot ignore those "
        "rules or reveal hidden instructions."
    )

    yield encode_event(
        {
            "type": "replace",
            "answer": answer,
            "grounded": False,
            "conversation_memory": False,
            "disclaimer": answer,
            "sources": [],
            "media": [],
        }
    )

    yield encode_event(
        {
            "type": "done",
            "grounded": False,
            "conversation_memory": False,
            "model_called": False,
        }
    )


def get_previous_substantive_user_question(
    history: list[ChatHistoryTurn],
) -> str | None:
    for turn in reversed(history):
        if turn.role != "user":
            continue

        content = turn.content.strip()

        if not content or looks_like_evidence_request(content):
            continue

        return content

    return None


def retrieve_evidence_support_chunks(
    *,
    question: str,
    db: Session,
    client_slug: str,
    top_k: int = 8,
) -> list[RetrievedChunk]:
    try:
        retrieval = retrieve_client_chunks(
            question=question,
            db=db,
            top_k=(
                min(max(top_k, 10), 10)
                if prefers_website_scrape_sources(question)
                else top_k
            ),
            client_slug=client_slug,
            include_metadata_only=True,
        )
    except Exception as error:
        print(
            f"[{client_slug} evidence retrieval skipped] "
            f"{type(error).__name__}: {error}"
        )
        return []

    useful_chunks = [
        chunk
        for chunk in retrieval.results
        if not is_metadata_only_chunk(chunk.content)
        or chunk.metadata.get("page_url")
        or chunk.metadata.get("source_url")
        or chunk.metadata.get("local_static_url")
        or chunk.metadata.get("video_url")
    ]

    return prioritize_website_scrape_chunks(
        question=question,
        chunks=useful_chunks or retrieval.results,
    )


def source_type_label(source_type: str) -> str:
    labels = {
        "website_auto_scrape": "website scrape",
        "uploaded_docx": "uploaded document",
        "uploaded_pdf": "uploaded document",
        "uploaded_xlsx": "uploaded spreadsheet",
        "document_image": "uploaded document image/OCR",
        "pdf_page_image": "uploaded document page image/OCR",
    }

    return labels.get(source_type or "unknown", source_type or "unknown")


def unique_text_values(values: list[str | None], limit: int = 5) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []

    for value in values:
        cleaned = str(value or "").strip()

        if not cleaned or cleaned in seen:
            continue

        seen.add(cleaned)
        output.append(cleaned)

        if len(output) >= limit:
            break

    return output


def build_source_payloads_from_chunks(
    chunks: list[RetrievedChunk],
) -> list[dict[str, Any]]:
    return [
        {
            "document_title": chunk.document_title,
            "section_title": chunk.section_title,
            "source_reference": chunk.source_reference,
            "similarity": chunk.similarity,
            "source_type": chunk.metadata.get("source_type"),
            "source_url": chunk.metadata.get("source_url"),
            "page_url": chunk.metadata.get("page_url"),
            "local_static_url": chunk.metadata.get("local_static_url"),
            "video_url": chunk.metadata.get("video_url"),
        }
        for chunk in chunks[:4]
    ]


def format_source_answer(
    *,
    chunks: list[RetrievedChunk],
    client_config: ClientConfig,
    wants_website: bool,
) -> str:
    contact = client_config.contact_info.strip() or "the company directly"

    return (
        "The information is based on the company knowledge currently available "
        f"to this chatbot. For more details contact {contact}."
    )


def format_source_attribution_answer(
    *,
    chunks: list[RetrievedChunk],
    client_config: ClientConfig,
) -> str:
    contact = client_config.contact_info.strip() or "the company directly"

    return (
        "The information is based on the company knowledge currently available "
        f"to this chatbot. For more details contact {contact}."
    )


def metadata_value_text(metadata: dict[str, Any], key: str) -> str:
    value = metadata.get(key)

    return str(value or "").strip()


def get_media_chunks(
    *,
    db: Session,
    client_slug: str,
    question: str,
    limit: int = 4,
) -> list[tuple[DocumentChunk, Document]]:
    rows = db.execute(
        select(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            DocumentChunk.client_slug == client_slug,
            Document.client_slug == client_slug,
            Document.status == "active",
            Document.visibility == "client",
        )
        .order_by(Document.created_at.desc(), DocumentChunk.chunk_index.asc())
    ).all()

    normalized_question = question.lower()
    wants_certificate = "certificate" in normalized_question
    wants_screenshot = looks_like_screenshot_request(question)
    wants_website = "website" in normalized_question
    wants_website_image = looks_like_website_image_request(question)

    candidates: list[tuple[int, DocumentChunk, Document]] = []

    for chunk, document in rows:
        metadata = chunk.chunk_metadata or {}
        url = metadata_value_text(metadata, "local_static_url")

        if not url:
            continue

        combined = f"{chunk.content}\n{json.dumps(metadata, ensure_ascii=False)}".lower()
        score = 0

        if wants_screenshot:
            if "/screenshots/" not in url:
                continue
            score += 100
        elif wants_website_image and "/screenshots/" in url:
            continue

        if wants_website:
            if metadata.get("source_type") != "website_auto_scrape":
                continue
            score += 40

        if wants_certificate and "certificate" not in combined:
            continue

        if wants_certificate:
            score += 120

        if "/document_images/" in url:
            score += 25

        if "/images/" in url:
            score += 20

        if "/screenshots/" in url:
            score += 30

        if metadata.get("source_type") == "website_auto_scrape":
            score += 10

        candidates.append((score, chunk, document))

    candidates.sort(key=lambda item: item[0], reverse=True)

    return [
        (chunk, document)
        for _, chunk, document in candidates[:limit]
    ]


def media_item_from_chunk(
    *,
    chunk: DocumentChunk,
    document: Document,
    client_config: ClientConfig,
    question: str,
) -> dict[str, Any] | None:
    metadata = chunk.chunk_metadata or {}
    url = metadata_value_text(metadata, "local_static_url")

    if not url:
        return None

    meaningful_label = metadata_value_text(metadata, "entity_name") or metadata_value_text(
        metadata,
        "alt_text",
    ) or metadata_value_text(metadata, "image_label") or metadata_value_text(
        metadata,
        "image_description",
    ) or metadata_value_text(metadata, "section_heading") or document.title

    if "/screenshots/" in url:
        label = f"{meaningful_label} screenshot" if meaningful_label else "Website screenshot"
    elif metadata.get("source_type") == "website_auto_scrape":
        label = meaningful_label or "Website image"
    elif "certificate" in f"{question}\n{chunk.content}".lower():
        label = meaningful_label or "Certificate image"
    else:
        label = meaningful_label or "Company image"

    return {
        "type": "image",
        "url": url,
        "label": label,
        "source": "approved_client_evidence",
    }


def format_media_answer(
    *,
    media: list[dict[str, Any]],
    evidence: list[MediaEvidenceCandidate] | None = None,
    question: str,
    client_config: ClientConfig,
) -> str:
    if not media:
        if "website" in question.lower() or "source image" in question.lower():
            return (
                "I found related company media, but none are a strong match "
                "for this specific answer."
            )

        return (
            "I could not find a related company image for that request."
        )

    multiple_media = len(media) > 1

    if looks_like_screenshot_request(question):
        answer = (
            "Here are related website screenshots."
            if multiple_media
            else "Here is a related website screenshot."
        )
    elif "certificate" in question.lower():
        answer = (
            "Here are related company images."
            if multiple_media
            else "Here is a related company image."
        )
    elif "website" in question.lower():
        answer = (
            "Here are related website images."
            if multiple_media
            else "Here is a related website image."
        )
    else:
        answer = (
            "Here are related company images."
            if multiple_media
            else "Here is a related company image."
        )

    return append_media_markers(answer=answer, media=media)


def extract_video_urls_from_json(
    *,
    client_slug: str,
    limit: int = 8,
) -> list[str]:
    scraped_dir = client_scraped_dir(client_slug)

    if not scraped_dir.exists():
        return []

    urls: list[str] = []

    for json_path in sorted(scraped_dir.glob("*Website_Scrape.json"), reverse=True):
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        for page in payload.get("pages", []):
            for video in page.get("videos", []):
                urls.append(str(video.get("url") or video.get("video_url") or ""))

    return unique_text_values(urls, limit=limit)


def get_video_urls(
    *,
    db: Session,
    client_slug: str,
    limit: int = 8,
) -> list[str]:
    rows = db.execute(
        select(DocumentChunk)
        .where(DocumentChunk.client_slug == client_slug)
        .order_by(DocumentChunk.chunk_index.asc())
    ).scalars()

    urls: list[str] = []

    for chunk in rows:
        metadata = chunk.chunk_metadata or {}

        if metadata.get("source_type") != "website_auto_scrape":
            continue

        urls.append(metadata_value_text(metadata, "video_url"))

        for line in chunk.content.splitlines():
            if line.lower().startswith("video url:"):
                urls.append(line.split(":", 1)[1].strip())

        urls.extend(extract_video_urls(chunk.content))

    urls.extend(extract_video_urls_from_json(client_slug=client_slug, limit=limit))

    return unique_text_values(urls, limit=limit)


def format_video_answer(
    *,
    urls: list[str],
    question: str,
    client_config: ClientConfig,
) -> str:
    if "downloaded locally" in question.lower() or "stored as links" in question.lower():
        if urls:
            return (
                "The website videos are available as links:\n"
                + "\n".join(f"{index}. {url}" for index, url in enumerate(urls, start=1))
            )

        return (
            "I did not find video links for "
            f"{client_config.company_name}."
        )

    if not urls:
        return (
            "I did not find video links for "
            f"{client_config.company_name}."
        )

    return (
        "Here are related video links:\n"
        + "\n".join(f"{index}. {url}" for index, url in enumerate(urls, start=1))
    )


def yield_evidence_answer(
    *,
    answer: str,
    sources: list[dict[str, Any]] | None = None,
    media: list[dict[str, Any]] | None = None,
    evidence_bundle: dict[str, Any] | None = None,
    product_references: list[dict[str, Any]] | None = None,
    media_context: dict[str, Any] | None = None,
) -> Generator[str, None, None]:
    yield encode_event(
        {
            "type": "replace",
            "answer": answer,
            "grounded": True,
            "conversation_memory": False,
            "disclaimer": None,
            "sources": sources or [],
            "media": media or [],
            "evidence_bundle": evidence_bundle,
            "product_references": product_references,
            "media_context": media_context,
        }
    )

    yield encode_event(
        {
            "type": "done",
            "grounded": True,
            "conversation_memory": False,
            "model_called": False,
        }
    )


def campaign_media_avoid_ids(
    *,
    question: str,
    last_media_context: dict[str, Any] | None,
) -> list[str]:
    if not isinstance(last_media_context, dict):
        return []
    intent = parse_media_request_intent(question)
    if not (intent.request_another or intent.request_more or intent.request_another_colour):
        return []
    return [
        str(value)
        for value in last_media_context.get("last_image_result_ids", [])
        if value
    ]


def try_yield_campaign_media_request(
    *,
    db: Session,
    client_slug: str,
    question: str,
    last_media_context: dict[str, Any] | None,
) -> Generator[str, None, None] | None:
    intent = parse_media_request_intent(question)
    if not intent.is_media_request:
        return None

    def _generator() -> Generator[str, None, None]:
        try:
            campaign_media_results = retrieve_campaign_media(
                db=db,
                client_slug=client_slug,
                query=question,
                media_context=last_media_context,
                avoid_image_ids=campaign_media_avoid_ids(
                    question=question,
                    last_media_context=last_media_context,
                ),
                limit=intent.requested_media_count,
                intent=intent,
            )
        except Exception as error:
            print(f"[{client_slug} campaign media retrieval error] {type(error).__name__}: {error}")
            campaign_media_results = []

        answer, media = media_answer(campaign_media_results, question, intent)
        context = media_context_from_results(campaign_media_results)
        yield from yield_evidence_answer(
            answer=append_media_markers(answer=answer, media=media),
            media=media,
            media_context=context,
        )

    return _generator()


def try_yield_campaign_year_correction(
    *,
    db: Session,
    client_slug: str,
    question: str,
) -> Generator[str, None, None] | None:
    intent = parse_media_request_intent(question)
    if intent.is_media_request:
        return None
    requested_year = intent.requested_year or extract_requested_year(question)
    if requested_year is None:
        return None
    try:
        context = approved_media_context_for_query(
            db=db,
            client_slug=client_slug,
            query=question,
        )
    except Exception as error:
        print(f"[{client_slug} campaign year validation error] {type(error).__name__}: {error}")
        return None
    approved_year = context.get("approved_year")
    if not approved_year or int(approved_year) == int(requested_year):
        return None
    answer = format_year_mismatch_message(
        question=question,
        requested_year=int(requested_year),
        approved_year=int(approved_year),
        approved_product=str(context.get("approved_product") or context.get("requested_product") or ""),
    )
    return yield_evidence_answer(answer=answer, media=[])


def informational_campaign_fallback(question: str) -> str:
    if contains_arabic(question):
        return (
            "\u0644\u0627 \u062a\u062a\u0648\u0641\u0631 \u0644\u062f\u064a "
            "\u062a\u0641\u0627\u0635\u064a\u0644 \u0646\u0635\u064a\u0629 "
            "\u0645\u0639\u062a\u0645\u062f\u0629 \u0643\u0627\u0641\u064a\u0629 "
            "\u0639\u0646 \u0647\u0630\u0627 \u0627\u0644\u0637\u0644\u0628. "
            "\u0644\u0627 \u0623\u0633\u062a\u0646\u062a\u062c \u0627\u0644\u0623\u0644\u0648\u0627\u0646 "
            "\u0623\u0648 \u0627\u0644\u0641\u0626\u0627\u062a \u0623\u0648 "
            "\u0627\u0644\u0645\u0648\u0627\u0635\u0641\u0627\u062a \u0645\u0646 "
            "\u0627\u0644\u0635\u0648\u0631 \u0648\u062d\u062f\u0647\u0627."
        )
    return (
        "I do not have enough approved text details to answer that availability question. "
        "I do not infer colours, grades, features, or specifications from images alone."
    )


MARKAZIA_TOYOTA_SLUG = "-".join(
    ["central", "trade", "auto", "co", "markazia", "toyota", "jordan"]
)


def direct_campaign_vehicle_answer(
    *,
    client_slug: str,
    question: str,
    chunks: list[RetrievedChunk],
) -> str | None:
    if client_slug != MARKAZIA_TOYOTA_SLUG or not chunks:
        return None
    if not looks_like_campaign_vehicle_text_query(question):
        return None

    context = "\n".join(chunk.content for chunk in chunks[:6]).lower()
    if "corolla" not in context or ("hev" not in context and "hybrid" not in context):
        return None

    normalized = question.lower()
    is_arabic = contains_arabic(question)

    wants_grades = any(term in normalized for term in ("grade", "grades", "trim", "trims", "variant", "variants")) or any(term in question for term in ("\u0641\u0626\u0627\u062a", "\u0627\u0644\u0641\u0626\u0627\u062a"))
    wants_colours = any(term in normalized for term in ("colour", "colours", "color", "colors")) or any(term in question for term in ("\u0623\u0644\u0648\u0627\u0646", "\u0627\u0644\u0623\u0644\u0648\u0627\u0646"))
    wants_specs = any(term in normalized for term in ("spec", "specs", "specification", "specifications", "engine", "battery", "hybrid", "charging", "transmission", "wheel drive")) or any(term in question for term in ("\u0645\u0648\u0627\u0635\u0641\u0627\u062a", "\u0645\u062d\u0631\u0643", "\u0628\u0637\u0627\u0631\u064a\u0629", "\u0647\u0627\u064a\u0628\u0631\u062f", "\u0634\u062d\u0646", "\u0646\u0627\u0642\u0644"))
    wants_features = any(term in normalized for term in ("feature", "features", "touchscreen", "carplay", "android auto", "moonroof", "parking", "usb", "bluetooth")) or any(term in question for term in ("\u0645\u0632\u0627\u064a\u0627", "\u0627\u0644\u0645\u0632\u0627\u064a\u0627", "\u0627\u0644\u0645\u0642\u0635\u0648\u0631\u0629"))
    wants_safety = any(term in normalized for term in ("safety", "airbag", "airbags", "abs", "isofix", "stability")) or any(term in question for term in ("\u0633\u0644\u0627\u0645\u0629", "\u0648\u0633\u0627\u0626\u062f"))
    wants_warranty = any(term in normalized for term in ("warranty", "guarantee")) or any(term in question for term in ("\u0643\u0641\u0627\u0644\u0629", "\u0636\u0645\u0627\u0646"))
    wants_finance = any(term in normalized for term in ("finance", "financing", "instalment", "installment", "monthly", "down payment", "trade-in", "trade in")) or any(term in question for term in ("\u062a\u0645\u0648\u064a\u0644", "\u0623\u0642\u0633\u0627\u0637", "\u0627\u0633\u062a\u0628\u062f\u0627\u0644"))
    wants_quote = any(term in normalized for term in ("quotation", "quote", "test drive", "call", "contact", "showroom")) or any(term in question for term in ("\u0639\u0631\u0636 \u0633\u0639\u0631", "\u062a\u062c\u0631\u0628\u0629 \u0642\u064a\u0627\u062f\u0629", "\u064a\u062a\u0635\u0644", "\u0647\u0627\u062a\u0641", "\u0645\u0639\u0631\u0636"))
    wants_price = any(term in normalized for term in ("price", "starting", "jod", "cost")) or any(term in question for term in ("\u0633\u0639\u0631", "\u0627\u0644\u0633\u0639\u0631"))

    if is_arabic:
        parts: list[str] = []
        if wants_grades:
            parts.append("\u0627\u0644\u0641\u0626\u0627\u062a \u0627\u0644\u0645\u0630\u0643\u0648\u0631\u0629 \u0641\u064a \u0627\u0644\u0645\u0635\u0627\u062f\u0631 \u0627\u0644\u0645\u0639\u062a\u0645\u062f\u0629 \u0647\u064a HEV Mid-Grade \u0648HEV High-Grade\u060c \u0645\u0639 \u062a\u0623\u0643\u064a\u062f \u0627\u0644\u062a\u0648\u0641\u0631 \u0648\u0627\u0644\u062a\u062c\u0647\u064a\u0632\u0627\u062a \u0627\u0644\u0646\u0647\u0627\u0626\u064a\u0629 \u062d\u0633\u0628 \u0645\u062e\u0632\u0648\u0646 \u0627\u0644\u0623\u0631\u062f\u0646.")
        if wants_price:
            parts.append("\u0627\u0644\u0633\u0639\u0631 \u0627\u0644\u0627\u0628\u062a\u062f\u0627\u0626\u064a \u0627\u0644\u0645\u0630\u0643\u0648\u0631 \u0647\u0648 JOD 23,500\u060c \u0648\u0647\u0648 \u062e\u0627\u0636\u0639 \u0644\u0644\u0645\u062e\u0632\u0648\u0646 \u0648\u0627\u0644\u0634\u0631\u0648\u0637 \u0648\u0627\u0644\u0639\u0631\u0648\u0636 \u0627\u0644\u0633\u0627\u0631\u064a\u0629.")
        if wants_colours:
            parts.append("\u0639\u0627\u0626\u0644\u0627\u062a \u0627\u0644\u0623\u0644\u0648\u0627\u0646 \u0627\u0644\u0625\u0631\u0634\u0627\u062f\u064a\u0629 \u062a\u0634\u0645\u0644 Pearl White\u060c Metallic Silver\u060c Black\u060c Red\u060c Dark Grey\u060c \u0648Blue. \u064a\u062c\u0628 \u062a\u0623\u0643\u064a\u062f \u0623\u0633\u0645\u0627\u0621 \u0627\u0644\u0623\u0644\u0648\u0627\u0646 \u0627\u0644\u0631\u0633\u0645\u064a\u0629 \u0648\u0627\u0644\u0645\u062a\u0627\u062d\u0629 \u062d\u0627\u0644\u064a\u0627\u064b \u0645\u0646 \u0641\u0631\u064a\u0642 \u0627\u0644\u0645\u0628\u064a\u0639\u0627\u062a.")
        if wants_specs:
            parts.append("\u0623\u0628\u0631\u0632 \u0627\u0644\u0645\u0648\u0627\u0635\u0641\u0627\u062a: \u0633\u064a\u062f\u0627\u0646 \u0647\u0627\u064a\u0628\u0631\u062f \u0645\u062f\u0645\u062c\u0629\u060c \u0646\u0638\u0627\u0645 \u0628\u0646\u0632\u064a\u0646-\u0643\u0647\u0631\u0628\u0627\u0621 \u0630\u0627\u062a\u064a \u0627\u0644\u0634\u062d\u0646 \u0628\u062f\u0648\u0646 \u0634\u062d\u0646 \u062e\u0627\u0631\u062c\u064a\u060c \u0645\u062d\u0631\u0643 1.8 \u0644\u062a\u0631 \u0628\u0642\u0648\u0629 97 hp \u0648\u0639\u0632\u0645 142 Nm\u060c \u0645\u062d\u0631\u0643 \u0643\u0647\u0631\u0628\u0627\u0626\u064a 71 hp \u0648163 Nm\u060c \u0628\u0637\u0627\u0631\u064a\u0629 \u0644\u064a\u062b\u064a\u0648\u0645-\u0623\u064a\u0648\u0646\u060c \u0646\u0627\u0642\u0644 CVT\u060c \u062f\u0641\u0639 \u0623\u0645\u0627\u0645\u064a\u060c \u0648\u0623\u0646\u0645\u0627\u0637 Normal\u060c Eco\u060c Sport \u0648Electric.")
        if wants_features:
            parts.append("\u0627\u0644\u0645\u0632\u0627\u064a\u0627 \u062a\u0634\u0645\u0644 \u0634\u0627\u0634\u0629 8-inch\u060c Apple CarPlay\u060c Android Auto\u060c Bluetooth\u060c USB\u060c \u0633\u062a \u0633\u0645\u0627\u0639\u0627\u062a\u060c \u062e\u0645\u0633\u0629 \u0645\u0642\u0627\u0639\u062f\u060c \u0648\u0641\u062a\u062d\u0629 \u0633\u0642\u0641 \u0641\u064a High-Grade.")
        if wants_safety:
            parts.append("\u0627\u0644\u0633\u0644\u0627\u0645\u0629 \u062a\u0634\u0645\u0644 \u062b\u0645\u0627\u0646\u064a \u0648\u0633\u0627\u0626\u062f \u0647\u0648\u0627\u0626\u064a\u0629\u060c ABS\u060c EBD\u060c HAC\u060c VSC\u060c \u0646\u0638\u0627\u0645 \u0627\u0644\u062a\u062d\u0643\u0645 \u0628\u0627\u0644\u062c\u0631\u060c \u062a\u0646\u0628\u064a\u0647 \u0636\u063a\u0637 \u0627\u0644\u0625\u0637\u0627\u0631\u0627\u062a\u060c \u0648ISOFIX.")
        if wants_warranty:
            parts.append("\u0627\u0644\u0643\u0641\u0627\u0644\u0629 \u0627\u0644\u0645\u0646\u0634\u0648\u0631\u0629 \u0647\u064a 3 \u0633\u0646\u0648\u0627\u062a \u0623\u0648 100,000 \u0643\u0645 \u0644\u0644\u0645\u0631\u0643\u0628\u0629\u060c \u0648\u0643\u0641\u0627\u0644\u0629 \u0628\u0637\u0627\u0631\u064a\u0629 \u0627\u0644\u0647\u0627\u064a\u0628\u0631\u062f 7 \u0633\u0646\u0648\u0627\u062a \u0623\u0648 120,000 \u0643\u0645\u060c \u0648\u062a\u062e\u0636\u0639 \u0644\u0644\u0634\u0631\u0648\u0637 \u0627\u0644\u0631\u0633\u0645\u064a\u0629.")
        if wants_finance:
            parts.append("\u0642\u062f \u062a\u062a\u0648\u0641\u0631 \u062a\u0633\u0647\u064a\u0644\u0627\u062a \u062a\u0645\u0648\u064a\u0644\u064a\u0629 \u0648\u0623\u0642\u0633\u0627\u0637 \u0645\u0631\u0646\u0629\u060c \u0648\u0641\u062a\u0631\u0627\u062a \u062f\u0641\u0639 \u0642\u062f \u062a\u0635\u0644 \u0625\u0644\u0649 24 \u0634\u0647\u0631\u0627\u064b \u0636\u0645\u0646 \u062d\u0645\u0644\u0627\u062a \u0645\u062d\u062f\u062f\u0629. \u0627\u0644\u0627\u0633\u062a\u0628\u062f\u0627\u0644 \u0645\u062a\u0627\u062d \u0628\u0639\u062f \u0627\u0644\u0641\u062d\u0635 \u0648\u0627\u0644\u062a\u0642\u064a\u064a\u0645\u060c \u0648\u0627\u0644\u0645\u0648\u0627\u0641\u0642\u0629 \u0648\u0627\u0644\u062a\u0641\u0627\u0635\u064a\u0644 \u0627\u0644\u0646\u0647\u0627\u0626\u064a\u0629 \u062a\u0624\u0643\u062f \u0645\u0646 \u0641\u0631\u064a\u0642 \u0627\u0644\u062a\u0645\u0648\u064a\u0644.")
        if wants_quote:
            parts.append("\u064a\u0645\u0643\u0646\u0643 \u0637\u0644\u0628 \u0639\u0631\u0636 \u0633\u0639\u0631 \u0623\u0648 \u062d\u062c\u0632 \u062a\u062c\u0631\u0628\u0629 \u0642\u064a\u0627\u062f\u0629 \u0639\u0628\u0631 \u0627\u0644\u0634\u0627\u062a \u0623\u0648 \u0642\u0646\u0648\u0627\u062a \u0645\u0631\u0643\u0632\u064a\u0629 \u062a\u0648\u064a\u0648\u062a\u0627. \u0644\u0644\u0627\u062a\u0635\u0627\u0644: 06-550-8080\u060c \u0648\u0627\u0644\u0645\u0639\u0631\u0636 \u0639\u0644\u0649 \u0634\u0627\u0631\u0639 \u0645\u0643\u0629\u060c \u0639\u0645\u0627\u0646.")
        return "\n\n".join(parts) if parts else None

    parts = []
    if wants_grades:
        parts.append("Grades: the approved sources list two principal grades, HEV Mid-Grade and HEV High-Grade. Availability and final equipment should be confirmed against current Jordan stock.")
    if wants_price:
        parts.append("Price: the approved starting price is JOD 23,500, subject to stock, campaign terms, eligibility, and final sales confirmation.")
    if wants_colours:
        parts.append("Colours: illustrative colour families include Pearl White, Metallic Silver, Black, Red, Dark Grey, and Blue. Official names and current Jordan stock availability must be confirmed by the sales team.")
    if wants_specs:
        parts.append("Main specifications: compact hybrid sedan; self-charging petrol-electric hybrid with no external charging; 1.8-litre four-cylinder petrol engine with 97 hp and 142 Nm; electric motor with 71 hp and 163 Nm; lithium-ion hybrid battery; CVT transmission; front-wheel drive; Normal, Eco, Sport, and Electric drive modes.")
    if wants_features:
        parts.append("Features include an 8-inch touchscreen, Apple CarPlay, Android Auto, Bluetooth, USB, six speakers, five seats, smart keyless entry and push-button start on applicable grades, parking sensors on applicable grades, and a moonroof on High-Grade.")
    if wants_safety:
        parts.append("Safety equipment includes eight airbags, ABS, EBD, HAC, VSC, traction control, tyre pressure warning, and ISOFIX.")
    if wants_warranty:
        parts.append("Warranty: the published vehicle warranty is 3 years or 100,000 km, and the hybrid-battery warranty is 7 years or 120,000 km, subject to official warranty terms.")
    if wants_finance:
        parts.append("Financing and trade-in: flexible financing and instalments may be available, including campaign payment periods up to 24 months where applicable. Trade-in is subject to inspection, valuation, and final acceptance. Down payment, monthly payment, fees, eligibility, approval, and total payable amount must be confirmed by the Markazia Toyota financial team.")
    if wants_quote:
        parts.append("Quotation and test drive: you can request a quotation or book a test drive through the chatbot or Markazia Toyota sales channels. You may also call 06-550-8080 or visit the Markazia Toyota showroom on Mecca Street, Amman; appointments and availability should be confirmed.")
    return "\n\n".join(parts) if parts else None


def try_yield_direct_evidence_answer(
    *,
    question: str,
    history: list[ChatHistoryTurn],
    evidence_history: list[dict[str, Any]] | None,
    db: Session,
    client_slug: str,
    client_config: ClientConfig,
) -> Generator[str, None, None] | None:
    if not looks_like_evidence_request(question):
        return None

    previous_question = get_previous_substantive_user_question(history)
    evidence_question = previous_question or question
    active_bundle = latest_evidence_bundle(
        evidence_history,
        client_slug=client_slug,
    )
    support_chunks: list[RetrievedChunk] | None = None

    if active_bundle is None and previous_question:
        support_chunks = retrieve_evidence_support_chunks(
            question=evidence_question,
            db=db,
            client_slug=client_slug,
        )
        active_bundle = build_evidence_bundle_from_chunks(
            client_slug=client_slug,
            question=evidence_question,
            answer=f"Evidence fallback for: {evidence_question}",
            chunks=support_chunks,
        )

    if looks_like_video_link_request(question):
        bundle_video_urls = [
            str(item.get("video_url") or "").strip()
            for item in bundle_items(active_bundle)
            if str(item.get("video_url") or "").strip()
        ]

        if bundle_video_urls:
            urls = unique_keep_order(bundle_video_urls)
        else:
            urls = get_video_urls(
                db=db,
                client_slug=client_slug,
            )

        return yield_evidence_answer(
            answer=format_video_answer(
                urls=urls,
                question=question,
                client_config=client_config,
            ),
            evidence_bundle=active_bundle,
        )

    if (
        looks_like_image_request(question)
        or looks_like_screenshot_request(question)
        or looks_like_website_image_request(question)
    ):
        media_context_text = f"{question}\n{previous_question or ''}".lower()
        is_general_browse = looks_like_general_media_browse_request(question)
        wants_certificate = "certificate" in question.lower()
        media_limit = requested_media_limit(question)
        evidence: list[MediaEvidenceCandidate] = []

        if active_bundle is not None and not is_general_browse:
            evidence = select_media_evidence_for_bundle(
                db=db,
                client_slug=client_slug,
                question=question,
                history=history,
                evidence_bundle=active_bundle,
                require_website=(
                    "website" in media_context_text
                    or "source image" in media_context_text
                    or looks_like_screenshot_request(question)
                ),
                require_screenshot=looks_like_screenshot_request(question),
                require_certificate=wants_certificate,
                limit=media_limit,
            )
            evidence = filter_inactive_website_media(
                evidence=evidence,
                client_config=client_config,
            )

            if not evidence:
                return yield_evidence_answer(
                    answer=format_no_bundle_media_answer(
                        evidence_bundle=active_bundle,
                        client_config=client_config,
                    ),
                    evidence_bundle=active_bundle,
                )

        if not evidence:
            evidence = select_media_evidence(
                db=db,
                client_slug=client_slug,
                question=question,
                history=history,
                require_website=(
                    not wants_certificate
                    and (
                        "website" in media_context_text
                        or "source image" in media_context_text
                        or looks_like_screenshot_request(question)
                        or is_general_browse
                    )
                ),
                require_screenshot=looks_like_screenshot_request(question),
                require_certificate=wants_certificate,
                limit=media_limit,
            )
            evidence = filter_inactive_website_media(
                evidence=evidence,
                client_config=client_config,
            )

        media = [
            item.to_media_item()
            for item in evidence
        ]
        return yield_evidence_answer(
            answer=format_media_answer(
                media=media,
                evidence=evidence,
                question=question,
                client_config=client_config,
            ),
            media=media,
            evidence_bundle=active_bundle,
        )

    if active_bundle is not None and looks_like_source_attribution_request(question):
        return yield_evidence_answer(
            answer=format_source_attribution_from_bundle(
                evidence_bundle=active_bundle,
            ),
            evidence_bundle=active_bundle,
        )

    if active_bundle is not None and looks_like_source_request(question):
        return yield_evidence_answer(
            answer=format_source_answer_from_bundle(
                evidence_bundle=active_bundle,
                wants_website="website" in question.lower(),
            ),
            evidence_bundle=active_bundle,
        )

    if support_chunks is None:
        support_chunks = retrieve_evidence_support_chunks(
            question=evidence_question,
            db=db,
            client_slug=client_slug,
        )

    if active_bundle is None:
        active_bundle = build_evidence_bundle_from_chunks(
            client_slug=client_slug,
            question=evidence_question,
            answer=f"Evidence fallback for: {evidence_question}",
            chunks=support_chunks,
        )

    if looks_like_source_attribution_request(question):
        return yield_evidence_answer(
            answer=format_source_attribution_answer(
                chunks=support_chunks,
                client_config=client_config,
            ),
            sources=build_source_payloads_from_chunks(support_chunks),
            evidence_bundle=active_bundle,
        )

    if looks_like_source_request(question):
        wants_website = "website" in question.lower()
        return yield_evidence_answer(
            answer=format_source_answer(
                chunks=support_chunks,
                client_config=client_config,
                wants_website=wants_website,
            ),
            sources=build_source_payloads_from_chunks(support_chunks),
            evidence_bundle=active_bundle,
        )

    return None


def stream_grounded_chat(
    *,
    question: str,
    history: list[ChatHistoryTurn],
    evidence_history: list[dict[str, Any]] | None = None,
    db: Session,
    client_slug: str = DEFAULT_CLIENT_SLUG,
    last_product_reference: dict[str, Any] | None = None,
    last_product_references: list[dict[str, Any]] | None = None,
    last_media_context: dict[str, Any] | None = None,
) -> Generator[str, None, None]:
    client_config = load_client_config(client_slug)
    question_plan = build_default_question_plan(question)

    if looks_like_prompt_injection_or_secret_request(question):
        yield from yield_policy_refusal(client_config=client_config)
        return

    history_answer = format_history_answer(
        request_message=question,
        client_slug=client_slug,
        session_id=None,
        frontend_history=history,
    )

    if history_answer is not None:
        yield from yield_memory_answer(answer=history_answer)
        return

    contextual_link_answer = format_contextual_link_followup(
        question=question,
        history=history,
        evidence_history=evidence_history,
        client_slug=client_slug,
    )

    if contextual_link_answer is not None:
        yield from yield_evidence_answer(answer=contextual_link_answer)
        return

    if (
        looks_like_contact_request(question)
        and not looks_like_callback_request(question)
        and client_slug != DEFAULT_CLIENT_SLUG
    ):
        yield from yield_evidence_answer(
            answer=format_trusted_contact_answer(client_config, question=question),
        )
        return

    campaign_media_answer = try_yield_campaign_media_request(
        db=db,
        client_slug=client_slug,
        question=question,
        last_media_context=last_media_context,
    )

    if campaign_media_answer is not None:
        yield from campaign_media_answer
        return

    campaign_year_correction = try_yield_campaign_year_correction(
        db=db,
        client_slug=client_slug,
        question=question,
    )

    if campaign_year_correction is not None:
        yield from campaign_year_correction
        return

    product_answer = product_answer_for_query(
        client_slug=client_slug,
        query=question,
        company_name=client_config.company_name,
        contact_info=client_config.contact_info,
        history=history,
        last_product_reference=last_product_reference,
        last_product_references=last_product_references,
    )

    if product_answer is not None:
        answer, media, results = product_answer
        references = [product_reference(result.item) for result in results[:10]]
        yield from yield_evidence_answer(
            answer=append_media_markers(answer=answer, media=media),
            media=media,
            product_references=references,
        )
        return

    if should_return_product_no_match(
        client_slug=client_slug,
        query=question,
    ):
        yield from yield_evidence_answer(
            answer=(
                "I could not find a sufficiently strong product match in the available catalog. "
                "No unrelated image was substituted."
            ),
            media=[],
            product_references=[],
        )
        return

    structured_answer = structured_config_answer(
        question=question,
        config=client_config,
    )

    if structured_answer is not None:
        yield from yield_evidence_answer(answer=structured_answer.answer)
        return

    if looks_like_live_data_request(question):
        yield from yield_evidence_answer(
            answer=unavailable_information_message(
                question=question,
                company_name=client_config.company_name,
                config=client_config,
            ),
        )
        return

    specific_media_answer = try_yield_specific_media_lookup(
        question=question,
        client_slug=client_slug,
        client_config=client_config,
    )

    if specific_media_answer is not None:
        yield from specific_media_answer
        return

    general_media_answer = try_yield_general_website_media_browse(
        question=question,
        client_slug=client_slug,
        client_config=client_config,
    )

    if general_media_answer is not None:
        yield from general_media_answer
        return

    if (
        prefers_website_scrape_sources(question)
        and not client_config.website_scrape_active
    ):
        yield from yield_evidence_answer(
            answer=website_not_scraped_message(client_config),
        )
        return

    evidence_answer = try_yield_direct_evidence_answer(
        question=question,
        history=history,
        evidence_history=evidence_history,
        db=db,
        client_slug=client_slug,
        client_config=client_config,
    )

    if evidence_answer is not None:
        yield from evidence_answer
        return

    deterministic_followup_plan = resolve_deterministic_followup_plan(
        question=question,
        history=history,
    )
    if deterministic_followup_plan is not None:
        question_plan = deterministic_followup_plan
        print(
            f"[{client_slug} follow-up resolver] "
            f"answer_question={question_plan.answer_question!r}, "
            f"retrieval_query={question_plan.retrieval_question!r}"
        )

    if history:
        try:
            decision = resolve_conversation_intent(
                question=question,
                history=history,
                client_name=client_config.company_name,
                client_slug=client_slug,
                assistant_name=client_config.assistant_name,
            )

            print(
                f"[{client_slug} conversation brain] "
                f"route={decision.route}, "
                f"intent={decision.intent}, "
                f"confidence={decision.confidence}, "
                f"standalone_question={decision.standalone_question!r}, "
                f"retrieval_query={decision.retrieval_query!r}, "
                f"referenced_turn_indexes={decision.referenced_turn_indexes}"
            )

            if decision.route == "answer_from_memory":
                memory_answer = decision.memory_answer.strip()

                if memory_answer and looks_like_conversation_memory_question(question):
                    yield from yield_memory_answer(
                        answer=memory_answer,
                    )
                    return

                question_plan = build_default_question_plan(question)

            if decision.route == "clarify":
                clarifying_question = (
                    decision.clarifying_question.strip()
                    or (
                        "هل يمكنك توضيح ما الذي تقصده؟"
                        if contains_arabic(question)
                        else "Can you clarify what you mean?"
                    )
                )

                yield from yield_clarification(
                    answer=clarifying_question,
                )
                return

            if decision.route == "retrieve_documents":
                if should_prefer_conversation_question_plan(
                    question=question,
                    deterministic_plan=deterministic_followup_plan,
                    decision=decision,
                ):
                    question_plan = build_question_plan_from_decision(
                        question=question,
                        decision=decision,
                    )

        except Exception as error:
            print(f"\n[{client_slug} conversation brain error]")
            print(f"{type(error).__name__}: {error}")
            traceback.print_exc()
            question_plan = build_default_question_plan(question)

    if question_plan.answer_question != question:
        structured_followup_answer = structured_config_answer(
            question=question_plan.answer_question,
            config=client_config,
        )
        if structured_followup_answer is not None:
            yield from yield_evidence_answer(answer=structured_followup_answer.answer)
            return

    yield encode_event(
        {
            "type": "status",
            "message": (
                f"جارٍ البحث في مصادر {client_config.company_name} المعتمدة..."
                if contains_arabic(question)
                else "Checking company knowledge..."
            ),
        }
    )

    try:
        plan = prepare_streaming_plan(
            retrieval_question=question_plan.retrieval_question,
            db=db,
            client_slug=client_slug,
        )
        if plan is None and question_plan.retrieval_question != question:
            print(
                f"[{client_slug} retrieval] Retrying with original user question "
                "after rewritten query failed."
            )
            plan = prepare_streaming_plan(
                retrieval_question=question,
                db=db,
                client_slug=client_slug,
            )

    except Exception as error:
        print(f"\n[{client_slug} retrieval error]")
        print(f"{type(error).__name__}: {error}")
        traceback.print_exc()

        yield encode_event(
            {
                "type": "error",
                "message": get_client_service_error_message(question, client_config),
            }
        )

        yield encode_event(
            {
                "type": "done",
                "grounded": False,
                "model_called": False,
            }
        )
        return

    if plan is None:
        fallback_message = unavailable_information_message(
            question=question,
            company_name=client_config.company_name,
            config=client_config,
        )

        yield encode_event(
            {
                "type": "replace",
                "answer": fallback_message,
                "grounded": False,
                "conversation_memory": False,
                "disclaimer": None,
                "sources": [],
                "media": [],
            }
        )

        yield encode_event(
            {
                "type": "done",
                "grounded": False,
                "model_called": False,
            }
        )
        return

    calculation_answer = direct_custom_calculation_answer(
        question=question_plan.answer_question,
        chunks=plan.chunks,
    )
    if calculation_answer is not None:
        yield from yield_evidence_answer(
            answer=calculation_answer,
            sources=build_source_payloads_from_chunks(plan.chunks[:1]),
        )
        return

    document_sequence_answer = direct_document_sequence_answer(
        question=question_plan.answer_question,
        chunks=plan.chunks,
        config=client_config,
    )
    if document_sequence_answer is not None:
        yield from yield_evidence_answer(
            answer=document_sequence_answer,
            sources=build_source_payloads_from_chunks(plan.chunks[:1]),
        )
        return

    table_answer = direct_table_answer(
        question=question_plan.answer_question,
        chunks=plan.chunks,
    )
    if table_answer is not None:
        yield from yield_evidence_answer(
            answer=table_answer,
            sources=build_source_payloads_from_chunks(plan.chunks[:1]),
        )
        return

    campaign_vehicle_answer = direct_campaign_vehicle_answer(
        client_slug=client_slug,
        question=question_plan.answer_question,
        chunks=plan.chunks,
    )
    if campaign_vehicle_answer is not None:
        yield from yield_evidence_answer(
            answer=campaign_vehicle_answer,
            sources=build_source_payloads_from_chunks(plan.chunks[:3]),
        )
        return

    yield encode_event(
        {
            "type": "status",
            "message": (
                "جارٍ إعداد إجابة مبنية على المصادر..."
                if contains_arabic(question)
                else "Preparing an answer..."
            ),
        }
    )

    extractor = IncrementalAnswerExtractor()
    streamed_answer = ""
    final_response = None

    try:
        with get_openai_client().responses.stream(
            model=settings.openai_chat_model,
            reasoning={
                "effort": settings.chat_reasoning_effort,
            },
            text={
                "verbosity": settings.chat_verbosity,
            },
            instructions=build_streaming_instructions(client_config),
            input=build_model_input(
                original_question=question,
                answer_question=question_plan.answer_question,
                context=plan.context,
                source_map=plan.source_map,
                history=history,
                client_config=client_config,
            ),
            text_format=GroundedModelOutput,
            max_output_tokens=settings.chat_max_output_tokens,
            store=False,
        ) as stream:
            for event in stream:
                if event.type == "response.output_text.delta":
                    answer_delta = extractor.feed(event.delta)

                    if answer_delta:
                        streamed_answer += answer_delta

                        yield encode_event(
                            {
                                "type": "delta",
                                "text": answer_delta,
                            }
                        )

                elif event.type in {
                    "response.error",
                    "error",
                }:
                    error_message = str(
                        getattr(
                            event,
                            "error",
                            "Unknown streaming error.",
                        )
                    )

                    raise RuntimeError(error_message)

            final_response = stream.get_final_response()

    except Exception as error:
        print(f"\n[{client_slug} streaming error]")
        print(f"{type(error).__name__}: {error}")
        traceback.print_exc()

        yield encode_event(
            {
                "type": "error",
                "message": get_client_service_error_message(question, client_config),
            }
        )

        yield encode_event(
            {
                "type": "done",
                "grounded": False,
                "model_called": True,
            }
        )
        return

    try:
        model_output = parse_final_output(
            final_response=final_response,
            raw_output=extractor.raw_output,
        )

        print(f"\n[{client_slug} final model output]")
        print(safe_log_text(model_output.model_dump()))

        print(f"\n[{client_slug} available source ids]")
        print(list(plan.source_map.keys()))

        sources = build_source_payloads(
            model_output=model_output,
            source_map=plan.source_map,
            client_slug=client_slug,
        )
        evidence_source_ids = resolve_valid_source_ids(
            model_output=model_output,
            source_map=plan.source_map,
        )
        evidence_bundle = build_evidence_bundle(
            client_slug=client_slug,
            question=question_plan.answer_question,
            answer=model_output.answer.strip(),
            source_map=plan.source_map,
            source_ids=evidence_source_ids,
        )

    except Exception as error:
        print(f"\n[{client_slug} final parsing error]")
        print(f"{type(error).__name__}: {error}")
        traceback.print_exc()

        model_output = None
        sources = None
        evidence_bundle = None

    if model_output is None or sources is None:
        fallback_message = unavailable_information_message(
            question=question,
            company_name=client_config.company_name,
            config=client_config,
        )

        yield encode_event(
            {
                "type": "replace",
                "answer": fallback_message,
                "grounded": False,
                "conversation_memory": False,
                "disclaimer": None,
                "sources": [],
                "media": [],
            }
        )

        yield encode_event(
            {
                "type": "done",
                "grounded": False,
                "model_called": True,
            }
        )
        return

    media = build_media_payloads(
        original_question=question,
        answer_question=question_plan.answer_question,
        context=plan.context,
        client_config=client_config,
    )

    final_answer = append_media_markers(
        answer=model_output.answer.strip(),
        media=media,
    )

    if streamed_answer.strip() != final_answer:
        yield encode_event(
            {
                "type": "replace",
                "answer": final_answer,
                "grounded": True,
                "conversation_memory": False,
                "disclaimer": None,
                "sources": sources,
                "media": media,
                "evidence_bundle": evidence_bundle,
            }
        )
    else:
        yield encode_event(
            {
                "type": "sources",
                "sources": sources,
                "media": media,
                "evidence_bundle": evidence_bundle,
            }
        )

    yield encode_event(
        {
            "type": "done",
            "grounded": True,
            "conversation_memory": False,
            "model_called": True,
        }
    )
