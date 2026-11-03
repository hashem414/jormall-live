-- Managers may create tenant-scoped custom roles. Application-level checks ensure
-- they can grant only permissions already present in their own access snapshot.
INSERT INTO "role_permissions" ("organization_id", "role_id", "permission_id", "scope")
SELECT role."organization_id", role."id", permission."id", 'ORGANIZATION'::"PermissionScope"
FROM "roles" AS role
JOIN "permissions" AS permission ON permission."code" = 'roles.manage'
WHERE role."system_key" = 'ORGANIZATION_MANAGER'::"TenantRoleKey"
ON CONFLICT ("organization_id", "role_id", "permission_id")
DO UPDATE SET "scope" = EXCLUDED."scope";
