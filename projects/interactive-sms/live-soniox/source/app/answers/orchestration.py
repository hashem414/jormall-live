from __future__ import annotations

import json
import re
import traceback
from dataclasses import dataclass, replace
from typing import Any, Generator

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.language_detection import detect_supported_language
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
    get_no_answer_message,
    get_question_language,
    question_requests_comprehensive_answer,
    looks_like_live_data_request,
    structured_config_answer,
    unavailable_information_message,
    row_to_retrieved_chunk,
)
from app.services.conversation_intent_service import (
    ConversationBrainDecision,
    resolve_conversation_intent,
)
from app.services.openai_client import get_openai_client, model_response_controls
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
from app.services.answer_safety_service import (
    business_generation_fallback,
    combine_partial_answer_with_graceful_fallback,
    greeting_only_answer,
    has_meaningful_answer,
)
from app.services.public_branding_service import (
    PublicBrandingStreamGuard,
    canonicalize_public_branding,
    canonicalize_public_payload,
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
    return detect_supported_language(text) == "ar"


def language_preference_answer(question: str) -> str | None:
    normalized = re.sub(r"\s+", " ", question.strip().lower())
    wants_arabic = bool(
        re.search(r"\b(?:speak|talk|answer|respond|continue)\b.{0,24}\barabic\b", normalized)
        or re.search(r"(?:احكي|تكلم|تحدث|جاوب|كمل).{0,16}(?:عربي|العربية)", normalized)
        or re.search(r"(?:بتحكي|تتكلم|تتحدث).{0,12}(?:عربي|العربية)", normalized)
    )
    if wants_arabic:
        return "بالتأكيد، سأتحدث معك بالعربية. كيف يمكنني مساعدتك؟"

    wants_english = bool(
        re.search(r"\b(?:speak|talk|answer|respond|continue)\b.{0,24}\benglish\b", normalized)
        or re.search(r"(?:احكي|تكلم|تحدث|جاوب|كمل).{0,16}(?:انجليزي|إنجليزي|الإنجليزية)", normalized)
    )
    if wants_english:
        return "Of course. I’ll continue in English. How can I help?"
    return None


def get_required_answer_language(question: str) -> str:
    return "Arabic" if contains_arabic(question) else "English"


def normalize_repeated_question(text: str) -> str:
    normalized = re.sub(r"[\u0640\u064B-\u065F\u0670\u06D6-\u06ED]", "", text)
    normalized = normalized.casefold()
    normalized = normalized.translate(
        str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي"})
    )
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    return re.sub(r"\s+", " ", normalized).strip()


def repeated_answer_from_history(
    question: str,
    history: list[ChatHistoryTurn],
) -> str | None:
    """Return the latest exact grounded answer for the same normalized question."""
    target = normalize_repeated_question(question)
    if not target:
        return None

    for index in range(len(history) - 2, -1, -1):
        user_turn = history[index]
        assistant_turn = history[index + 1]
        if user_turn.role != "user" or assistant_turn.role != "assistant":
            continue
        if normalize_repeated_question(user_turn.content) != target:
            continue
        answer = assistant_turn.content.strip()
        if answer and not answer.startswith("Earlier conversation summary:"):
            return answer
    return None


def get_service_error_message(question: str) -> str:
    return business_generation_fallback(question)


def get_client_service_error_message(
    question: str,
    client_config: ClientConfig,
) -> str:
    if client_config.client_slug == DEFAULT_CLIENT_SLUG:
        return get_service_error_message(question)
    return business_generation_fallback(question)


def looks_like_contact_request(text: str) -> bool:
    normalized = text.lower()
    return bool(
        re.search(
            r"\b(contact(?: info| information)?|phone(?: number)?|telephone|email|"
            r"call you|reach you|whatsapp|customer service number)\b",
            normalized,
        )
    )


def format_trusted_contact_answer(client_config: ClientConfig) -> str:
    contact = client_config.contact_info.strip()
    if contact:
        return f"Contact information: {contact}"
    return (
        f"I do not have validated contact details for {client_config.company_name} "
        "in the configured company profile."
    )


def encode_event(payload: dict) -> str:
    return json.dumps(
        canonicalize_public_payload(payload),
        ensure_ascii=False,
    ) + "\n"


def safe_log_text(value: object) -> str:
    return str(value).encode(
        "ascii",
        errors="backslashreplace",
    ).decode("ascii")


def build_streaming_instructions(
    client_config: ClientConfig,
    *,
    voice_mode: bool = False,
    comprehensive_answer: bool = False,
) -> str:
    voice_instruction = (
        "\n20. VOICE RESPONSE MODE: Answer only the exact question in one or two "
        "short, natural sentences. Do not use headings, bullet lists, preambles, "
        "or additional related facts unless they are required to answer."
        if voice_mode and not comprehensive_answer
        else (
            "\n20. VOICE RESPONSE MODE: The user requested broad or complete coverage. "
            "Give the full supported answer in natural spoken language; do not enforce "
            "the normal two-sentence voice limit. Organize related details clearly and "
            "avoid repetition."
            if voice_mode
            else ""
        )
    )
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
        + "\n15a. For questions asking about the company, all services, all products, "
        "all benefits, or a full explanation, provide a complete categorized answer "
        "covering all relevant retrieved excerpts. Do not omit requested categories "
        "merely to keep the answer short."
        + "\n15b. For broad catalog questions, first identify every distinct product or "
        "service heading present in the approved excerpts and cover each one. Prefer "
        "a concise description of every supported item over detailed descriptions of "
        "only the first few items."
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
        + voice_instruction
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


def broad_catalog_coverage_requirement(
    *,
    question: str,
    source_map: dict[str, RetrievedChunk],
) -> str:
    """Require complete coverage using product headings found in retrieved evidence."""

    if not looks_like_service_overview_question(question):
        return ""
    product_names = list(
        dict.fromkeys(
            product_heading_name(chunk.content)
            for chunk in source_map.values()
            if product_heading_name(chunk.content)
        )
    )
    if len(product_names) < 2:
        return ""
    headings = "\n".join(f"- {name}" for name in product_names)
    return (
        "CATALOG COVERAGE REQUIREMENT:\n"
        "Name every official product below exactly as written, then explain its "
        "supported purpose or uses concisely in the required answer language. Do "
        "not stop after the first few products:\n"
        f"{headings}"
    )


def ensure_broad_catalog_coverage(
    *,
    answer: str,
    question: str,
    chunks: list[RetrievedChunk],
) -> str:
    """Prepend the complete retrieved catalog when a generated answer omits items."""

    if not looks_like_service_overview_question(question):
        return answer
    product_names = list(
        dict.fromkeys(
            product_heading_name(chunk.content)
            for chunk in chunks
            if product_heading_name(chunk.content)
        )
    )
    if len(product_names) < 2 or all(
        product_name.casefold() in answer.casefold()
        for product_name in product_names
    ):
        return answer
    heading = (
        "قائمة منتجات الرسائل النصية المعتمدة الكاملة:"
        if contains_arabic(question)
        else "Complete approved SMS product list:"
    )
    catalog = "\n".join(f"- {product_name}" for product_name in product_names)
    return f"{heading}\n{catalog}\n\n{answer.strip()}"


def build_model_input(
    *,
    original_question: str,
    answer_question: str,
    context: str,
    source_map: dict[str, RetrievedChunk],
    history: list[ChatHistoryTurn],
    client_config: ClientConfig,
    voice_mode: bool = False,
) -> str:
    history_text = format_recent_history(history)

    required_answer_language = get_required_answer_language(
        original_question
    )

    protected_names: list[str] = []
    assistant_brand_name = re.sub(
        r"\s+(?:assistant|chatbot)\s*$",
        "",
        str(client_config.assistant_name or ""),
        flags=re.IGNORECASE,
    ).strip()
    for candidate in (
        assistant_brand_name,
        client_config.assistant_name,
        client_config.company_name,
        *re.findall(
            r"\b[A-Z][A-Za-z0-9-]*(?:\s+(?:[A-Z][A-Za-z0-9-]*|SMS|API|GPT)){0,4}",
            original_question,
        ),
    ):
        clean_candidate = re.sub(r"\s+", " ", str(candidate or "")).strip()
        if clean_candidate and clean_candidate not in protected_names:
            protected_names.append(clean_candidate)
    if required_answer_language == "Arabic":
        protected_name_instruction = (
            "\nPUBLIC COMPANY NAME: Write the company name only as جورمول. "
            "Do not write the company name in Latin characters or use an alternate name."
        )
    else:
        protected_name_instruction = (
            "\nPROTECTED NAME SPELLING: If any of these names is mentioned, copy it "
            "exactly in Latin characters; never translate or transliterate it: "
            + ", ".join(protected_names[:8])
            if protected_names
            else ""
        )

    language_instruction = (
        f"REQUIRED ANSWER LANGUAGE: {required_answer_language}\n"
        "Write the complete answer in that language, even if the approved "
        "document excerpts are written in another language.\n"
        "Do not switch answer languages because of the document language."
        f"{protected_name_instruction}"
    )
    if voice_mode and not question_requests_comprehensive_answer(original_question):
        language_instruction += (
            "\nVOICE OUTPUT LIMIT: Give only the direct answer in at most two short "
            "sentences and normally 20 to 35 spoken words. Include only the core fact "
            "needed for the question. No lists, headings, introductions, repeated "
            "details, or extra suggestions."
        )

    question_section = (
        f"Original user question:\n{original_question}\n\n"
        f"Resolved standalone question:\n{answer_question}"
    )

    source_id_section = (
        "Available approved source IDs that may be used in used_source_ids:\n"
        f"{format_available_source_ids(source_map)}"
    )
    catalog_coverage_section = broad_catalog_coverage_requirement(
        question=original_question,
        source_map=source_map,
    )
    catalog_coverage_block = (
        f"{catalog_coverage_section}\n\n" if catalog_coverage_section else ""
    )

    if history_text:
        return (
            f"{language_instruction}\n\n"
            "Recent conversation context "
            "(for reference resolution only; not factual evidence):\n"
            f"{history_text}\n\n"
            f"{question_section}\n\n"
            f"{catalog_coverage_block}"
            f"{source_id_section}\n\n"
            f"Approved {client_config.company_name} document excerpts:\n{context}"
        )

    return (
        f"{language_instruction}\n\n"
        f"{question_section}\n\n"
        f"{catalog_coverage_block}"
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

    explicit_pricing_request = bool(
        re.search(
            r"\b(price|pricing|prices|rate|rates|fee|fees|cost|costs|quotation|quote|how much)\b",
            query,
            flags=re.IGNORECASE,
        )
        or any(term in query for term in ("سعر", "أسعار", "اسعار", "تكلفة", "رسوم", "كم تبلغ"))
    )
    if not explicit_pricing_request:
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
        re.search(rf"\b{re.escape(phrase)}\b", normalized)
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
            "JorMall bulk SMS SMS vendor "
            "هيئة تنظيم قطاع الاتصالات مرخص رخصة الاتصالات الفئوية العامة "
            "فئة ج جورمول رسائل الجملة"
        )

    return f"{query}{generic_evidence_terms}{video_terms}{license_terms}"


def looks_like_company_overview_question(query: str) -> bool:
    """Recognize natural company-overview questions in English and Jordanian Arabic."""
    normalized = re.sub(r"\s+", " ", query.casefold()).strip(" .?!؟،")
    brand = r"(?:jormall|jor\s+mall|the\s+company|your\s+company|جور\s*مول|الشركة|شركتكم)"
    english = (
        rf"\b(?:who|what)\s+is\s+{brand}(?=$|[؟?!.])|"
        rf"\bwhat\s+(?:do\s+you|does\s+{brand})\s+do\b|"
        rf"\b(?:tell|talk)\s+(?:me\s+)?about\s+{brand}\b|"
        rf"\b(?:company|business)\s+(?:overview|profile|background|information)\b|"
        rf"\babout\s+{brand}\b"
    )
    arabic = (
        rf"(?:مين|من\s+هي|ما\s+هي)\s+{brand}|"
        rf"(?:شو|ايش|إيش|ماذا)\s+(?:بتعمل|تعمل)\s+{brand}|"
        rf"(?:احكيلي|احكي\s+لي|احكي|حدثني|تحدث)\s+عن\s+{brand}|"
        rf"(?:نبذة|معلومات)\s+عن\s+{brand}"
    )
    return bool(re.search(english, normalized) or re.search(arabic, normalized))


def looks_like_service_overview_question(query: str) -> bool:
    """Recognize broad requests for the services the company provides."""
    normalized = re.sub(r"\s+", " ", query.casefold()).strip(" .?!؟،")
    return bool(
        re.search(
            r"\bwhat (?:services|products|solutions) (?:do you|does jor\s*mall) "
            r"(?:offer|provide|have)\b|"
            r"\bwhat (?:do you|can you) (?:offer|provide)\b|"
            r"\b(?:list|describe|explain|tell me about) (?:all )?(?:your|jor\s*mall'?s) "
            r"(?:services|products|solutions)\b|"
            r"\bwhat\b.{0,45}\b(?:services|products|solutions)\b.{0,60}"
            r"\b(?:you|jor\s*mall)\b.{0,25}\b(?:offer|provide|have)\b",
            normalized,
        )
        or re.search(
            r"(?:شو|ايش|إيش|ما|ماذا)\s+(?:هي\s+)?(?:خدماتكم|منتجاتكم|حلولكم)|"
            r"(?:ما|ماذا)\s+(?:هي\s+)?(?:خدمات|منتجات|حلول|أنواع\s+الرسائل)\b|"
            r"(?:شو|ايش|إيش|ماذا)\s+(?:بتقدموا|بتقدمو|تقدمون|تقدموا)|"
            r"(?:اذكر|اشرح|احكيلي\s+عن|احكي\s+لي\s+عن)\s+(?:كل\s+|جميع\s+)?"
            r"(?:خدمات|منتجات|حلول)\s+(?:جور\s*مول|الشركة)",
            normalized,
        )
    )


NAMED_PRODUCT_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Service Messages", (r"\bservice messages?\b", r"رسائل\s+(?:الخدمة|الخدمات|الخدمية)")),
    ("Smart Reach SMS to JorMall’s Database Messages", (r"\bsmart reach\b", r"سمارت\s+ريتش")),
    ("OTP & Financial SMS Messaging", (r"\botp\b", r"رسائل\s+(?:otp|التحقق|كلمة\s+المرور)")),
    ("Interactive SMS", (r"\binteractive sms\b", r"الرسائل\s+التفاعلية")),
    ("International SMS Messaging", (r"\binternational sms\b", r"الرسائل\s+الدولية")),
    ("Premium Messages", (r"\bpremium messages?\b", r"الرسائل\s+المميزة")),
    ("Client-based SMS Messages", (r"\bclient[- ]based sms\b", r"رسائل\s+قاعدة\s+بيانات\s+العميل")),
)


