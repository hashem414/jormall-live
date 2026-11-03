# Karmalite workflow verification checkpoint

This is the Phase 1 verification record, not final acceptance of the superseding multi-phase
specification.

## Verified before final checkpoint

- Baseline: 103 integration tests and all nine workspace typechecks passed.
- Routing: format, lint, boundaries, typecheck, 91 unit tests and two affected EN/AR/mobile browser
  journeys passed.
- Completion security: format, lint, boundaries, typecheck, 97 unit tests and 105 PostgreSQL/Redis
  integration tests passed.
- Full existing browser suite: 16 tests passed after note changes. These cover existing workflows,
  not the new doctor/health/escalation/inventory journeys.
- Prisma validation and generation passed.
- All 42 migrations deployed successfully to a disposable empty local database; the note-history
  trigger was verified and only that disposable database removed.
- Upgrade: the additive migration deployed to the existing local Karmalite database without
  rewriting existing rows. Note immutability and retained record contents were verified by
  integration tests.

## New regression locations

- `apps/web/src/lib/appointment-tab-context.test.ts`: selectors, malformed/repeated input, transient
  feedback/authority stripping, EN/AR and room context.
- `apps/web/src/components/workspace-navigation.test.ts`: retired links remain absent even when
  AI/handoff grants exist.
- `packages/domain/src/appointment-completion.test.ts`: note normalization, bounds, valid
  completion-only usage and optional notes.
- `tests/integration/tenant-security.integration.test.ts`: scoped completion-note write denial,
  atomic unchanged status on rejection, preserved legacy records, idempotent note/audit insertion,
  append-only trigger and cross-tenant note denial.
- `tests/e2e/foundation.spec.ts`: retired EN/AR screens and retained verified channels.
- `packages/domain/src/patient-health.test.ts`: explicit health states, detail binding, consent and
  provenance requirements.
- `packages/domain/src/availability.test.ts`: patient-overlap and break exclusion from calculated
  availability.
- `tests/integration/tenant-security.integration.test.ts`: protected health permission/RLS/audit,
  directory non-disclosure, explicit doctor schedules and breaks, cross-tenant denial, room
  compatibility, and concurrent same-patient booking protection.

## Final verification of this partial checkpoint

- Prisma schema validation and client generation passed.
- The existing Karmalite database upgraded through all 43 additive migrations without a reset. The
  same 43 migrations also applied successfully to a disposable empty database, which was then
  removed.
- Format, lint, dependency-boundary lint and all nine workspace typechecks passed.
- 102 unit tests passed across 32 files.
- 109 PostgreSQL/Redis integration tests passed across 9 files, including the protected-health
  permission/RLS/audit cases, doctor schedules and breaks, cross-tenant denial, room compatibility,
  and deterministic same-patient booking race.
- 17 Playwright tests passed in the final full run, including English/Arabic and mobile coverage.
- The dedicated Karmalite verifier passed: one BEAUTY_CENTER tenant, one branch, five Draft
  services, null/unpublished prices, no unapproved doctors, no active knowledge versions and no
  production provider claims. It accepts either an unexpired secure Owner invitation or an
  invitation-activated tenant Owner, and production requires the Owner email to be verified.
- Production build passed and generated 122 static pages.
- Windows Turbo emitted a long symlink-name cache warning. Development tests also emitted the
  existing PostgreSQL `client.query` deprecation, `NO_COLOR`/`FORCE_COLOR`, and Next Gzip listener
  warnings. No framework upgrade or warning suppression was performed.

Manual acceptance remains separate from automated verification. Phase 2 daily doctor tables, the
final doctor-column calendar, live room calling/Next Appointment, waitlist changes, chatbot
check-in/escalations, persistent notifications, and inventory remain intentionally outstanding.

The statement above is retained as the historical Phase 1 checkpoint and is superseded by the
remaining-work verification below.

## Phase 2 automated verification completion (2026-09-07)

- The disposable PostgreSQL fixture applied all 45 migrations and reported an up-to-date schema; the
  disposable Redis fixture supported the worker tests.
- The persistent local Karmalite database was inspected read-only. Its two Phase 2 migrations remain
  unapplied; no reset, destructive migration, or data rewrite was performed.
- The final run passed 102 unit tests across 32 files, 109 PostgreSQL/Redis integration tests across
  9 files, and all 17 Playwright journeys (English, Arabic/RTL, desktop, and mobile).
- Format, lint, dependency-boundary lint, all nine workspace typechecks, Prisma validation and
  generation, production build, and the local production startup smoke test passed.
- Manual acceptance is documented by the automated lifecycle, permission, tenancy, and responsive
  coverage above; no separate human click-through was represented as production acceptance.

## Remaining-work final verification and local activation (2026-09-08)

- Prisma format, validation and client generation passed. All 46 migrations applied to an empty
  disposable database. A template-preserving upgrade clone of `jormall_karmalite` retained runtime
  role grants, applied `20260907140000_remaining_karmalite_workflows`, and preserved exact pre-seed
  counts: 183 organizations, 615 patients, 8,475 appointments and 128 services.
