# Inventory workflow

Inventory is implemented as operational stock workflow: Items, Item Approvals, Order Requests, and
Incoming Orders. It does not purchase automatically and is not a prescription,
medication-administration, pharmacy, insurance, or EMR module.

Service Providers receive default access only to branch availability and their own proposal/order
creation. Owner receives organization management grants. Manager receives no implicit inventory
grant. Supplier and cost projections require their dedicated permissions.

Authorized reviewers can approve proposals, request more information, reject proposals, approve or
reject order requests, and mark approved requests Ordered with an HOURS or DAYS ETA. These actions
are audited and produce safe recipient notifications.

Receiving locks the order, validates cumulative quantity, updates stock atomically, appends an
immutable StockTransaction, updates partial/complete status, audits, and notifies the requester.
`(organization_id, request_key)` plus a request fingerprint makes retries idempotent; conflicting
key reuse fails. Deterministic integration coverage proves idempotent replay and concurrent
over-receipt protection. No supplier, price, or production inventory record is fabricated.
