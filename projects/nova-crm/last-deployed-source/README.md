# Nova — AI Division Operations

Nova is an internal operating system for AI projects, specialist capacity, daily delivery, risk and executive outcomes. It is built as a Cloudflare-compatible Vinext application with durable D1 records and server-side OpenAI planning.

## What works

- Manager command center with real project, task, capacity and activity records.
- Persistent project creation and task status changes.
- Server-side role enforcement and owner-authenticated Sites access.
- Strict-schema AI plan generation through the Responses API when `OPENAI_API_KEY` is set.
- Safe deterministic plan preview when no API key is configured.
- Advisory plan workflow: generation never inserts or activates tasks directly.
- Deterministic suitability scoring and daily scheduling with dependency and capacity controls.
- Individual employee login with PBKDF2 password hashing, revocable server sessions and role-scoped data.
- AI estimates represent human work after normal AI assistance and are expanded into dependency-safe daily tasks of at most 8 hours.
- Project progress recalculation and auditable material changes.
- Project, task, team, workload, personal work and grounded assistant views.

## Local development

Requirements: Node.js 22.13 or newer.

```bash
npm install
npm run dev
```

Copy `.env.example` to `.env` and set `OPENAI_API_KEY` to enable live AI planning. Secrets remain server-side.

Open `http://localhost:3000/login`. The local fallback manager is `manager@nova.local` with password `Nova-Local-Manager!26`. Hosted deployments must set `NOVA_MANAGER_EMAIL`, `NOVA_MANAGER_NAME`, and the secret `NOVA_MANAGER_PASSWORD`; the production password is never stored in source.

## Data and migrations

The logical D1 binding is `DB` in `.openai/hosting.json`. The runtime initializes missing core tables safely for local previews. Schema changes are defined in `db/schema.ts` and generated with:

```bash
npm run db:generate
```

Generated SQL in `drizzle/` must be reviewed and committed before deployment.

## Quality checks

```bash
npm run lint
npm test
```

Tests cover the deployment build, server render, daily capacity limits, dependency order, position/skill matching, and schema-safe planning fallback.

## Architecture

- `app/dashboard-client.tsx`: connected operational workspace and workflows.
- `app/api`: bootstrap, authorized actions, and AI planning endpoints.
- `lib/engines.ts`: deterministic scheduling, scoring, and validated planning schema.
- `lib/server-store.ts`: D1 access, realistic JorMall workspace seed, authorization context, progress calculation and audit writes.
- `db/schema.ts`: normalized operational tables.

Authentication uses application-owned credentials inside the outer private Sites access boundary. The backend derives the actor and role from an opaque, hashed session token in an `HttpOnly` cookie; it never trusts role data from the browser. Managers can manage the workspace, employees receive only their assigned work and related projects, and viewers are read-only.

## Deployment and operations

Deploy through Sites so D1 and environment values are provisioned consistently. Set `OPENAI_API_KEY` as a secret and `OPENAI_MODEL` as an environment variable. Keep the application owner-only until an explicit access list is approved.

Back up the D1 database on an operational schedule appropriate to your organization. Before schema changes, export a backup and rehearse restoration. Review AI usage, rejected plans and audit records regularly.

## Security notes

Writes use prepared statements and validated payloads. AI output is strict-schema validated and never performs direct mutations. Consequential plan activation remains a manager decision. Add organization-specific membership provisioning before enabling broader employee access.
