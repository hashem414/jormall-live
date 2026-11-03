import { DomainError } from "./errors";

export function assertBranchCanBeDeleted(branchCount: number): void {
  if (!Number.isInteger(branchCount) || branchCount <= 1) {
    throw new DomainError({
      code: "VALIDATION_FAILED",
      message: "An organization must keep at least one branch.",
    });
  }
}
