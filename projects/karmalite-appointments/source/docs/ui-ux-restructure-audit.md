# JorMall UI/UX Restructure Audit

Status: Implementation baseline, 2026-09-01

## Product and architecture baseline

JorMall is a Next.js 16 / React 19 modular monolith. `apps/web` composes authenticated pages, server
actions, and HTTP adapters. PostgreSQL/Prisma repositories in `packages/db` implement ports and
policies from `packages/domain`; Better Auth provides database sessions; BullMQ/Redis handles
asynchronous communications and predictive work. English and Arabic route segments and RTL styling
already exist.

The implemented product is materially broader than its current navigation suggests. Tenant-aware
repositories already cover identity/RBAC, CRM, conflict-safe appointments, resources, waitlists,
communications, AI knowledge/actions/channels, operational reporting, Copilot, predictive
recommendations, imports, audit, platform support access, and legacy gym operations. The restructure
must reuse these workflows instead of duplicating them in React components.

The product decision for this restructure is that `BEAUTY_CENTER` is the only supported operating
sector. Historical enum members and gym tables may remain for migration compatibility, but normal
application routes, APIs, seed data, permissions, and presentation must not expose them.

## Current delivery surfaces

### Routes

| Existing route                                             | Current responsibility                                             | Target workspace                      |
| ---------------------------------------------------------- | ------------------------------------------------------------------ | ------------------------------------- |
| `/[locale]/dashboard`                                      | Organization overview and sector command center                    | Home                                  |
| `/dashboard/today`                                         | Appointment operations and status actions                          | Schedule / Today                      |
| `/dashboard/calendar`                                      | Appointment filters, creation, and rescheduling                    | Schedule / Calendar                   |
| `/dashboard/appointments/[appointmentId]`                  | Appointment detail, notes, records, and messages                   | Shared appointment drawer             |
| `/dashboard/waitlist`                                      | Waitlist lifecycle and mock slot offers                            | Schedule / Waitlist                   |
| `/dashboard/customers[/[customerId]]`                      | CRM directory and profile                                          | Customers                             |
| `/dashboard/communications`                                | Conversations, messages, delivery, and provider configuration      | Inbox and Settings / Channels         |
| `/dashboard/services`                                      | Services and branch configuration                                  | Business / Services                   |
| `/dashboard/staff`                                         | Staff, invitations, assignments, and availability                  | Business / Team & Access              |
| `/dashboard/roles`                                         | Tenant roles and permissions                                       | Business / Team & Access              |
| `/dashboard/resources`                                     | Resource groups, units, hours, and requirements                    | Business / Resources                  |
| `/dashboard/branches`                                      | Branch administration                                              | Business / Branches                   |
| `/dashboard/reports`                                       | Operational report runs, attribution, and exports                  | Insights / Reports and Attribution    |
| `/dashboard/copilot`                                       | Evidence-linked operational insights                               | Insights / Recommendations            |
| `/dashboard/predictions`                                   | Predictive settings, jobs, evidence, and feedback                  | Insights / Recommendations            |
| `/dashboard/knowledge`                                     | Knowledge source/version lifecycle                                 | AI Studio / Knowledge                 |
| `/dashboard/ai-settings`                                   | Prompt policy and evaluations                                      | AI Studio / Behavior                  |
| `/dashboard/ai-actions`                                    | AI action audit                                                    | AI Studio / Actions                   |
| `/dashboard/ai-usage`                                      | AI usage                                                           | AI Studio / Usage                     |
| `/dashboard/ai-conversations[/[id]]`                       | AI conversation history                                            | Inbox / Handoffs and AI test evidence |
| `/dashboard/ai-handoffs`                                   | Human handoff queue                                                | Inbox / Handoffs                      |
| `/dashboard/ai-channels`                                   | Website, WhatsApp, and voice fixtures/configuration                | Settings / Channels                   |
| `/dashboard/settings`                                      | Organization, locale, timezone, currency, booking window, branding | Settings                              |
| `/dashboard/imports`                                       | Staged customer imports                                            | Settings / Imports                    |
| `/dashboard/audit`                                         | Tenant audit                                                       | Settings / Audit                      |
| `/[locale]/platform/organizations`                         | Platform organizations, support access, worker health              | Platform Console                      |
| `/[locale]/platform/audit`                                 | Platform audit                                                     | Platform Console                      |
| `/dashboard/gym/**`, `/trainee`, `/trainee-invitations/**` | Legacy gym and trainee features                                    | Retired; no beauty-center equivalent  |

### Components and styling

The current shell is implemented directly in the dashboard layout. Navigation uses one collapsible
`DashboardNavigation`; header controls contain a permanent history Back button and locale switch.
Branding components already provide organization logo fallback, CSS theme tokens, client-side logo
palette extraction, and a settings preview. `DashboardPageHero`, `Feedback`, `SubmitButton`, and
`MessageTimeline` are reusable presentation foundations. There is no shared drawer, tabs, data
table, permission boundary, global search, alerts, branch selector, user menu, or workspace-state
layer. Most styling is centralized in `globals.css`.

### Server actions and HTTP APIs

`/[locale]/actions.ts` exposes validated server actions for login/logout, tenant switching,
organization lifecycle/settings, branches, staff invitations/roles, services, customers/consent,
appointments, resources, waitlists, communications, AI knowledge/configuration/handoffs, widgets,
Copilot, reports, imports, and exports. Predictive and legacy gym actions are split into their own
files.

