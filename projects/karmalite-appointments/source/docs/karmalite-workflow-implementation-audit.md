# Karmalite operational workflows: implementation audit

Status: Phase 2 implemented; automated verification completed on 2026-09-07. This document is not a
production acceptance claim; the deferred workflows below remain outside Phase 2.

The source specification is the user-approved 54-section Karmalite Appointment, Patient, Doctor,
Escalation, Notification, and Inventory Workflows prompt. Work is restricted to
`appo-main-2 - Customize`. The initial worktree has one unrelated generated change,
`apps/web/next-env.d.ts`, which must be preserved.

## Architecture and existing sources of truth

Next.js App Router 16.3.2 and React compose the web application. pnpm 10.33.2, TypeScript strict
mode, Zod, Prisma 7.9.1, PostgreSQL, Redis/BullMQ, Better Auth, Vitest and Playwright are already
installed. URL query state and server actions are the existing UI state/mutation mechanisms. No
replacement framework is needed.

`packages/domain` owns policies; `packages/contracts` owns external contracts; `packages/db` owns
persistence. `apps/web/src/server/identity.ts` resolves trusted session membership and grants.
`runInTenant` sets PostgreSQL tenant and actor context with the restricted `jormall_app` role.
Organization IDs must not be accepted from ordinary browser commands. Grant scope is ORGANIZATION,
ASSIGNED_BRANCHES or SELF, not inferred from a displayed role title.

The authoritative scheduling records are Appointment, AppointmentStatusHistory,
AppointmentStaffReservation and AppointmentResource. CrmAppointmentRepository and
SchedulingRepository already protect scheduling conflicts, versions, idempotency, availability,
resource allocation and waitlist conversion. AuditEvent remains the authoritative audit source.
Communications use outbox/worker processing; simulated provider results must not be presented as
live delivery.

## Requirement-to-repository map

