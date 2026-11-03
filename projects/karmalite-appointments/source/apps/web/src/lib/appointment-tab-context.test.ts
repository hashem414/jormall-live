import { describe, expect, it } from "vitest";
import { appointmentTabHref } from "./appointment-tab-context";

const id = "fd8ce5ee-1648-48de-8013-e39a3ca2d090";
describe("appointment workspace URL context", () => {
  it.each(["en", "ar"])("preserves shared filters and open appointment for %s", (locale) => {
    const href = appointmentTabHref(
      `/${locale}/schedule/calendar`,
      `appointment=${id}&branchId=${id}&day=2026-09-06&providerId=${id}&serviceId=${id}&status=CONFIRMED&q=سارة`,
    );
    const query = new URL(href, "http://localhost").searchParams;
    for (const key of ["appointment", "branchId", "providerId", "serviceId"])
      expect(query.get(key)).toBe(id);
    expect(query.get("day")).toBe("2026-09-06");
    expect(query.get("status")).toBe("CONFIRMED");
    expect(query.get("q")).toBe("سارة");
  });
  it("drops authority, credentials, transient feedback and incompatible views", () => {
    expect(
      appointmentTabHref(
        "/en/schedule/appointments",
        "organizationId=another&role=OWNER&token=secret&notes=private&error=BAD&notice=OK&view=week&tab=past&page=3",
      ),
    ).toBe("/en/schedule/appointments");
  });
  it("drops invalid or ambiguous selectors independently", () => {
    expect(
      appointmentTabHref("/en/schedule/today", "day=bad&providerId=bad&q=a&q=b&status=CONFIRMED"),
    ).toBe("/en/schedule/today?status=CONFIRMED");
  });
  it("does not interpret appointment status as waitlist status", () => {
    expect(appointmentTabHref("/en/schedule/waitlist", "status=CONFIRMED&day=2026-09-06")).toBe(
      "/en/schedule/waitlist?day=2026-09-06",
    );
  });
  it("preserves a room selector without carrying transient feedback", () => {
    expect(
      appointmentTabHref(
        "/en/schedule/appointments",
        `resourceId=${id}&notice=APPOINTMENT_UPDATED`,
      ),
    ).toBe(`/en/schedule/appointments?resourceId=${id}`);
  });
});
