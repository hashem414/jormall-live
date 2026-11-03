# Persistent notifications

Notifications are tenant-, recipient-, and optionally branch-scoped. The header bell shows recent
unread records and links to the full All / Unread / Read / Done page. Opening a notification marks
it Read but never Done. Marking it Done never mutates the related appointment, escalation, waitlist,
or inventory record. Bulk Done exists only on the full page and requires explicit confirmation when
HIGH or URGENT records are included.

Preview content is deliberately short and excludes allergies, known conditions, Doctor notes,
emergency transcripts, and inventory cost or supplier details. PostgreSQL RLS restricts SELECT and
UPDATE to the authenticated recipient while allowing tenant-scoped workflow inserts. Every state
change uses the existing AuditEvent source.

WorkspaceAlerts remains available for real computed attention evidence. Persistent notifications
extend that mechanism; they do not fabricate operational events or claim external delivery.
