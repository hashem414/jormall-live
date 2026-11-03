# Schedule permissions

Navigation visibility is a convenience only. Each page, server action, repository method, and
database row-level policy independently enforces access.

| Capability            | Owner        | Manager             | Secretary     | Service Provider       |
| --------------------- | ------------ | ------------------- | ------------- | ---------------------- |
| Read appointments     | Organization | Granted scope       | Granted scope | Self                   |
| Create appointments   | Organization | Granted scope       | Organization  | Not granted by default |
| Reschedule/cancel     | Organization | Granted scope       | Organization  | Self                   |
| Normal status actions | Organization | Granted scope       | Organization  | Self                   |
| Correct status        | Organization | Explicit grant only | Not granted   | Not granted            |
| Waitlist              | Organization | Granted scope       | Granted scope | Not granted by default |

Custom roles receive only their actual grants. Assigned-branch scope rejects a supplied branch
outside the membership assignment. Self scope requires the appointment provider to match the
authenticated staff profile.

Out-of-tenant record identifiers are treated as not found. Bulk operations apply the same checks per
row and expose only stable result codes. No Schedule browser form or query accepts an organization
identifier.

Appointment completion notes require the existing appointment-record write grant. Customer creation
within the wizard additionally requires `customers.write`.
