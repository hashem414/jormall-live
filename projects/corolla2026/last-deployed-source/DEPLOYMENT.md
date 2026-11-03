# central-trade-auto-co-markazia-toyota-jordan Standalone Chatbot

This folder is a single-client Docker deployment for `central-trade-auto-co-markazia-toyota-jordan`. It contains
the public chatbot, target-client knowledge seed, static assets, pre-chat lead
capture, callback/history persistence when enabled, and selected protected dashboards.

Enabled dashboards: Sales Callback Dashboard, Chat History Dashboard.

It intentionally excludes other clients, real `.env` files, existing conversation
history, lead records, callback records, dashboard notes, assignments, and production
secrets.

## 1. Requirements

- Docker Engine with Docker Compose v2
- Network access from the server to the OpenAI API for production answer synthesis
- A domain or server IP that can reach the exposed application port

## 2. Folder Structure

- `app/` - FastAPI application source
- `data/clients/central-trade-auto-co-markazia-toyota-jordan/` - exported target-client config and approved files
- `data/runtime/db_seed.json` - target-client PostgreSQL/pgvector seed
- `db/init/` - PostgreSQL extension initialization
- `docker-compose.yml` - application and PostgreSQL services
- `Dockerfile` - application image build
- `.env.example` - safe placeholder environment file
- `PACKAGE_MANIFEST.json` - generated file inventory and checksum metadata

## 3. Create `.env`

Copy the example and edit the new `.env` file:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

## 4. Required Environment Variables

- `OPENAI_API_KEY` - required for production-equivalent model answers
- `POSTGRES_DB` - PostgreSQL database name
- `POSTGRES_USER` - PostgreSQL username
- `POSTGRES_PASSWORD` - PostgreSQL password
- `APP_BASE_PATH` - public path prefix, default `/central-trade-auto-co-markazia-toyota-jordan`
- `HOST_PORT` - localhost host port for the chatbot, default `3001`
- `STANDALONE_CLIENT_SLUG` - must remain `central-trade-auto-co-markazia-toyota-jordan`
- `DASHBOARD_PASSWORD` or `CALLBACK_DASHBOARD_PASSWORD` - employee dashboard password
- `CALLBACK_ADMIN_TOKEN` - token for protected callback admin API exports
- `SESSION_SECRET` and `CSRF_SECRET` - dashboard session and CSRF signing secrets

## 5. Generate Safe Secrets

Use long random values. Examples:

```bash
openssl rand -base64 32
```

PowerShell:

```powershell
[Convert]::ToBase64String((1..32 | ForEach-Object { Get-Random -Maximum 256 }))
```

## 6. Build And Start

```bash
docker compose config
docker compose up -d --build
docker compose ps
```

## 7. Check Status

```bash
docker compose ps
docker compose logs -f chatbot
```

## 8. Health URLs

- Application health: `http://localhost:3001/health`
- Database health: `http://localhost:3001/db-health`

## 9. Chatbot URL

`http://localhost:3001/central-trade-auto-co-markazia-toyota-jordan/`

Embed loader:

`http://localhost:3001/central-trade-auto-co-markazia-toyota-jordan/embed/jormall-chatbot.js`

## 10. Sales Callback Dashboard URL

`http://localhost:3001/central-trade-auto-co-markazia-toyota-jordan/sales-callbacks/`

## 11. Chat History Dashboard URL

`http://localhost:3001/central-trade-auto-co-markazia-toyota-jordan/chat-history/`

Shared dashboard login:

`http://localhost:3001/central-trade-auto-co-markazia-toyota-jordan/admin/login`

## 12. Stop

```bash
docker compose down
```

Never run `docker compose down -v` unless permanent deletion of PostgreSQL and runtime data is intended.

## 13. Restart

```bash
docker compose restart
```

## 14. Update

Replace this deployable folder with a newly generated package, keep the production
`.env`, then run:

```bash
docker compose up -d --build
```

## 15. Back Up PostgreSQL

```bash
docker compose exec postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup.sql
```

## 16. Restore PostgreSQL

```bash
docker compose exec -T postgres psql -U "$POSTGRES_USER" "$POSTGRES_DB" < backup.sql
```

## 17. Back Up Runtime Data

Back up the Compose volumes `chatbot_db` and `chatbot_conversations`, plus the
server-side `.env` file. Do not commit `.env` to source control.

## 18. Persistent Data

- PostgreSQL data: Docker volume `chatbot_db`
- Conversation runtime files: Docker volume `chatbot_conversations`
- Seed source: `data/runtime/db_seed.json`

## 19. Export CSV

Log in to an enabled dashboard and use the `Export CSV` button. Employees do not
need API tokens, curl, database access, or PowerShell commands.

## 20. Reverse Proxy Example

```nginx
location /central-trade-auto-co-markazia-toyota-jordan/ {
    proxy_pass http://127.0.0.1:3001;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;
    proxy_read_timeout 300s;
}
```

## 21. Security Notes

- Keep `.env` private.
- Use HTTPS in production.
- Use a strong dashboard password.
- Rotate `CALLBACK_ADMIN_TOKEN` if it is shared.
- This package is locked to `central-trade-auto-co-markazia-toyota-jordan` and should not be modified to serve other clients.

## 22. First Deployment Checklist

- `.env` exists and contains deployment secrets.
- `docker compose config` passes.
- `docker compose up -d --build` completes.
- `/health` returns healthy.
- `/db-health` reports pgvector available.
- Chatbot page loads.
- Enabled dashboard login pages load.
- Test enabled dashboard CSV exports work.
- Backups are scheduled.

## Knowledge Mode

The application initializes an idempotent PostgreSQL/pgvector schema and imports
the target-client seed from `data/runtime/db_seed.json`. The seed contains only
active client-visible documents and chunks for `central-trade-auto-co-markazia-toyota-jordan`.
