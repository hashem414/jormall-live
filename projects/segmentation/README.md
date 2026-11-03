# Audience segmentation

Audience segmentation, ranking and explanation service with configurable business rules.

## Directory layout

- [source/](source/)

## Requirements

Python 3.13, packages from source/requirements.txt and the required input datasets.

## Setup

source/config_data contains rule definitions. Supply datasets separately and review source_roots.local.json for environment-specific locations.

Install dependencies from the selected component's dependency file, supply private configuration through the runtime environment, and use its Dockerfile or package scripts to start it. Deployment paths and service definitions must be adapted to the target host.

## Configuration

Environment variable names used by the services:

`AI_REQUIRED`, `AI_REVIEW_TOP_RESULTS`, `ALLOW_NETWORK_PACKAGE_INSTALL`, `ALLOW_PAID_API_CALLS`, `ALLOW_PAID_EMBEDDINGS`, `ALLOW_WEB_RESEARCH`, `HOST`, `INTENT_PARSER_PROVIDER`, `LEXICAL_TOP_K`, `MAX_FUSED_CANDIDATES`, `OPENAI_API_KEY`, `OPENAI_CHAT_MODEL`, `OPENAI_EMBEDDING_MODEL`, `OPENAI_INTENT_TIMEOUT_SECONDS`, `OPENAI_REVIEW_TIMEOUT_SECONDS`, `PORT`, `RECOMMENDATION_ENGINE`, `SEMANTIC_HASH_DIM`, `SEMANTIC_PROVIDER`, `SEMANTIC_TOP_K`, `SEMANTIC_VECTOR_DIM`.

Set credentials privately. Values marked `REDACTED_CONFIGURE_LOCALLY` must be replaced before use.

## Deployment status

Dependencies, private configuration and persistent data are managed separately. A successful application build, migration and smoke test are required before deployment; repository availability alone does not establish readiness.
