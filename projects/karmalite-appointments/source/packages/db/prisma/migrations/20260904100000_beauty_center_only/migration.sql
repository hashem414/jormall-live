-- Keep historical enum members for migration compatibility while enforcing the supported product.
UPDATE "organization_settings"
SET "business_sector" = 'BEAUTY_CENTER'
WHERE "business_sector" IS NULL OR "business_sector" <> 'BEAUTY_CENTER';

ALTER TABLE "organization_settings"
  ALTER COLUMN "business_sector" SET DEFAULT 'BEAUTY_CENTER',
  ALTER COLUMN "business_sector" SET NOT NULL;

ALTER TABLE "organization_settings"
  ADD CONSTRAINT "organization_settings_beauty_center_only"
  CHECK ("business_sector" = 'BEAUTY_CENTER');

UPDATE "roles"
SET
  "name_en" = CASE "system_key"
    WHEN 'ORGANIZATION_OWNER' THEN 'Owner'
    WHEN 'ORGANIZATION_MANAGER' THEN 'Manager'
    WHEN 'SECRETARY' THEN 'Secretary'
    WHEN 'PROVIDER' THEN 'Service Provider'
    ELSE "name_en"
  END,
  "name_ar" = CASE "system_key"
    WHEN 'ORGANIZATION_OWNER' THEN 'المالك'
    WHEN 'ORGANIZATION_MANAGER' THEN 'المدير'
    WHEN 'SECRETARY' THEN 'سكرتير'
    WHEN 'PROVIDER' THEN 'مقدم الخدمة'
    ELSE "name_ar"
  END
WHERE "is_system" = true;
