ALTER TYPE "AppointmentStatus" ADD VALUE IF NOT EXISTS 'CALLED' AFTER 'CHECKED_IN';
ALTER TYPE "AppointmentHistoryType" ADD VALUE IF NOT EXISTS 'ROOM_CHANGED';
ALTER TYPE "AppointmentHistoryType" ADD VALUE IF NOT EXISTS 'DOCTOR_CHANGED';
CREATE TYPE "AppointmentTransitionSource" AS ENUM ('STAFF_UI', 'SYSTEM', 'ACTION_GATEWAY', 'IMPORT', 'API');

ALTER TABLE "appointment_status_history"
  ADD COLUMN "transition_source" "AppointmentTransitionSource" NOT NULL DEFAULT 'SYSTEM';
ALTER TABLE "appointment_status_history"
  ALTER COLUMN "transition_source" SET DEFAULT 'STAFF_UI';

ALTER TABLE "appointments"
  ADD COLUMN "actual_provider_id" UUID,
  ADD COLUMN "actual_room_id" UUID,
  ADD COLUMN "confirmed_by_user_id" UUID,
  ADD COLUMN "checked_in_by_user_id" UUID,
  ADD COLUMN "called_at" TIMESTAMPTZ(3),
  ADD COLUMN "called_by_user_id" UUID,
  ADD COLUMN "service_started_by_user_id" UUID,
  ADD COLUMN "completed_by_user_id" UUID,
  ADD COLUMN "actual_duration_mins" INTEGER,
  ADD COLUMN "cancelled_by_user_id" UUID,
  ADD COLUMN "no_show_by_user_id" UUID,
  ADD CONSTRAINT "appointments_actual_duration_nonnegative" CHECK ("actual_duration_mins" IS NULL OR "actual_duration_mins" >= 0),
  ADD CONSTRAINT "appointments_organization_id_actual_provider_id_fkey" FOREIGN KEY ("organization_id", "actual_provider_id") REFERENCES "staff_profiles"("organization_id", "id") ON DELETE RESTRICT ON UPDATE CASCADE,
  ADD CONSTRAINT "appointments_organization_id_actual_room_id_fkey" FOREIGN KEY ("organization_id", "actual_room_id") REFERENCES "resources"("organization_id", "id") ON DELETE RESTRICT ON UPDATE CASCADE,
  ADD CONSTRAINT "appointments_confirmed_by_user_id_fkey" FOREIGN KEY ("confirmed_by_user_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE,
  ADD CONSTRAINT "appointments_checked_in_by_user_id_fkey" FOREIGN KEY ("checked_in_by_user_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE,
  ADD CONSTRAINT "appointments_called_by_user_id_fkey" FOREIGN KEY ("called_by_user_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE,
  ADD CONSTRAINT "appointments_service_started_by_user_id_fkey" FOREIGN KEY ("service_started_by_user_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE,
  ADD CONSTRAINT "appointments_completed_by_user_id_fkey" FOREIGN KEY ("completed_by_user_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE,
  ADD CONSTRAINT "appointments_cancelled_by_user_id_fkey" FOREIGN KEY ("cancelled_by_user_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE,
  ADD CONSTRAINT "appointments_no_show_by_user_id_fkey" FOREIGN KEY ("no_show_by_user_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE;

CREATE INDEX "appointments_organization_id_actual_room_id_status_idx" ON "appointments"("organization_id", "actual_room_id", "status");

CREATE TABLE "room_occupancies" (
  "id" UUID NOT NULL DEFAULT gen_random_uuid(),
  "organization_id" UUID NOT NULL,
  "resource_id" UUID NOT NULL,
  "appointment_id" UUID NOT NULL,
  "slot" INTEGER NOT NULL,
  "claimed_by_user_id" UUID NOT NULL,
  "claimed_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "released_by_user_id" UUID,
  "released_at" TIMESTAMPTZ(3),
  "release_reason" VARCHAR(120),
  CONSTRAINT "room_occupancies_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "room_occupancies_slot_positive" CHECK ("slot" > 0),
  CONSTRAINT "room_occupancies_release_complete" CHECK (
    ("released_at" IS NULL AND "released_by_user_id" IS NULL AND "release_reason" IS NULL)
    OR ("released_at" IS NOT NULL AND "released_by_user_id" IS NOT NULL AND NULLIF(BTRIM("release_reason"), '') IS NOT NULL)
  ),
  CONSTRAINT "room_occupancies_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "room_occupancies_organization_id_resource_id_fkey" FOREIGN KEY ("organization_id", "resource_id") REFERENCES "resources"("organization_id", "id") ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "room_occupancies_organization_id_appointment_id_fkey" FOREIGN KEY ("organization_id", "appointment_id") REFERENCES "appointments"("organization_id", "id") ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "room_occupancies_claimed_by_user_id_fkey" FOREIGN KEY ("claimed_by_user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "room_occupancies_released_by_user_id_fkey" FOREIGN KEY ("released_by_user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE UNIQUE INDEX "room_occupancies_organization_id_id_key" ON "room_occupancies"("organization_id", "id");
CREATE INDEX "room_occupancies_organization_id_resource_id_released_at_idx" ON "room_occupancies"("organization_id", "resource_id", "released_at");
CREATE INDEX "room_occupancies_organization_id_appointment_id_released_at_idx" ON "room_occupancies"("organization_id", "appointment_id", "released_at");
CREATE UNIQUE INDEX "room_occupancies_active_room_slot_key" ON "room_occupancies"("organization_id", "resource_id", "slot") WHERE "released_at" IS NULL;
CREATE UNIQUE INDEX "room_occupancies_active_appointment_key" ON "room_occupancies"("organization_id", "appointment_id") WHERE "released_at" IS NULL;

CREATE FUNCTION "enforce_room_occupancy_capacity"() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  room_capacity INTEGER;
  room_status "ResourceStatus";
  room_kind "ResourceKind";
BEGIN
  IF NEW."released_at" IS NOT NULL THEN
    RETURN NEW;
  END IF;
  SELECT resource."capacity", resource."status", resource_group."kind"
  INTO room_capacity, room_status, room_kind
  FROM "resources" AS resource
  JOIN "resource_groups" AS resource_group
    ON resource_group."organization_id" = resource."organization_id"
   AND resource_group."id" = resource."group_id"
  WHERE resource."organization_id" = NEW."organization_id"
    AND resource."id" = NEW."resource_id";
  IF room_capacity IS NULL OR room_kind <> 'ROOM' OR room_status <> 'ACTIVE' OR NEW."slot" > room_capacity THEN
    RAISE EXCEPTION 'ROOM_OCCUPANCY_INVALID' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER "room_occupancies_capacity_guard"
BEFORE INSERT OR UPDATE OF "resource_id", "slot", "released_at" ON "room_occupancies"
FOR EACH ROW EXECUTE FUNCTION "enforce_room_occupancy_capacity"();

ALTER TABLE "room_occupancies" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "room_occupancies" FORCE ROW LEVEL SECURITY;
CREATE POLICY "room_occupancies_tenant_isolation" ON "room_occupancies"
  USING ("organization_id" = NULLIF(CURRENT_SETTING('app.organization_id', true), '')::uuid)
  WITH CHECK ("organization_id" = NULLIF(CURRENT_SETTING('app.organization_id', true), '')::uuid);
GRANT SELECT, INSERT, UPDATE, DELETE ON "room_occupancies" TO jormall_app;

INSERT INTO "permissions" ("id", "code", "name_en", "name_ar")
SELECT gen_random_uuid(), code, name_en, name_ar FROM (VALUES
  ('appointment.confirm', 'Confirm appointments', 'تأكيد المواعيد'),
  ('appointment.bulkConfirm', 'Bulk confirm appointments', 'تأكيد المواعيد المحددة'),
  ('appointment.checkIn', 'Check in patients', 'تسجيل وصول المرضى'),
  ('appointment.callToRoom', 'Call patients to rooms', 'استدعاء المرضى إلى الغرف'),
  ('appointment.startService', 'Start appointment services', 'بدء خدمات المواعيد'),
  ('appointment.complete', 'Complete appointment services', 'إتمام خدمات المواعيد'),
  ('appointment.reschedule', 'Reschedule appointments', 'إعادة جدولة المواعيد'),
  ('appointment.cancel', 'Cancel appointments', 'إلغاء المواعيد'),
  ('appointment.noShow', 'Mark appointment no-shows', 'تسجيل عدم حضور المواعيد'),
  ('room.occupancy.claim', 'Claim operational room capacity', 'حجز سعة الغرفة التشغيلية'),
  ('room.occupancy.release', 'Release operational room capacity', 'تحرير سعة الغرفة التشغيلية'),
  ('room.assignment.change', 'Change active room assignments', 'تغيير تعيينات الغرف النشطة'),
  ('doctor.queue.next', 'Call the next Doctor appointment', 'استدعاء موعد الطبيب التالي')
) AS permission_values(code, name_en, name_ar)
ON CONFLICT ("code") DO NOTHING;

WITH role_grants ("role_key", "permission_code", "scope") AS (
  VALUES
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'appointment.confirm', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'appointment.bulkConfirm', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'appointment.checkIn', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'appointment.callToRoom', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'appointment.startService', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'appointment.complete', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'appointment.reschedule', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'appointment.cancel', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'appointment.noShow', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'room.occupancy.claim', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'room.occupancy.release', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'room.assignment.change', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'doctor.queue.next', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_MANAGER'::"TenantRoleKey", 'appointment.confirm', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_MANAGER'::"TenantRoleKey", 'appointment.bulkConfirm', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_MANAGER'::"TenantRoleKey", 'appointment.checkIn', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_MANAGER'::"TenantRoleKey", 'appointment.callToRoom', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_MANAGER'::"TenantRoleKey", 'appointment.startService', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_MANAGER'::"TenantRoleKey", 'appointment.complete', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_MANAGER'::"TenantRoleKey", 'appointment.reschedule', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_MANAGER'::"TenantRoleKey", 'appointment.cancel', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_MANAGER'::"TenantRoleKey", 'appointment.noShow', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_MANAGER'::"TenantRoleKey", 'room.occupancy.claim', 'ASSIGNED_BRANCHES'::"PermissionScope"),
    ('ORGANIZATION_MANAGER'::"TenantRoleKey", 'room.occupancy.release', 'ASSIGNED_BRANCHES'::"PermissionScope"),
    ('ORGANIZATION_MANAGER'::"TenantRoleKey", 'room.assignment.change', 'ASSIGNED_BRANCHES'::"PermissionScope"),
    ('ORGANIZATION_MANAGER'::"TenantRoleKey", 'doctor.queue.next', 'ASSIGNED_BRANCHES'::"PermissionScope"),
    ('SECRETARY'::"TenantRoleKey", 'appointment.confirm', 'ORGANIZATION'::"PermissionScope"),
    ('SECRETARY'::"TenantRoleKey", 'appointment.bulkConfirm', 'ORGANIZATION'::"PermissionScope"),
    ('SECRETARY'::"TenantRoleKey", 'appointment.checkIn', 'ORGANIZATION'::"PermissionScope"),
    ('SECRETARY'::"TenantRoleKey", 'appointment.callToRoom', 'ORGANIZATION'::"PermissionScope"),
    ('SECRETARY'::"TenantRoleKey", 'appointment.startService', 'ORGANIZATION'::"PermissionScope"),
    ('SECRETARY'::"TenantRoleKey", 'appointment.complete', 'ORGANIZATION'::"PermissionScope"),
    ('SECRETARY'::"TenantRoleKey", 'appointment.reschedule', 'ORGANIZATION'::"PermissionScope"),
    ('SECRETARY'::"TenantRoleKey", 'appointment.cancel', 'ORGANIZATION'::"PermissionScope"),
    ('SECRETARY'::"TenantRoleKey", 'appointment.noShow', 'ORGANIZATION'::"PermissionScope"),
    ('SECRETARY'::"TenantRoleKey", 'room.occupancy.claim', 'ASSIGNED_BRANCHES'::"PermissionScope"),
    ('SECRETARY'::"TenantRoleKey", 'room.occupancy.release', 'ASSIGNED_BRANCHES'::"PermissionScope"),
    ('SECRETARY'::"TenantRoleKey", 'room.assignment.change', 'ASSIGNED_BRANCHES'::"PermissionScope"),
    ('SECRETARY'::"TenantRoleKey", 'doctor.queue.next', 'ASSIGNED_BRANCHES'::"PermissionScope"),
    ('PROVIDER'::"TenantRoleKey", 'appointment.confirm', 'SELF'::"PermissionScope"),
    ('PROVIDER'::"TenantRoleKey", 'appointment.checkIn', 'SELF'::"PermissionScope"),
    ('PROVIDER'::"TenantRoleKey", 'appointment.callToRoom', 'SELF'::"PermissionScope"),
    ('PROVIDER'::"TenantRoleKey", 'appointment.startService', 'SELF'::"PermissionScope"),
    ('PROVIDER'::"TenantRoleKey", 'appointment.complete', 'SELF'::"PermissionScope"),
    ('PROVIDER'::"TenantRoleKey", 'appointment.reschedule', 'SELF'::"PermissionScope"),
    ('PROVIDER'::"TenantRoleKey", 'appointment.cancel', 'SELF'::"PermissionScope"),
    ('PROVIDER'::"TenantRoleKey", 'appointment.noShow', 'SELF'::"PermissionScope"),
    ('PROVIDER'::"TenantRoleKey", 'room.occupancy.claim', 'ASSIGNED_BRANCHES'::"PermissionScope"),
    ('PROVIDER'::"TenantRoleKey", 'room.occupancy.release', 'ASSIGNED_BRANCHES'::"PermissionScope"),
    ('PROVIDER'::"TenantRoleKey", 'room.assignment.change', 'ASSIGNED_BRANCHES'::"PermissionScope"),
    ('PROVIDER'::"TenantRoleKey", 'doctor.queue.next', 'SELF'::"PermissionScope")
)
INSERT INTO "role_permissions" ("organization_id", "role_id", "permission_id", "scope")
SELECT role."organization_id", role."id", permission."id", role_grants."scope"
FROM role_grants
JOIN "roles" AS role ON role."system_key" = role_grants."role_key"
JOIN "permissions" AS permission ON permission."code" = role_grants."permission_code"
ON CONFLICT ("organization_id", "role_id", "permission_id") DO NOTHING;
