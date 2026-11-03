import { describe, expect, it } from "vitest";

import {
  assertAppointmentStartsInFuture,
  assertAppointmentTransition,
  canRescheduleAppointment,
  canTransitionAppointment,
} from "./appointment-state";
import { normalizeJordanianPhone } from "./jordan-phone";
import { localDateForInstant, localDateTimeToUtc, utcRangeForLocalDate } from "./timezone";

describe("appointment state machine", () => {
  it("permits only its defined legal transitions", () => {
    expect(canTransitionAppointment("PENDING", "CONFIRMED")).toBe(true);
    expect(canTransitionAppointment("CONFIRMED", "CHECKED_IN")).toBe(true);
    expect(canTransitionAppointment("CHECKED_IN", "CALLED")).toBe(true);
    expect(canTransitionAppointment("CALLED", "IN_PROGRESS")).toBe(true);
    expect(canTransitionAppointment("CHECKED_IN", "COMPLETED")).toBe(false);
    expect(canTransitionAppointment("CONFIRMED", "IN_PROGRESS")).toBe(false);
    expect(canTransitionAppointment("NO_SHOW", "CHECKED_IN")).toBe(false);
    expect(canTransitionAppointment("COMPLETED", "CONFIRMED")).toBe(false);
    expect(() => assertAppointmentTransition("PENDING", "COMPLETED")).toThrow(/cannot transition/);
    expect(canRescheduleAppointment("CONFIRMED")).toBe(true);
    expect(canRescheduleAppointment("CHECKED_IN")).toBe(false);
  });

  it("rejects appointment starts that are not in the future", () => {
    const now = new Date("2026-09-13T12:00:00.000Z");

    expect(() =>
      assertAppointmentStartsInFuture(new Date("2026-09-13T12:00:00.000Z"), now),
    ).toThrow(/must be in the future/u);
    expect(() =>
      assertAppointmentStartsInFuture(new Date("2026-09-13T11:59:59.999Z"), now),
    ).toThrow(/must be in the future/u);
    expect(() =>
      assertAppointmentStartsInFuture(new Date("2026-09-13T12:00:00.001Z"), now),
    ).not.toThrow();
  });
});

describe("Jordanian phones and Asia/Amman dates", () => {
  it("normalizes only safe Jordanian phone variants and keeps foreign values unguessed", () => {
    expect(normalizeJordanianPhone("079 123 4567")).toBe("+962791234567");
    expect(normalizeJordanianPhone("٠٧٩١٢٣٤٥٦٧")).toBe("+962791234567");
    expect(normalizeJordanianPhone("+1 202 555 0100")).toBeNull();
    expect(normalizeJordanianPhone("not a phone")).toBeNull();
  });

  it("uses Amman local day boundaries rather than UTC day boundaries", () => {
    const range = utcRangeForLocalDate("2026-08-23", "Asia/Amman");
    expect(range.startsAt.toISOString()).toBe("2026-08-22T21:00:00.000Z");
    expect(range.endsAt.toISOString()).toBe("2026-08-23T21:00:00.000Z");
    const appointment = localDateTimeToUtc("2026-08-23T00:30", "Asia/Amman");
    expect(appointment >= range.startsAt && appointment < range.endsAt).toBe(true);
    expect(localDateForInstant(appointment, "Asia/Amman")).toBe("2026-08-23");
  });
});
