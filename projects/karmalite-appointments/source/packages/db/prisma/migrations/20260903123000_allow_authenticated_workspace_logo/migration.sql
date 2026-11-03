-- The customized Karmalite deployment serves its supplied official logo through an
-- authenticated, tenant-resolved endpoint. Keep HTTPS as the general rule and allow
-- only this exact same-origin endpoint as the local deployment exception.
ALTER TABLE "organization_settings"
DROP CONSTRAINT "organization_settings_brand_logo_url_check";

ALTER TABLE "organization_settings"
ADD CONSTRAINT "organization_settings_brand_logo_url_check"
CHECK (
  "brand_logo_url" IS NULL
  OR "brand_logo_url" ~ '^https://'
  OR "brand_logo_url" = '/api/workspace/logo'
);
