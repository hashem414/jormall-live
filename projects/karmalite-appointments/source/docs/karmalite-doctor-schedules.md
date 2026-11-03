# Karmalite doctor schedules

Doctor schedules are stored as tenant-owned branch-local availability periods. Each weekday can be
working or off and can use independent start/end times. Up to two breaks are accepted by the Phase 1
form, while the repository supports multiple validated, non-overlapping breaks.

All entered clock values are converted to minutes only at the validated server boundary. Users see
normal clock inputs, never minute offsets. A working period must fit within that branch's opening
hours; a break must fit inside a period and must not overlap another break.

Date-specific leave is stored as UTC instants with branch context, reason, creator, and timestamps.
When a schedule or leave change affects future active appointments, the first request returns the
affected references and requires explicit confirmation. Appointments are not silently moved or
cancelled.

Availability excludes branch closures, doctor days off, breaks, leave, existing doctor reservations,
patient overlaps, and unavailable compatible rooms. The final booking transaction repeats these
checks and database constraints resolve races safely.
