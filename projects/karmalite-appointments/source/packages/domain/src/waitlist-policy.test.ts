import { describe, expect, it } from "vitest";

import { assertWaitlistWindowAllowed, waitlistWindowIssue } from "./waitlist-policy";

const branchHours = [
  { endMinuteLocal: 1140, startMinuteLocal: 540, weekday: "SUNDAY" },
  { endMinuteLocal: 1140, startMinuteLocal: 540, weekday: "MONDAY" },
] as const;
const now = new Date("2026-09-13T07:00:00.000Z"); // 10:00 in Amman on Sunday
const base = {
  branchHours,
  preferredEndDate: "2026-09-14",
  preferredEndMinute: 1020,
  preferredStartDate: "2026-09-14",
  preferredStartMinute: 540,
  timezone: "Asia/Amman",
} as const;

describe("waitlist window policy", () => {
  it("allows a future preference covered by branch opening hours", () => {
    expect(waitlistWindowIssue(base, now)).toBeUndefined();
    expect(() => assertWaitlistWindowAllowed(base, now)).not.toThrow();
  });

  it("rejects past dates and times", () => {
    expect(
      waitlistWindowIssue(
        {
          ...base,
          preferredEndDate: "2026-09-13",
          preferredStartDate: "2026-09-13",
          preferredStartMinute: 600,
        },
        now,
      ),
    ).toBe("PAST");
  });

  it("rejects closed days and times outside opening hours", () => {
    expect(
      waitlistWindowIssue(
        { ...base, preferredEndDate: "2026-09-18", preferredStartDate: "2026-09-18" },
        now,
      ),
    ).toBe("CLOSED");
    expect(waitlistWindowIssue({ ...base, preferredStartMinute: 480 }, now)).toBe("CLOSED");
  });
});
