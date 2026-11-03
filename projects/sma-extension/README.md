# SMA extension

SMA hosted interface, browser extension components and AI gateway backends.

## Directory layout

- [csv-test/](csv-test/)
- [production/](production/)
- [test/](test/)

## Requirements

Python 3.12 for gateway backends, a static HTTP server for frontends and Chrome for browser extension installation.

## Setup

production, test and csv-test are independent variants. The Chrome extension is present in csv-test/chrome-extension; the test variant includes a hosted frontend and backend. Configure gateway URLs, browser permissions and authentication for the selected environment.

Install dependencies from the selected component's dependency file, supply private configuration through the runtime environment, and use its Dockerfile or package scripts to start it. Deployment paths and service definitions must be adapted to the target host.

## Configuration

Environment variable names used by the services:

`DYNPKG_RELEASE`, `LANG`, `NGINX_VERSION`, `NJS_RELEASE`, `NJS_VERSION`, `OPENAI_API_KEY`, `OPENAI_MAX_OUTPUT_TOKENS`, `OPENAI_MODEL`, `OPENAI_REASONING_EFFORT`, `PKG_RELEASE`, `SMA_EXTENSION_SHARED_KEY`.

Set credentials privately. Values marked `REDACTED_CONFIGURE_LOCALLY` must be replaced before use.

## Component documentation

- [csv-test/backend/source/README.md](csv-test/backend/source/README.md)
- [production/backend/source/README.md](production/backend/source/README.md)
- [production/frontend/backend/README.md](production/frontend/backend/README.md)
- [test/backend/source/README.md](test/backend/source/README.md)

## Deployment status

Dependencies, private configuration and persistent data are managed separately. A successful application build, migration and smoke test are required before deployment; repository availability alone does not establish readiness.
