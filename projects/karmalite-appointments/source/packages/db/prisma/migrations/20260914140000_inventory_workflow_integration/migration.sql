-- Additive migration for Inventory module integrated with appointment workflow
ALTER TYPE "InventoryCategory" ADD VALUE IF NOT EXISTS 'SKINCARE_PRODUCT';
ALTER TYPE "InventoryCategory" ADD VALUE IF NOT EXISTS 'CLEANING_MATERIAL';
ALTER TYPE "InventoryCategory" ADD VALUE IF NOT EXISTS 'RETAIL_PRODUCT';

CREATE TYPE "InventoryReservationMode" AS ENUM ('NONE', 'FORECAST_ONLY', 'RESERVE_ON_CONFIRMATION');

CREATE TYPE "StockMovementType" AS ENUM (
  'PURCHASE_RECEIPT',
  'APPOINTMENT_CONSUMPTION',
  'TRANSFER_IN',
  'TRANSFER_OUT',
  'EXPIRED',
  'DAMAGED',
  'LOST',
  'SPILLED',
  'RETURN_TO_SUPPLIER',
  'MANUAL_CORRECTION',
  'RESERVATION',
  'RESERVATION_RELEASE'
);

CREATE TABLE "suppliers" (
  "id" UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  "organization_id" UUID NOT NULL,
  "name" VARCHAR(160) NOT NULL,
  "phone" VARCHAR(40) NOT NULL,
  "email" VARCHAR(160),
  "notes" TEXT,
  "is_active" BOOLEAN NOT NULL DEFAULT TRUE,
  "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" TIMESTAMPTZ(3) NOT NULL,
  FOREIGN KEY ("organization_id") REFERENCES "organizations"("id") ON DELETE CASCADE
);
CREATE UNIQUE INDEX "suppliers_org_id_key" ON "suppliers"("organization_id", "id");
CREATE UNIQUE INDEX "suppliers_org_name_key" ON "suppliers"("organization_id", "name");

ALTER TABLE "inventory_items"
  ADD COLUMN IF NOT EXISTS "sku" VARCHAR(60),
  ADD COLUMN IF NOT EXISTS "reorder_quantity" DECIMAL(14,3) NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS "reserved_quantity" DECIMAL(14,3) NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS "batch_tracking_enabled" BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS "expiry_tracking_enabled" BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS "default_supplier_id" UUID;

ALTER TABLE "inventory_items"
  ADD CONSTRAINT "inventory_items_reorder_qty_check" CHECK ("reorder_quantity" >= 0),
  ADD CONSTRAINT "inventory_items_reserved_qty_check" CHECK ("reserved_quantity" >= 0),
  ADD CONSTRAINT "inventory_items_default_supplier_fkey" FOREIGN KEY ("organization_id", "default_supplier_id") REFERENCES "suppliers"("organization_id", "id") ON DELETE RESTRICT;

CREATE TABLE "inventory_locations" (
  "id" UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  "organization_id" UUID NOT NULL,
  "branch_id" UUID NOT NULL,
  "name" VARCHAR(120) NOT NULL,
  "description" TEXT,
  "is_default" BOOLEAN NOT NULL DEFAULT FALSE,
  "is_active" BOOLEAN NOT NULL DEFAULT TRUE,
  "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" TIMESTAMPTZ(3) NOT NULL,
  FOREIGN KEY ("organization_id") REFERENCES "organizations"("id") ON DELETE CASCADE,
  FOREIGN KEY ("organization_id", "branch_id") REFERENCES "branches"("organization_id", "id") ON DELETE RESTRICT
);
CREATE UNIQUE INDEX "inventory_locations_org_id_key" ON "inventory_locations"("organization_id", "id");
CREATE UNIQUE INDEX "inventory_locations_branch_name_key" ON "inventory_locations"("organization_id", "branch_id", "name");

-- Preserve existing branch inventory by giving every branch an explicit default location.
INSERT INTO "inventory_locations" (
  "id", "organization_id", "branch_id", "name", "description", "is_default", "is_active", "created_at", "updated_at"
)
SELECT
  gen_random_uuid(), b."organization_id", b."id", 'Main Store',
  'Default inventory location', TRUE, TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM "branches" b
ON CONFLICT ("organization_id", "branch_id", "name") DO NOTHING;

