# Start Here

1. Copy `.env.example` to `.env`.
2. Set a strong `POSTGRES_PASSWORD`.
3. Set dashboard credentials plus `SESSION_SECRET` and `CSRF_SECRET`.
4. Set a valid `OPENAI_API_KEY`.
5. Run:

```powershell
.\start.ps1
```

6. Open the printed chatbot and dashboard URLs.

Do not change `POSTGRES_USER`, `POSTGRES_PASSWORD`, or `POSTGRES_DB` after the database volume has been initialized unless a planned database credential migration is performed.

Never use `docker compose down -v` unless permanent removal of all PostgreSQL and runtime data is intended.

Canonical URLs:

- Chatbot: `http://127.0.0.1:3001/central-trade-auto-co-markazia-toyota-jordan/`
- Shared login: `http://127.0.0.1:3001/central-trade-auto-co-markazia-toyota-jordan/admin/login`
- Sales callbacks: `http://127.0.0.1:3001/central-trade-auto-co-markazia-toyota-jordan/sales-callbacks/`
- Chat history: `http://127.0.0.1:3001/central-trade-auto-co-markazia-toyota-jordan/chat-history/`
- Health: `http://127.0.0.1:3001/health`
