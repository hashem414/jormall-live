# Platform assistant

FastAPI assistant service with a dedicated HTTP application.

## Directory layout

- [source/](source/)

## Requirements

Python 3.10, packages from source/requirements.txt and configured external integrations.

## Setup

The declared entry point is fastapi_app.main:app. Configure authentication, provider access and persistent application content before startup.

Install dependencies from the selected component's dependency file, supply private configuration through the runtime environment, and use its Dockerfile or package scripts to start it. Deployment paths and service definitions must be adapted to the target host.

## Configuration

Environment variable names used by the services:

`APP_BASE_PATH`, `APP_ENV`, `CHAT_LOG_DIR`, `CHAT_LOG_MAX_BYTES`, `ENABLE_MAINTENANCE_ROUTES`, `LANG`, `OPENAI_API_KEY`, `OPENAI_CHAT_MODEL`, `OPENAI_EMBEDDING_MODEL`, `SESSION_COOKIE_SAMESITE`, `SESSION_COOKIE_SECURE`, `SESSION_MAX_AGE_SECONDS`.

Set credentials privately. Values marked `REDACTED_CONFIGURE_LOCALLY` must be replaced before use.

## Deployment status

Dependencies, private configuration and persistent data are managed separately. A successful application build, migration and smoke test are required before deployment; repository availability alone does not establish readiness.