- Formatting, ESLint, dependency-boundary lint and all nine workspace typechecks passed.
- 105 unit tests passed across 33 files. 113 PostgreSQL/Redis integration tests passed across ten
  files. The final full Playwright run passed 18 journeys; one additional persistent Karmalite
  authenticated EN/AR/mobile smoke journey also passed.
- Integration coverage includes tenant/recipient notification isolation, independent Read/Done
  state, escalation ordering/assignment/resolution, proposal review/rejection, supplier/cost
  projection privacy, inventory approval/order/ETA, atomic partial/complete receipt, idempotent
  replay, concurrent over-receipt rejection, waitlist conversion and resource race protection.

- Patient entry uses a searchable combobox in booking, waitlist, and communication workflows.
- Appointment and waitlist date/time fields reject past selections. Closed days and time windows
  outside the active branch's configured opening hours are rejected in both the interface and server
  workflow.
- Production build passed. It generated 128 pages before the final smoke-test addition and emitted
  only the documented Windows standalone symlink warning.
- Backup: `backups/karmalite-pre-remaining-work-20260908.dump`, 3,950,572 bytes, SHA-256
  `B25D02B77BE7A1844639F1EDB47BB495E24C40733315B55241A223ACAFE163A0`.
- The verified remaining-work migration was then applied to persistent `jormall_karmalite` with no
  reset. Counts remained 183 / 615 / 8,475 / 128. All eight new tenant tables have enabled and
  forced RLS.
- The local production build started on port 3000. Authenticated Karmalite smoke covered Today,
  Calendar, All Appointments and an existing detail, Patients, Doctors, Services, Resources,
  Waitlist, Notifications, Chatbot Escalations, Inventory, Arabic RTL, and 390px mobile layout.
- Mock communication and deterministic AI adapters remain clearly non-production. No live delivery,
  diagnosis, prescription, insurance, EMR, or automatic supplier-purchasing claim was introduced.

## Inventory integration verification and local activation (2026-09-14)

- Prisma format, validation and generation passed. All 48 migrations applied from empty, and a
  restored clone of the persistent database applied `20260914140000_inventory_workflow_integration`.
- The upgrade clone preserved 285 organizations, 244 branches, 672 users, 1,110 patients, 11,804
  appointments, 183 services and 8 existing inventory items. Its item and location balances both
  totaled 40, and no item was left without a location.
- All nine workspace typechecks, ESLint, dependency boundaries and formatting passed. Inventory
  domain tests passed 7/7 and the focused PostgreSQL integration suite passed 5/5.
- The proposal-to-receipt Inventory Playwright journey, the appointment-consumption journey and the
  authenticated Karmalite EN/AR/mobile smoke each passed. The production build generated 131 routes.
- Backup: `backups/jormall_karmalite-before-inventory-20260914-1617.dump`, 5,775,624 bytes, SHA-256
  `9474758EEF912EDA7EE675B77A53A780A8379CF76F4A997ECE40AD925522D3EB`.
- The migration was applied to persistent `jormall_karmalite` without reset or reseeding. Immediate
  post-migration baseline counts and the total stock balance matched the pre-migration snapshot.

## Inventory role verification (2026-09-15)

- Applied `20260915113000_karmalite_inventory_request_access` to grant existing Karmalite Manager
  and Secretary roles assigned-branch Inventory read and request-only access.
- Verified the complete Owner proposal, approval, order, ETA, partial receipt, full receipt and
  movement-history journey.
- Verified Manager, Secretary and Service Provider request visibility with no create-item, approval,
  receiving or stock-change controls. Verified Owner visibility of the separately grantable
  Inventory permissions.
- Verified an Owner can create, edit and delete a custom request-only role from Roles & Access.
- Verified a new local Manager account through the normal invitation and activation pages, including
  automatic assignment to Karmalite's sole active branch. No existing account password was changed.

## In-progress service change and account security (2026-09-15)

- Backup: `backups/jormall_karmalite-before-service-change-20260915.dump`, 5,950,770 bytes, SHA-256
  `B828DD25922EB38EB1570E5ABB34CDF55D16A4463DB7E8258AFA32F06E52F759`.
- Applied `20260915150000_appointment_service_change` to persistent `jormall_karmalite` without a
  reset or reseed. Counts remained 289 organizations, 248 branches, 683 users, 1,112 patients,
  11,810 appointments, 190 services, and 32 inventory items.
- Focused PostgreSQL coverage verifies an assigned doctor can change an `IN_PROGRESS` appointment to
  another branch-enabled, doctor-assigned, occupied-room-compatible service. The same transaction
  replaces inventory reservations, increments the version, appends `SERVICE_CHANGED` history and
  audit evidence, and denies cross-tenant access.
- Focused Playwright coverage changes an active local Service Provider test account's password
  through the authenticated Account Security page, signs in with the changed password, restores the
  original local test password through the same page, and signs in again. Better Auth revokes other
  sessions while the replacement current session preserves the validated workspace selection.
