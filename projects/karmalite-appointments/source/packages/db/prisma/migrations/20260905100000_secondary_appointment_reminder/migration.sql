ALTER TABLE "organization_settings"
ADD COLUMN "secondary_reminder_lead_mins" INTEGER;

ALTER TABLE "organization_settings"
ADD CONSTRAINT "organization_settings_secondary_reminder_lead_mins_check"
CHECK (
  "secondary_reminder_lead_mins" IS NULL
  OR (
    "secondary_reminder_lead_mins" >= 0
    AND "secondary_reminder_lead_mins" <= 525600
    AND "secondary_reminder_lead_mins" <> "reminder_lead_mins"
  )
);
