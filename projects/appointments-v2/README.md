# Appointments platform

Next.js appointments interface with a background worker and shared business packages.

## Directory layout

- [deployment/](deployment/)
- [deployment-original/](deployment-original/)
- [web-runtime/](web-runtime/)
- [worker-runtime/](worker-runtime/)

## Requirements

Node.js 24, pnpm, PostgreSQL and Redis.

## Setup

The web directory contains a compiled Next.js build. Original editable web source and a complete reproducible web build are unavailable. Worker TypeScript and database migrations are included.

Install dependencies from the selected component's dependency file, supply private configuration through the runtime environment, and use its Dockerfile or package scripts to start it. Deployment paths and service definitions must be adapted to the target host.

## Configuration

Environment variable names used by the services:

`APP_URL`, `AUTH_SECRET`, `BETTER_AUTH_SECRET`, `DATABASE_URL`, `DIRECT_URL`, `ENCRYPTION_KEY`, `HOSTNAME`, `NEXT_PUBLIC_APP_URL`, `NEXT_PUBLIC_ENABLE_PUBLIC_REGISTRATION`, `NEXT_TELEMETRY_DISABLED`, `NODE_ENV`, `NODE_OPTIONS`, `NODE_VERSION`, `PORT`, `REDIS_URL`, `YARN_VERSION`.

Set credentials privately. Values marked `REDACTED_CONFIGURE_LOCALLY` must be replaced before use.

## Deployment status

Dependencies, private configuration and persistent data are managed separately. A successful application build, migration and smoke test are required before deployment; repository availability alone does not establish readiness.
