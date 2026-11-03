DO $$ BEGIN
  CREATE TYPE "ConversationPriority" AS ENUM ('LOW', 'NORMAL', 'HIGH', 'URGENT');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
  CREATE TYPE "ProviderIntegrationMode" AS ENUM ('MOCK', 'DEVELOPMENT', 'TEST', 'PRODUCTION');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

ALTER TABLE "organization_settings"
  ADD COLUMN IF NOT EXISTS "cancellation_window_mins" INTEGER NOT NULL DEFAULT 1440,
  ADD COLUMN IF NOT EXISTS "reschedule_window_mins" INTEGER NOT NULL DEFAULT 720,
  ADD COLUMN IF NOT EXISTS "default_appointment_status" "AppointmentStatus" NOT NULL DEFAULT 'PENDING',
  ADD COLUMN IF NOT EXISTS "confirmation_enabled" BOOLEAN NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS "reminder_lead_mins" INTEGER NOT NULL DEFAULT 1440,
  ADD COLUMN IF NOT EXISTS "no_show_policy_en" TEXT,
  ADD COLUMN IF NOT EXISTS "no_show_policy_ar" TEXT;
DO $$ BEGIN
  ALTER TABLE "organization_settings" ADD CONSTRAINT "organization_settings_booking_windows_nonnegative"
    CHECK ("cancellation_window_mins" >= 0 AND "reschedule_window_mins" >= 0 AND "reminder_lead_mins" >= 0);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

ALTER TABLE "branches"
  ADD COLUMN IF NOT EXISTS "email" VARCHAR(320),
  ADD COLUMN IF NOT EXISTS "map_url" VARCHAR(2048);

ALTER TABLE "services"
  ADD COLUMN IF NOT EXISTS "category" VARCHAR(120),
  ADD COLUMN IF NOT EXISTS "is_online_bookable" BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS "minimum_notice_mins" INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS "pre_treatment_instructions_en" TEXT,
  ADD COLUMN IF NOT EXISTS "pre_treatment_instructions_ar" TEXT,
  ADD COLUMN IF NOT EXISTS "post_treatment_instructions_en" TEXT,
  ADD COLUMN IF NOT EXISTS "post_treatment_instructions_ar" TEXT;
DO $$ BEGIN
  ALTER TABLE "services" ADD CONSTRAINT "services_minimum_notice_nonnegative"
    CHECK ("minimum_notice_mins" >= 0);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

ALTER TABLE "customers"
  ADD COLUMN IF NOT EXISTS "preferred_branch_id" UUID,
  ADD COLUMN IF NOT EXISTS "reference_code" VARCHAR(20),
  ADD COLUMN IF NOT EXISTS "tags" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[];
UPDATE "customers"
SET "reference_code" = 'CUS-' || upper(substr(replace("id"::text, '-', ''), 1, 8))
WHERE "reference_code" IS NULL;
ALTER TABLE "customers"
  ALTER COLUMN "reference_code" SET NOT NULL,
  ALTER COLUMN "reference_code" SET DEFAULT ('CUS-' || upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 8)));
DO $$ BEGIN
  ALTER TABLE "customers" ADD CONSTRAINT "customers_preferred_branch_id_fkey"
    FOREIGN KEY ("organization_id", "preferred_branch_id") REFERENCES "branches"("organization_id", "id") ON DELETE RESTRICT ON UPDATE CASCADE;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS "customers_organization_id_reference_code_key" ON "customers"("organization_id", "reference_code");
CREATE INDEX IF NOT EXISTS "customers_organization_id_preferred_branch_id_idx" ON "customers"("organization_id", "preferred_branch_id");

ALTER TABLE "appointments"
  ADD COLUMN IF NOT EXISTS "reference_code" VARCHAR(20),
  ADD COLUMN IF NOT EXISTS "created_by_user_id" UUID;
UPDATE "appointments"
SET "reference_code" = 'APT-' || upper(substr(replace("id"::text, '-', ''), 1, 8))
WHERE "reference_code" IS NULL;
ALTER TABLE "appointments"
  ALTER COLUMN "reference_code" SET NOT NULL,
  ALTER COLUMN "reference_code" SET DEFAULT ('APT-' || upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 8)));