HTTP routes currently cover Better Auth, AI widget sessions/turns/verification, protected import
error and export downloads, verified WhatsApp/voice webhooks, and widget assets. Internal employee
reads are server-rendered; authenticated interactive search, alert, appointment-drawer, and staff AI
endpoints do not yet exist.

### Repositories and data models

- `IdentityRepository`: organizations, settings/branding, memberships, roles/grants, branches,
  staff, invitations, services, and availability rules.
- `CrmAppointmentRepository`: customers, contacts, consent, appointment options/create/list/detail,
  rescheduling, state transitions, records/notes, and Today projections.
- `SchedulingRepository`: branch hours, resource groups/units/availability, service requirements,
  slot search, waitlist, and slot offers.
- `CommunicationRepository`: conversations/messages/preferences, provider connections, delivery
  attempts, webhooks, outbox processing, and worker health.
- `AIFoundationRepository` and `AIChannelRepository`: knowledge, prompt policies, AI conversations,
  actions/confirmations, usage, evaluations, handoffs, widget/WhatsApp/voice channel state.
- `CopilotRepository`, `OperationsIntelligenceRepository`, and `PredictiveRepository`: operational
  insights, attribution, reports/exports/imports/audit, predictions, recommendations, and feedback.
- `GymRepository`: legacy gym-only profiles/plans/progress/portal; it is outside the supported
  beauty-center product and is scheduled for retirement from application exports.

The Prisma schema already contains tenant-aware models and RLS migrations for every working
aggregate. Gaps required by the restructure are active branch session state, customer/appointment
references, beauty-service instructions/categories, customer notes/tags/preferred branch,
conversation assignment/read state, provider mode, resource maintenance history, richer branch
contact fields, and typed booking rules.

### Permissions and tenancy

The active tenant is resolved only from a verified Better Auth session and active membership or
audited platform support access. Permission grants use organization, assigned-branch, and self
scopes. Repositories require a `TenantAccessSnapshot`, tenant-owned relations carry
`organizationId`, and PostgreSQL RLS is defense in depth. Page helpers redirect forbidden users;
individual repositories enforce record scope. New navigation must be derived from these grants, but
hiding navigation will never replace route, endpoint, repository, branch, self, export, or RLS
authorization.

Legacy gym permission codes currently exist in the active registry and default role templates. They
must be removed from active application policy while historical permission rows may remain.

### Tests and starting health

Vitest contains 22 passing unit files (67 tests). PostgreSQL/Redis integration suites cover tenant
security, appointment/resource concurrency, communications workers, AI foundation/channels, Copilot,
operations intelligence, prediction, and legacy gym behavior. Playwright covers login, tenant
isolation, customers, Calendar, Today, resources/waitlist, communications, AI, reports,
imports/audit, predictions, gym/trainee paths, branding, mobile layout, English, and Arabic RTL.

At audit time, `pnpm.cmd format:check`, `lint`, `lint:boundaries`, `typecheck`, and `test` pass.
Integration and Playwright suites remain phase gates because they require their PostgreSQL/Redis and
browser runtime.

## Specification coverage and implementation gaps

| Requirements | Existing coverage                                                      | Required change                                                                                                                |
| ------------ | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| 1–3          | Architecture/docs, mature modules, healthy checks                      | Preserve behavior; maintain this audit throughout delivery                                                                     |
| 4–7          | Branded header, locale switch, grouped navigation                      | Persistent shell/sidebar, breadcrumbs, organization/branch controls, search, alerts, Ask JorMall, user menu, fixed terminology |
| 8            | Overview plus separate Today page                                      | Permission-aware Home projections; retain detailed Schedule/Today                                                              |
| 9–15         | Appointment lifecycle, Today, Calendar, waitlist, detail, availability | Schedule tabs, list, shared drawer, wizard, URL state, conflict UX                                                             |
| 16           | Customer directory/profile, consent, messages, insights                | Beauty-center Customer workspace, richer filters/timeline/notes                                                                |
| 17           | Communications and AI handoff pages                                    | Unified Inbox and integration-mode presentation                                                                                |
| 18–22        | Services, staff, roles, resources, branches                            | Consolidated Business workspace and beauty-specific fields/labels                                                              |
| 23–26        | Reports, attribution, Copilot, predictions                             | Consolidated Insights workspace and shared filters/saved views                                                                 |
| 27–32        | Knowledge, prompts/evals, conversations, actions, usage                | Simplified AI Studio plus internal test surface                                                                                |
| 33–39        | General settings, branding, channels, imports, audit                   | Settings subroutes, booking rules, preview/contrast, audit filters                                                             |
| 40           | Separate platform routes already exist                                 | Dedicated Platform shell/index and clearer separation/support banner                                                           |
| 41–44        | Repository authorization, basic RTL/mobile/focus                       | Permission-built navigation, responsive role navigation, semantic reusable controls, complete RTL/keyboard/contrast            |
| 45           | Existing deep links                                                    | Redirect compatibility and route-migration document                                                                            |
| 46–48        | Mock adapters and page-specific states                                 | Normalized integration modes and reusable loading/empty/error/permission states                                                |
| 49–50        | Strong unit/integration/e2e foundations                                | Replace sector/gym coverage and add all new critical journeys                                                                  |
| 51           | Server rendering and indexed core queries                              | Pagination, debounce, lazy panels, indexes, query review                                                                       |
| 52–55        | Existing architecture/operations docs and commands                     | Update all affected docs, run every gate, report exact evidence and remaining real-provider limitations                        |
