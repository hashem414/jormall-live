"use client";

import type { RecurringAvailabilityRule } from "@jormall/domain/availability";
import { localDateForInstant } from "@jormall/domain/timezone";
import { waitlistWindowIssue } from "@jormall/domain/waitlist-policy";
import { useEffect, useMemo, useRef, useState } from "react";

function minuteValue(value: string): number {
  const parts = value.split(":").map(Number);
  const hour = parts[0];
  const minute = parts[1];
  return hour !== undefined &&
    minute !== undefined &&
    Number.isInteger(hour) &&
    Number.isInteger(minute)
    ? hour * 60 + minute
    : -1;
}

function timeValue(minute: number): string {
  const validMinute = Math.min(minute, 1439);
  return `${Math.floor(validMinute / 60)
    .toString()
    .padStart(2, "0")}:${(validMinute % 60).toString().padStart(2, "0")}`;
}

export function WaitlistScheduleFields({
  branchHours,
  locale,
  timezone,
}: Readonly<{
  branchHours: readonly RecurringAvailabilityRule[];
  locale: "ar" | "en";
  timezone: string;
}>) {
  const [now, setNow] = useState(() => new Date());
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const earliestOpening = Math.min(...branchHours.map(({ startMinuteLocal }) => startMinuteLocal));
  const latestClosing = Math.max(...branchHours.map(({ endMinuteLocal }) => endMinuteLocal));
  const [startTime, setStartTime] = useState(
    Number.isFinite(earliestOpening) ? timeValue(earliestOpening) : "09:00",
  );
  const [endTime, setEndTime] = useState(
    Number.isFinite(latestClosing) ? timeValue(latestClosing) : "19:00",
  );
  const startDateReference = useRef<HTMLInputElement>(null);
  const minimumDate = localDateForInstant(now, timezone);
  const complete = Boolean(startDate && endDate && startTime && endTime);
  const issue = complete
    ? waitlistWindowIssue(
        {
          branchHours,
          preferredEndDate: endDate,
          preferredEndMinute: minuteValue(endTime),
          preferredStartDate: startDate,
          preferredStartMinute: minuteValue(startTime),
          timezone,
        },
        now,
      )
    : undefined;
  const text = useMemo(
    () =>
      locale === "ar"
        ? {
            CLOSED: "اختر يوماً مفتوحاً ووقتاً يقع بالكامل ضمن ساعات عمل الفرع.",
            DATE_ORDER: "يجب أن يكون تاريخ النهاية في تاريخ البداية أو بعده.",
            INVALID: "راجع تاريخ ووقت قائمة الانتظار.",
            PAST: "لا يمكن إضافة طلب قائمة انتظار لتاريخ أو وقت مضى.",
            TIME_ORDER: "يجب أن يكون وقت النهاية بعد وقت البداية.",
            endDate: "إلى تاريخ",
            endTime: "وقت نهاية الفترة المفضل",
            hours: "يجب أن يقع الطلب ضمن أيام وساعات عمل الفرع.",
            startDate: "من تاريخ",
            startTime: "وقت بداية الفترة المفضل",
          }
        : {
            CLOSED: "Choose an open day and a time fully within branch working hours.",
            DATE_ORDER: "The end date must be on or after the start date.",
            INVALID: "Review the waitlist date and time.",
            PAST: "A waitlist request cannot use a past date or time.",
            TIME_ORDER: "The end time must be after the start time.",
            endDate: "To date",
            endTime: "Preferred end time",
            hours: "The request must be within branch opening days and hours.",
            startDate: "From date",
            startTime: "Preferred start time",
          },
    [locale],
  );

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    startDateReference.current?.setCustomValidity(issue ? text[issue] : "");
  }, [issue, text]);

  return (
    <>
      <label className="field">
        <span className="field-label">{text.startDate}</span>
        <input
          aria-describedby="waitlist-hours-guidance waitlist-window-feedback"
          aria-invalid={issue ? "true" : undefined}
          className="input"
          min={minimumDate}
          name="preferredStartDate"
          onChange={(event) => setStartDate(event.currentTarget.value)}
          ref={startDateReference}
          required
          type="date"
          value={startDate}
        />
      </label>
      <label className="field">
        <span className="field-label">{text.endDate}</span>
        <input
          className="input"
          min={startDate || minimumDate}
          name="preferredEndDate"
          onChange={(event) => setEndDate(event.currentTarget.value)}
          required
          type="date"
          value={endDate}
        />
      </label>
      <label className="field">
        <span className="field-label">{text.startTime}</span>
        <input
          className="input"
          name="preferredStartTime"
          onChange={(event) => setStartTime(event.currentTarget.value)}
          required
          step="900"
          type="time"
          value={startTime}
        />
      </label>
      <label className="field">
        <span className="field-label">{text.endTime}</span>
        <input
          className="input"
          name="preferredEndTime"
          onChange={(event) => setEndTime(event.currentTarget.value)}
          required
          step="900"
          type="time"
          value={endTime}
        />
      </label>
      <p className="field-hint field-wide" id="waitlist-hours-guidance">
        {text.hours}
      </p>
      <p
        aria-live="polite"
        className={issue ? "inline-alert field-wide" : "field-hint field-wide"}
        id="waitlist-window-feedback"
      >
        {issue ? text[issue] : ""}
      </p>
    </>
  );
}
