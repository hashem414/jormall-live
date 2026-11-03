import { describe, expect, it } from "vitest";

import { appointmentFiltersResetHref } from "./appointment-filter-href";

describe("appointmentFiltersResetHref", () => {
  it("removes every filter while keeping a non-default appointment category", () => {
    expect(appointmentFiltersResetHref("en", "past")).toBe("/en/schedule/appointments?tab=past");
    expect(appointmentFiltersResetHref("ar", "exceptions")).toBe(
      "/ar/schedule/appointments?tab=exceptions",
    );
  });

  it("uses the clean appointment URL for the default category", () => {
    expect(appointmentFiltersResetHref("en", "upcoming")).toBe("/en/schedule/appointments");
  });
});
