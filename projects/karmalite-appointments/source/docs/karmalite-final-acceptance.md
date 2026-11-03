# Karmalite final acceptance checkpoint

Date: 2026-09-08

## Implemented workflows

- Waiting List uses Patient lookup, Doctor or Any Doctor preference, four named priorities,
  mandatory reasons for HIGH/URGENT, compatible opening checks, transactional conversion,
  idempotency, linked appointments, history and audit.
- The allowlisted chatbot check-in action verifies trusted Patient ownership, tenant, local date,
  configured window and CONFIRMED state before using the appointment state machine. PENDING and
  duplicate cases return safe results; sensitive health and Doctor-note content is excluded.
- Chatbot Escalations is a dedicated permissioned queue with HIGH/CRITICAL ordering, assignment,
  acknowledgement, progress, resolution/dismissal reasons, evidence, history, audit and safe
  notifications. It is not a diagnosis or emergency-service replacement.
- Persistent Notifications has recipient-isolated All/Unread/Read/Done states, safe deep links,
  audited commands and high-priority bulk confirmation. Notification state does not mutate the
  related business entity.
- Inventory supports items, proposals, permission-based approval/review/rejection, order requests,
  HOURS/DAYS ETA, partial/full receipt, immutable stock transactions and idempotent atomic stock.

## Verification evidence

- Static checks: format, lint, boundaries and nine workspace typechecks passed.
- Automated checks: 105 unit, 113 PostgreSQL/Redis integration and 18 full Playwright journeys
  passed. One additional persistent authenticated Karmalite smoke journey passed.
- Database: empty migration and upgrade path passed; persistent migration applied only after those
  gates and backup. Forced RLS is active on every new tenant table.
- Concurrency: provider/resource scheduling races, waitlist conversion and inventory receipt races
  preserve single-commit and stock-consistency invariants.
- Local activation: production build and port-3000 startup passed. Core Phase 2 and new module
  routes loaded for the real Karmalite tenant in English, Arabic RTL and 390px mobile mode.

## Launch boundaries

Communications and AI adapters remain Mock/Development. The product does not claim live delivery,
medical diagnosis, prescriptions, insurance, EMR, automatic supplier ordering, or chatbot emergency
response. A business owner should still perform final operational sign-off with approved real-world
content and production integrations before launch.
