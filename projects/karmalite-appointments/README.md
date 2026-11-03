# Karmalite appointments

Multi-tenant appointments application with web UI, worker services, shared packages and database migrations.

## Directory layout

- [deployment/](deployment/)
- [source/](source/)

## Requirements

Node.js 24, pnpm as specified in source/package.json, PostgreSQL and Redis.

## Setup

source is the workspace root. Package scripts provide build, typecheck, test and database migration commands. Configure tenant settings before provisioning accounts.

Install dependencies from the selected component's dependency file, supply private configuration through the runtime environment, and use its Dockerfile or package scripts to start it. Deployment paths and service definitions must be adapted to the target host.

## Configuration

Environment variable names used by the services:

`APP_IMAGE`, `AUTH_SECRET`, `CREDENTIAL_ENCRYPTION_KEY`, `DATABASE_URL`, `DEV_SEED_PASSWORD`, `HOSTNAME`, `KARMALITE_OWNER_EMAIL`, `KARMALITE_PROVISIONING_ADMIN_EMAIL`, `MOCK_VOICE_WEBHOOK_SECRET`, `MOCK_WHATSAPP_WEBHOOK_SECRET`, `NEXT_PUBLIC_APP_URL`, `NEXT_TELEMETRY_DISABLED`, `NODE_ENV`, `NODE_VERSION`, `OTEL_SERVICE_NAME`, `PORT`, `POSTGRES_DB`, `POSTGRES_PASSWORD`, `POSTGRES_PORT`, `POSTGRES_USER`, `REDIS_PASSWORD`, `REDIS_PORT`, `REDIS_URL`, `WIDGET_SIGNING_SECRET`, `YARN_VERSION`.

Set credentials privately. Values marked `REDACTED_CONFIGURE_LOCALLY` must be replaced before use.

## Component documentation

- [source/docs/decisions/README.md](source/docs/decisions/README.md)
- [source/README.md](source/README.md)

## Deployment status

Dependencies, private configuration and persistent data are managed separately. A successful application build, migration and smoke test are required before deployment; repository availability alone does not establish readiness.
