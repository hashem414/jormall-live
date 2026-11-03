# JorMall SMA Hybrid AI Gateway

This Flask service replaces the previously external-only gateway source. It keeps GPT-5 nano as the answer model and combines sanitized live SMA data with relevant passages retrieved from the three reference documents.

## Local setup

```bash
cd JorMall_SMA_Backend_SIDE_TEST_SAFE_20260820
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
```

Load `.env` with your deployment's secret manager or process supervisor. Do not serve `.env`, copy it into `hosted-app`, or commit it.

Required variables:

- `OPENAI_API_KEY`: server-side OpenAI project key.
- `SMA_EXTENSION_SHARED_KEY`: must initially match the installed extension's `X-SMA-Extension-Key`. Rotate this distributed shared credential as a separate security migration.
- `OPENAI_MODEL`: defaults to `gpt-5-nano`.
- `OPENAI_REASONING_EFFORT`: defaults to `minimal` for reliable low-latency structured answers.
- `OPENAI_MAX_OUTPUT_TOKENS`: defaults to `4000` so reasoning does not consume the complete answer budget.

## One-time document ingestion

From this directory, with `OPENAI_API_KEY` exported:

```bash
python3 ingest_documents.py --dry-run
python3 ingest_documents.py
```

The successful command creates `vector_store_manifest.json`. The gateway reads its `vector_store_id` automatically. Production may instead set `OPENAI_VECTOR_STORE_ID` and omit the manifest.

Re-running without `--vector-store-id` creates a replacement vector store. Test the replacement, deploy its ID, then delete the old vector store manually only after rollback is no longer needed.

## Run and test

```bash
python3 -m pytest tests
gunicorn -c gunicorn.conf.py wsgi:app
```

The service binds to `127.0.0.1:8088` by default. Proxy `https://sma-extension.jormallapp.com` to that address and retain request-size and timeout limits in nginx.

## API behavior

- `GET /health`: public status without secrets or document contents.
- `POST /api/chat`: authenticated hybrid chat for all three assistant screens.
- `POST /sma/analyze-notes`: authenticated notes summary compatibility endpoint.
- `POST /sma/notify-sales-priority`: authenticated optional SMTP notification endpoint.

Every protected endpoint requires `X-SMA-Extension-Key`. Document retrieval failures fall back to webpage-only answering and are reported as `retrieval.status = "unavailable"`.

## Deployment and rollback

1. Back up the currently deployed gateway and environment configuration.
2. Install `requirements.txt` in a fresh virtual environment.
3. Ingest the documents and configure the resulting vector-store ID.
4. Configure the OpenAI and extension secrets in the service environment.
5. Start Gunicorn and verify `/health` locally.
6. Switch nginx upstream traffic to `127.0.0.1:8088`.
7. Test webpage-only, document-only, hybrid, Arabic, and unavailable-retrieval cases.
8. Deploy `hosted-app/` only after the gateway is healthy.

To roll back, restore the previous gateway upstream and the previous `hosted-app/` assets. Keep the old vector store until the rollout is accepted.
