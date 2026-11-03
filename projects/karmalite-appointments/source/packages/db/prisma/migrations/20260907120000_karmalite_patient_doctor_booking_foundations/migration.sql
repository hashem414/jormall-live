CREATE TYPE "HealthInformationState" AS ENUM ('NOT_PROVIDED', 'NONE_REPORTED', 'PROVIDED', 'DECLINED');

ALTER TABLE "staff_profiles"
  ADD COLUMN "is_doctor" BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN "is_active" BOOLEAN NOT NULL DEFAULT true,
  ADD COLUMN "phone" VARCHAR(80),
  ADD COLUMN "email" VARCHAR(320),
  ADD COLUMN "profession" VARCHAR(160),
  ADD COLUMN "specialty" VARCHAR(160);

ALTER TABLE "time_off" ADD COLUMN "created_by_user_id" UUID;
ALTER TABLE "time_off" ADD CONSTRAINT "time_off_created_by_user_id_fkey" FOREIGN KEY ("created_by_user_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE;

ALTER TABLE "resources"
  ADD COLUMN "capacity" INTEGER NOT NULL DEFAULT 1,
  ADD COLUMN "notes" TEXT,
  ADD CONSTRAINT "resources_capacity_positive" CHECK ("capacity" > 0);

ALTER TABLE "appointments" ADD COLUMN "room_id" UUID;
CREATE INDEX "appointments_organization_id_room_id_starts_at_idx" ON "appointments"("organization_id", "room_id", "starts_at");
ALTER TABLE "appointments" ADD CONSTRAINT "appointments_organization_id_room_id_fkey" FOREIGN KEY ("organization_id", "room_id") REFERENCES "resources"("organization_id", "id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "appointments" ADD CONSTRAINT "appointments_patient_no_overlap" EXCLUDE USING gist (
  "organization_id" WITH =,
  "customer_id" WITH =,
  tstzrange("starts_at", "ends_at", '[)') WITH &&
) WHERE ("status" IN ('PENDING', 'CONFIRMED', 'CHECKED_IN', 'IN_PROGRESS'));

CREATE TABLE "patient_health_information" (
  "id" UUID NOT NULL DEFAULT gen_random_uuid(), "organization_id" UUID NOT NULL,
  "customer_id" UUID NOT NULL, "allergy_state" "HealthInformationState" NOT NULL DEFAULT 'NOT_PROVIDED',
  "allergy_details" TEXT, "medical_condition_state" "HealthInformationState" NOT NULL DEFAULT 'NOT_PROVIDED',
  "medical_condition_details" TEXT, "updated_by_user_id" UUID NOT NULL, "consent_id" UUID,
  "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP, "updated_at" TIMESTAMPTZ(3) NOT NULL,
  CONSTRAINT "patient_health_information_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "patient_health_allergy_state_details" CHECK (("allergy_state" = 'PROVIDED' AND NULLIF(BTRIM("allergy_details"), '') IS NOT NULL) OR ("allergy_state" <> 'PROVIDED' AND "allergy_details" IS NULL)),
  CONSTRAINT "patient_health_condition_state_details" CHECK (("medical_condition_state" = 'PROVIDED' AND NULLIF(BTRIM("medical_condition_details"), '') IS NOT NULL) OR ("medical_condition_state" <> 'PROVIDED' AND "medical_condition_details" IS NULL)),
  CONSTRAINT "patient_health_consent_required" CHECK (("allergy_state" = 'NOT_PROVIDED' AND "medical_condition_state" = 'NOT_PROVIDED') OR "consent_id" IS NOT NULL)
);
CREATE UNIQUE INDEX "patient_health_information_organization_id_id_key" ON "patient_health_information"("organization_id", "id");
CREATE UNIQUE INDEX "patient_health_information_customer_id_key" ON "patient_health_information"("customer_id");
CREATE UNIQUE INDEX "patient_health_information_organization_id_customer_id_key" ON "patient_health_information"("organization_id", "customer_id");
CREATE UNIQUE INDEX "patient_health_information_organization_id_consent_id_key" ON "patient_health_information"("organization_id", "consent_id");
CREATE UNIQUE INDEX "patient_health_information_organization_id_consent_id_customer_id_key" ON "patient_health_information"("organization_id", "consent_id", "customer_id");
CREATE UNIQUE INDEX "consents_organization_id_id_customer_id_key" ON "consents"("organization_id", "id", "customer_id");

CREATE TABLE "doctor_breaks" (
  "id" UUID NOT NULL DEFAULT gen_random_uuid(), "organization_id" UUID NOT NULL,
  "staff_profile_id" UUID NOT NULL, "branch_id" UUID NOT NULL, "weekday" "Weekday" NOT NULL,
  "start_minute_local" INTEGER NOT NULL, "end_minute_local" INTEGER NOT NULL, "label" VARCHAR(160),
  "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP, "updated_at" TIMESTAMPTZ(3) NOT NULL,
  CONSTRAINT "doctor_breaks_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "doctor_breaks_valid_minutes" CHECK ("start_minute_local" >= 0 AND "end_minute_local" <= 1440 AND "end_minute_local" > "start_minute_local")
);
CREATE UNIQUE INDEX "doctor_breaks_organization_id_id_key" ON "doctor_breaks"("organization_id", "id");
CREATE INDEX "doctor_breaks_organization_id_staff_profile_id_weekday_idx" ON "doctor_breaks"("organization_id", "staff_profile_id", "weekday");

CREATE TABLE "room_service_compatibilities" (
  "organization_id" UUID NOT NULL, "resource_id" UUID NOT NULL, "service_id" UUID NOT NULL,
  "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "room_service_compatibilities_pkey" PRIMARY KEY ("organization_id", "resource_id", "service_id")
);
CREATE INDEX "room_service_compatibilities_organization_id_service_id_resource_id_idx" ON "room_service_compatibilities"("organization_id", "service_id", "resource_id");

ALTER TABLE "patient_health_information" ADD CONSTRAINT "patient_health_information_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "patient_health_information" ADD CONSTRAINT "patient_health_information_organization_id_customer_id_fkey" FOREIGN KEY ("organization_id", "customer_id") REFERENCES "customers"("organization_id", "id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "patient_health_information" ADD CONSTRAINT "patient_health_information_updated_by_user_id_fkey" FOREIGN KEY ("updated_by_user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "patient_health_information" ADD CONSTRAINT "patient_health_information_organization_id_consent_id_customer_id_fkey" FOREIGN KEY ("organization_id", "consent_id", "customer_id") REFERENCES "consents"("organization_id", "id", "customer_id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "doctor_breaks" ADD CONSTRAINT "doctor_breaks_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "doctor_breaks" ADD CONSTRAINT "doctor_breaks_organization_id_staff_profile_id_fkey" FOREIGN KEY ("organization_id", "staff_profile_id") REFERENCES "staff_profiles"("organization_id", "id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "doctor_breaks" ADD CONSTRAINT "doctor_breaks_organization_id_branch_id_fkey" FOREIGN KEY ("organization_id", "branch_id") REFERENCES "branches"("organization_id", "id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "room_service_compatibilities" ADD CONSTRAINT "room_service_compatibilities_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "room_service_compatibilities" ADD CONSTRAINT "room_service_compatibilities_organization_id_resource_id_fkey" FOREIGN KEY ("organization_id", "resource_id") REFERENCES "resources"("organization_id", "id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "room_service_compatibilities" ADD CONSTRAINT "room_service_compatibilities_organization_id_service_id_fkey" FOREIGN KEY ("organization_id", "service_id") REFERENCES "services"("organization_id", "id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "patient_health_information" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "patient_health_information" FORCE ROW LEVEL SECURITY;
CREATE POLICY "patient_health_information_tenant_isolation" ON "patient_health_information" USING ("organization_id" = NULLIF(CURRENT_SETTING('app.organization_id', true), '')::uuid) WITH CHECK ("organization_id" = NULLIF(CURRENT_SETTING('app.organization_id', true), '')::uuid);
ALTER TABLE "doctor_breaks" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "doctor_breaks" FORCE ROW LEVEL SECURITY;
CREATE POLICY "doctor_breaks_tenant_isolation" ON "doctor_breaks" USING ("organization_id" = NULLIF(CURRENT_SETTING('app.organization_id', true), '')::uuid) WITH CHECK ("organization_id" = NULLIF(CURRENT_SETTING('app.organization_id', true), '')::uuid);
ALTER TABLE "room_service_compatibilities" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "room_service_compatibilities" FORCE ROW LEVEL SECURITY;
CREATE POLICY "room_service_compatibilities_tenant_isolation" ON "room_service_compatibilities" USING ("organization_id" = NULLIF(CURRENT_SETTING('app.organization_id', true), '')::uuid) WITH CHECK ("organization_id" = NULLIF(CURRENT_SETTING('app.organization_id', true), '')::uuid);

INSERT INTO "permissions" ("id", "code", "name_en", "name_ar") SELECT gen_random_uuid(), code, name_en, name_ar FROM (VALUES
  ('patients.health.read', 'View protected health information', 'عرض المعلومات الصحية المحمية'),
  ('patients.health.write', 'Manage protected health information', 'إدارة المعلومات الصحية المحمية'),
  ('patients.directory.read', 'View patient directory', 'عرض دليل المرضى'), ('patients.profile.read', 'View patient profiles', 'عرض ملفات المرضى'),
  ('patients.contact.read', 'View patient contact information', 'عرض معلومات اتصال المريض'), ('patients.contact.write', 'Manage patient contact information', 'إدارة معلومات اتصال المريض'),
  ('patients.doctor_notes.read', 'View protected doctor notes', 'عرض ملاحظات الطبيب المحمية'), ('patients.doctor_notes.write', 'Create protected doctor notes', 'إنشاء ملاحظات الطبيب المحمية'),
  ('patients.appointments.read', 'View patient appointments', 'عرض مواعيد المريض'), ('doctors.directory.read', 'View doctor directory', 'عرض دليل الأطباء'),
  ('doctors.profile.read', 'View doctor profiles', 'عرض ملفات الأطباء'), ('doctors.profile.write', 'Manage doctor profiles', 'إدارة ملفات الأطباء'),
  ('doctors.schedule.read', 'View doctor schedules', 'عرض جداول الأطباء'), ('doctors.schedule.write', 'Manage doctor schedules', 'إدارة جداول الأطباء'),
  ('doctors.time_off.read', 'View doctor time off', 'عرض إجازات الأطباء'), ('doctors.time_off.write', 'Manage doctor time off', 'إدارة إجازات الأطباء'),
  ('doctors.services.assign', 'Assign services to doctors', 'تعيين الخدمات للأطباء'), ('doctors.permissions.manage', 'Manage doctor permissions', 'إدارة صلاحيات الأطباء'),
  ('doctors.appointments.read', 'View doctor appointments', 'عرض مواعيد الأطباء')
) AS p(code, name_en, name_ar) ON CONFLICT ("code") DO NOTHING;

WITH role_grants ("role_key", "permission_code", "scope") AS (
  VALUES
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'patients.directory.read', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'patients.profile.read', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'patients.contact.read', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'patients.contact.write', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'patients.health.read', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'patients.health.write', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'patients.doctor_notes.read', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'patients.doctor_notes.write', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'patients.appointments.read', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'doctors.directory.read', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'doctors.profile.read', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'doctors.profile.write', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'doctors.schedule.read', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'doctors.schedule.write', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'doctors.time_off.read', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'doctors.time_off.write', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'doctors.services.assign', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'doctors.permissions.manage', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_OWNER'::"TenantRoleKey", 'doctors.appointments.read', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_MANAGER'::"TenantRoleKey", 'patients.directory.read', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_MANAGER'::"TenantRoleKey", 'patients.profile.read', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_MANAGER'::"TenantRoleKey", 'patients.contact.read', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_MANAGER'::"TenantRoleKey", 'patients.contact.write', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_MANAGER'::"TenantRoleKey", 'patients.health.read', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_MANAGER'::"TenantRoleKey", 'patients.health.write', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_MANAGER'::"TenantRoleKey", 'patients.appointments.read', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_MANAGER'::"TenantRoleKey", 'doctors.directory.read', 'ORGANIZATION'::"PermissionScope"),
    ('ORGANIZATION_MANAGER'::"TenantRoleKey", 'doctors.profile.read', 'ORGANIZATION'::"PermissionScope"),
    ('SECRETARY'::"TenantRoleKey", 'patients.directory.read', 'ORGANIZATION'::"PermissionScope"),
    ('SECRETARY'::"TenantRoleKey", 'patients.profile.read', 'ORGANIZATION'::"PermissionScope"),
    ('SECRETARY'::"TenantRoleKey", 'patients.contact.read', 'ORGANIZATION'::"PermissionScope"),
    ('SECRETARY'::"TenantRoleKey", 'patients.contact.write', 'ORGANIZATION'::"PermissionScope"),
    ('SECRETARY'::"TenantRoleKey", 'patients.appointments.read', 'ORGANIZATION'::"PermissionScope"),
    ('SECRETARY'::"TenantRoleKey", 'doctors.directory.read', 'ORGANIZATION'::"PermissionScope"),
    ('SECRETARY'::"TenantRoleKey", 'doctors.profile.read', 'ORGANIZATION'::"PermissionScope"),
    ('SECRETARY'::"TenantRoleKey", 'doctors.schedule.read', 'ASSIGNED_BRANCHES'::"PermissionScope"),
    ('PROVIDER'::"TenantRoleKey", 'patients.directory.read', 'SELF'::"PermissionScope"),
    ('PROVIDER'::"TenantRoleKey", 'patients.profile.read', 'SELF'::"PermissionScope"),
    ('PROVIDER'::"TenantRoleKey", 'patients.contact.read', 'SELF'::"PermissionScope"),
    ('PROVIDER'::"TenantRoleKey", 'patients.health.read', 'SELF'::"PermissionScope"),
    ('PROVIDER'::"TenantRoleKey", 'patients.health.write', 'SELF'::"PermissionScope"),
    ('PROVIDER'::"TenantRoleKey", 'patients.doctor_notes.read', 'SELF'::"PermissionScope"),
    ('PROVIDER'::"TenantRoleKey", 'patients.doctor_notes.write', 'SELF'::"PermissionScope"),
    ('PROVIDER'::"TenantRoleKey", 'patients.appointments.read', 'SELF'::"PermissionScope"),
    ('PROVIDER'::"TenantRoleKey", 'doctors.directory.read', 'ORGANIZATION'::"PermissionScope"),
    ('PROVIDER'::"TenantRoleKey", 'doctors.profile.read', 'SELF'::"PermissionScope"),
    ('PROVIDER'::"TenantRoleKey", 'doctors.schedule.read', 'SELF'::"PermissionScope"),
    ('PROVIDER'::"TenantRoleKey", 'doctors.time_off.read', 'SELF'::"PermissionScope"),
    ('PROVIDER'::"TenantRoleKey", 'doctors.appointments.read', 'SELF'::"PermissionScope")
)
INSERT INTO "role_permissions" ("organization_id", "role_id", "permission_id", "scope")
SELECT role."organization_id", role."id", permission."id", role_grants."scope"
FROM role_grants
JOIN "roles" AS role ON role."system_key" = role_grants."role_key"
JOIN "permissions" AS permission ON permission."code" = role_grants."permission_code"
ON CONFLICT ("organization_id", "role_id", "permission_id") DO NOTHING;

GRANT SELECT, INSERT, UPDATE, DELETE ON "patient_health_information", "doctor_breaks", "room_service_compatibilities" TO jormall_app;
