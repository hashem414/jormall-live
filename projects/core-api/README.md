# Core API

Flask API providing authentication and application endpoints.

## Directory layout

- [source/](source/)

## Requirements

Python, Flask, SQLAlchemy, JWT configuration and any configured Firebase integration.

## Setup

The entry point is run:app. Configure persistent storage and provision users before exposing protected endpoints.

Install dependencies from the selected component's dependency file, supply private configuration through the runtime environment, and use its Dockerfile or package scripts to start it. Deployment paths and service definitions must be adapted to the target host.

## Configuration

Environment variable names used by the services:

`APP_PORT`, `BITLY_API_KEY`, `ENABLE_OPENAI`, `FLASK_APP`, `FROM_EMAIL`, `JWT_SECRET_KEY`, `LANG`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `SMA_ALLOWED_ORIGINS`, `SMTP_HOST`, `SMTP_PASS`, `SMTP_PORT`, `SMTP_USER`, `VITE_API_URL`, `VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_APP_ID`, `VITE_FIREBASE_AUTH_DOMAIN`, `VITE_FIREBASE_MESSAGING_SENDER_ID`, `VITE_FIREBASE_PROJECT_ID`, `VITE_FIREBASE_STORAGE_BUCKET`, `VITE_FIREBASE_VAPID_KEY`.

Set credentials privately. Values marked `REDACTED_CONFIGURE_LOCALLY` must be replaced before use.

## Deployment status

Dependencies, private configuration and persistent data are managed separately. A successful application build, migration and smoke test are required before deployment; repository availability alone does not establish readiness.
