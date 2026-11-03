from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


EMBEDDING_DIMENSIONS = 3072


class Document(Base):
    __tablename__ = "documents"

    __table_args__ = (
        UniqueConstraint(
            "client_slug",
            "content_hash",
            name="uq_documents_client_content_hash",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    client_slug: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="jormall",
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_path: Mapped[str] = mapped_column(String(500), nullable=False)

    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    document_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="general",
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="active",
    )

    visibility: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="client",
    )

    issued_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_document_chunks_document_index",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    document_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)

    section_title: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    source_reference: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    embedding_model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    document: Mapped["Document"] = relationship(
        back_populates="chunks",
    )

    client_slug: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="jormall",
        index=True,
    )


class KnowledgeSeedState(Base):
    """Tracks only rows managed by the packaged knowledge seed."""

    __tablename__ = "knowledge_seed_states"

    client_slug: Mapped[str] = mapped_column(String(100), primary_key=True)
    seed_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    seed_version: Mapped[str] = mapped_column(String(100), nullable=False)
    document_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    chunk_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    document_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedding_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ChatbotLead(Base):
    __tablename__ = "chatbot_leads"

    __table_args__ = (
        UniqueConstraint(
            "client_slug",
            "normalized_phone",
            name="uq_chatbot_leads_client_phone",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    client_slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    phone: Mapped[str] = mapped_column(String(10), nullable=False)
    normalized_phone: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    sessions: Mapped[list["ChatbotLeadSession"]] = relationship(
        back_populates="lead",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    callback_requests: Mapped[list["SalesCallbackRequest"]] = relationship(
        back_populates="lead",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ChatbotLeadSession(Base):
    __tablename__ = "chatbot_lead_sessions"

    __table_args__ = (
        UniqueConstraint(
            "client_slug",
            "session_id",
            name="uq_chatbot_lead_sessions_client_session",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    lead_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("chatbot_leads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    cookie_consent_accepted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    privacy_consent_accepted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    consent_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    consent_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    notice_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    notice_presented_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    cookie_notice_opened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    privacy_notice_opened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    processing_basis: Mapped[str | None] = mapped_column(String(80), nullable=True)

    lead: Mapped["ChatbotLead"] = relationship(back_populates="sessions")


class SalesCallbackRequest(Base):
    __tablename__ = "sales_callback_requests"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    client_slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    lead_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("chatbot_leads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    contacted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    lead: Mapped["ChatbotLead"] = relationship(back_populates="callback_requests")


class ChatConversation(Base):
    __tablename__ = "chat_conversations"

    __table_args__ = (
        UniqueConstraint(
            "client_slug",
            "public_session_id",
            name="uq_chat_conversations_client_public_session",
        ),
        Index("ix_chat_conversations_started_at", "started_at"),
        Index("ix_chat_conversations_last_activity_at", "last_activity_at"),
        Index("ix_chat_conversations_customer_mobile", "customer_mobile"),
        Index("ix_chat_conversations_company_name", "company_name"),
        Index("ix_chat_conversations_campaign_name", "campaign_name"),
        Index("ix_chat_conversations_status", "status"),
        Index("ix_chat_conversations_assigned_employee", "assigned_employee"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    client_slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    public_session_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    lead_session_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    lead_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("chatbot_leads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    campaign_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    chatbot_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    customer_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    company_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    customer_mobile: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    source: Mapped[str] = mapped_column(String(80), nullable=False, default="interactive_sms")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open")
    assigned_employee: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    follow_up_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    internal_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    lead: Mapped[ChatbotLead | None] = relationship()
    messages: Mapped[list["ChatConversationMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ChatConversationMessage.created_at",
    )


class ChatConversationMessage(Base):
    __tablename__ = "chat_conversation_messages"

    __table_args__ = (
        Index("ix_chat_conversation_messages_conversation_created", "conversation_id", "created_at"),
        Index("ix_chat_conversation_messages_role", "role"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("chat_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    model_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    response_id: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    error_state: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    conversation: Mapped["ChatConversation"] = relationship(back_populates="messages")
