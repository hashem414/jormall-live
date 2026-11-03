# Corolla campaign chatbot

FastAPI chatbot and campaign interface for Corolla/Toyota content.

## Directory layout

- [last-deployed-source/](last-deployed-source/)

## Requirements

Python 3.13, PostgreSQL and the configured model/media providers.

## Setup

Use last-deployed-source as the application root. Knowledge documents, scraped media and production records must be supplied separately.

Install dependencies from the selected component's dependency file, supply private configuration through the runtime environment, and use its Dockerfile or package scripts to start it. Deployment paths and service definitions must be adapted to the target host.

## Component documentation

- [last-deployed-source/frontend/README.md](last-deployed-source/frontend/README.md)
- [last-deployed-source/README.md](last-deployed-source/README.md)

## Deployment status

Dependencies, private configuration and persistent data are managed separately. A successful application build, migration and smoke test are required before deployment; repository availability alone does not establish readiness.
