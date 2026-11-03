from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.schemas.chat import ChatHistoryTurn
from app.services.client_config_service import DATA_DIR


CONVERSATIONS_DIR = DATA_DIR / "conversations"
MAX_RECENT_EXACT_TURNS = 18
MAX_SUMMARY_CHARACTERS = 1800
SAFE_SESSION_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
MEDIA_MARKER_PATTERN = re.compile(
    r"\[\[(?:image|video):[^\]\r\n]+?\]\]",
    flags=re.IGNORECASE,
)

HISTORY_INTENT_PATTERNS = (
    r"\bwhole\s+(?:previous\s+)?(?:chat|conversation)\b",
    r"\bconversation\s+history\b",
    r"\bchat\s+history\b",
    r"\bprevious\s+(?:chat|conversation|messages)\b",
    r"\bprevious\s+messages\b",
    r"\bmessages\s+from\s+this\s+chat\b",
    r"\bwhat\s+did\s+(?:we|i)\s+(?:talk\s+about|discuss|ask|say)\b",
    r"\bwhat\s+was\s+my\s+first\s+question\b",
    r"\blist\s+the\s+questions\s+i\s+asked\b",
    r"\bgive\s+me\s+a\s+recap\b",
    r"\bsummarize\s+(?:our|this|the)\s+(?:chat|conversation)\b",
    r"\bdo\s+you\s+remember\s+the\s+conversation\b",
    r"\bremember\s+the\s+conversation\s+history\b",
)

HISTORY_CAPABILITY_PATTERNS = (
    r"\bcan\s+you\s+(?:remember|refer\s+to)\s+(?:the\s+)?(?:conversation|chat)\s+history\b",
    r"\bcould\s+you\s+(?:remember|refer\s+to)\s+(?:the\s+)?(?:conversation|chat)\s+history\b",
    r"\bdo\s+you\s+remember\s+(?:the\s+)?(?:conversation|chat)\b",
    r"\bcan\s+you\s+summarize\s+(?:the\s+)?(?:conversation|chat)\b",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_session_id(session_id: str | None) -> str:
    cleaned = SAFE_SESSION_PATTERN.sub("_", (session_id or "default").strip())
    cleaned = cleaned.strip("._")

    return cleaned[:120] or "default"


def conversation_path(*, client_slug: str, session_id: str | None) -> Path:
    return CONVERSATIONS_DIR / client_slug / f"{safe_session_id(session_id)}.json"


def load_conversation(*, client_slug: str, session_id: str | None) -> dict[str, Any]:
    path = conversation_path(client_slug=client_slug, session_id=session_id)

    if not path.exists():
        return {
            "client_slug": client_slug,
            "session_id": safe_session_id(session_id),
            "summary": "",
            "messages": [],
            "last_product_reference": None,
            "last_product_references": [],
            "updated_at": utc_now_iso(),
        }

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "client_slug": client_slug,
            "session_id": safe_session_id(session_id),
            "summary": "",
            "messages": [],
            "last_product_reference": None,
            "last_product_references": [],
            "updated_at": utc_now_iso(),
        }

    if not isinstance(payload.get("messages"), list):
        payload["messages"] = []

    payload["summary"] = str(payload.get("summary") or "")
    if not isinstance(payload.get("last_product_reference"), dict):
        payload["last_product_reference"] = None
    if not isinstance(payload.get("last_product_references"), list):
        payload["last_product_references"] = []
    return payload


