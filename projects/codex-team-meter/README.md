# Team usage meter

Usage dashboard and parsers for Codex team activity.

## Directory layout

- [last-deployed-source/](last-deployed-source/)

## Requirements

Node.js 24 and private administrator configuration.

## Setup

Use last-deployed-source as the application root. Consult its Arabic README for setup and parser details.

Install dependencies from the selected component's dependency file, supply private configuration through the runtime environment, and use its Dockerfile or package scripts to start it. Deployment paths and service definitions must be adapted to the target host.

## Component documentation

- [last-deployed-source/README_AR.md](last-deployed-source/README_AR.md)
- [last-deployed-source/skills/team-usage-meter/README_AR.md](last-deployed-source/skills/team-usage-meter/README_AR.md)

## Deployment status

Dependencies, private configuration and persistent data are managed separately. A successful application build, migration and smoke test are required before deployment; repository availability alone does not establish readiness.
