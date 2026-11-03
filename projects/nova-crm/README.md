# Nova CRM

CRM application with web pages, a worker and database definitions.

## Directory layout

- [last-deployed-source/](last-deployed-source/)

## Requirements

Node.js, the package manager specified by the application and its configured storage services.

## Setup

Use last-deployed-source as the application root. Its Dockerfile uses a local Wrangler runtime and persistent /data storage; review this model before deploying multiple replicas.

Install dependencies from the selected component's dependency file, supply private configuration through the runtime environment, and use its Dockerfile or package scripts to start it. Deployment paths and service definitions must be adapted to the target host.

## Component documentation

- [last-deployed-source/README.md](last-deployed-source/README.md)

## Deployment status

Dependencies, private configuration and persistent data are managed separately. A successful application build, migration and smoke test are required before deployment; repository availability alone does not establish readiness.
