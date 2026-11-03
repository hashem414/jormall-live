import { describe, expect, it } from "vitest";

import { defaultProviderIdForAppointmentRead } from "./appointment-read-scope";

describe("defaultProviderIdForAppointmentRead", () => {
  it("does not self-filter a multi-role user who also has organization access", () => {
    expect(
      defaultProviderIdForAppointmentRead(
        [
          { code: "appointments.read", scope: "SELF" },
          { code: "appointments.read", scope: "ORGANIZATION" },
        ],
        "current-provider",
      ),
    ).toBeUndefined();
  });

  it("defaults a self-only user to their own provider", () => {
    expect(
      defaultProviderIdForAppointmentRead(
        [{ code: "appointments.read", scope: "SELF" }],
        "current-provider",
      ),
    ).toBe("current-provider");
  });
});