def named_product_from_question(query: str) -> str:
    """Map bilingual product wording to the heading stored in approved documents."""
    normalized = re.sub(r"\s+", " ", query.casefold()).strip()
    for product_name, aliases in NAMED_PRODUCT_ALIASES:
        if any(re.search(alias, normalized, flags=re.IGNORECASE) for alias in aliases):
            return product_name
    return ""


def expand_company_and_service_query(query: str) -> str:
    """Add approved-source vocabulary to short, semantically clear overview requests."""
    named_product = named_product_from_question(query)
    if named_product:
        return f"{query} Product Name: {named_product} {named_product} description features uses compliance"
    if looks_like_company_overview_question(query):
        return (
            f"{query} JorMall company business overview "
            "Jordan experience services bulk SMS interactive campaign chatbot license "
            "sectors contact معلومات جورمول نبذة خدمات"
        )
    if looks_like_service_overview_question(query):
        return (
            f"{query} JorMall services products solutions bulk SMS targeted campaigns "
            "Service Messages OTP API Smart Reach SMS interactive campaign chatbot "
            "خدمات جورمول منتجات الرسائل النصية الحملات الشات بوت"
        )
    return query


def expand_retrieval_query(query: str) -> str:
    expanded_query = expand_company_and_service_query(query)
    expanded_query = expand_contract_approval_query(expanded_query)
    expanded_query = expand_document_pricing_query(expanded_query)
    expanded_query = expand_arabic_table_query(expanded_query)
    expanded_query = expand_visual_evidence_query(expanded_query)

    return expanded_query


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


