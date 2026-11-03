"use client";

import Link from "next/link";
import type { DragEvent } from "react";
import { useTransition } from "react";
import { z } from "zod";

import { rescheduleAppointmentAction } from "../app/[locale]/actions";

const draggedAppointmentSchema = z.object({
  appointmentId: z.uuid(),
  expectedVersion: z.number().int().positive(),
  providerId: z.uuid(),
});

type CalendarCard = Readonly<{
  appointmentId: string;
  canReschedule: boolean;
  expectedVersion: number;
  href: string;
  patient: string;
  room: string;
  service: string;
  startsAtLocal: string;
  status: string;
}>;

export function CalendarTimeGrid({
  appointments,
  branchId,
  breaks,
  day,
  locale,
  providerId,
  returnTo,
  slots,
}: Readonly<{
  appointments: readonly CalendarCard[];
  branchId?: string | undefined;
  breaks: readonly string[];
  day: string;
  locale: "ar" | "en";
  providerId: string;
  returnTo: string;
  slots: readonly string[];
}>) {
  const [isPending, startTransition] = useTransition();
  const byTime = new Map(
    appointments.map((appointment) => [appointment.startsAtLocal.slice(11), appointment]),
  );
  const breakTimes = new Set(breaks);

  function acceptDrop(event: DragEvent, time: string): void {
    event.preventDefault();
    const parsed = draggedAppointmentSchema.safeParse(
      parseDraggedAppointment(event.dataTransfer.getData("application/x-jormall-appointment")),
    );
    if (!parsed.success) return;
    if (parsed.data.providerId !== providerId) {
      window.alert(
        locale === "ar"
          ? "يحافظ السحب على الطبيب المعيّن. أفلت الموعد ضمن عمود الطبيب نفسه."
          : "Dragging keeps the assigned Doctor. Drop within the same Doctor column.",
      );
      return;
    }
    const confirmed = window.confirm(
      locale === "ar"
        ? `هل تريد اقتراح إعادة جدولة الموعد إلى ${time}؟ سيتم التحقق من التوفر قبل الحفظ.`
        : `Propose rescheduling this appointment to ${time}? Availability will be checked before saving.`,
    );
    if (!confirmed) return;
    const formData = new FormData();
    formData.set("locale", locale);
    formData.set("appointmentId", parsed.data.appointmentId);
    formData.set("expectedVersion", String(parsed.data.expectedVersion));
    formData.set("idempotencyKey", crypto.randomUUID());
    formData.set("startsAtLocal", `${day}T${time}`);
    formData.set("returnTo", returnTo);
    startTransition(() => void rescheduleAppointmentAction(formData));
  }

  return (
    <ol className="calendar-time-grid" aria-busy={isPending}>
      {slots.map((time) => {
        const appointment = byTime.get(time);
        const isBreak = breakTimes.has(time);
        const newAppointmentQuery = new URLSearchParams({ day, providerId, time });
        if (branchId) newAppointmentQuery.set("branchId", branchId);
        return (
          <li
            key={time}
            data-break={isBreak}
            onDragOver={(event) => {
              if (!isBreak) event.preventDefault();
            }}
            onDrop={(event) => {
              if (!isBreak) acceptDrop(event, time);
            }}
          >
            <time>{time}</time>
            {appointment ? (
              <article
                className="calendar-appointment"
                data-status={appointment.status.toLowerCase()}
                draggable={appointment.canReschedule}
                onDragStart={(event) => {
                  event.dataTransfer.effectAllowed = "move";
                  event.dataTransfer.setData(
                    "application/x-jormall-appointment",
                    JSON.stringify({
                      appointmentId: appointment.appointmentId,
                      expectedVersion: appointment.expectedVersion,
                      providerId,
                    }),
                  );
                }}
              >
                <div className="calendar-appointment-main">
                  <span className="status">{appointment.status}</span>
                  <h3>
                    <Link href={appointment.href}>{appointment.patient}</Link>
                  </h3>
                  <p>{appointment.service}</p>
                  <p>{appointment.room}</p>
                </div>
              </article>
            ) : isBreak ? (
              <span className="calendar-break-slot">{locale === "ar" ? "استراحة" : "Break"}</span>
            ) : (
              <Link
                className="calendar-empty-slot"
                href={`/${locale}/schedule/calendar?${newAppointmentQuery.toString()}#create-appointment-title`}
              >
                {locale === "ar" ? "موعد جديد" : "Open New Appointment"}
              </Link>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function parseDraggedAppointment(value: string): unknown {
  try {
    return JSON.parse(value) as unknown;
  } catch {
    return null;
  }
}
