# JorMall SMA Extension AI Gateway

Production FastAPI/Uvicorn backend for the JorMall SMA browser extension. It supports both root routes and `/sma-extension/...` routes, so it works whether Nginx preserves or removes the URL prefix.

## Extension endpoints

- `GET /health`
- `POST /api/chat`
- `POST /sma/notify-sales-priority`
- `POST /sma/analyze-company`
- `POST /sma/analyze-page`
- `POST /sma/analyze-notes`
- `POST /sma/analyze-category-monthly-delivery`
- `POST /sma/analyze-route`
- `POST /sma/draft-followup`
- `POST /sma/log-action`

## Behavior

- With `OPENAI_API_KEY`: uses the OpenAI Responses API.
- Without `OPENAI_API_KEY`: health and every analysis route still work using a deterministic local summary.
- Sales-priority email is sent only when SMTP is fully configured. Priority accounts are logged even when email is unavailable.
- Optional shared-key authentication uses the `X-SMA-Extension-Key` header.

## Local test

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
set -a; source .env; set +a
pytest -q
uvicorn app:app --host 127.0.0.1 --port 5055
```

Then test:

```bash
curl http://127.0.0.1:5055/health
curl -X POST http://127.0.0.1:5055/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"screen":"sales-report","question":"Summarize risks","rows":[{"companyName":"Test","risks":["ATT"]}]}'
```

## Production URL

Set the extension gateway URL to:

```text
https://jormallapp.com/sma-extension
```