def load_product_context(
    *,
    client_slug: str,
    session_id: str | None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    if not session_id:
        return None, []
    payload = load_conversation(client_slug=client_slug, session_id=session_id)
    reference = payload.get("last_product_reference")
    references = [
        item
        for item in payload.get("last_product_references", [])
        if isinstance(item, dict) and item.get("product_name")
    ][:10]
    return (reference if isinstance(reference, dict) else None), references


def save_conversation(payload: dict[str, Any], *, client_slug: str, session_id: str | None) -> None:
    path = conversation_path(client_slug=client_slug, session_id=session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["updated_at"] = utc_now_iso()
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def clean_message_content(content: str, max_characters: int = 1600) -> str:
    cleaned = clean_visible_history_text(content)

    return cleaned[:max_characters]


def clean_visible_history_text(content: str) -> str:
    cleaned = MEDIA_MARKER_PATTERN.sub("", str(content or ""))
    cleaned = re.sub(
        r"\s*(?:Sources used|المصادر المستخدمة)\s*(?:\r?\n[\s\S]*)?$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned


def is_history_request(message: str) -> bool:
    normalized = str(message or "").lower().strip()

    if any(re.search(pattern, normalized) for pattern in HISTORY_INTENT_PATTERNS):
        return True

    return any(
        phrase in str(message or "")
        for phrase in [
            "لخص المحادثة",
            "اعرض سجل المحادثة",
            "ماذا سألتك سابق",
            "سجل المحادثة",
        ]
    )


def is_history_capability_request(message: str) -> bool:
    normalized = str(message or "").lower().strip()

    return any(re.search(pattern, normalized) for pattern in HISTORY_CAPABILITY_PATTERNS)


def combined_session_messages(
    *,
    client_slug: str,
    session_id: str | None,
    frontend_history: list[ChatHistoryTurn],
) -> list[dict[str, str]]:
    payload = load_conversation(client_slug=client_slug, session_id=session_id)
    messages = [
        {
            "role": message.get("role"),
            "content": clean_visible_history_text(message.get("content", "")),
        }
        for message in payload.get("messages", [])
        if isinstance(message, dict)
        and message.get("role") in {"user", "assistant"}
        and clean_visible_history_text(message.get("content", ""))
    ]

    for turn in frontend_history:
        content = clean_visible_history_text(turn.content)

        if not content:
            continue

        if messages and messages[-1]["role"] == turn.role and messages[-1]["content"] == content:
            continue

        messages.append(
            {
                "role": turn.role,
                "content": content,
            }
        )

    return messages


def question_answer_pairs(messages: list[dict[str, str]]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    pending_question = ""

    for message in messages:
        role = message.get("role")
        content = clean_visible_history_text(message.get("content", ""))

        if not content:
            continue

        if role == "user":
            pending_question = content
            continue

        if role == "assistant" and pending_question:
            pairs.append((pending_question, content))
            pending_question = ""

    return pairs


def format_history_answer(
    *,
    request_message: str,
    client_slug: str,
    session_id: str | None,
    frontend_history: list[ChatHistoryTurn],
) -> str | None:
    if not (is_history_request(request_message) or is_history_capability_request(request_message)):
        return None

    if is_history_capability_request(request_message):
        return "Yes, I can summarize or list the previous messages from this chat."

    messages = combined_session_messages(
        client_slug=client_slug,
        session_id=session_id,
        frontend_history=frontend_history,
    )

    if not messages:
        return "I do not have previous messages in this chat yet."

    normalized = request_message.lower()

    if "what did i ask" in normalized or "list the questions" in normalized:
        questions = [
            clean_visible_history_text(message.get("content", ""))
            for message in messages
            if message.get("role") == "user"
        ]

        if not questions:
            return "I do not have previous messages in this chat yet."

        lines = ["Here are the questions you asked earlier:"]
        lines.extend(
            f"{index}. {question}"
            for index, question in enumerate(questions[-20:], start=1)
        )
        return "\n".join(lines)

    pairs = question_answer_pairs(messages)

    if not pairs:
        return "I do not have previous messages in this chat yet."

    if len(pairs) > 12:
        visible_pairs = pairs[-12:]
        lines = [
            "Here is the recent conversation as Q&A. Older parts were summarized in this chat's memory:"
        ]
    else:
        visible_pairs = pairs
        lines = ["Here is the conversation so far as Q&A:"]

    for index, (question, answer) in enumerate(visible_pairs, start=1):
        lines.append("")
        lines.append(f"Q{index}: {question}")
        lines.append(f"A{index}: {answer}")

    return "\n".join(lines)


def summarize_messages(messages: list[dict[str, str]]) -> str:
    if not messages:
        return ""

    important_lines: list[str] = []

    for message in messages:
        role = message.get("role")
        content = clean_message_content(message.get("content", ""), 500)

        if not content:
            continue

        lowered = content.lower()
        is_important = (
            role == "user"
            and (
                "my name is" in lowered
                or "i am interested" in lowered
                or "interested in" in lowered
                or "contact" in lowered
                or "phone" in lowered
                or "email" in lowered
                or "prefer" in lowered
                or "looking for" in lowered
                or "isn't it" in lowered
                or "isnt it" in lowered
                or "i think" in lowered
                or "the document says" in lowered
            )
        )

        if is_important:
            if (
                "isn't it" in lowered
                or "isnt it" in lowered
                or "i think" in lowered
                or "the document says" in lowered
            ):
                important_lines.append(f"User suggested, not verified: {content}")
            else:
                important_lines.append(f"User said: {content}")

    if not important_lines:
        for message in messages[-8:]:
            role = (
                "User said"
                if message.get("role") == "user"
                else "Assistant answered in chat, not approved evidence"
            )
            content = clean_message_content(message.get("content", ""), 220)

            if content:
                important_lines.append(f"{role}: {content}")

    summary = "Earlier conversation summary:\n" + "\n".join(important_lines[-12:])

    return summary[:MAX_SUMMARY_CHARACTERS]


def merge_history(
    *,
    stored_messages: list[dict[str, str]],
    frontend_history: list[ChatHistoryTurn],
) -> list[ChatHistoryTurn]:
    turns: list[ChatHistoryTurn] = []

    for message in stored_messages[-MAX_RECENT_EXACT_TURNS:]:
        try:
            turns.append(
                ChatHistoryTurn(
                    role=message.get("role"),
                    content=clean_message_content(message.get("content", ""), 800),
                )
            )
        except Exception:
            continue

    for turn in frontend_history:
        if turns and turns[-1].role == turn.role and turns[-1].content == turn.content:
            continue
        turns.append(turn)

    return turns[-MAX_RECENT_EXACT_TURNS:]


def history_for_prompt(
    *,
    client_slug: str,
    session_id: str | None,
    frontend_history: list[ChatHistoryTurn],
) -> list[ChatHistoryTurn]:
    payload = load_conversation(client_slug=client_slug, session_id=session_id)
    turns = merge_history(
        stored_messages=payload.get("messages", []),
        frontend_history=frontend_history,
    )
    summary = clean_message_content(payload.get("summary", ""), 800)

    if summary:
        return [
            ChatHistoryTurn(
                role="assistant",
                content=summary,
            ),
            *turns[-MAX_RECENT_EXACT_TURNS:],
        ]

    return turns[-MAX_RECENT_EXACT_TURNS:]


def append_exchange(
    *,
    client_slug: str,
    session_id: str | None,
    user_message: str,
    assistant_message: str,
    product_references: list[dict[str, Any]] | None = None,
) -> None:
    if not session_id:
        return

    payload = load_conversation(client_slug=client_slug, session_id=session_id)
    messages = [
        message
        for message in payload.get("messages", [])
        if isinstance(message, dict)
        and message.get("role") in {"user", "assistant"}
        and message.get("content")
    ]
    messages.extend(
        [
            {
                "role": "user",
                "content": clean_message_content(user_message),
                "created_at": utc_now_iso(),
            },
            {
                "role": "assistant",
                "content": clean_message_content(assistant_message),
                "created_at": utc_now_iso(),
            },
        ]
    )
    payload["messages"] = messages

    if product_references is not None:
        clean_references = [
            {
                key: value
                for key, value in reference.items()
                if key in {
                    "product_id",
                    "product_name",
                    "product_url",
                    "current_price",
                    "old_price",
                    "currency",
                    "image_url",
                    "local_image_url",
                    "image_alt",
                    "description",
                }
            }
            for reference in product_references
            if isinstance(reference, dict) and reference.get("product_name")
        ][:10]
        payload["last_product_references"] = clean_references
        payload["last_product_reference"] = clean_references[0] if clean_references else None

    if len(messages) > MAX_RECENT_EXACT_TURNS:
        payload["summary"] = summarize_messages(messages[:-MAX_RECENT_EXACT_TURNS])

    save_conversation(payload, client_slug=client_slug, session_id=session_id)
