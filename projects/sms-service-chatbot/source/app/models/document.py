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
    Float,
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


class MediaCollection(Base):
    __tablename__ = "media_collections"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    client_slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    campaign_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    chatbot_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    general_description_original: Mapped[str] = mapped_column(Text, nullable=False)
    general_description_language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    general_description_en: Mapped[str] = mapped_column(Text, nullable=False, default="")
    general_description_ar: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Deprecated collection-level business detail fields kept for compatibility
    # with media collections created before the simplified Campaign Images form.
    shared_brand: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    shared_product_family: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    shared_campaign_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    shared_model: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    shared_model_year: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    shared_offer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    shared_warranty: Mapped[str] = mapped_column(Text, nullable=False, default="")
    shared_financing: Mapped[str] = mapped_column(Text, nullable=False, default="")
    shared_location: Mapped[str] = mapped_column(Text, nullable=False, default="")
    shared_cta_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    shared_keywords_en: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    shared_keywords_ar: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    analysis_status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft", index=True)
    total_images: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_images: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_images: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    flagged_images: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_images: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false", index=True)
    approved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    images: Mapped[list["MediaImage"]] = relationship(
        back_populates="collection",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class MediaImage(Base):
    __tablename__ = "media_images"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    collection_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("media_collections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    campaign_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    chatbot_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    safe_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_storage_path: Mapped[str] = mapped_column(String(700), nullable=False)
    public_storage_path: Mapped[str] = mapped_column(String(700), nullable=False, default="")
    thumbnail_path: Mapped[str] = mapped_column(String(700), nullable=False, default="")
    mime_type: Mapped[str] = mapped_column(String(80), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    ai_title_en: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    ai_title_ar: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    visual_description_en: Mapped[str] = mapped_column(Text, nullable=False, default="")
    visual_description_ar: Mapped[str] = mapped_column(Text, nullable=False, default="")
    alt_text_en: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    alt_text_ar: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    detected_category: Mapped[str] = mapped_column(String(120), nullable=False, default="", index=True)
    detected_product_type: Mapped[str] = mapped_column(String(120), nullable=False, default="", index=True)
    detected_brand: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    detected_model: Mapped[str] = mapped_column(String(120), nullable=False, default="", index=True)
    detected_colour: Mapped[str] = mapped_column(String(80), nullable=False, default="", index=True)
    detected_view: Mapped[str] = mapped_column(String(80), nullable=False, default="", index=True)
    detected_image_type: Mapped[str] = mapped_column(String(120), nullable=False, default="", index=True)
    detected_features: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    detected_objects: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    visible_text: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    dominant_subject: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    suggested_group: Mapped[str] = mapped_column(String(120), nullable=False, default="", index=True)
    keywords_en: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    keywords_ar: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    searchable_text_en: Mapped[str] = mapped_column(Text, nullable=False, default="")
    searchable_text_ar: Mapped[str] = mapped_column(Text, nullable=False, default="")
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=True)
    vision_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true", index=True)
    review_reasons: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    analysis_status: Mapped[str] = mapped_column(String(40), nullable=False, default="uploaded", index=True)
    analysis_error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false", index=True)
    duplicate_of_image_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    is_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true", index=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    collection: Mapped["MediaCollection"] = relationship(back_populates="images")


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
    conversation_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("chat_conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    client_message: Mapped[str | None] = mapped_column(Text, nullable=True)
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
            "session_id",
            name="uq_chat_conversations_client_session",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    client_slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    lead_session_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    lead_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("chatbot_leads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    customer_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    customer_phone: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    customer_company: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open", index=True)
    follow_up_status: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    assignee: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false", index=True)
    last_message_at: Mapped[datetime] = mapped_column(
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

    messages: Mapped[list["ChatConversationMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ChatConversationMessage(Base):
    __tablename__ = "chat_conversation_messages"

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
    client_slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    media: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    conversation: Mapped["ChatConversation"] = relationship(back_populates="messages")
