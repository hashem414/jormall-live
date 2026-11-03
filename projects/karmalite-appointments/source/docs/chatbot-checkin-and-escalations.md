# Chatbot check-in and escalations

The Action Gateway now allowlists `check_in_appointment` and `create_emergency_escalation`. Check-in
requires the gateway's verified customer binding, tenant-owned appointment, the appointment's local
date, the configured before/after window, CONFIRMED state, expected version, and request
idempotency. It records ACTION_GATEWAY history and returns safe status codes only.

Emergency escalations are a dedicated organization workflow, separate from general handoffs. HIGH
and CRITICAL records preserve the patient's report and relevant evidence without adding diagnosis.
NEW, ACKNOWLEDGED, IN_PROGRESS, RESOLVED and DISMISSED changes are versioned, audited, and append
history. Notifications contain a safe summary and link to the protected detail page; they never
contain health intake or Doctor notes.

Dedicated verified chatbot check-in and emergency escalation workflows are not implemented yet.
General Handoffs screens are retired, as requested; they must not be described as a functioning
replacement escalation queue. Internal HumanHandoff, AI gateway, knowledge, transport verification
and audit infrastructure remain.

The next implementation must verify patient identity, tenant, appointment date and configured
check-in window, allow CONFIRMED only, and append action/history/audit evidence. Escalation read and
resolve grants must be distinct. Notifications must contain sanitized summaries, not health details.
No automatic diagnosis or invented emergency number is permitted. No public chatbot may receive
operational notes.