DO $$ BEGIN
  ALTER TABLE "appointments" ADD CONSTRAINT "appointments_created_by_user_id_fkey"
    FOREIGN KEY ("created_by_user_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS "appointments_organization_id_reference_code_key" ON "appointments"("organization_id", "reference_code");
CREATE INDEX IF NOT EXISTS "appointments_organization_id_service_id_starts_at_idx" ON "appointments"("organization_id", "service_id", "starts_at");
CREATE INDEX IF NOT EXISTS "appointments_organization_id_status_starts_at_idx" ON "appointments"("organization_id", "status", "starts_at");

ALTER TABLE "conversations"
  ADD COLUMN IF NOT EXISTS "priority" "ConversationPriority" NOT NULL DEFAULT 'NORMAL',
  ADD COLUMN IF NOT EXISTS "assigned_membership_id" UUID;
DO $$ BEGIN
  ALTER TABLE "conversations" ADD CONSTRAINT "conversations_assigned_membership_id_fkey"
    FOREIGN KEY ("organization_id", "assigned_membership_id") REFERENCES "organization_memberships"("organization_id", "id") ON DELETE RESTRICT ON UPDATE CASCADE;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
CREATE INDEX IF NOT EXISTS "conversations_assignee_status_message_idx"
  ON "conversations"("organization_id", "assigned_membership_id", "status", "last_message_at");

ALTER TABLE "provider_connections"
  ADD COLUMN IF NOT EXISTS "integration_mode" "ProviderIntegrationMode" NOT NULL DEFAULT 'MOCK';

CREATE TABLE IF NOT EXISTS "customer_notes" (
  "id" UUID NOT NULL DEFAULT gen_random_uuid(),
  "organization_id" UUID NOT NULL,
  "customer_id" UUID NOT NULL,
  "author_user_id" UUID NOT NULL,
  "body" TEXT NOT NULL,
  "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "customer_notes_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "customer_notes_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "customer_notes_customer_id_fkey" FOREIGN KEY ("organization_id", "customer_id") REFERENCES "customers"("organization_id", "id") ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "customer_notes_author_user_id_fkey" FOREIGN KEY ("author_user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS "customer_notes_organization_id_id_key" ON "customer_notes"("organization_id", "id");
CREATE INDEX IF NOT EXISTS "customer_notes_customer_created_idx" ON "customer_notes"("organization_id", "customer_id", "created_at");

CREATE TABLE IF NOT EXISTS "conversation_read_states" (
  "organization_id" UUID NOT NULL,
  "conversation_id" UUID NOT NULL,
  "membership_id" UUID NOT NULL,
  "last_read_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "conversation_read_states_pkey" PRIMARY KEY ("organization_id", "conversation_id", "membership_id"),
  CONSTRAINT "conversation_read_states_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "conversation_read_states_conversation_id_fkey" FOREIGN KEY ("organization_id", "conversation_id") REFERENCES "conversations"("organization_id", "id") ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "conversation_read_states_membership_id_fkey" FOREIGN KEY ("organization_id", "membership_id") REFERENCES "organization_memberships"("organization_id", "id") ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE INDEX IF NOT EXISTS "conversation_read_states_membership_read_idx" ON "conversation_read_states"("organization_id", "membership_id", "last_read_at");

CREATE TABLE IF NOT EXISTS "resource_maintenance_history" (
  "id" UUID NOT NULL DEFAULT gen_random_uuid(),
  "organization_id" UUID NOT NULL,
  "resource_id" UUID NOT NULL,
  "actor_user_id" UUID NOT NULL,
  "from_status" "ResourceStatus" NOT NULL,
  "to_status" "ResourceStatus" NOT NULL,
  "reason" VARCHAR(500) NOT NULL,
  "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "resource_maintenance_history_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "resource_maintenance_history_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "resource_maintenance_history_resource_id_fkey" FOREIGN KEY ("organization_id", "resource_id") REFERENCES "resources"("organization_id", "id") ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "resource_maintenance_history_actor_user_id_fkey" FOREIGN KEY ("actor_user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS "resource_maintenance_history_organization_id_id_key" ON "resource_maintenance_history"("organization_id", "id");
CREATE INDEX IF NOT EXISTS "resource_maintenance_history_resource_created_idx" ON "resource_maintenance_history"("organization_id", "resource_id", "created_at");

GRANT SELECT, INSERT ON "customer_notes", "resource_maintenance_history" TO jormall_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON "conversation_read_states" TO jormall_app;

ALTER TABLE "customer_notes" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "customer_notes" FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "customer_notes_tenant_isolation" ON "customer_notes";
CREATE POLICY "customer_notes_tenant_isolation" ON "customer_notes"
  USING ("organization_id" = NULLIF(CURRENT_SETTING('app.organization_id', true), '')::uuid)
  WITH CHECK ("organization_id" = NULLIF(CURRENT_SETTING('app.organization_id', true), '')::uuid);
ALTER TABLE "conversation_read_states" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "conversation_read_states" FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "conversation_read_states_tenant_isolation" ON "conversation_read_states";
CREATE POLICY "conversation_read_states_tenant_isolation" ON "conversation_read_states"
  USING ("organization_id" = NULLIF(CURRENT_SETTING('app.organization_id', true), '')::uuid)
  WITH CHECK ("organization_id" = NULLIF(CURRENT_SETTING('app.organization_id', true), '')::uuid);
ALTER TABLE "resource_maintenance_history" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "resource_maintenance_history" FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "resource_maintenance_history_tenant_isolation" ON "resource_maintenance_history";
CREATE POLICY "resource_maintenance_history_tenant_isolation" ON "resource_maintenance_history"
  USING ("organization_id" = NULLIF(CURRENT_SETTING('app.organization_id', true), '')::uuid)
  WITH CHECK ("organization_id" = NULLIF(CURRENT_SETTING('app.organization_id', true), '')::uuid);

CREATE OR REPLACE FUNCTION prevent_workspace_history_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
END;
$$;
DROP TRIGGER IF EXISTS "customer_notes_immutable" ON "customer_notes";
CREATE TRIGGER "customer_notes_immutable" BEFORE UPDATE OR DELETE ON "customer_notes"
FOR EACH ROW EXECUTE FUNCTION prevent_workspace_history_mutation();
DROP TRIGGER IF EXISTS "resource_maintenance_history_immutable" ON "resource_maintenance_history";
CREATE TRIGGER "resource_maintenance_history_immutable" BEFORE UPDATE OR DELETE ON "resource_maintenance_history"
FOR EACH ROW EXECUTE FUNCTION prevent_workspace_history_mutation();
