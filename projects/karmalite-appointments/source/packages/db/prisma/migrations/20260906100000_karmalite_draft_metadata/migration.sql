CREATE TYPE "ConfigurationApprovalStatus" AS ENUM ('DRAFT', 'APPROVED');

ALTER TABLE "organizations"
  ADD COLUMN "description_en" TEXT,
  ADD COLUMN "description_ar" TEXT,
  ADD COLUMN "subtitle_ar" VARCHAR(200),
  ADD COLUMN "profile_status" "ConfigurationApprovalStatus" NOT NULL DEFAULT 'DRAFT';

ALTER TABLE "organization_settings"
  ALTER COLUMN "booking_window_days" DROP NOT NULL,
  ADD COLUMN "booking_policy_status" "ConfigurationApprovalStatus" NOT NULL DEFAULT 'DRAFT';

ALTER TABLE "branches"
  ADD COLUMN "mobile_phone" VARCHAR(40),
  ADD COLUMN "location_status" "ConfigurationApprovalStatus" NOT NULL DEFAULT 'DRAFT';

ALTER TABLE "services"
  ALTER COLUMN "minimum_notice_mins" DROP NOT NULL,
  ADD COLUMN "configuration_status" "ConfigurationApprovalStatus" NOT NULL DEFAULT 'DRAFT';
