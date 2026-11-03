# Innovation website

Static website for the JorMall innovation service.

## Directory layout

- [source/](source/)

## Requirements

A static HTTP server.

## Setup

Serve source as the document root. Review external URLs before publishing under a new hostname.

Install dependencies from the selected component's dependency file, supply private configuration through the runtime environment, and use its Dockerfile or package scripts to start it. Deployment paths and service definitions must be adapted to the target host.

## Deployment status

Dependencies, private configuration and persistent data are managed separately. A successful application build, migration and smoke test are required before deployment; repository availability alone does not establish readiness.
