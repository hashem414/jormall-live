# Deployment service

API and host-side runner for managing application deployments.

## Directory layout

- [api/](api/)
- [runner/](runner/)
- [tests/](tests/)

## Requirements

Python 3.12, an explicit application registry and restricted host permissions.

## Setup

api, runner and tests are separate components. Review filesystem paths, allowed operations and authentication before enabling the runner.

Install dependencies from the selected component's dependency file, supply private configuration through the runtime environment, and use its Dockerfile or package scripts to start it. Deployment paths and service definitions must be adapted to the target host.

## Configuration

Environment variable names used by the services:

`LANG`.

Set credentials privately. Values marked `REDACTED_CONFIGURE_LOCALLY` must be replaced before use.

## Deployment status

Dependencies, private configuration and persistent data are managed separately. A successful application build, migration and smoke test are required before deployment; repository availability alone does not establish readiness.
