# Main website

Public JorMall website and an offline maintenance page.

## Directory layout

- [deployment/](deployment/)
- [offline-page/](offline-page/)
- [source/](source/)

## Requirements

Nginx or another static HTTP server.

## Setup

source contains the public site; deployment contains the Nginx image definition; offline-page contains the maintenance page. Review the Docker build context before using the image definition.

Install dependencies from the selected component's dependency file, supply private configuration through the runtime environment, and use its Dockerfile or package scripts to start it. Deployment paths and service definitions must be adapted to the target host.

## Configuration

Environment variable names used by the services:

`DYNPKG_RELEASE`, `NGINX_VERSION`, `NJS_RELEASE`, `NJS_VERSION`, `PKG_RELEASE`.

Set credentials privately. Values marked `REDACTED_CONFIGURE_LOCALLY` must be replaced before use.

## Deployment status

Dependencies, private configuration and persistent data are managed separately. A successful application build, migration and smoke test are required before deployment; repository availability alone does not establish readiness.
