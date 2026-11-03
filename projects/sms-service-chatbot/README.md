# SMS service chatbot

FastAPI chatbot for SMS service enquiries and related application workflows.

## Directory layout

- [deployment/](deployment/)
- [source/](source/)

## Requirements

Python 3.13, PostgreSQL and configured model/speech providers.

## Setup

source contains the application; deployment contains supplementary image and service definitions. Configure business content, callbacks and provider credentials separately.

Install dependencies from the selected component's dependency file, supply private configuration through the runtime environment, and use its Dockerfile or package scripts to start it. Deployment paths and service definitions must be adapted to the target host.

## Configuration

Environment variable names used by the services:

`ALLOWED_ORIGINS`, `APP_BASE_PATH`, `APP_ENV`, `APP_HOST`, `CALLBACK_ADMIN_TOKEN`, `CALLBACK_DASHBOARD_PASSWORD`, `CHAT_HISTORY_DASHBOARD_ENABLED`, `CHAT_MAX_OUTPUT_TOKENS`, `COOKIE_SECURE`, `CROSS_LANGUAGE_MIN_RETRIEVAL_SIMILARITY`, `CSRF_SECRET`, `DASHBOARD_PASSWORD`, `DASHBOARD_USERNAME`, `DATABASE_URL`, `EMBEDDING_DIMENSIONS`, `HOST_PORT`, `LOG_LEVEL`, `MIN_RETRIEVAL_SIMILARITY`, `OPENAI_API_KEY`, `OPENAI_CHAT_MODEL`, `OPENAI_EMBEDDING_MODEL`, `POSTGRES_DB`, `POSTGRES_PASSWORD`, `POSTGRES_USER`, `RETRIEVAL_TOP_K`, `SALES_CALLBACK_DASHBOARD_ENABLED`, `SESSION_SECRET`, `STANDALONE_CLIENT_SLUG`.

Set credentials privately. Values marked `REDACTED_CONFIGURE_LOCALLY` must be replaced before use.

## Component documentation

- [source/frontend/README.md](source/frontend/README.md)
- [source/README.md](source/README.md)

## Deployment status

Dependencies, private configuration and persistent data are managed separately. A successful application build, migration and smoke test are required before deployment; repository availability alone does not establish readiness.