PRODUCT_HEADING_PATTERN = re.compile(
    r"^\s*Product\s+Name\s*:\s*([^\r\n]+)",
    flags=re.IGNORECASE,
)
GENERIC_PRODUCT_WORDS = {
    "product", "name", "sms", "message", "messages", "messaging",
    "jormall", "database", "the", "to", "and",
}
BROAD_PRODUCT_QUESTION_PATTERN = re.compile(
    r"\b(?:all|list|types?|kinds?|available)\b.{0,30}\b(?:sms|messages?|services?|products?)\b"
    r"|(?:ما|ماذا)\s+(?:هي|عن)\s+(?:كل|جميع|أنواع|قائمة)\s+(?:الخدمات|الرسائل|المنتجات)",
    flags=re.IGNORECASE,
)


def product_heading_name(content: str) -> str:
    match = PRODUCT_HEADING_PATTERN.search(content or "")
    return match.group(1).strip() if match else ""


def compact_product_overview_content(content: str) -> str:
    """Keep a source-derived product name and description for broad catalog answers."""

    product_name = product_heading_name(content)
    if not product_name:
        return content
    description_match = re.search(
        r"\bDescription\s*:\s*(.+?)(?=\n(?:Key Features|Features|Use Cases?|"
        r"Regulatory Compliance|Client Obligations)\s*:|\Z)",
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if description_match is None:
        return content
    description = re.sub(r"\s+", " ", description_match.group(1)).strip()
    return f"Product Name: {product_name}\nDescription: {description}"


def question_targets_product_heading(*, question: str, product_name: str) -> bool:
    if (
        not product_name
        or BROAD_PRODUCT_QUESTION_PATTERN.search(question)
        or looks_like_service_overview_question(question)
    ):
        return False

    question_tokens = set(re.findall(r"[a-z0-9]+", question.lower()))
    name_tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", product_name.lower())
        if token not in GENERIC_PRODUCT_WORDS and len(token) > 2
    }
    if question_tokens & name_tokens:
        return True

    # Arabic questions may name an English-labelled product descriptively.
    # The vector-ranked product heading remains the selector, except for broad
    # browse/list questions handled above.
    return contains_arabic(question)


