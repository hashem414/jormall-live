-- Preserve scheduled instants and record actual operational lifecycle timestamps separately.
ALTER TABLE "appointments"
  ADD COLUMN "confirmed_at" TIMESTAMPTZ(3),
  ADD COLUMN "checked_in_at" TIMESTAMPTZ(3),
  ADD COLUMN "service_started_at" TIMESTAMPTZ(3),
  ADD COLUMN "completed_at" TIMESTAMPTZ(3),
  ADD COLUMN "no_show_at" TIMESTAMPTZ(3);

UPDATE "appointments" AS appointment
SET
  "confirmed_at" = history."confirmed_at",
  "checked_in_at" = history."checked_in_at",
  "service_started_at" = history."service_started_at",
  "completed_at" = history."completed_at",
  "no_show_at" = history."no_show_at"
FROM (
  SELECT
    "appointment_id",
    MIN("created_at") FILTER (WHERE "to_status" = 'CONFIRMED') AS "confirmed_at",
    MIN("created_at") FILTER (WHERE "to_status" = 'CHECKED_IN') AS "checked_in_at",
    MIN("created_at") FILTER (WHERE "to_status" = 'IN_PROGRESS') AS "service_started_at",
    MIN("created_at") FILTER (WHERE "to_status" = 'COMPLETED') AS "completed_at",
    MIN("created_at") FILTER (WHERE "to_status" = 'NO_SHOW') AS "no_show_at"
  FROM "appointment_status_history"
  GROUP BY "appointment_id"
) AS history
WHERE history."appointment_id" = appointment."id";
