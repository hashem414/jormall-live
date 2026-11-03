# Interactive SMS services

SMS chatbot services with separate production and test variants, including Soniox and Gemini speech integrations.

## Directory layout

- [central-test/](central-test/)
- [gemini-tts/](gemini-tts/)
- [live-soniox/](live-soniox/)
- [side-test/](side-test/)

## Requirements

Python 3.13, PostgreSQL and the providers required by the selected variant.

## Setup

live-soniox, central-test, gemini-tts and side-test have separate configuration. Select one variant per service and review callback URLs and outbound messaging settings.

Install dependencies from the selected component's dependency file, supply private configuration through the runtime environment, and use its Dockerfile or package scripts to start it. Deployment paths and service definitions must be adapted to the target host.

## Configuration

Environment variable names used by the services:

`ADMIN_SESSION_TIMEOUT`, `ALLOWED_ORIGINS`, `APP_BASE_PATH`, `APP_HOST`, `APP_PORT`, `APP_TIMEZONE`, `CALLBACK_ADMIN_TOKEN`, `CALLBACK_DASHBOARD_PASSWORD`, `CHATBOT_HOSTING_12_MONTHS_JOD`, `CHATBOT_HOSTING_1_MONTH_JOD`, `CHATBOT_HOSTING_3_MONTHS_JOD`, `CHATBOT_HOSTING_6_MONTHS_JOD`, `CHATBOT_SETUP_PRICE_JOD`, `CHAT_EXPORT_MAX_ROWS`, `CHAT_HISTORY_ENABLED`, `CHAT_MAX_OUTPUT_TOKENS`, `CHAT_REASONING_EFFORT`, `CHAT_VERBOSITY`, `CROSS_LANGUAGE_MIN_RETRIEVAL_SIMILARITY`, `DATABASE_URL`, `DEEPGRAM_API_KEY`, `EMBEDDING_BATCH_SIZE`, `EMBEDDING_DIMENSIONS`, `ENABLE_API_DOCS`, `GEMINI_TTS_CACHE_TTL_SECONDS`, `GEMINI_TTS_LANGUAGE_AR`, `GEMINI_TTS_LANGUAGE_EN`, `GEMINI_TTS_MODEL`, `GEMINI_TTS_VOICE_AR`, `GEMINI_TTS_VOICE_EN`, `GOOGLE_APPLICATION_CREDENTIALS`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_REGION`, `MIN_RETRIEVAL_SIMILARITY`, `OPENAI_API_KEY`, `OPENAI_CHAT_MODEL`, `OPENAI_EMBEDDING_MODEL`, `POSTGRES_DB`, `POSTGRES_PASSWORD`, `POSTGRES_PORT`, `POSTGRES_USER`, `PUBLIC_CHATBOT_BASE_URL`, `RETRIEVAL_TOP_K`, `SONIOX_API_KEY`, `SONIOX_STT_FALLBACK_MODEL`, `SONIOX_STT_MIN_CONFIDENCE`, `SONIOX_STT_MODEL`, `SONIOX_STT_WORKFLOW`, `SONIOX_TTS_ARABIC_SPEED`, `SONIOX_TTS_ENGLISH_SPEED`, `SONIOX_TTS_MODEL`, `SONIOX_TTS_REDUCE_SILENCE`, `SONIOX_TTS_VOICE`, `STANDALONE_CLIENT_SLUG`, `VOICE_BROWSER_FALLBACK_ENABLED`, `VOICE_ENABLED`, `VOICE_STT_PROVIDER`, `VOICE_TTS_PROVIDER`, `VOICE_USAGE_SYNC_ENABLED`, `VOICE_USAGE_SYNC_INTERVAL_SECONDS`.

Set credentials privately. Values marked `REDACTED_CONFIGURE_LOCALLY` must be replaced before use.

## Component documentation

- [central-test/source/README.md](central-test/source/README.md)
- [gemini-tts/source/README.md](gemini-tts/source/README.md)
- [live-soniox/source/README.md](live-soniox/source/README.md)
- [side-test/source/README.md](side-test/source/README.md)

## Deployment status

Dependencies, private configuration and persistent data are managed separately. A successful application build, migration and smoke test are required before deployment; repository availability alone does not establish readiness.
