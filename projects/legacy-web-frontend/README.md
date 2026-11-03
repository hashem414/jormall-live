# Legacy web frontend

Compiled Flutter web application, including separate spin interface variants.

## Directory layout

- [source/](source/)

## Requirements

A static HTTP server and compatible backend endpoints.

## Setup

Serve source as static content. Editable Dart source is unavailable; backend URL changes may require the original Flutter project and a new build.

Install dependencies from the selected component's dependency file, supply private configuration through the runtime environment, and use its Dockerfile or package scripts to start it. Deployment paths and service definitions must be adapted to the target host.

## Deployment status

Dependencies, private configuration and persistent data are managed separately. A successful application build, migration and smoke test are required before deployment; repository availability alone does not establish readiness.
