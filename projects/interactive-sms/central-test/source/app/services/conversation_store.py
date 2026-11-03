from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import (
    ChatConversation,
    ChatConversationMessage,
    ChatbotLead,
    ChatbotLeadSession,
)


VALID_CONVERSATION_STATUSES = {
    "open",
    "needs_follow_up",
    "assigned",
    "completed",
    "archived",
}
VALID_MESSAGE_ROLES = {"user", "assistant", "system"}
MAX_MESSAGE_CHARACTERS = 20000
MAX_NOTE_CHARACTERS = 4000
MAX_ASSIGNMENT_CHARACTERS = 120


def detect_language(text: str) -> str:
    return "ar" if re.search(r"[\u0600-\u06FF]", text or "") else "en"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def clean_text(value: str | None, *, limit: int) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())[:limit]


def lead_for_session(
    *,
    db: Session,
    client_slug: str,
    session_id: str | None,
) -> ChatbotLead | None:
    clean_session_id = clean_text(session_id, limit=120)
    if not clean_session_id:
        return None
    return db.scalar(
        select(ChatbotLead)
        .join(ChatbotLeadSession, ChatbotLeadSession.lead_id == ChatbotLead.id)
        .where(
            ChatbotLead.client_slug == client_slug,
            ChatbotLeadSession.client_slug == client_slug,
            ChatbotLeadSession.session_id == clean_session_id,
        )
    )


def conversation_for_session(
    *,
    db: Session,
    client_slug: str,
    session_id: str,
) -> ChatConversation | None:
    return db.scalar(
        select(ChatConversation).where(
            ChatConversation.client_slug == client_slug,
            ChatConversation.public_session_id == clean_text(session_id, limit=120),
        )
    )


def ensure_conversation(
    *,
    db: Session,
    client_slug: str,
    session_id: str,
    lead_session_id: str | None,
    config: Any,
    language: str,
) -> ChatConversation:
    public_session_id = clean_text(session_id, limit=120)
    clean_lead_session_id = clean_text(lead_session_id or session_id, limit=120)
    conversation = conversation_for_session(
        db=db,
        client_slug=client_slug,
        session_id=public_session_id,
    )
    lead = lead_for_session(
        db=db,
        client_slug=client_slug,
        session_id=clean_lead_session_id,
    ) or lead_for_session(
        db=db,
        client_slug=client_slug,
        session_id=public_session_id,
    )

    if conversation is None:
        conversation = ChatConversation(
            client_slug=client_slug,
            public_session_id=public_session_id,
            lead_session_id=clean_lead_session_id,
            lead_id=lead.id if lead else None,
            customer_name=lead.name if lead else "",
            customer_mobile=lead.phone if lead else "",
            campaign_name=getattr(config, "campaign_name", "") or "",
            chatbot_name=getattr(config, "assistant_name", "") or "",
            language=language if language in {"ar", "en"} else "en",
            source="interactive_sms",
            status="open",
        )
        db.add(conversation)
        db.flush()
        return conversation

    if lead and conversation.lead_id != lead.id:
        conversation.lead_id = lead.id
    if lead:
        conversation.customer_name = lead.name
        conversation.customer_mobile = lead.phone
    if clean_lead_session_id and not conversation.lead_session_id:
        conversation.lead_session_id = clean_lead_session_id
    if language in {"ar", "en"}:
        conversation.language = language
    if not conversation.campaign_name:
        conversation.campaign_name = getattr(config, "campaign_name", "") or ""
    if not conversation.chatbot_name:
        conversation.chatbot_name = getattr(config, "assistant_name", "") or ""
    conversation.last_activity_at = func.now()
    conversation.updated_at = func.now()
    db.flush()
    return conversation


def save_conversation_message(
    *,
    db: Session,
    conversation: ChatConversation,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
    model_name: str = "",
    response_id: str = "",
    error_state: str = "",
) -> ChatConversationMessage | None:
    clean_role = role if role in VALID_MESSAGE_ROLES else "system"
    clean_content = (content or "").strip()[:MAX_MESSAGE_CHARACTERS]
    if not clean_content:
        return None

    last_message = db.scalar(
        select(ChatConversationMessage)
        .where(ChatConversationMessage.conversation_id == conversation.id)
        .order_by(ChatConversationMessage.created_at.desc())
        .limit(1)
    )
    if (
        last_message
        and last_message.role == clean_role
        and last_message.content == clean_content
        and last_message.error_state == (error_state or "")
    ):
        conversation.last_activity_at = func.now()
        conversation.updated_at = func.now()
        db.flush()
        return last_message

    message = ChatConversationMessage(
        conversation_id=conversation.id,
        role=clean_role,
        content=clean_content,
        message_metadata=metadata or {},
        model_name=model_name[:120],
        response_id=response_id[:120],
        error_state=error_state[:80],
    )
    db.add(message)
    conversation.last_activity_at = func.now()
    conversation.updated_at = func.now()
    db.flush()
    return message


def save_customer_message(
    *,
    db: Session,
    client_slug: str,
    session_id: str,
    lead_session_id: str | None,
    config: Any,
    message: str,
) -> ChatConversation:
    conversation = ensure_conversation(
        db=db,
        client_slug=client_slug,
        session_id=session_id,
        lead_session_id=lead_session_id,
        config=config,
        language=detect_language(message),
    )
    save_conversation_message(
        db=db,
        conversation=conversation,
        role="user",
        content=message,
    )
    return conversation


def save_assistant_message(
    *,
    db: Session,
    conversation: ChatConversation,
    message: str,
    error_state: str = "",
) -> None:
    save_conversation_message(
        db=db,
        conversation=conversation,
        role="assistant",
        content=message,
        model_name=settings.openai_chat_model if not error_state else "",
        error_state=error_state,
    )
