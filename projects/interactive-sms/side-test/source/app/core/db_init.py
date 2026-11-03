from sqlalchemy import text

from app.models.document import (  # noqa: F401
    ChatConversation,
    ChatConversationMessage,
    ChatbotLead,
    ChatbotLeadSession,
    Document,
    DocumentChunk,
    KnowledgeSeedState,
    SalesCallbackRequest,
)

from app.core.database import Base, engine


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
        "ALTER TABLE chatbot_leads ADD COLUMN IF NOT EXISTS company_name VARCHAR(160)",
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
        """
        WITH ranked AS (
            SELECT
                id,
                first_value(id) OVER (
                    PARTITION BY client_slug, normalized_phone
                    ORDER BY created_at ASC, id ASC
                ) AS canonical_id
            FROM chatbot_leads
            WHERE client_slug = 'central-e-commerce-co-ltd'
        )
        UPDATE chatbot_lead_sessions sessions
        SET lead_id = ranked.canonical_id
        FROM ranked
        WHERE sessions.lead_id = ranked.id
          AND ranked.id <> ranked.canonical_id
        """,
        """
        WITH ranked AS (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY client_slug, normalized_phone
                    ORDER BY created_at ASC, id ASC
                ) AS duplicate_rank
            FROM chatbot_leads
            WHERE client_slug = 'central-e-commerce-co-ltd'
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
        "ALTER TABLE chatbot_lead_sessions ADD COLUMN IF NOT EXISTS notice_version VARCHAR(40)",
        "ALTER TABLE chatbot_lead_sessions ADD COLUMN IF NOT EXISTS notice_presented_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE chatbot_lead_sessions ADD COLUMN IF NOT EXISTS cookie_notice_opened_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE chatbot_lead_sessions ADD COLUMN IF NOT EXISTS privacy_notice_opened_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE chatbot_lead_sessions ADD COLUMN IF NOT EXISTS processing_basis VARCHAR(80)",
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
            public_session_id VARCHAR(120) NOT NULL,
            lead_session_id VARCHAR(120),
            lead_id UUID REFERENCES chatbot_leads(id) ON DELETE SET NULL,
            campaign_name VARCHAR(255) NOT NULL DEFAULT '',
            chatbot_name VARCHAR(255) NOT NULL DEFAULT '',
            customer_name VARCHAR(100) NOT NULL DEFAULT '',
            company_name VARCHAR(160),
            customer_mobile VARCHAR(20) NOT NULL DEFAULT '',
            language VARCHAR(10) NOT NULL DEFAULT 'en',
            source VARCHAR(80) NOT NULL DEFAULT 'interactive_sms',
            status VARCHAR(30) NOT NULL DEFAULT 'open',
            assigned_employee VARCHAR(120) NOT NULL DEFAULT '',
            follow_up_required BOOLEAN NOT NULL DEFAULT FALSE,
            internal_notes TEXT NOT NULL DEFAULT '',
            started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            last_activity_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            completed_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_conversations_client_public_session
        ON chat_conversations (client_slug, public_session_id)
        """,
        "CREATE INDEX IF NOT EXISTS ix_chat_conversations_client_slug ON chat_conversations (client_slug)",
        "CREATE INDEX IF NOT EXISTS ix_chat_conversations_public_session_id ON chat_conversations (public_session_id)",
        "CREATE INDEX IF NOT EXISTS ix_chat_conversations_lead_session_id ON chat_conversations (lead_session_id)",
        "CREATE INDEX IF NOT EXISTS ix_chat_conversations_lead_id ON chat_conversations (lead_id)",
        "CREATE INDEX IF NOT EXISTS ix_chat_conversations_started_at ON chat_conversations (started_at)",
        "CREATE INDEX IF NOT EXISTS ix_chat_conversations_last_activity_at ON chat_conversations (last_activity_at)",
        "CREATE INDEX IF NOT EXISTS ix_chat_conversations_customer_mobile ON chat_conversations (customer_mobile)",
        "ALTER TABLE chat_conversations ADD COLUMN IF NOT EXISTS company_name VARCHAR(160)",
        "CREATE INDEX IF NOT EXISTS ix_chat_conversations_company_name ON chat_conversations (company_name)",
        "CREATE INDEX IF NOT EXISTS ix_chat_conversations_campaign_name ON chat_conversations (campaign_name)",
        "CREATE INDEX IF NOT EXISTS ix_chat_conversations_status ON chat_conversations (status)",
        "CREATE INDEX IF NOT EXISTS ix_chat_conversations_assigned_employee ON chat_conversations (assigned_employee)",
        """
        CREATE TABLE IF NOT EXISTS chat_conversation_messages (
            id UUID PRIMARY KEY,
            conversation_id UUID NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
            role VARCHAR(20) NOT NULL,
            content TEXT NOT NULL,
            message_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            model_name VARCHAR(120) NOT NULL DEFAULT '',
            response_id VARCHAR(120) NOT NULL DEFAULT '',
            error_state VARCHAR(80) NOT NULL DEFAULT '',
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_chat_conversation_messages_conversation_id ON chat_conversation_messages (conversation_id)",
        "CREATE INDEX IF NOT EXISTS ix_chat_conversation_messages_role ON chat_conversation_messages (role)",
        """
        CREATE INDEX IF NOT EXISTS ix_chat_conversation_messages_conversation_created
        ON chat_conversation_messages (conversation_id, created_at)
        """,
    ]

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)
    run_lightweight_migrations()
