# Karmalite service and room compatibility

Services retain bilingual name and description, category, duration, active/configuration status,
online-bookable setting, minimum notice, preparation instructions, and aftercare instructions. Price
remains technically nullable. Karmalite's seeded services have no approved dated price and therefore
display the configured contact-for-current-price message rather than an estimate.

Rooms reuse the existing tenant resource model with `ROOM` groups. Each room has bilingual names,
capacity metadata, notes, status, branch ownership, and an explicit allowlist of compatible
services. Only active compatible rooms appear during booking. A room compatibility entry is also
connected to the service's branch resource requirement so final allocation remains transactional.

Changing compatibility reports future affected appointments and requires confirmation before a
service is removed. The change does not rewrite historical appointment records. Room, service, and
branch identifiers are revalidated within the active tenant at the repository boundary.

Phase 1 treats a selected treatment room as exclusively reserved for one appointment even when its
capacity metadata is greater than one. Multi-seat occupancy policy is not inferred from capacity.