CREATE TABLE "item_location_stocks" (
  "id" UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  "organization_id" UUID NOT NULL,
  "branch_id" UUID NOT NULL,
  "item_id" UUID NOT NULL,
  "location_id" UUID NOT NULL,
  "quantity" DECIMAL(14,3) NOT NULL DEFAULT 0,
  "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" TIMESTAMPTZ(3) NOT NULL,
  CHECK ("quantity" >= 0),
  FOREIGN KEY ("organization_id") REFERENCES "organizations"("id") ON DELETE CASCADE,
  FOREIGN KEY ("organization_id", "branch_id") REFERENCES "branches"("organization_id", "id") ON DELETE RESTRICT,
  FOREIGN KEY ("organization_id", "item_id") REFERENCES "inventory_items"("organization_id", "id") ON DELETE RESTRICT,
  FOREIGN KEY ("organization_id", "location_id") REFERENCES "inventory_locations"("organization_id", "id") ON DELETE RESTRICT
);
CREATE UNIQUE INDEX "item_location_stocks_org_id_key" ON "item_location_stocks"("organization_id", "id");
CREATE UNIQUE INDEX "item_location_stocks_item_loc_key" ON "item_location_stocks"("organization_id", "item_id", "location_id");

-- Move the legacy item balance into the branch default location without changing totals.
INSERT INTO "item_location_stocks" (
  "id", "organization_id", "branch_id", "item_id", "location_id", "quantity", "created_at", "updated_at"
)
SELECT
  gen_random_uuid(), item."organization_id", item."branch_id", item."id", location."id",
  GREATEST(item."current_stock", 0), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM "inventory_items" item
JOIN "inventory_locations" location
  ON location."organization_id" = item."organization_id"
 AND location."branch_id" = item."branch_id"
 AND location."is_default" = TRUE
ON CONFLICT ("organization_id", "item_id", "location_id") DO NOTHING;

CREATE TABLE "inventory_batches" (
  "id" UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  "organization_id" UUID NOT NULL,
  "branch_id" UUID NOT NULL,
  "item_id" UUID NOT NULL,
  "location_id" UUID NOT NULL,
  "batch_number" VARCHAR(80) NOT NULL,
  "quantity" DECIMAL(14,3) NOT NULL DEFAULT 0,
  "purchase_cost" DECIMAL(14,3),
  "expiry_date" DATE,
  "received_date" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "is_active" BOOLEAN NOT NULL DEFAULT TRUE,
  "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" TIMESTAMPTZ(3) NOT NULL,
  CHECK ("quantity" >= 0),
  FOREIGN KEY ("organization_id") REFERENCES "organizations"("id") ON DELETE CASCADE,
  FOREIGN KEY ("organization_id", "branch_id") REFERENCES "branches"("organization_id", "id") ON DELETE RESTRICT,
  FOREIGN KEY ("organization_id", "item_id") REFERENCES "inventory_items"("organization_id", "id") ON DELETE RESTRICT,
  FOREIGN KEY ("organization_id", "location_id") REFERENCES "inventory_locations"("organization_id", "id") ON DELETE RESTRICT
);
CREATE UNIQUE INDEX "inventory_batches_org_id_key" ON "inventory_batches"("organization_id", "id");
CREATE UNIQUE INDEX "inventory_batches_batch_num_key" ON "inventory_batches"("organization_id", "item_id", "location_id", "batch_number");
CREATE INDEX "inventory_batches_expiry_idx" ON "inventory_batches"("organization_id", "item_id", "expiry_date", "quantity");

CREATE TABLE "inventory_stock_movements" (
  "id" UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  "organization_id" UUID NOT NULL,
  "branch_id" UUID NOT NULL,
  "item_id" UUID NOT NULL,
  "batch_id" UUID,
  "location_id" UUID,
  "to_location_id" UUID,
  "order_request_id" UUID,
  "appointment_id" UUID,
  "type" "StockMovementType" NOT NULL,
  "quantity" DECIMAL(14,3) NOT NULL,
  "balance_before" DECIMAL(14,3) NOT NULL,
  "balance_after" DECIMAL(14,3) NOT NULL,
  "reason" TEXT,
  "request_key" VARCHAR(120),
  "actor_user_id" UUID NOT NULL REFERENCES "users"("id") ON DELETE RESTRICT,
  "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY ("organization_id") REFERENCES "organizations"("id") ON DELETE CASCADE,
  FOREIGN KEY ("organization_id", "branch_id") REFERENCES "branches"("organization_id", "id") ON DELETE RESTRICT,
  FOREIGN KEY ("organization_id", "item_id") REFERENCES "inventory_items"("organization_id", "id") ON DELETE RESTRICT,
  FOREIGN KEY ("organization_id", "batch_id") REFERENCES "inventory_batches"("organization_id", "id") ON DELETE RESTRICT,
  FOREIGN KEY ("organization_id", "location_id") REFERENCES "inventory_locations"("organization_id", "id") ON DELETE RESTRICT,
  FOREIGN KEY ("organization_id", "to_location_id") REFERENCES "inventory_locations"("organization_id", "id") ON DELETE RESTRICT,
  FOREIGN KEY ("organization_id", "order_request_id") REFERENCES "inventory_order_requests"("organization_id", "id") ON DELETE RESTRICT,
  FOREIGN KEY ("organization_id", "appointment_id") REFERENCES "appointments"("organization_id", "id") ON DELETE RESTRICT
);
CREATE UNIQUE INDEX "inventory_stock_movements_org_id_key" ON "inventory_stock_movements"("organization_id", "id");
CREATE INDEX "inventory_stock_movements_item_idx" ON "inventory_stock_movements"("organization_id", "item_id", "created_at");
CREATE INDEX "inventory_stock_movements_apt_idx" ON "inventory_stock_movements"("organization_id", "appointment_id");
CREATE INDEX "inventory_stock_movements_key_idx" ON "inventory_stock_movements"("organization_id", "request_key");
CREATE UNIQUE INDEX "inventory_stock_movements_request_key_unique"
  ON "inventory_stock_movements"("organization_id", "request_key")
  WHERE "request_key" IS NOT NULL;