def isolate_named_product_context(
    *,
    question: str,
    chunks: list[RetrievedChunk],
    db: Session,
    client_slug: str,
) -> list[RetrievedChunk]:
    """Keep one product's contiguous source section from bleeding into another."""
    if not chunks:
        return chunks

    anchor = chunks[0]
    requested_product = named_product_from_question(question)
    if requested_product:
        requested_key = requested_product.casefold()
        matching_anchor = next(
            (
                chunk
                for chunk in chunks
                if product_heading_name(chunk.content).casefold() == requested_key
            ),
            None,
        )
        if matching_anchor is None:
            matching_row = db.execute(
                select(DocumentChunk, Document)
                .join(Document, Document.id == DocumentChunk.document_id)
                .where(
                    DocumentChunk.client_slug == client_slug,
                    Document.client_slug == client_slug,
                    Document.status == "active",
                    Document.visibility == "client",
                    DocumentChunk.content.ilike(f"%Product Name: {requested_product}%"),
                )
                .order_by(DocumentChunk.chunk_index)
                .limit(1)
            ).first()
            if matching_row is not None:
                database_chunk, document = matching_row
                matching_anchor = row_to_retrieved_chunk(
                    database_chunk=database_chunk,
                    document=document,
                    similarity=max(chunk.similarity for chunk in chunks),
                )
        if matching_anchor is not None:
            anchor = matching_anchor
    product_name = product_heading_name(anchor.content)
    if not question_targets_product_heading(question=question, product_name=product_name):
        return chunks

    anchor_row = db.scalar(
        select(DocumentChunk).where(
            DocumentChunk.id == anchor.chunk_id,
            DocumentChunk.client_slug == client_slug,
        )
    )
    if anchor_row is None:
        return chunks

    rows = db.execute(
        select(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            DocumentChunk.document_id == anchor.document_id,
            DocumentChunk.chunk_index >= anchor_row.chunk_index,
            DocumentChunk.client_slug == client_slug,
            Document.client_slug == client_slug,
            Document.status == "active",
            Document.visibility == "client",
        )
        .order_by(DocumentChunk.chunk_index)
        .limit(12)
    ).all()

    isolated: list[RetrievedChunk] = []
    for database_chunk, document in rows:
        if isolated and product_heading_name(database_chunk.content):
            break
        isolated.append(
            row_to_retrieved_chunk(
                database_chunk=database_chunk,
                document=document,
                similarity=anchor.similarity,
            )
        )

    if not isolated:
        return chunks

    print(
        f"[{client_slug} retrieval] isolated_product={safe_log_text(repr(product_name))}, "
        f"section_chunks={len(isolated)}"
    )
    return isolated


