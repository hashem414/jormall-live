# Authentication services

Shared sign-in service and user directory used by JorMall applications.

## Directory layout

- [sso-runtime/](sso-runtime/)
- [sso-source/](sso-source/)
- [user-directory/](user-directory/)

## Requirements

Python, private session/signing secrets and a separately provisioned user directory.

## Setup

sso-runtime contains the application; sso-source contains host-side settings/code; user-directory contains the directory service. User accounts must be provisioned separately.

Install dependencies from the selected component's dependency file, supply private configuration through the runtime environment, and use its Dockerfile or package scripts to start it. Deployment paths and service definitions must be adapted to the target host.

## Configuration

Environment variable names used by the services:

`BITLY_API_KEY`, `FLASK_SECRET_KEY`, `LANG`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_REASONING_EFFORT`, `PLAYWRIGHT_BROWSERS_PATH`, `SMTP_PASSWORD`, `SMTP_PORT`, `SMTP_SENDER`, `SMTP_SERVER`, `USER_DIRECTORY_TOKEN`, `USER_DIRECTORY_URL`.

Set credentials privately. Values marked `REDACTED_CONFIGURE_LOCALLY` must be replaced before use.

## Component documentation

- [sso-runtime/source/README.md](sso-runtime/source/README.md)

## Deployment status

Dependencies, private configuration and persistent data are managed separately. A successful application build, migration and smoke test are required before deployment; repository availability alone does not establish readiness.
