from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.models.document import (  # noqa: F401
    ChatConversation,
    ChatConversationMessage,
    ChatbotLead,
    ChatbotLeadSession,
    Document,
    DocumentChunk,
    MediaCollection,
    MediaImage,
    SalesCallbackRequest,
)

from app.core.config import settings
from app.core.database import Base, engine
from app.models.document import EMBEDDING_DIMENSIONS


logger = logging.getLogger(__name__)

MEDIA_EMBEDDING_OLD_INDEX_NAME = "ix_media_images_embedding_cosine"
MEDIA_EMBEDDING_HALFVEC_INDEX_NAME = "ix_media_images_embedding_halfvec_cosine"
PGVECTOR_IVFFLAT_MAX_DIMENSIONS = 2000


@dataclass(frozen=True, slots=True)
class PgvectorCapabilities:
    extversion: str | None
    has_halfvec_type: bool
    has_halfvec_cosine_ops: bool
    has_hnsw_access_method: bool

    @property
    def supports_halfvec_hnsw_cosine(self) -> bool:
        return (
            self.has_halfvec_type
            and self.has_halfvec_cosine_ops
            and self.has_hnsw_access_method
        )


def media_embedding_dimension() -> int:
    return settings.embedding_dimensions


def validate_media_embedding_dimension() -> None:
    configured_dimension = media_embedding_dimension()
    if configured_dimension != EMBEDDING_DIMENSIONS:
        raise RuntimeError(
            "Media embedding dimension mismatch. "
            f"Model column is vector({EMBEDDING_DIMENSIONS}) but "
            f"EMBEDDING_DIMENSIONS is configured as {configured_dimension}."
        )


def media_halfvec_index_sql(dimension: int | None = None) -> str:
    dimension = dimension or media_embedding_dimension()
    return f"""
        CREATE INDEX IF NOT EXISTS {MEDIA_EMBEDDING_HALFVEC_INDEX_NAME}
        ON media_images
        USING hnsw ((embedding::halfvec({dimension})) halfvec_cosine_ops)
        WHERE embedding IS NOT NULL
        """


def media_old_vector_index_drop_sql() -> str:
    return f"DROP INDEX IF EXISTS {MEDIA_EMBEDDING_OLD_INDEX_NAME}"


def load_pgvector_capabilities(connection) -> PgvectorCapabilities:
    row = connection.execute(
        text(
            """
            SELECT
                (SELECT extversion FROM pg_extension WHERE extname = 'vector') AS extversion,
                to_regtype('halfvec') IS NOT NULL AS has_halfvec_type,
                EXISTS (
                    SELECT 1
                    FROM pg_opclass
                    WHERE opcname = 'halfvec_cosine_ops'
                ) AS has_halfvec_cosine_ops,
                EXISTS (
                    SELECT 1
                    FROM pg_am
                    WHERE amname = 'hnsw'
                ) AS has_hnsw_access_method
            """
        )
    ).mappings().one()
    return PgvectorCapabilities(
        extversion=row["extversion"],
        has_halfvec_type=bool(row["has_halfvec_type"]),
        has_halfvec_cosine_ops=bool(row["has_halfvec_cosine_ops"]),
        has_hnsw_access_method=bool(row["has_hnsw_access_method"]),
    )