def expand_broad_product_context(
    *,
    question: str,
    chunks: list[RetrievedChunk],
    db: Session,
    client_slug: str,
) -> list[RetrievedChunk]:
    """Include every product overview when the user asks for the full list."""
    if not (
        BROAD_PRODUCT_QUESTION_PATTERN.search(question)
        or looks_like_service_overview_question(question)
    ) or not chunks:
        return chunks

    candidate_document_ids = list(dict.fromkeys(
        chunk.document_id
        for chunk in chunks
        if "product" in chunk.document_title.casefold()
        or product_heading_name(chunk.content)
    ))
    if not candidate_document_ids:
        return chunks

    rows = db.execute(
        select(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            DocumentChunk.document_id.in_(candidate_document_ids),
            DocumentChunk.client_slug == client_slug,
            Document.client_slug == client_slug,
            Document.status == "active",
            Document.visibility == "client",
        )
        .order_by(Document.original_filename, DocumentChunk.chunk_index)
    ).all()
    best_similarity = max(chunk.similarity for chunk in chunks)
    overview_chunks = [
        row_to_retrieved_chunk(
            database_chunk=database_chunk,
            document=document,
            similarity=best_similarity,
        )
        for database_chunk, document in rows
        if product_heading_name(database_chunk.content)
        or database_chunk.chunk_index == 0
    ]
    return dedupe_retrieved_chunks(overview_chunks + chunks)


