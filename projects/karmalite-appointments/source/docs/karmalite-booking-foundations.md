# Karmalite booking foundations

The appointment wizard follows six steps: Patient, Service, Doctor, Date & Time, Room, and Review.
It supports an existing patient search with debouncing/stale-response protection and authorized
inline creation of a new patient.

Doctor selection supports a specific qualified doctor or any available qualified doctor. The
availability request is tenant-authenticated and includes only branch, service, optional doctor,
date range, and optional patient selectors. It returns slots derived from stored branch hours,
service duration/buffers, doctor hours/breaks/leave, doctor and patient reservations, and active
compatible room availability.

The review shows patient, service, doctor, room, start/end, duration, preparation/cleanup buffers,
booking source, instructions, and only boolean safety indicators when authorized. It does not show
allergy or condition text. Price is shown only when an approved numeric service price exists;
otherwise the Karmalite contact message is shown.

Creation may be Pending or Confirmed. The transaction revalidates tenant ownership, doctor active
and bookable state, branch/service assignments, schedules, breaks, leave, patient/provider overlap,
room compatibility and resource capacity. Provider, resource, and patient database constraints
protect concurrent requests. Stable conflict codes return the user to refresh availability instead
of creating a partial appointment.