| Specification                                      | Existing implementation to reuse                                                                      | Required change and validation                                                                                                                                                                                                                   |
| -------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1–4 Product, audit, navigation                     | `workspace-navigation.ts`, dashboard layout, `next.config.ts`, beauty catalogs, organization settings | Retain BEAUTY_CENTER. Tenant terminology must not confer Doctor status. Remove AI Studio and general Handoffs delivery screens, retain backend AI infrastructure. Navigation and retired-route tests.                                            |
| 5 Shared appointment workspace                     | `workspace-tabs.tsx`, `(workspace)/schedule/*`                                                        | Preserve applicable URL context without carrying transient success/error or view-specific pagination across tabs. All pages continue using CRM scheduling records.                                                                               |
| 6–7 Lifecycle and timestamps                       | `domain/appointment-state.ts`, Prisma Appointment and AppointmentHistory, CRM transition methods      | Add CALLED and calledAt/rescheduledAt through explicit migrations. Keep IN_PROGRESS internally, render In Service. Preserve intermediate combined histories and actors. Domain and upgrade tests.                                                |
| 8–13 Today, doctor tables, attention, confirmation | `dashboard/today/page.tsx`, CRM list/transition/bulk methods, submit buttons                          | Default doctor grouping only for explicitly configured doctors, chronological tie-breaks, empty tables, schedule/break/leave evidence, status-aware actions and real issue sources. Per-row partial bulk results. Scope and Playwright coverage. |
| 14 Shared details                                  | `dashboard/appointments/[appointmentId]/page.tsx`, drawer read API                                    | Reuse URL-addressed details; add protected health/notes reads, history, communication and audit tabs, sticky status action. Cross-tenant/SELF denial tests.                                                                                      |
| 15–19 Booking                                      | appointment wizard, options/availability APIs, `scheduling-transaction.ts`, CRM create                | Shared normalized patient lookup/new profile; do not overwrite existing data. Any qualified doctor, compatible room, accepted confirmation, final patient/provider/room conflict checks and safe recovery. Concurrency and EN/AR browser tests.  |
| 20–21 Calendar/register                            | dashboard calendar, workspace appointment register, page-local scheduling helpers                     | Doctor-column time grid, authorized prefill and confirmed drag/drop, working-hours blocks; shared filters/search, ascending ordering, scoped export/print.                                                                                       |
| 22 Verified chatbot check-in                       | contracts Action Gateway, AI gateway/runtime, signed capabilities, appointment transition             | Allowlisted verified patient action with correct tenant/date/window, CONFIRMED only; no public health/notes access. Gateway authorization and replay tests.                                                                                      |
| 23–25 Next/room/start/done                         | resource allocation and appointment transition/history/records                                        | Separate live room occupancy from scheduled reservations. Atomic earliest checked-in claim, compatible room lock, called event/outbox, completion releases occupancy and appends notes. Deterministic concurrent-doctor/room tests.              |
| 26 Waiting list                                    | SchedulingRepository, waitlist/slot-offer models and page, priority helpers                           | Per-doctor/any grouping, priority 1–4 with reasons/urgent grants, fresh opening match and transactional conversion. Preserve lifecycle history and no automatic booking.                                                                         |
| 27–28 Patients                                     | Customer/contact/consent/notes, CRM directory/detail and search                                       | Locale-aware alphabetical/paged lookup and separately protected health profile with NONE/DECLINED/provided states and audited reads. No health data in search, general notifications or unrestricted exports.                                    |
| 29 Doctors                                         | StaffProfile, StaffService, branch assignments, availability rules, time off, Team page               | Explicit profession configuration, per-day split hours/breaks, date leave and affected-appointment warnings. Never invent people, qualifications or schedules.                                                                                   |
| 30–31 Rooms/services                               | resource groups/units/maintenance history, service requirements/configuration                         | Explicit room/service compatibility and warnings on changes; active compatible options, transaction revalidation, real null/unpublished prices retained.                                                                                         |
| 32 Escalations                                     | HumanHandoff, Conversation, verified AI context, audit                                                | Dedicated authorized emergency queue/history/assignment/resolution; HIGH/CRITICAL states and sanitized notifications. No diagnosis or invented emergency number. Read and resolve permissions distinct.                                          |
| 33 Notifications                                   | computed WorkspaceAlerts and `/api/workspace/alerts`                                                  | New persistent per-recipient tenant/branch notifications with independent read/done state, safe deep links and audited commands. Bell cannot mark all done. Underlying entities unaffected.                                                      |
| 34–40 Inventory                                    | No existing inventory models/repository or pages                                                      | Add items/proposals/orders/stock ledger, permission-based approval, supplier/cost projection guards, ETA and atomic partial receipts/idempotency. No automatic supplier purchases. New RLS, FK, race and UI tests.                               |
| 41–43 Permissions/audit/events                     | identity permission catalog, tenant-policy, AuditEvent, outbox/communications worker                  | Separate contact, health, doctor note, escalation, supplier and cost permissions. Extend grants explicitly; do not silently elevate managers or providers. Audit sensitive access. Queue events in mutation transaction.                         |
| 44–46 Refresh/EN/AR/responsiveness                 | server revalidation, locale switch, logical CSS, dialogs                                              | Reuse polling/invalidation with expected versions. Preserve route/query on language changes, mobile single-doctor cards and accessible touch targets.                                                                                            |
| 47 Database/API                                    | explicit Prisma migrations, tenant context, strict Zod actions                                        | Additive migrations only, composite tenant FKs, RLS, constraints, authenticated branch/record selectors, idempotency. Empty/upgrade fixture checks.                                                                                              |
| 48–49 Tests/manual journeys                        | `tests/integration/*`, `tests/e2e/*`, colocated Vitest tests                                          | Add all requested policy/scope/race tests and seven complete browser journeys; do not equate existing baseline tests with new acceptance.                                                                                                        |
| 50–54 Delivery/docs/verification                   | existing operations/architecture/security docs and pnpm scripts                                       | Nine gated phases below; eight requested workflow docs, build/startup and explicit remaining-work report.                                                                                                                                        |

## Controlled phases

