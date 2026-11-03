ALTER TABLE "sessions" ADD COLUMN "active_branch_id" UUID;

CREATE INDEX "sessions_active_branch_id_idx" ON "sessions"("active_branch_id");

ALTER TABLE "sessions"
ADD CONSTRAINT "sessions_active_branch_id_fkey"
FOREIGN KEY ("active_branch_id") REFERENCES "branches"("id")
ON DELETE SET NULL ON UPDATE CASCADE;
