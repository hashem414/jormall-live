import { describe, expect, it } from "vitest";

import { normalizeHealthInformation, requiresHealthConsent } from "./patient-health";

describe("protected patient health information", () => {
  it("distinguishes all explicit states", () => {
    expect(normalizeHealthInformation("NOT_PROVIDED")).toEqual({
      details: null,
      state: "NOT_PROVIDED",
    });
    expect(normalizeHealthInformation("NONE_REPORTED")).toEqual({
      details: null,
      state: "NONE_REPORTED",
    });
    expect(normalizeHealthInformation("DECLINED")).toEqual({ details: null, state: "DECLINED" });
    expect(normalizeHealthInformation("PROVIDED", "  Latex  ")).toEqual({
      details: "Latex",
      state: "PROVIDED",
    });
  });

  it("rejects ambiguous state/detail combinations", () => {
    expect(() => normalizeHealthInformation("PROVIDED")).toThrow(/required/i);
    expect(() => normalizeHealthInformation("NONE_REPORTED", "none")).toThrow(/only permitted/i);
  });

  it("requires consent or provenance for every recorded patient response", () => {
    expect(requiresHealthConsent(["NOT_PROVIDED"])).toBe(false);
    expect(requiresHealthConsent(["DECLINED"])).toBe(true);
    expect(requiresHealthConsent(["NONE_REPORTED"])).toBe(true);
    expect(requiresHealthConsent(["PROVIDED"])).toBe(true);
  });
});
