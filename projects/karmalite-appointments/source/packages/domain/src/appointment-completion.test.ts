import { describe, expect, it } from "vitest";
import { completionNote } from "./appointment-completion";

describe("appointment completion note policy", () => {
  it("allows completion without a note", () => {
    expect(completionNote({ toStatus: "COMPLETED" })).toBeNull();
  });
  it("normalizes a valid append-only note", () => {
    expect(
      completionNote({
        toStatus: "COMPLETED",
        recordSummary: " Done ",
        recordDetails: " Follow up ",
      }),
    ).toEqual({ summary: "Done", details: "Follow up", body: "Done\n\nFollow up" });
  });
  it.each([
    { toStatus: "CONFIRMED" as const, recordSummary: "Must not be silently discarded" },
    { toStatus: "COMPLETED" as const, recordDetails: "Missing summary" },
    { toStatus: "COMPLETED" as const, recordSummary: "x".repeat(5001) },
    { toStatus: "COMPLETED" as const, recordSummary: "Valid", recordDetails: "x".repeat(10001) },
  ])("rejects an invalid completion note", (input) => {
    expect(() => completionNote(input)).toThrowError(
      expect.objectContaining({ code: "VALIDATION_FAILED" }),
    );
  });
});
