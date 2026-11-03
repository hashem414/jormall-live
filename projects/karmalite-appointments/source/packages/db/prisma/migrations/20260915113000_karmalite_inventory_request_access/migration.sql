-- Give existing Karmalite Manager and Secretary system roles least-privilege
-- access to view branch inventory and submit item/order requests. Approval,
-- receiving, supplier cost, transfer, and adjustment permissions remain unchanged.
WITH request_grants(code, scope) AS (
  VALUES
    ('inventory.items.read', 'ASSIGNED_BRANCHES'::"PermissionScope"),
    ('inventory.itemProposal.create', 'ASSIGNED_BRANCHES'::"PermissionScope"),
    ('inventory.orderRequest.create', 'ASSIGNED_BRANCHES'::"PermissionScope")
)
INSERT INTO "role_permissions" ("organization_id", "role_id", "permission_id", "scope")
SELECT role."organization_id", role."id", permission."id", request_grants.scope
FROM request_grants
JOIN "permissions" permission ON permission."code" = request_grants.code
JOIN "roles" role ON role."system_key" IN ('ORGANIZATION_MANAGER', 'SECRETARY')
JOIN "organizations" organization
  ON organization."id" = role."organization_id"
 AND organization."slug" = 'karmalite-medical-esthetic'
ON CONFLICT ("organization_id", "role_id", "permission_id")
DO UPDATE SET "scope" = EXCLUDED."scope";