-- Record an immutable opening balance for legacy stock imported into Main Store.
INSERT INTO "inventory_stock_movements" (
  "id", "organization_id", "branch_id", "item_id", "location_id", "type", "quantity",
  "balance_before", "balance_after", "reason", "actor_user_id", "created_at"
)
SELECT
  gen_random_uuid(), item."organization_id", item."branch_id", item."id", location."id",
  'MANUAL_CORRECTION'::"StockMovementType", item."current_stock", 0, item."current_stock",
  'Opening balance migrated from the existing inventory item', item."created_by_user_id", CURRENT_TIMESTAMP
FROM "inventory_items" item
JOIN "inventory_locations" location
  ON location."organization_id" = item."organization_id"
 AND location."branch_id" = item."branch_id"
 AND location."is_default" = TRUE
WHERE item."current_stock" > 0;

CREATE TABLE "service_inventory_requirements" (
  "id" UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  "organization_id" UUID NOT NULL,
  "service_id" UUID NOT NULL,
  "item_id" UUID NOT NULL,
  "expected_quantity" DECIMAL(14,3) NOT NULL,
  "unit_of_measure" VARCHAR(40) NOT NULL,
  "is_required" BOOLEAN NOT NULL DEFAULT FALSE,
  "reservation_mode" "InventoryReservationMode" NOT NULL DEFAULT 'FORECAST_ONLY',
  "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" TIMESTAMPTZ(3) NOT NULL,
  CHECK ("expected_quantity" > 0),
  FOREIGN KEY ("organization_id") REFERENCES "organizations"("id") ON DELETE CASCADE,
  FOREIGN KEY ("organization_id", "service_id") REFERENCES "services"("organization_id", "id") ON DELETE CASCADE,
  FOREIGN KEY ("organization_id", "item_id") REFERENCES "inventory_items"("organization_id", "id") ON DELETE RESTRICT
);
CREATE UNIQUE INDEX "service_inventory_requirements_org_id_key" ON "service_inventory_requirements"("organization_id", "id");
CREATE UNIQUE INDEX "service_inventory_requirements_svc_item_key" ON "service_inventory_requirements"("organization_id", "service_id", "item_id");

CREATE TABLE "inventory_reservations" (
  "id" UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  "organization_id" UUID NOT NULL,
  "branch_id" UUID NOT NULL,
  "appointment_id" UUID NOT NULL,
  "item_id" UUID NOT NULL,
  "quantity" DECIMAL(14,3) NOT NULL,
  "released_at" TIMESTAMPTZ(3),
  "consumed_at" TIMESTAMPTZ(3),
  "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK ("quantity" > 0),
  FOREIGN KEY ("organization_id") REFERENCES "organizations"("id") ON DELETE CASCADE,
  FOREIGN KEY ("organization_id", "branch_id") REFERENCES "branches"("organization_id", "id") ON DELETE RESTRICT,
  FOREIGN KEY ("organization_id", "appointment_id") REFERENCES "appointments"("organization_id", "id") ON DELETE CASCADE,
  FOREIGN KEY ("organization_id", "item_id") REFERENCES "inventory_items"("organization_id", "id") ON DELETE RESTRICT
);
CREATE UNIQUE INDEX "inventory_reservations_org_id_key" ON "inventory_reservations"("organization_id", "id");
CREATE UNIQUE INDEX "inventory_reservations_apt_item_key" ON "inventory_reservations"("organization_id", "appointment_id", "item_id");
CREATE INDEX "inventory_reservations_item_active_idx" ON "inventory_reservations"("organization_id", "item_id", "released_at", "consumed_at");

