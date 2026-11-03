# Patient and doctor permissions: Phase 1 checkpoint

The protected safety profile and explicit Doctor classification are implemented. Safety data must
never be entered into general searchable customer fields.

Appointment operational notes now require both the legacy `appointment_records.read/write` grant and
the dedicated `patients.doctor_notes.read/write` grant. Branch and SELF scopes are evaluated against
the appointment. A status-only operator can complete an appointment without a note, but cannot
submit completion notes. UI fields are hidden and the repository rejects forged requests.

Completion appends a note and audit event without replacing an earlier record. General
appointment/public projections still exclude operational notes. Direct cross-tenant note reads
return no rows under RLS. Regression tests cover missing write permission, unrelated provider scope,
other-tenant writes and immutable history.

Patient directory/profile/contact, safety-intake, doctor-note, doctor directory/profile/schedule,
time-off, service-assignment, permission-management, and doctor-appointment grants are registered in
English and Arabic. Health reads and updates are audited. Emergency escalation, supplier, and
inventory-cost grants remain outside Phase 1.
