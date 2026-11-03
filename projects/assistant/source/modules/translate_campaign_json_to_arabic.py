# -*- coding: utf-8 -*-
"""Translate an already-generated English campaign JSON into Arabic.

This keeps English and Arabic DOCX files identical in structure and meaning:
the campaign is generated once in English, then the Arabic JSON is a literal
translation of the same answers instead of asking the model to create a new
Arabic campaign from scratch.
"""
import os
import json
from copy import deepcopy
from dotenv import load_dotenv
from .language_helpers import localize_header, sanitize_arabic_sms_answer
from .openai_client import create_openai_client

load_dotenv()

_TRANSLATION_SYSTEM = """
You are a precise professional English-to-Arabic translator for JorMall client campaign documents.
Translate the user's text into Arabic only.
Rules:
- Keep the exact same meaning, recommendations, facts, quantities, order, and number of points.
- Do not add, remove, summarize, expand, or improve the marketing ideas.
- Preserve line breaks, bullet prefixes, numbering, section structure, URLs, phone numbers, brand names, and product names.
- Keep names such as JorMall, SmartBuy, Apple, Samsung, Lenovo, Dell, Sony, Huawei, Xiaomi, Bosch, Beko in Latin letters unless already Arabic.
- If the text is already Arabic, return it unchanged except for minor spelling normalization only.
- Return only the translated text, with no notes.
""".strip()


def _client():
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip().strip('"').strip("'")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing. Add it to the .env file beside app.py, then restart the app.")
    return create_openai_client(api_key)


def _looks_empty(text):
    return not str(text or "").strip()


def _contains_arabic(text):
    text = str(text or "")
    return any("\u0600" <= ch <= "\u06FF" or "\u0750" <= ch <= "\u077F" or "\u08A0" <= ch <= "\u08FF" for ch in text)


