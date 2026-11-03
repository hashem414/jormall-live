# Karmalite tenant implementation

## Repository-specific architecture map

Karmalite uses the existing modular-monolith boundaries. `Organization`, `OrganizationSettings`,
`Branch`, `BranchHoursRule`, `Service`, `ServiceBranch`, `Role`, `OrganizationInvitation`,
`KnowledgeSource`/`KnowledgeVersion`, `PromptConfiguration`, `WebsiteWidgetConfiguration`,
`ProviderConnection`, and `AuditEvent` are defined in `packages/db/prisma/schema.prisma`.

`IdentityRepository.createOrganization` is the platform-only creation path. It hardcodes
`BEAUTY_CENTER`, creates the four system roles and defaults, issues an Owner invitation, and audits
the operation. Tenant work is authorized through `TenantAccessSnapshot`; ordinary browser inputs do
not supply an organization ID. Support setup uses reason-bound, expiring platform support access,
and PostgreSQL RLS remains the database defense.

Branches, services, settings, staff, roles, invitations, and tenant audit behavior live in
`packages/db/src/identity-repository.ts`. Branch hours and availability live in
`packages/db/src/scheduling-repository.ts`. Appointment creation remains conflict-protected in the
CRM/scheduling repositories. A service cannot provide live slots without a real bookable provider,
branch assignment, service assignment, and availability.

Knowledge ingestion is text/Markdown-only in the current Phase 5A implementation. It creates Draft
versions which become customer-retrievable only through explicit activation. The AI orchestration
boundary is in `packages/ai`; allowlisted actions are independently re-authorized by
`AIFoundationRepository`. Communications use `ProviderIntegrationMode`; local seeded connections
remain `MOCK` and must not be represented as production delivery.

Branding currently persists only HTTPS logo URLs and theme colors in `OrganizationSettings`.
Although the architecture documents require tenant-prefixed object storage, this repository has no
implemented S3-compatible upload/storage adapter. Therefore the supplied logo is retained as an
operator approval input, no logo bytes are stored in PostgreSQL, no public bundled asset is
selected, and the provisioner preserves the neutral JorMall colors. Adding a production logo
requires the future storage adapter; extracted colors must remain unsaved suggestions until an
authorized Owner explicitly saves them after contrast review.

Tests use Vitest for unit behavior, PostgreSQL integration suites for RLS/transactions/repositories,
and Playwright for UI journeys. Standard gates are `pnpm format:check`, `pnpm lint`,
`pnpm lint:boundaries`, `pnpm typecheck`, `pnpm test`, `pnpm test:integration`, `pnpm test:e2e`, and
`pnpm build`.

## Setup command

Configure `KARMALITE_OWNER_EMAIL`, `KARMALITE_PROVISIONING_ADMIN_EMAIL`, and `NEXT_PUBLIC_APP_URL`,
then run:

```powershell
pnpm provision:karmalite
```

The first run creates missing records. Later runs verify invariants and add only missing template
records; they do not overwrite tenant-edited values. To deliberately reapply the tenant template:

```powershell
pnpm provision:karmalite -- --force
```

The command writes a private, expiring Owner activation URL to the git-ignored local file
`.env.karmalite-invitation` only when it creates a new invitation. It never creates an Owner
password. An unexpired pending invitation is reused without creating a duplicate.
`raja@karmalite.com` remains production-pending until address control is verified. If a pending
invitation link was lost, explicitly revoke and replace it with:

```powershell
pnpm provision:karmalite -- --rotate-owner-invitation
```

## Created configuration

- Organization slug `karmalite-medical-esthetic`, type `BEAUTY_CENTER`, tenant status Active in
  development
- Bilingual Karmalite organization profile and one Sweifieh branch in `Asia/Amman`, currency JOD
- Saturday–Thursday 09:00–19:00 hours; no Friday hours rule
- Exactly five Draft services with null prices and request-only online booking
- Owner, Manager, Secretary, and Service Provider system role templates
- One secure Owner invitation scoped only to Karmalite
- Draft Karmalite knowledge source transcribed from the clean production-draft DOCX; it is not
  activated
- Tenant prompt guardrails and a bilingual website assistant using neutral branding
- Mock/development provider defaults only; no live delivery claim

## Draft, provisional, and missing values

Service durations, preparation/aftercare, reminders, cancellation/rescheduling, late arrival, and
no-show rules are Draft. Minimum booking notice, maximum booking window, deposits, and payments are
unconfigured. Confirm the official Arabic name, exact address/map pin, mobile/WhatsApp, all five
service names/durations/instructions, and policies before publication.

No placeholder staff are created. Invite real providers through Business → Team & Access, then add
their Karmalite-only membership, branch assignment, service assignment, weekly availability, and
time off. Keep confirmed online booking disabled until this data exists and has been tested.

The supplied logo remains at the repository root for review. Production use is blocked on the
missing tenant-prefixed object-storage adapter. After that integration exists, upload the approved
logo, preview extracted suggestions, run contrast checks in English and Arabic, and save explicitly.

Review the Draft source in AI Studio → Knowledge. Activate only an approved sanitized version. Never
ingest the older broad medical document. Connect live communications only through tested production
provider adapters and credentials; otherwise retain `MOCK`/`DEVELOPMENT` wording.

## Verification

Apply migrations to the isolated `jormall_karmalite` database, run the provisioner twice, and verify
record counts, null prices, Draft knowledge, no placeholder staff, Owner scope, audit events, and
cross-tenant denial. Then run the repository gates listed above. The Karmalite workspace is
available through the Owner invitation after secure first-login account setup.

Run the tenant-data assertions with:

```powershell
pnpm verify:karmalite
```

## Material files changed

- `apps/web/scripts/provision-karmalite.ts` and `apps/web/scripts/verify-karmalite.ts` provide the
  idempotent tenant setup and executable database assertions.
- `apps/web/src/server/karmalite-template.ts` contains the approved Karmalite template; the
  organization, branch, service, settings, and AI administration pages consume persisted tenant
  records rather than a public hardcoded profile.
- `docs/tenants/karmalite/karmalite-beauty-center-knowledge.md` is the sanitized Draft knowledge
  source transcribed from the supplied production-draft document.
- `packages/domain/src/ai-safety.ts` and the AI orchestration/action boundaries enforce the exact
  medical-question refusal before retrieval, model invocation, or tool execution.
- `packages/db/prisma/schema.prisma`, `packages/db/src/identity-repository.ts`, and migrations
  `20260906100000_karmalite_draft_metadata` and `20260906110000_organization_profile_update_grant`
  add Draft/approval metadata, nullable policy inputs, mobile contact data, and least-privilege
  tenant profile updates.
- Service-price, organization-readiness, communications-provider, AI-safety, repository, tenant
  isolation, migration, and Playwright tests cover the changed behavior in English and Arabic.

The repository-root DOCX and logo remain source/operator-review materials. Neither is imported as an
active public asset, and no unrelated source document is deleted.