1. Audit and routing: retire delivery-only AI screens and Handoffs, preserve existing functional
   destinations and URL context. Introduce new destinations when their protected workflows exist,
   not empty placeholder modules.
2. Lifecycle/shared components: CALLED/timestamps, reusable details and patient lookup, strict
   booking contracts and additive migration.
3. Daily operations: doctor projections, chronological tables/calendar/register, safe confirmation,
   live room occupancy, Next Appointment, completion notes.
4. Patients/doctors/rooms/services: dedicated health permissions, explicit doctor configuration,
   schedules, compatibility and affected-booking warnings.
5. Waiting list: named priorities/reasons, doctor grouping, openings and conversion.
6. Chatbot: verified check-in and dedicated escalation gateway and queue.
7. Notifications: persistent scoped recipients, independent read/done, safe links.
8. Inventory: proposals/approval/orders/ETA/ledger/receipts and notifications.
9. Completion: EN/AR, responsive/keyboard behavior, security, all tests, docs, production build and
   local startup.

After each phase run targeted tests plus format:check, lint, lint:boundaries, typecheck and unit
tests. Database phases require db:validate, db:generate, explicit migration tests and relevant
PostgreSQL/Redis suites. UI phases require affected EN/AR Playwright coverage. Fix failures before
proceeding. Final acceptance also requires all integration/e2e tests, production build and all
requested manual workflows. Never reset a database or seed fabricated operational data.

## Baseline checkpoint

- Typecheck: passed before changes (9 workspaces).
- PostgreSQL/Redis integration baseline: passed (103 tests).
- No new workflow has passed acceptance yet.
- Existing null service prices and secure invitation credentials remain unchanged.

## Implemented Phase 1 checkpoint

Routing retirement, shared schedule URL context, immutable completion notes, the patient directory
and protected patient profile, explicit doctor configuration, independent weekly hours and breaks,
date-specific leave, service/doctor assignments, room/service compatibility, and the six-step
transactional booking foundation are implemented through additive migrations and existing domain
boundaries.

The narrow safety-intake exception stores only allergies and known conditions with explicit states,
patient authorization/provenance, updater, timestamps, tenant-aware foreign keys, forced RLS,
dedicated permissions, audit reads/writes, and restricted boolean booking indicators. It is not a
medical-record module and is excluded from ordinary search, schedule surfaces, notifications,
chatbot output, analytics, and general exports.

No doctors, patients, rooms, health details, qualifications, schedules, prices, suppliers, or
inventory were fabricated. Karmalite prices remain unpublished/null. The migration was applied to
the existing local Karmalite database without resetting tenant data.

## Implemented Phase 2 checkpoint

Phase 2 adds the CALLED lifecycle state and actor timestamps, granular operation grants, configured
Doctor tables, Today KPIs and attention evidence, partial bulk confirmation, live capacity-aware
room occupancy, Next Appointment, room-call/change/repeat-message commands, Start Service,
completion duration and release, cancellation notification choice, the four Calendar views with a
schedule-derived Doctor time grid, proposed drag rescheduling, and the completed All Appointments
filters/register. Shared Appointment Details exposes operational occupancy/history/events while
retaining protected Doctor notes and health boundaries.

Migrations are additive and retain BEAUTY_CENTER. No Doctor, Patient, schedule, service, room or
availability was fabricated. Operational communications remain simulated and never claim delivery.
The migration/application matrix and end-to-end acceptance are intentionally reserved for the
separate verification prompt.

## Remaining-work implementation (2026-09-07)

The former outstanding items are now represented by additive schema and application workflows:
waiting-list priorities/history/conversion, Action Gateway chatbot check-in, dedicated chatbot
escalations, recipient-scoped persistent notifications, and inventory proposals/orders/ETA/atomic
receipts. Navigation exposes Chatbot Escalations, Notifications and Inventory only when their
dedicated grants exist. Manager receives no implicit inventory permissions. Supplier and cost data
remain separately permissioned. Final verification and persistent activation results are recorded in
`testing-karmalite-workflows.md`.
