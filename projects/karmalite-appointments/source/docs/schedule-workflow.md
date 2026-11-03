# Schedule workflow

The Schedule workspace is the operational surface for a beauty center:

- `/[locale]/schedule/today` is the same-day command center.
- `/[locale]/schedule/calendar` provides Day, Week, Service Provider, Resource, and Branch views.
- `/[locale]/schedule/appointments` is the searchable appointment register.
- `/[locale]/schedule/waitlist` contains Active Waitlist, Available Matches, and Slot Offers.

All four pages read the same tenant-owned appointment, reservation, history, and waitlist records.
The active organization comes from the authenticated session. Browser inputs never provide an
organization identifier. Branch, provider, service, customer, resource, appointment, waitlist, and
offer identifiers are revalidated inside the active tenant.

## Today

Today resolves the date using the organization or selected branch timezone. It includes branch,
service-provider, service, status, and customer/phone/reference filters. KPI cards update the status
filter. Operational views are All Appointments, By Service Provider, and Needs Attention.

Needs Attention is evidence-based. It includes pending confirmations, late confirmed arrivals,
missing or unavailable resources, failed reminders, missing primary contacts, and configured
provider time off. It does not invent delivery results or resource assignments.

Row actions are permission- and status-aware. Bulk confirmation accepts pending appointments only
and returns a result for every selected row, so one stale or forbidden record does not undo
successful confirmations.

## Calendar

The calendar preserves its date, view, and filters in the URL. Day and Service Provider views group
the daily timeline by configured provider represented in the result. Week loads seven local dates in
parallel. Resource and Branch groupings use actual appointment reservations and branches.

Appointment cards show customer, service, start/end time, status, and resource/conflict state.
Opening a card uses the shared URL-addressable appointment drawer.

The current implementation does not provide drag-and-drop. Rescheduling is performed in the drawer
and requires the expected appointment version. Availability and resource conflicts are rechecked in
the server transaction before the schedule changes.

## New appointment

The six steps are Customer, Service & Branch, Service Provider, Date & Time, Resources, and Review.
Staff may select an existing customer or create a new customer when granted `customers.write`.

Available times come from the authoritative availability endpoint. It evaluates branch hours,
provider schedule and time off, service duration, existing reservations, required resources, and
tenant/branch permissions. Friday or any unconfigured closed day returns no bookable times. Required
resource units are assigned by the booking transaction.

Unpublished prices remain null and are displayed as:

- English: “Contact Karmalite for the current price.”
- Arabic: “يرجى التواصل مع كارمالايت لمعرفة السعر الحالي.”

## Refresh behavior

Server actions redirect to a fresh server-rendered projection after mutations. There is no WebSocket
or background polling mechanism in this delivery, so simultaneous changes made by another user
appear on navigation or manual refresh. Optimistic versions and database constraints prevent a stale
page from overwriting a newer booking.
