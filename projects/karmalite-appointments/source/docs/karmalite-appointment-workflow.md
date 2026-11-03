# Karmalite appointment workflow checkpoint

Implementation is partial; consult `karmalite-workflow-implementation-audit.md` for the requirement
map and remaining phases. BEAUTY_CENTER remains the only supported organization type. The new
Karmalite Patient/Doctor terminology is approved scope, but an employee must not be called a doctor
without explicit configuration.

## Changes implemented

- AI Studio and general Handoffs delivery screens/navigation are retired; backend AI, knowledge,
  gateway, conversation and audit infrastructure are retained.
- Shared schedule tabs preserve validated common URL selectors.
- The appointment register no longer discards repository telephone matches through a second
  name-only filter. Success notices no longer invalidate the register query.
- Completion notes require `appointment_records.write` for the appointment's branch and assigned
  provider. Status-transition permission alone is insufficient.
- Completion without a note remains available with status-transition permission.
- Completion appends an AppointmentNote and its audit event in the status transaction. An existing
  AppointmentRecord is not overwritten. Idempotent retries add no duplicate.
- The detail page offers Start Service only after check-in, matching the state machine.

## Migration

`20260907110000_appointment_notes_append_only` attaches the existing append-only history trigger to
`appointment_notes`. Existing rows are not changed. Updates and deletions fail, including direct
database writes. Corrections must be appended as new notes; there is no in-place editing UI.
Existing tenant RLS and composite appointment/organization relationships remain in force.

## Phase 2 implementation checkpoint

The active lifecycle is now PENDING → CONFIRMED → CHECKED_IN → CALLED → IN_PROGRESS → COMPLETED,
with CALLED displayed separately and IN_PROGRESS displayed as In Service. Every operational command
uses trusted tenant context, scoped grants, expected versions, idempotency, append-only history and
AuditEvent records. Confirmation, cancellation, completion and room-call notifications are outbox
events; the current operational adapter is explicitly presented as simulated.

Today now provides All Today, By Doctor and Needs Attention views, status KPI filtering, active
configured Doctor sections, real schedules/breaks/leave, mobile Doctor selection, partial bulk
confirmation, Next Appointment and status-aware actions. The Calendar provides Day, Week, Doctor and
Room views. Its Doctor grid is built from stored schedules, exposes bookable empty slots and treats
drag/drop as a proposed reschedule sent through the verified availability transaction. All
Appointments provides the four requested categories and tenant-scoped operational filters.

Scheduled room assignment remains distinct from live room occupancy. Calling claims an active,
compatible room slot; changing rooms releases and claims atomically; Start Service preserves the
claim; completion, cancellation and no-show release it. Database constraints prevent capacity from
being exceeded and RLS protects occupancy rows.

Waiting List policy changes, chatbot check-in/escalations, persistent notifications, inventory,
supplier management and stock remain intentionally outside Phase 2. This is an implementation
checkpoint, not the separate full verification checkpoint.
