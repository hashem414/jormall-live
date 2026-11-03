ALTER TABLE "organization_settings"
ADD COLUMN "brand_primary_color" CHAR(7) NOT NULL DEFAULT '#22b8e6',
ADD COLUMN "brand_accent_color" CHAR(7) NOT NULL DEFAULT '#ff474d',
ADD COLUMN "brand_logo_url" VARCHAR(2048);

ALTER TABLE "organization_settings"
ADD CONSTRAINT "organization_settings_brand_primary_color_check"
CHECK ("brand_primary_color" ~ '^#[0-9a-fA-F]{6}$'),
ADD CONSTRAINT "organization_settings_brand_accent_color_check"
CHECK ("brand_accent_color" ~ '^#[0-9a-fA-F]{6}$'),
ADD CONSTRAINT "organization_settings_brand_logo_url_check"
CHECK ("brand_logo_url" IS NULL OR "brand_logo_url" ~ '^https://');