CREATE TABLE "appointment_inventory_consumptions" (
  "id" UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  "organization_id" UUID NOT NULL,
  "appointment_id" UUID NOT NULL,
  "item_id" UUID NOT NULL,
  "batch_id" UUID,
  "location_id" UUID,
  "expected_quantity" DECIMAL(14,3) NOT NULL,
  "actual_quantity" DECIMAL(14,3) NOT NULL,
  "unit_of_measure" VARCHAR(40) NOT NULL,
  "is_reconciliation_required" BOOLEAN NOT NULL DEFAULT FALSE,
  "reconciliation_note" TEXT,
  "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK ("expected_quantity" >= 0 AND "actual_quantity" >= 0),
  FOREIGN KEY ("organization_id") REFERENCES "organizations"("id") ON DELETE CASCADE,
  FOREIGN KEY ("organization_id", "appointment_id") REFERENCES "appointments"("organization_id", "id") ON DELETE RESTRICT,
  FOREIGN KEY ("organization_id", "item_id") REFERENCES "inventory_items"("organization_id", "id") ON DELETE RESTRICT,
  FOREIGN KEY ("organization_id", "batch_id") REFERENCES "inventory_batches"("organization_id", "id") ON DELETE RESTRICT,
  FOREIGN KEY ("organization_id", "location_id") REFERENCES "inventory_locations"("organization_id", "id") ON DELETE RESTRICT
);
CREATE UNIQUE INDEX "appointment_inventory_consumptions_org_id_key" ON "appointment_inventory_consumptions"("organization_id", "id");
CREATE UNIQUE INDEX "appointment_inventory_consumptions_apt_item_key" ON "appointment_inventory_consumptions"("organization_id", "appointment_id", "item_id");
CREATE INDEX "appointment_inventory_consumptions_apt_idx" ON "appointment_inventory_consumptions"("organization_id", "appointment_id");

INSERT INTO "permissions" ("id", "code", "name_en", "name_ar") VALUES
  (gen_random_uuid(), 'inventory.items.manage', 'Manage inventory items', 'إدارة أصناف المخزون'),
  (gen_random_uuid(), 'inventory.stock.transfer', 'Transfer inventory stock', 'نقل رصيد المخزون بين المواقع'),
  (gen_random_uuid(), 'inventory.consumption.read', 'Read appointment inventory consumption', 'عرض استهلاك مخزون المواعيد'),
  (gen_random_uuid(), 'inventory.consumption.adjust', 'Record appointment inventory consumption', 'تسجيل وتعديل استهلاك مخزون المواعيد')
ON CONFLICT ("code") DO NOTHING;

WITH g AS (
  SELECT r."organization_id", r."id" AS role_id, p."id" AS permission_id
  FROM "roles" r
  CROSS JOIN "permissions" p
  WHERE r."system_key" = 'ORGANIZATION_OWNER'
    AND p."code" IN ('inventory.items.manage', 'inventory.stock.transfer', 'inventory.consumption.read', 'inventory.consumption.adjust')
)
INSERT INTO "role_permissions" ("organization_id", "role_id", "permission_id", "scope")
SELECT "organization_id", role_id, permission_id, 'ORGANIZATION'::"PermissionScope"
FROM g ON CONFLICT DO NOTHING;

WITH g(code, scope) AS (VALUES
  ('inventory.consumption.read', 'SELF'::"PermissionScope"),
  ('inventory.consumption.adjust', 'SELF'::"PermissionScope")
)
INSERT INTO "role_permissions" ("organization_id", "role_id", "permission_id", "scope")
SELECT r."organization_id", r."id", p."id", g.scope
FROM g
JOIN "permissions" p ON p."code" = g.code
JOIN "roles" r ON r."system_key" = 'PROVIDER'
ON CONFLICT DO NOTHING;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'suppliers',
    'inventory_locations',
    'item_location_stocks',
    'inventory_batches',
    'inventory_stock_movements',
    'service_inventory_requirements',
    'inventory_reservations',
    'appointment_inventory_consumptions'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY %I ON %I USING (organization_id=NULLIF(CURRENT_SETTING(''app.organization_id'',true),'''')::uuid) WITH CHECK (organization_id=NULLIF(CURRENT_SETTING(''app.organization_id'',true),'''')::uuid)', t||'_tenant_isolation', t);
    EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON %I TO jormall_app', t);
  END LOOP;
END $$;

CREATE TRIGGER "inventory_stock_movements_append_only"
  BEFORE UPDATE OR DELETE ON "inventory_stock_movements"
  FOR EACH ROW EXECUTE FUNCTION "reject_remaining_work_append_only_change"();
