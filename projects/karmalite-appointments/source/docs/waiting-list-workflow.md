# Waiting-list workflow

The Appointments workspace exposes By Doctor, Available Openings, and Converted / Closed views.
Priorities use LOW=1, NORMAL=2, HIGH=3 and URGENT=4; HIGH and URGENT require a recorded reason.
Urgent means scheduling priority only.

`Book This Opening` locks the waiting-list row, recalculates provider, room and patient availability
through the existing scheduling transaction, records an idempotency fingerprint, links the committed
appointment, appends immutable history, and changes the entry to CONVERTED. Matches never auto-book.

Existing `SlotOffer` remains the only external-offer mechanism. External communication continues
through the outbox, and mock delivery is shown as queued or simulated rather than delivered.