def compact_broad_product_context(
    *,
    question: str,
    chunks: list[RetrievedChunk],
) -> list[RetrievedChunk]:
    """Give broad catalog requests one concise evidence excerpt per product."""

    if not looks_like_service_overview_question(question):
        return chunks
    product_chunks = [chunk for chunk in chunks if product_heading_name(chunk.content)]
    if len(product_chunks) < 2:
        return chunks
    return [
        replace(chunk, content=compact_product_overview_content(chunk.content))
        for chunk in product_chunks
    ]


def dedupe_retrieved_chunks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    seen: set[str] = set()
    unique: list[RetrievedChunk] = []
    for chunk in chunks:
        key = str(chunk.chunk_id)
        if key not in seen:
            seen.add(key)
            unique.append(chunk)
    return unique


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

    if not has_strong_context_overlap(
        question=retrieval_question,
        chunks=retrieval_results,
        client_config=client_config,
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
    context_chunks = expand_broad_product_context(
        question=retrieval_question,
        chunks=context_chunks,
        db=db,
        client_slug=client_slug,
    )
    context_chunks = compact_broad_product_context(
        question=retrieval_question,
        chunks=context_chunks,
    )
    context_chunks = isolate_named_product_context(
        question=retrieval_question,
        chunks=context_chunks,
        db=db,
        client_slug=client_slug,
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


def website_not_scraped_message(
    *,
    question: str,
    client_config: ClientConfig,
) -> str:
    return get_no_answer_message(
        question,
        client_config.company_name,
        assistant_name=client_config.assistant_name,
        contact_info=client_config.contact_info,
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
    cleaned = re.sub(r"\s+", " ", canonicalize_public_branding(text)).strip()

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


def yield_reused_answer(
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
            "model_called": False,
            "reused_answer": True,
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
            return "دليل صورة خاص بـ جورمول"
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

    return answer.strip() + "\n\n" + "\n".join(markers)


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
            answer=website_not_scraped_message(
                question=question,
                client_config=client_config,
            ),
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
            answer=website_not_scraped_message(
                question=question,
                client_config=client_config,
            ),
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
    normalized = str(text or "").casefold()
    return has_any_phrase(
        normalized,
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
            "act as an administrator",
            "another client's private",
            "another client’s private",
            "other client's private",
            "cross-tenant",
            "تجاهل التعليمات",
            "تجاهل جميع التعليمات",
            "تجاهل كل التعليمات",
            "موجه النظام",
            "تعليمات النظام",
            "تعليمات المطور",
            "التعليمات المخفية",
            "مفتاح api",
            "المفتاح السري",
            "تصرف كمدير",
            "مستندات عميل آخر",
            "بيانات عميل آخر",
        ),
    )


def yield_policy_refusal(
    *,
    client_config: ClientConfig,
    question: str = "",
) -> Generator[str, None, None]:
    if contains_arabic(question):
        answer = (
            "يمكنني الإجابة فقط من مصادر جورمول المعتمدة، "
            "ولا يمكنني تجاهل هذه القواعد أو كشف التعليمات المخفية أو البيانات الخاصة."
        )
    else:
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


from app.answers.focused import ambiguous_question, clarification, focused_config_answer


def stream_grounded_chat(
    *,
    question: str,
    history: list[ChatHistoryTurn],
    evidence_history: list[dict[str, Any]] | None = None,
    db: Session,
    client_slug: str = DEFAULT_CLIENT_SLUG,
    last_product_reference: dict[str, Any] | None = None,
    last_product_references: list[dict[str, Any]] | None = None,
    voice_mode: bool = False,
) -> Generator[str, None, None]:
    client_config = load_client_config(client_slug)
    question_plan = build_default_question_plan(question)

    language_answer = language_preference_answer(question)
    if language_answer is not None:
        yield from yield_memory_answer(answer=language_answer)
        return

    greeting_answer = greeting_only_answer(question)
    if greeting_answer is not None:
        yield from yield_memory_answer(answer=greeting_answer)
        return

    if looks_like_prompt_injection_or_secret_request(question):
        yield from yield_policy_refusal(
            client_config=client_config,
            question=question,
        )
        return

    focused = focused_config_answer(question, client_config)
    if focused is not None:
        yield from yield_evidence_answer(answer=focused[0])
        return

    if not history and ambiguous_question(question):
        yield from yield_clarification(answer=clarification(question))
        return

    repeated_answer = repeated_answer_from_history(question, history)
    if repeated_answer is not None:
        yield from yield_reused_answer(answer=repeated_answer)
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
        and client_slug != DEFAULT_CLIENT_SLUG
        and not has_active_client_chunks(db=db, client_slug=client_slug)
    ):
        yield from yield_evidence_answer(
            answer=format_trusted_contact_answer(client_config),
        )
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
            answer=website_not_scraped_message(
                question=question,
                client_config=client_config,
            ),
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

    # A self-contained company/service question must not be turned into an
    # ambiguous follow-up merely because the browser has earlier chat history.
    standalone_overview_question = (
        looks_like_company_overview_question(question)
        or looks_like_service_overview_question(question)
    )

    if history and not standalone_overview_question:
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
                "جارٍ البحث في مصادر جورمول المعتمدة..."
                if contains_arabic(question)
                else "Checking company knowledge..."
            ),
        }
    )

    retrieval_question_for_plan = (
        question
        if looks_like_service_overview_question(question)
        else question_plan.retrieval_question
    )

    try:
        plan = prepare_streaming_plan(
            retrieval_question=retrieval_question_for_plan,
            db=db,
            client_slug=client_slug,
        )
        if plan is None and retrieval_question_for_plan != question:
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
                "type": "replace",
                "answer": business_generation_fallback(question),
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
                "error_state": "retrieval_error",
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
    streaming_error: Exception | None = None

    for generation_attempt in range(2):
        extractor = IncrementalAnswerExtractor()
        streamed_answer = ""
        branding_stream = PublicBrandingStreamGuard(
            language="ar" if contains_arabic(question) else "en",
        )
        try:
            with get_openai_client().responses.stream(
                model=settings.openai_chat_model,
                instructions=build_streaming_instructions(
                    client_config,
                    voice_mode=voice_mode,
                    comprehensive_answer=question_requests_comprehensive_answer(question),
                ),
                input=build_model_input(
                    original_question=question,
                    answer_question=question_plan.answer_question,
                    context=plan.context,
                    source_map=plan.source_map,
                    history=history,
                    client_config=client_config,
                    voice_mode=voice_mode,
                ),
                text_format=GroundedModelOutput,
                max_output_tokens=settings.chat_max_output_tokens,
                store=False,
                **model_response_controls(
                    model=settings.openai_chat_model,
                    verbosity=settings.chat_verbosity,
                ),
            ) as stream:
                for event in stream:
                    if event.type == "response.output_text.delta":
                        answer_delta = extractor.feed(event.delta)

                        if answer_delta:
                            streamed_answer += answer_delta
                            safe_delta = branding_stream.feed(answer_delta)
                            if safe_delta:
                                yield encode_event(
                                    {
                                        "type": "delta",
                                        "text": safe_delta,
                                    }
                                )

                    elif event.type in {"response.error", "error"}:
                        raise RuntimeError(
                            str(getattr(event, "error", "Unknown streaming error."))
                        )

                final_response = stream.get_final_response()
            final_safe_delta = branding_stream.flush()
            if final_safe_delta:
                yield encode_event(
                    {
                        "type": "delta",
                        "text": final_safe_delta,
                    }
                )
            streaming_error = None
            break
        except Exception as error:
            streaming_error = error
            if generation_attempt == 0 and not has_meaningful_answer(streamed_answer):
                print(f"[{client_slug} streaming retry] {type(error).__name__}: {error}")
                continue
            break

    if streaming_error is not None:
        error = streaming_error
        print(f"\n[{client_slug} streaming error]")
        print(f"{type(error).__name__}: {error}")
        traceback.print_exception(error)

        if has_meaningful_answer(streamed_answer):
            visible_answer = combine_partial_answer_with_graceful_fallback(
                question,
                streamed_answer,
            )
            yield encode_event(
                {
                    "type": "replace",
                    "answer": canonicalize_public_branding(
                        visible_answer,
                        language="ar" if contains_arabic(question) else "en",
                    ),
                    "grounded": False,
                    "conversation_memory": False,
                    "disclaimer": None,
                    "sources": [],
                    "media": [],
                }
            )
        else:
            yield encode_event(
                {
                    "type": "replace",
                    "answer": business_generation_fallback(question),
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
                "error_state": "partial_generation_error" if has_meaningful_answer(streamed_answer) else "generation_error",
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
        catalog_completed_answer = ensure_broad_catalog_coverage(
            answer=model_output.answer.strip(),
            question=question,
            chunks=plan.chunks,
        )
        completed_model_answer = canonicalize_public_branding(
            catalog_completed_answer,
            language="ar" if contains_arabic(question) else "en",
        )
        catalog_was_completed = catalog_completed_answer != model_output.answer.strip()
        evidence_source_ids = resolve_valid_source_ids(
            model_output=model_output,
            source_map=plan.source_map,
        )
        if catalog_was_completed:
            sources = build_source_payloads_from_chunks(plan.chunks)
            evidence_source_ids = list(plan.source_map.keys())
        evidence_bundle = build_evidence_bundle(
            client_slug=client_slug,
            question=question_plan.answer_question,
            answer=completed_model_answer,
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
        fallback_message = business_generation_fallback(question)
        if has_meaningful_answer(streamed_answer):
            fallback_message = combine_partial_answer_with_graceful_fallback(
                question,
                streamed_answer,
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
                "error_state": "partial_generation_error" if has_meaningful_answer(streamed_answer) else "generation_error",
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
        answer=completed_model_answer,
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
