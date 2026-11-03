# Karmalite chatbot

FastAPI chatbot for Karmalite services and customer interactions.

## Directory layout

- [source/](source/)

## Requirements

Python 3.13, PostgreSQL and the configured AI provider.

## Setup

The service entry point is app.api:app. Supply business content and private provider credentials separately.

Install dependencies from the selected component's dependency file, supply private configuration through the runtime environment, and use its Dockerfile or package scripts to start it. Deployment paths and service definitions must be adapted to the target host.

## Configuration

Environment variable names used by the services:

`ADMIN_TOKEN`, `CHAT_MODEL`, `CHUNK_MAX_CHARS`, `CHUNK_MIN_CHARS`, `CHUNK_OVERLAP_CHARS`, `CLINIC_ADDRESS_AR`, `CLINIC_ADDRESS_EN`, `CLINIC_AREA`, `CLINIC_BUILDING`, `CLINIC_FLOOR`, `CLINIC_LANDMARK`, `CLINIC_MAPS_URL`, `CLINIC_NAME`, `CLINIC_PHONE`, `CLINIC_STREET`, `DATABASE_URL`, `EMAIL_CODES_PER_HOUR`, `EMAIL_CODE_MAX_ATTEMPTS`, `EMAIL_CODE_TTL_MINUTES`, `EMBEDDING_DIM`, `EMBEDDING_MODEL`, `EMERGENCY_PHONE`, `HISTORY_TURNS`, `JOSMS_ACCNAME`, `JOSMS_ACCPASS`, `JOSMS_API_URL`, `JOSMS_MAX_ATTEMPTS`, `JOSMS_RETRY_MINUTES`, `JOSMS_SENDER_ID`, `JOSMS_SUCCESS_RESPONSES`, `JOSMS_TIMEOUT_SECONDS`, `LOG_LEVEL`, `MAIL_FROM`, `MAIL_FROM_NAME`, `MAX_ACTIVE_APPOINTMENTS_PER_PHONE`, `MAX_BOOKINGS_PER_HOUR_PER_PHONE`, `MIN_RELEVANCE_SCORE`, `OPENAI_API_KEY`, `RERANK_ENABLED`, `RETRIEVE_CANDIDATES`, `RETRIEVE_TOP_K`, `SMS_ENABLED`, `SMTP_HOST`, `SMTP_PASSWORD`, `SMTP_PORT`, `SMTP_STARTTLS`, `SMTP_USER`, `UTILITY_MODEL`.

Set credentials privately. Values marked `REDACTED_CONFIGURE_LOCALLY` must be replaced before use.

## Deployment status

Dependencies, private configuration and persistent data are managed separately. A successful application build, migration and smoke test are required before deployment; repository availability alone does not establish readiness.
