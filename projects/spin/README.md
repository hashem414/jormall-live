# Spin application

Flask spin application with campaign and administration logic.

## Directory layout

- [source/](source/)

## Requirements

Python 3.10, database configuration and private application secrets.

## Setup

The declared entry point is container_entry:app. Review campaign settings and initialize a fresh database before testing.

Install dependencies from the selected component's dependency file, supply private configuration through the runtime environment, and use its Dockerfile or package scripts to start it. Deployment paths and service definitions must be adapted to the target host.

## Configuration

Environment variable names used by the services:

`CORS_ORIGINS`, `DATABASE_URL`, `DEFAULT_PHONE_REGION`, `FLASK_DEBUG`, `FLASK_ENV`, `FLASK_HOST`, `FLASK_PORT`, `LANG`, `SECRET_KEY`, `SMS_ACCNAME`, `SMS_ACCPASS`, `SMS_API_URL`, `SMS_SENDER_ID`.

Set credentials privately. Values marked `REDACTED_CONFIGURE_LOCALLY` must be replaced before use.

## Deployment status

Dependencies, private configuration and persistent data are managed separately. A successful application build, migration and smoke test are required before deployment; repository availability alone does not establish readiness.
