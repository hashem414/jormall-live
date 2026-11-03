ALTER TABLE "appointments" DROP CONSTRAINT "appointments_patient_no_overlap";
ALTER TABLE "appointments" ADD CONSTRAINT "appointments_patient_no_overlap" EXCLUDE USING gist (
  "organization_id" WITH =,
  "customer_id" WITH =,
  tstzrange("starts_at", "ends_at", '[)') WITH &&
) WHERE ("status" IN ('PENDING', 'CONFIRMED', 'CHECKED_IN', 'CALLED', 'IN_PROGRESS'));
