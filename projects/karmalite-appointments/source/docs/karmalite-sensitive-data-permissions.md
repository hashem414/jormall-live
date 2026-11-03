# Karmalite sensitive-data permissions

Patient safety intake and doctor notes use dedicated grants in addition to normal patient and
appointment permissions.

| Data/workflow     | Read grant                   | Write grant                   | Default scope                                             |
| ----------------- | ---------------------------- | ----------------------------- | --------------------------------------------------------- |
| Patient directory | `patients.directory.read`    | —                             | Owner/Manager/Secretary organization; Provider self       |
| Patient profile   | `patients.profile.read`      | —                             | Owner/Manager/Secretary organization; Provider self       |
| Patient contact   | `patients.contact.read`      | `patients.contact.write`      | Owner/Manager/Secretary organization; Provider read self  |
| Safety intake     | `patients.health.read`       | `patients.health.write`       | Owner/Manager organization; Provider self; Secretary none |
| Doctor notes      | `patients.doctor_notes.read` | `patients.doctor_notes.write` | Owner organization; Provider self                         |

Every protected health read and update passes through tenant context, applies ORGANIZATION,
ASSIGNED_BRANCHES, or SELF record scope, and emits an audit event. PostgreSQL row-level security is
enabled and forced on the protected table. Consent is linked using organization, consent, and
patient identifiers so provenance cannot be attached across patients or tenants.

General patient search, global search, appointment tables, calendar cards, notification previews,
chatbot responses, normal analytics, and existing general exports do not select health states or
text. Booking may request a separate protected endpoint only for an authorized viewer; that endpoint
returns three booleans and audits the read. Restricted text is visible only on the protected patient
profile tab.

This protection does not turn JorMall into a medical-record system. No diagnosis, prescription,
medication, insurance, clinical-plan, surgery, or AI medical-advice capability is introduced.