def run_lightweight_migrations() -> None:
    """
    Keep existing single-tenant JorMall installs working while adding
    minimal multi-tenant columns for the MVP.
    """
    statements = [
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS client_slug VARCHAR(100)",
        "UPDATE documents SET client_slug = 'jormall' WHERE client_slug IS NULL",
        "ALTER TABLE documents ALTER COLUMN client_slug SET DEFAULT 'jormall'",
        "ALTER TABLE documents ALTER COLUMN client_slug SET NOT NULL",
        "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS client_slug VARCHAR(100)",
        """
        UPDATE document_chunks
        SET client_slug = documents.client_slug
        FROM documents
        WHERE document_chunks.document_id = documents.id
          AND document_chunks.client_slug IS NULL
        """,
        "UPDATE document_chunks SET client_slug = 'jormall' WHERE client_slug IS NULL",
        "ALTER TABLE document_chunks ALTER COLUMN client_slug SET DEFAULT 'jormall'",
        "ALTER TABLE document_chunks ALTER COLUMN client_slug SET NOT NULL",
        "ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_content_hash_key",
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_documents_client_content_hash
        ON documents (client_slug, content_hash)
        """,
        "CREATE INDEX IF NOT EXISTS ix_documents_client_slug ON documents (client_slug)",
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_client_slug ON document_chunks (client_slug)",
        "ALTER TABLE chatbot_leads ADD COLUMN IF NOT EXISTS normalized_phone VARCHAR(10)",
        "UPDATE chatbot_leads SET normalized_phone = phone WHERE normalized_phone IS NULL",
        "ALTER TABLE chatbot_leads ALTER COLUMN normalized_phone SET NOT NULL",
        "ALTER TABLE chatbot_leads ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMP WITH TIME ZONE",
        "UPDATE chatbot_leads SET last_seen_at = COALESCE(updated_at, created_at, now()) WHERE last_seen_at IS NULL",
        "ALTER TABLE chatbot_leads ALTER COLUMN last_seen_at SET DEFAULT now()",
        "ALTER TABLE chatbot_leads ALTER COLUMN last_seen_at SET NOT NULL",
        """
        CREATE TABLE IF NOT EXISTS chatbot_lead_sessions (
            id UUID PRIMARY KEY,
            lead_id UUID NOT NULL REFERENCES chatbot_leads(id) ON DELETE CASCADE,
            client_slug VARCHAR(100) NOT NULL,
            session_id VARCHAR(120) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            last_seen_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """,
        "CREATE EXTENSION IF NOT EXISTS pgcrypto",
        """
        INSERT INTO chatbot_lead_sessions (
            id,
            lead_id,
            client_slug,
            session_id,
            created_at,
            last_seen_at
        )
        SELECT
            gen_random_uuid(),
            id,
            client_slug,
            session_id,
            created_at,
            COALESCE(updated_at, created_at, now())
        FROM chatbot_leads
        WHERE session_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM chatbot_lead_sessions existing
              WHERE existing.client_slug = chatbot_leads.client_slug
                AND existing.session_id = chatbot_leads.session_id
          )
        """,
        f"""
        WITH ranked AS (
            SELECT
                id,
                first_value(id) OVER (
                    PARTITION BY client_slug, normalized_phone
                    ORDER BY created_at ASC, id ASC
                ) AS canonical_id
            FROM chatbot_leads
            WHERE client_slug = '{"-".join(["central", "e", "commerce", "co", "ltd"])}'
        )
        UPDATE chatbot_lead_sessions sessions
        SET lead_id = ranked.canonical_id
        FROM ranked
        WHERE sessions.lead_id = ranked.id
          AND ranked.id <> ranked.canonical_id
        """,
        f"""
        WITH ranked AS (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY client_slug, normalized_phone
                    ORDER BY created_at ASC, id ASC
                ) AS duplicate_rank
            FROM chatbot_leads
            WHERE client_slug = '{"-".join(["central", "e", "commerce", "co", "ltd"])}'
        )
        DELETE FROM chatbot_leads leads
        USING ranked
        WHERE leads.id = ranked.id
          AND ranked.duplicate_rank > 1
        """,
        """
        UPDATE chatbot_leads leads
        SET last_seen_at = subquery.last_seen_at
        FROM (
            SELECT lead_id, max(last_seen_at) AS last_seen_at
            FROM chatbot_lead_sessions
            GROUP BY lead_id
        ) subquery
        WHERE leads.id = subquery.lead_id
        """,
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'uq_chatbot_leads_client_session'
            ) THEN
                ALTER TABLE chatbot_leads
                DROP CONSTRAINT uq_chatbot_leads_client_session;
            END IF;
        END $$;
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_chatbot_leads_client_phone
        ON chatbot_leads (client_slug, normalized_phone)
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_chatbot_lead_sessions_client_session
        ON chatbot_lead_sessions (client_slug, session_id)
        """,
        "CREATE INDEX IF NOT EXISTS ix_chatbot_lead_sessions_lead_id ON chatbot_lead_sessions (lead_id)",
        "ALTER TABLE chatbot_lead_sessions ADD COLUMN IF NOT EXISTS cookie_consent_accepted BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE chatbot_lead_sessions ADD COLUMN IF NOT EXISTS privacy_consent_accepted BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE chatbot_lead_sessions ADD COLUMN IF NOT EXISTS consent_version VARCHAR(40)",
        "ALTER TABLE chatbot_lead_sessions ADD COLUMN IF NOT EXISTS consent_accepted_at TIMESTAMP WITH TIME ZONE",
        """
        CREATE TABLE IF NOT EXISTS sales_callback_requests (
            id UUID PRIMARY KEY,
            client_slug VARCHAR(100) NOT NULL,
            lead_id UUID NOT NULL REFERENCES chatbot_leads(id) ON DELETE CASCADE,
            session_id VARCHAR(120) NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'pending',
            requested_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            contacted_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """,
        "ALTER TABLE sales_callback_requests ADD COLUMN IF NOT EXISTS contacted_at TIMESTAMP WITH TIME ZONE",
        "CREATE INDEX IF NOT EXISTS ix_sales_callback_requests_client_slug ON sales_callback_requests (client_slug)",
        "CREATE INDEX IF NOT EXISTS ix_sales_callback_requests_lead_id ON sales_callback_requests (lead_id)",
        "CREATE INDEX IF NOT EXISTS ix_sales_callback_requests_session_id ON sales_callback_requests (session_id)",
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_sales_callback_requests_pending_lead
        ON sales_callback_requests (client_slug, lead_id)
        WHERE status = 'pending'
        """,
        """
        CREATE TABLE IF NOT EXISTS chat_conversations (
            id UUID PRIMARY KEY,
            client_slug VARCHAR(100) NOT NULL,
            session_id VARCHAR(120) NOT NULL,
            lead_session_id VARCHAR(120),
            lead_id UUID REFERENCES chatbot_leads(id) ON DELETE SET NULL,
            customer_name VARCHAR(100) NOT NULL DEFAULT '',
            customer_phone VARCHAR(20) NOT NULL DEFAULT '',
            customer_company VARCHAR(120) NOT NULL DEFAULT '',
            status VARCHAR(30) NOT NULL DEFAULT 'open',
            follow_up_status VARCHAR(40) NOT NULL DEFAULT '',
            assignee VARCHAR(120) NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            archived BOOLEAN NOT NULL DEFAULT FALSE,
            last_message_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """,
        "ALTER TABLE chat_conversations ADD COLUMN IF NOT EXISTS lead_session_id VARCHAR(120)",
        "ALTER TABLE chat_conversations ADD COLUMN IF NOT EXISTS lead_id UUID REFERENCES chatbot_leads(id) ON DELETE SET NULL",
        "ALTER TABLE chat_conversations ADD COLUMN IF NOT EXISTS customer_name VARCHAR(100) NOT NULL DEFAULT ''",
        "ALTER TABLE chat_conversations ADD COLUMN IF NOT EXISTS customer_phone VARCHAR(20) NOT NULL DEFAULT ''",
        "ALTER TABLE chat_conversations ADD COLUMN IF NOT EXISTS customer_company VARCHAR(120) NOT NULL DEFAULT ''",
        "ALTER TABLE chat_conversations ADD COLUMN IF NOT EXISTS status VARCHAR(30) NOT NULL DEFAULT 'open'",
        "ALTER TABLE chat_conversations ADD COLUMN IF NOT EXISTS follow_up_status VARCHAR(40) NOT NULL DEFAULT ''",
        "ALTER TABLE chat_conversations ADD COLUMN IF NOT EXISTS assignee VARCHAR(120) NOT NULL DEFAULT ''",
        "ALTER TABLE chat_conversations ADD COLUMN IF NOT EXISTS notes TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE chat_conversations ADD COLUMN IF NOT EXISTS archived BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE chat_conversations ADD COLUMN IF NOT EXISTS last_message_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_conversations_client_session ON chat_conversations (client_slug, session_id)",
        "CREATE INDEX IF NOT EXISTS ix_chat_conversations_client_status ON chat_conversations (client_slug, status)",
        "CREATE INDEX IF NOT EXISTS ix_chat_conversations_client_archived ON chat_conversations (client_slug, archived)",
        "CREATE INDEX IF NOT EXISTS ix_chat_conversations_lead_id ON chat_conversations (lead_id)",
        "ALTER TABLE sales_callback_requests ADD COLUMN IF NOT EXISTS conversation_id UUID REFERENCES chat_conversations(id) ON DELETE SET NULL",
        "CREATE INDEX IF NOT EXISTS ix_sales_callback_requests_conversation_id ON sales_callback_requests (conversation_id)",
        """
        CREATE TABLE IF NOT EXISTS chat_conversation_messages (
            id UUID PRIMARY KEY,
            conversation_id UUID NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
            client_slug VARCHAR(100) NOT NULL,
            role VARCHAR(20) NOT NULL,
            content TEXT NOT NULL,
            language VARCHAR(10) NOT NULL DEFAULT '',
            media JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """,
        "ALTER TABLE chat_conversation_messages ADD COLUMN IF NOT EXISTS language VARCHAR(10) NOT NULL DEFAULT ''",
        "ALTER TABLE chat_conversation_messages ADD COLUMN IF NOT EXISTS media JSONB NOT NULL DEFAULT '[]'::jsonb",
        "CREATE INDEX IF NOT EXISTS ix_chat_conversation_messages_conversation_id ON chat_conversation_messages (conversation_id)",
        "CREATE INDEX IF NOT EXISTS ix_chat_conversation_messages_client_slug ON chat_conversation_messages (client_slug)",
        "CREATE INDEX IF NOT EXISTS ix_media_collections_client_enabled ON media_collections (client_slug, is_enabled)",
        "CREATE INDEX IF NOT EXISTS ix_media_collections_client_approved ON media_collections (client_slug, is_approved)",
        "CREATE INDEX IF NOT EXISTS ix_media_images_client_collection ON media_images (client_slug, collection_id)",
        "CREATE INDEX IF NOT EXISTS ix_media_images_public_filter ON media_images (client_slug, is_approved, is_active, is_duplicate)",
        "CREATE INDEX IF NOT EXISTS ix_media_images_direct_metadata ON media_images (client_slug, detected_product_type, detected_colour, detected_image_type, detected_view)",
        "CREATE INDEX IF NOT EXISTS ix_media_images_group ON media_images (client_slug, suggested_group)",
        "ALTER TABLE media_images ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE media_images ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE media_images ADD COLUMN IF NOT EXISTS processing_error_at TIMESTAMP WITH TIME ZONE",
    ]

    with engine.begin() as connection:
        validate_media_embedding_dimension()
        for statement in statements:
            connection.execute(text(statement))


def run_optional_media_vector_indexes() -> None:
    """
    Add best-effort media similarity indexes.

    The media embedding column stores 3072-dimensional full precision vectors.
    pgvector IVFFlat cannot index vectors over 2000 dimensions, so this path
    uses a halfvec HNSW expression index when supported and otherwise leaves
    retrieval on exact vector search.
    """
    dimension = media_embedding_dimension()
    try:
        with engine.begin() as connection:
            connection.execute(text(media_old_vector_index_drop_sql()))
            capabilities = load_pgvector_capabilities(connection)
            if capabilities.supports_halfvec_hnsw_cosine:
                connection.execute(text(media_halfvec_index_sql(dimension)))
                logger.info(
                    "Campaign media halfvec HNSW index is available",
                    extra={
                        "index_name": MEDIA_EMBEDDING_HALFVEC_INDEX_NAME,
                        "embedding_dimension": dimension,
                        "embedding_model": settings.openai_embedding_model,
                        "pgvector_version": capabilities.extversion,
                    },
                )
                return

            logger.warning(
                "Campaign media vector performance index skipped; exact vector search remains available",
                extra={
                    "embedding_dimension": dimension,
                    "embedding_model": settings.openai_embedding_model,
                    "pgvector_version": capabilities.extversion,
                    "has_halfvec_type": capabilities.has_halfvec_type,
                    "has_halfvec_cosine_ops": capabilities.has_halfvec_cosine_ops,
                    "has_hnsw_access_method": capabilities.has_hnsw_access_method,
                    "reason": "halfvec_hnsw_not_supported",
                },
            )
    except SQLAlchemyError as error:
        logger.warning(
            "Campaign media vector performance index skipped after optional migration failure; exact vector search remains available",
            extra={
                "embedding_dimension": dimension,
                "embedding_model": settings.openai_embedding_model,
                "error_category": type(error).__name__,
            },
            exc_info=True,
        )


def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)
    run_lightweight_migrations()
    run_optional_media_vector_indexes()
