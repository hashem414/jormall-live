# Schedule testing

## Automated coverage

Domain tests cover allowed and rejected appointment transitions. PostgreSQL integration tests cover:

- operational timestamps;
- append-only status history;
- combined actions and intermediate history;
- per-item bulk-confirm results;
- idempotent retries;
- stale-version conflicts;
- provider self-scope and assigned-branch scope;
- cross-tenant non-disclosure;
- waitlist and slot-offer mutations;
- concurrent rescheduling and resource conflict protection.

Browser tests cover English and Arabic direction, Schedule navigation, wizard access, customer
creation, configured working-hour availability, human-readable waitlist time/priority controls, and
mobile overflow.

## Manual workflow

1. Sign in as a tenant Owner, Manager, or Secretary.
2. Open Schedule > Calendar and verify the Day, Week, Service Provider, Resource, and Branch view
   links preserve the selected date and filters.
3. Create an appointment for an existing customer, then repeat with New customer.
4. Verify a closed branch day offers no times and an open day offers only configured provider slots.
5. Open Today. Confirm a pending appointment, check it in, start service, and complete it.
6. Repeat with Confirm and Check In and Check In and Start; verify the drawer history contains both
   intermediate transitions.
7. Select several pending appointments and Bulk Confirm. Include a row changed in another session
   and verify successful rows remain confirmed while the stale row reports a failure.
8. Open an appointment drawer and reschedule it. In a second session take the chosen slot first and
   verify the stale reschedule is rejected.
9. Cancel a pending or confirmed appointment with a reason. Mark a confirmed appointment no-show
   with a reason.
10. Add a waitlist entry using a named priority and human-readable start/end times. Find real
    matches, create an offer, and accept it.
11. Repeat the critical workflow in Arabic and verify right-to-left layout, localized labels, and
    correct date/time display.
12. Sign in with a Service Provider account and verify only that provider's appointments and allowed
    actions are visible.

## Required commands

```text
pnpm db:validate
pnpm db:generate
pnpm format:check
pnpm lint
pnpm lint:boundaries
pnpm typecheck
pnpm test
pnpm test:integration
pnpm test:e2e
pnpm build
```
