import { describe, expect, it } from "vitest";

import { formatServicePrice } from "./service-price";

describe("service price presentation", () => {
  it("uses the approved Karmalite contact message when price is unpublished", () => {
    expect(formatServicePrice("en", null, "JOD")).toBe("Contact Karmalite for the current price.");
    expect(formatServicePrice("ar", null, "JOD")).toBe(
      "يرجى التواصل مع كارمالايت لمعرفة السعر الحالي.",
    );
  });

  it("formats an approved numeric price", () => {
    expect(formatServicePrice("en", 3500, "JOD")).toContain("35.00");
  });
});