def _mostly_arabic_or_symbols(text):
    """True when text is already Arabic content. Latin brand names/numbers are ignored.

    This is important because English DOCX already contains Arabic SMS suggestions.
    Sending those through the translator caused the model to rewrite them, so the
    Arabic DOCX no longer matched the English DOCX.
    """
    text = str(text or "")
    arabic = sum(1 for ch in text if "\u0600" <= ch <= "\u06FF" or "\u0750" <= ch <= "\u077F" or "\u08A0" <= ch <= "\u08FF")
    latin = sum(1 for ch in text if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))
    # Allow Latin brand names inside Arabic SMS.
    return arabic > 0 and arabic >= max(6, latin // 2)


def _should_keep_original_text(text, label="content"):
    label_l = str(label or "").lower()

    # The Arabic DOCX must still include a dedicated English 160-character SMS
    # section, exactly like the English DOCX includes Arabic SMS sections.
    # Do not send this section through the Arabic translator, even when the
    # whole document language is Arabic.
    english_only_sections = (
        "english sms suggestions",
        "social media caption (english)",
        "radio announcement script (english)",
        "radio dialogue script (english)",
        "english opt-out sms",
    )
    if any(token in label_l for token in english_only_sections):
        return True

    # Arabic SMS suggestions are already Arabic in the canonical English JSON;
    # keep them unchanged so the two generated documents stay consistent.
    if "arabic sms suggestions" in label_l:
        return True

    return _mostly_arabic_or_symbols(text)


def translate_text_to_arabic(text, label="content"):
    text = str(text or "")
    if _looks_empty(text):
        return text
    # Do not rewrite Arabic content that already exists in the English report.
    # This keeps Arabic SMS suggestions identical in both documents.
    if _should_keep_original_text(text, label):
        return text.strip()
    response = _client().chat.completions.create(
        model="gpt-5.5",
        messages=[
            {"role": "system", "content": _TRANSLATION_SYSTEM},
            {"role": "user", "content": text},
        ],
    )
    content = response.choices[0].message.content
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                value = item.get("text") or item.get("content") or item.get("value") or ""
                if isinstance(value, dict):
                    value = value.get("value") or value.get("text") or ""
                parts.append(str(value or ""))
            else:
                value = getattr(item, "text", None)
                if value is not None:
                    value = getattr(value, "value", value)
                    parts.append(str(value or ""))
                else:
                    parts.append(str(item or ""))
        return "\n".join(part for part in parts if part).strip()
    return str(content or "").strip()


def translate_campaign_json_to_arabic(source_json_path, output_json_path=None):
    source_json_path = str(source_json_path)
    if output_json_path is None:
        if source_json_path.lower().endswith(".json"):
            output_json_path = source_json_path[:-5] + "_ar.json"
        else:
            output_json_path = source_json_path + "_ar.json"

    with open(source_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    ar_data = deepcopy(data)
    ar_data["source_output_language"] = data.get("output_language", "en")
    ar_data["output_language"] = "ar"
    ar_data["document_language"] = "ar"
    ar_data["translation_mode"] = "literal_from_english_json"

    # Translate user-facing campaign title/brief if they appear in Arabic pages.
    if ar_data.get("campaign_brief"):
        ar_data["campaign_brief_ar"] = translate_text_to_arabic(ar_data.get("campaign_brief", ""), "campaign brief")
    if ar_data.get("chain_campaign_title"):
        ar_data["chain_campaign_title_ar"] = translate_text_to_arabic(ar_data.get("chain_campaign_title", ""), "chain campaign title")

    # Chain message titles/pitches used on message separator pages.
    # chain_messages may now be canonical dictionaries containing pitch/date/time;
    # translate only the visible pitch and never translate the metadata representation.
    if isinstance(ar_data.get("chain_messages"), list):
        ar_chain = []
        for i, msg in enumerate(ar_data.get("chain_messages") or [], start=1):
            if isinstance(msg, dict):
                pitch = msg.get("pitch") or msg.get("message") or msg.get("text") or ""
            else:
                pitch = str(msg or "")
            ar_chain.append(translate_text_to_arabic(str(pitch), f"chain message {i}"))
        ar_data["chain_messages_ar"] = ar_chain

    translated_analysis = {}
    raw_analysis = data.get("analysis") or {}
    if isinstance(raw_analysis, str):
        try:
            raw_analysis = json.loads(raw_analysis)
        except (json.JSONDecodeError, TypeError):
            raw_analysis = {"Campaign Analysis": raw_analysis}
    if isinstance(raw_analysis, list):
        raw_analysis = {f"Section {i}": item for i, item in enumerate(raw_analysis, start=1)}
    if not isinstance(raw_analysis, dict):
        raw_analysis = {"Campaign Analysis": str(raw_analysis or "")}

    for key, content in raw_analysis.items():
        if isinstance(content, str):
            content = {"header": str(key), "answer": content}
        elif not isinstance(content, dict):
            content = {"header": str(key), "answer": str(content or "")}
        else:
            content = dict(content)
        original_header = str(content.get("header") or key)
        arabic_header = localize_header(original_header)
        original_answer = str(content.get("answer") or "")

        original_header_l = original_header.lower()
        english_only_sections = (
            "english sms suggestions",
            "social media caption (english)",
            "radio announcement script (english)",
            "radio dialogue script (english)",
            "english opt-out sms",
        )
        if any(token in original_header_l for token in english_only_sections):
            # Preserve explicitly English content inside the Arabic document while
            # localizing only the visible section heading.
            arabic_answer = original_answer.strip()
        elif "arabic sms suggestions" in original_header_l:
            # Keep Arabic SMS sections Arabic-only and clean mixed LTR/RTL offer fragments.
            arabic_answer = sanitize_arabic_sms_answer(original_answer.strip())
        else:
            arabic_answer = translate_text_to_arabic(original_answer, original_header)

        new_content = dict(content)
        new_content["original_header"] = original_header
        new_content["english_answer"] = original_answer
        new_content["header"] = arabic_header
        new_content["answer"] = arabic_answer

        # Translate any per-message pitch so Arabic separator pages match the same message.
        if new_content.get("pitch"):
            new_content["pitch_ar"] = translate_text_to_arabic(str(new_content.get("pitch")), f"pitch - {original_header}")

        # Preserve order, but use Arabic visible keys.
        translated_key = arabic_header
        if content.get("message_index"):
            translated_key = f"{arabic_header} - الرسالة {content.get('message_index')}"
        # Avoid accidental overwrite if a repeated section exists.
        if translated_key in translated_analysis:
            suffix = 2
            base_key = translated_key
            while f"{base_key} ({suffix})" in translated_analysis:
                suffix += 1
            translated_key = f"{base_key} ({suffix})"
        translated_analysis[translated_key] = new_content

    ar_data["analysis"] = translated_analysis

    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(ar_data, f, ensure_ascii=False, indent=4)

    return output_json_path
