import type { RecurringAvailabilityRule, WeekdayValue } from "./availability";
import { DomainError } from "./errors";
import { localDateForInstant, localDateTimePartsForInstant } from "./timezone";

export type WaitlistWindowIssue = "CLOSED" | "DATE_ORDER" | "INVALID" | "PAST" | "TIME_ORDER";

export type WaitlistWindowInput = Readonly<{
  branchHours: readonly RecurringAvailabilityRule[];
  preferredEndDate: string;
  preferredEndMinute: number;
  preferredStartDate: string;
  preferredStartMinute: number;
  timezone: string;
}>;

const weekdayNames: readonly WeekdayValue[] = [
  "SUNDAY",
  "MONDAY",
  "TUESDAY",
  "WEDNESDAY",
  "THURSDAY",
  "FRIDAY",
  "SATURDAY",
];

function parseDate(value: string): Date | undefined {
  if (!/^\d{4}-\d{2}-\d{2}$/u.test(value)) return undefined;
  const parsed = new Date(`${value}T00:00:00.000Z`);
  return parsed.toISOString().slice(0, 10) === value ? parsed : undefined;
}

function ruleCovers(
  rule: RecurringAvailabilityRule,
  date: string,
  weekday: WeekdayValue,
  startMinute: number,
  endMinute: number,
): boolean {
  return (
    rule.weekday === weekday &&
    (!rule.effectiveFrom || rule.effectiveFrom <= date) &&
    (!rule.effectiveUntil || rule.effectiveUntil >= date) &&
    rule.startMinuteLocal <= startMinute &&
    rule.endMinuteLocal >= endMinute
  );
}

export function waitlistWindowIssue(
  input: WaitlistWindowInput,
  now = new Date(),
): WaitlistWindowIssue | undefined {
  const startDate = parseDate(input.preferredStartDate);
  const endDate = parseDate(input.preferredEndDate);
  if (
    !startDate ||
    !endDate ||
    !Number.isInteger(input.preferredStartMinute) ||
    !Number.isInteger(input.preferredEndMinute) ||
    input.preferredStartMinute < 0 ||
    input.preferredEndMinute > 1440
  ) {
    return "INVALID";
  }
  if (endDate < startDate) return "DATE_ORDER";
  if (input.preferredStartMinute >= input.preferredEndMinute) return "TIME_ORDER";

  const today = localDateForInstant(now, input.timezone);
  const localNow = localDateTimePartsForInstant(now, input.timezone);
  const currentMinute = localNow.hour * 60 + localNow.minute;
  if (
    input.preferredStartDate < today ||
    (input.preferredStartDate === today && input.preferredStartMinute <= currentMinute)
  ) {
    return "PAST";
  }

  for (
    let cursor = startDate;
    cursor <= endDate;
    cursor = new Date(cursor.getTime() + 86_400_000)
  ) {
    const date = cursor.toISOString().slice(0, 10);
    const weekday = weekdayNames[cursor.getUTCDay()] ?? "SUNDAY";
    if (
      input.branchHours.some((rule) =>
        ruleCovers(rule, date, weekday, input.preferredStartMinute, input.preferredEndMinute),
      )
    ) {
      return undefined;
    }
  }
  return "CLOSED";
}

export function assertWaitlistWindowAllowed(input: WaitlistWindowInput, now = new Date()): void {
  const issue = waitlistWindowIssue(input, now);
  if (!issue) return;
  throw new DomainError({
    code: "VALIDATION_FAILED",
    message: "The waitlist preference must be in the future and within branch opening hours.",
    metadata: { reason: "WAITLIST_TIME_INVALID", waitlistWindowIssue: issue },
  });
}
