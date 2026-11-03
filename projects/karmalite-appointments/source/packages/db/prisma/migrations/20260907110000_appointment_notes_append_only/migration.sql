-- Preserve existing notes; reuse the existing append-only history guard.
-- No existing rows are rewritten or deleted.
CREATE TRIGGER "appointment_notes_immutable"
BEFORE UPDATE OR DELETE ON "appointment_notes"
FOR EACH ROW EXECUTE FUNCTION prevent_phase2_append_only_mutation();
