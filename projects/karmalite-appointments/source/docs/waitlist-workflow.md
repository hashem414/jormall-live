# Waitlist workflow

The Waitlist page has three URL-addressable views:

- Active Waitlist shows active customer requests and their branch, service, optional provider, date
  range, preferred time window, and named priority.
- Available Matches evaluates real availability for a selected entry and lists bookable results.
- Slot Offers shows offers and their current expiry/status.

Priority is entered and displayed as Low, Normal, High, or Urgent rather than as a raw number.
Preferred windows use human-readable time inputs such as `09:00`, while the persistence model
continues storing local minutes.

Creating and mutating entries is tenant- and branch-scoped. Availability matching uses configured
providers, schedules, time off, branch hours, services, existing reservations, and resource
capacity. Accepting an offer books or reschedules through the same conflict-protected scheduling
transaction used by staff bookings.

An offer is not a booking. The final acceptance rechecks availability and may return a conflict when
another booking has taken the slot. The current schema has expiry-bearing offers but no independent
slot-hold record; the UI therefore does not claim that a displayed match is reserved.

Mock communication remains clearly identified and no live delivery result is fabricated.
