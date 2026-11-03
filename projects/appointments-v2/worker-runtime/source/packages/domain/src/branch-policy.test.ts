import { describe, expect, it } from "vitest";

import type { DomainError } from "./errors";
import { assertBranchCanBeDeleted } from "./branch-policy";

describe("branch policy", () => {
  it("prevents deleting the only branch", () => {
    expect(() => assertBranchCanBeDeleted(1)).toThrowError(
      expect.objectContaining<Partial<DomainError>>({ code: "VALIDATION_FAILED" }),
    );
  });

  it("allows deletion when another branch remains", () => {
    expect(() => assertBranchCanBeDeleted(2)).not.toThrow();
  });
});
