from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.document import (
    ChatConversation,
    ChatConversationMessage,
    ChatbotLead,
    ChatbotLeadSession,
)
from app.services.client_config_service import load_client_config


logger = logging.getLogger(__name__)

ARABIC_PATTERN = re.compile(r"[\u0600-\u06ff]")


def chat_history_enabled(client_slug: str) -> bool:
    if client_slug == "jormall":
        return False
    try:
        config = load_client_config(client_slug)
    except FileNotFoundError:
        return False
    return bool(getattr(config, "include_chat_history_dashboard", True))


def message_language(text: str) -> str:
    return "ar" if ARABIC_PATTERN.search(text or "") else "en"


def media_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        items = value.get("items") or value.get("media") or []
    else:
        items = value or []
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)][:12]


def lead_for_session(
    *,
    db: Session,
    client_slug: str,
    session_id: str,
) -> ChatbotLead | None:
    clean_session = session_id.strip()[:120]
    if not clean_session:
        return None
    return db.scalar(
        select(ChatbotLead)
        .join(ChatbotLeadSession, ChatbotLeadSession.lead_id == ChatbotLead.id)
        .where(
            ChatbotLead.client_slug == client_slug,
            ChatbotLeadSession.client_slug == client_slug,
            ChatbotLeadSession.session_id == clean_session,
        )
    ) or db.scalar(
        select(ChatbotLead).where(
            ChatbotLead.client_slug == client_slug,
            ChatbotLead.session_id == clean_session,
        )
    )


def get_or_create_conversation(
    *,
    db: Session,
    client_slug: str,
    session_id: str,
    lead_session_id: str,
) -> ChatConversation:
    conversation = db.scalar(
        select(ChatConversation).where(
            ChatConversation.client_slug == client_slug,
            ChatConversation.session_id == session_id,
        )
    )
    if conversation is None:
        conversation = ChatConversation(
            client_slug=client_slug,
            session_id=session_id,
            lead_session_id=lead_session_id or None,
        )
        db.add(conversation)
        db.flush()
    elif lead_session_id and not conversation.lead_session_id:
        conversation.lead_session_id = lead_session_id
    return conversation


def last_message(
    *,
    db: Session,
    conversation_id,
    role: str,
) -> ChatConversationMessage | None:
    return db.scalar(
        select(ChatConversationMessage)
        .where(
            ChatConversationMessage.conversation_id == conversation_id,
            ChatConversationMessage.role == role,
        )
        .order_by(desc(ChatConversationMessage.created_at))
        .limit(1)
    )


def append_message_once(
    *,
    db: Session,
    conversation: ChatConversation,
    role: str,
    content: str,
    media: list[dict[str, Any]] | None = None,
) -> None:
    cleaned = (content or "").strip()
    if not cleaned:
        return
    previous = last_message(db=db, conversation_id=conversation.id, role=role)
    if previous is not None and previous.content == cleaned:
        return
    db.add(
        ChatConversationMessage(
            conversation_id=conversation.id,
            client_slug=conversation.client_slug,
            role=role,
            content=cleaned,
            language=message_language(cleaned),
            media=media or [],
        )
    )


def record_chat_exchange(
    *,
    db: Session,
    client_slug: str,
    session_id: str | None,
    lead_session_id: str | None,
    user_message: str,
    assistant_message: str,
    media_context: Any = None,
) -> None:
    if not chat_history_enabled(client_slug):
        return
    clean_session = (session_id or lead_session_id or "").strip()[:120]
    if not clean_session:
        return
    clean_lead_session = (lead_session_id or "").strip()[:120]

    try:
        conversation = get_or_create_conversation(
            db=db,
            client_slug=client_slug,
            session_id=clean_session,
            lead_session_id=clean_lead_session,
        )
        lead = lead_for_session(
            db=db,
            client_slug=client_slug,
            session_id=clean_lead_session or clean_session,
        )
        if lead is not None:
            conversation.lead_id = lead.id
            conversation.customer_name = lead.name
            conversation.customer_phone = lead.phone

        append_message_once(
            db=db,
            conversation=conversation,
            role="user",
            content=user_message,
        )
        append_message_once(
            db=db,
            conversation=conversation,
            role="assistant",
            content=assistant_message,
            media=media_items(media_context),
        )
        conversation.last_message_at = func.now()
        conversation.updated_at = func.now()
        db.commit()
    except Exception:
        db.rollback()
        logger.warning(
            "Could not record chat history",
            extra={"client_slug": client_slug},
            exc_info=True,
        )
