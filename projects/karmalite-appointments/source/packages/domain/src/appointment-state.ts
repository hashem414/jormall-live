import { DomainError } from "./errors";

export const appointmentStatuses = [
  "PENDING",
  "CONFIRMED",
  "CHECKED_IN",
  "CALLED",
  "IN_PROGRESS",
  "COMPLETED",
  "CANCELLED",
  "NO_SHOW",
] as const;

export type AppointmentStatusValue = (typeof appointmentStatuses)[number];

const transitions: Readonly<Record<AppointmentStatusValue, readonly AppointmentStatusValue[]>> = {
  PENDING: ["CONFIRMED", "CANCELLED"],
  CONFIRMED: ["CHECKED_IN", "CANCELLED", "NO_SHOW"],
  CHECKED_IN: ["CALLED", "IN_PROGRESS", "CANCELLED"],
  CALLED: ["IN_PROGRESS", "CANCELLED"],
  IN_PROGRESS: ["COMPLETED", "CANCELLED"],
  COMPLETED: [],
  CANCELLED: [],
  NO_SHOW: [],
};

export function canTransitionAppointment(
  from: AppointmentStatusValue,
  to: AppointmentStatusValue,
): boolean {
  return transitions[from].includes(to);
}

export function assertAppointmentTransition(
  from: AppointmentStatusValue,
  to: AppointmentStatusValue,
): void {
  if (!canTransitionAppointment(from, to)) {
    throw new DomainError({
      code: "CONFLICT",
      message: `Appointment cannot transition from ${from} to ${to}.`,
    });
  }
}

export function isAppointmentTerminal(status: AppointmentStatusValue): boolean {
  return status === "COMPLETED" || status === "CANCELLED" || status === "NO_SHOW";
}

export function canRescheduleAppointment(status: AppointmentStatusValue): boolean {
  return status === "PENDING" || status === "CONFIRMED";
}

export function assertAppointmentStartsInFuture(startsAt: Date, now = new Date()): void {
  if (!Number.isFinite(startsAt.getTime()) || startsAt.getTime() <= now.getTime()) {
    throw new DomainError({
      code: "VALIDATION_FAILED",
      message: "Appointment time must be in the future.",
      metadata: { reason: "APPOINTMENT_TIME_PASSED" },
    });
  }
}
