# Appointment status transitions

The stored `IN_PROGRESS` status is presented as “In service.”

## Standard lifecycle

```text
PENDING -> CONFIRMED -> CHECKED_IN -> CALLED -> IN_PROGRESS -> COMPLETED
```

Exceptional transitions:

```text
PENDING -> CANCELLED
CONFIRMED -> CANCELLED
CONFIRMED -> NO_SHOW
CHECKED_IN -> CANCELLED
CALLED -> CANCELLED
IN_PROGRESS -> CANCELLED
```

Normal actions cannot skip lifecycle states. In particular, `CONFIRMED -> IN_PROGRESS` and
`NO_SHOW -> CHECKED_IN` are not standard transitions.

## Combined actions

- Confirm and Check In writes `PENDING -> CONFIRMED` and `CONFIRMED -> CHECKED_IN`.
- Check In and Start writes `CONFIRMED -> CHECKED_IN` and `CHECKED_IN -> IN_PROGRESS`.

Both happen atomically, increment the version for both transitions, and append both intermediate
history entries. They require the normal status-transition permission and an expected version.

## Operational timestamps

Scheduled instants remain in `startsAt` and `endsAt`; they are never overwritten with actual event
times. Status changes populate `confirmedAt`, `checkedInAt`, `calledAt`, `serviceStartedAt`,
`completedAt`, `cancelledAt`, and `noShowAt`. Each field has a corresponding actor reference.
Creation time remains `createdAt`.

Each transition history record stores actor, source, previous status, next status, scheduled times,
reason, version, transition source, and event time. Cancellation requires a reason; no-show reason
is optional. Completion notes are optional and require the separate scoped
`appointment_records.write` permission. They are appended as immutable appointment notes in the
completion transaction. The existing appointment record is created only if absent; earlier content
is never overwritten by completion. Status-only operators may complete without a note.

## Concurrency and idempotency

Every mutation includes an expected version and uses a conditional update in the tenant transaction.
A stale version returns `CONFLICT`. Idempotency keys prevent retries from duplicating a transition
or its history. Calling claims compatible live room capacity. Completing, cancelling, or marking
no-show releases staff reservations, scheduled resource reservations, and any live room occupancy in
the same transaction.

The existing protected correction permission remains restricted to explicitly granted owner/manager
workflows. It is not exposed as a general quick action.
