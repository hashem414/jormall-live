"use client";

import type { DragEvent } from "react";
import { useRef, useState } from "react";
import Link from "next/link";

import {
  startAppointmentServiceAction,
  transitionAppointmentAction,
} from "../app/[locale]/actions";
import {
  appointmentKanbanDisplayStatus,
  type AppointmentKanbanMove,
  type AppointmentKanbanStatus,
} from "../lib/appointment-kanban";

type KanbanAppointment = Readonly<{
  doctor: string;
  href: string;
  id: string;
  moves: readonly AppointmentKanbanMove[];
  patient: string;
  room: string;
  service: string;
  status: AppointmentKanbanStatus;
  time: string;
  version: number;
}>;

export function AppointmentKanban({
  appointments,
  columns,
  locale,
  returnTo,
}: Readonly<{
  appointments: readonly KanbanAppointment[];
  columns: readonly Readonly<{ label: string; status: AppointmentKanbanStatus }>[];
  locale: "ar" | "en";
  returnTo: string;
}>) {
  const forms = useRef(new Map<string, HTMLFormElement>());
  const [draggedId, setDraggedId] = useState<string>();
  const [dropTarget, setDropTarget] = useState<AppointmentKanbanStatus>();
  const dragged = appointments.find(({ id }) => id === draggedId);
  const labels =
    locale === "ar"
      ? {
          empty: "لا توجد مواعيد",
          instruction:
            "اسحب الموعد إلى المرحلة التالية المظللة. الإجراءات التي تحتاج غرفة أو ملاحظات تُستكمل من تفاصيل الموعد.",
          move: "نقل إلى",
          moving: "جارٍ تحديث الموعد…",
          open: "فتح التفاصيل",
        }
      : {
          empty: "No appointments",
          instruction:
            "Drag an appointment to its highlighted next stage. Actions requiring a room or notes are completed from appointment details.",
          move: "Move to",
          moving: "Updating appointment…",
          open: "Open details",
        };

  function moveKey(appointmentId: string, target: AppointmentKanbanStatus): string {
    return `${appointmentId}:${target}`;
  }

  function submitMove(appointmentId: string, target: AppointmentKanbanStatus): void {
    forms.current.get(moveKey(appointmentId, target))?.requestSubmit();
  }

  function drop(event: DragEvent<HTMLElement>, target: AppointmentKanbanStatus): void {
    event.preventDefault();
    const appointmentId = event.dataTransfer.getData("text/plain") || draggedId;
    const appointment = appointments.find(({ id }) => id === appointmentId);
    if (appointment?.moves.some((move) => move.target === target)) {
      submitMove(appointment.id, target);
    }
    setDraggedId(undefined);
    setDropTarget(undefined);
  }

  return (
    <div className="kanban-workflow">
      <p className="kanban-instruction">{labels.instruction}</p>
      <p aria-live="polite" className="sr-only">
        {draggedId ? labels.moving : ""}
      </p>
      <section className="appointment-kanban" aria-label="Kanban">
        {columns.map((column) => {
          const rows = appointments.filter(
            ({ status }) => appointmentKanbanDisplayStatus(status) === column.status,
          );
          const canReceive = Boolean(dragged?.moves.some(({ target }) => target === column.status));
          return (
            <section
              className="appointment-kanban-column"
              data-can-drop={canReceive || undefined}
              data-drop-active={(canReceive && dropTarget === column.status) || undefined}
              key={column.status}
              onDragEnter={() => {
                if (canReceive) setDropTarget(column.status);
              }}
              onDragLeave={(event) => {
                if (
                  !(event.relatedTarget instanceof Node) ||
                  !event.currentTarget.contains(event.relatedTarget)
                ) {
                  setDropTarget(undefined);
                }
              }}
              onDragOver={(event) => {
                if (canReceive) event.preventDefault();
              }}
              onDrop={(event) => drop(event, column.status)}
            >
              <header>
                <h2>{column.label}</h2>
                <span>{rows.length}</span>
              </header>
              <div className="appointment-kanban-cards">
                {rows.length === 0 ? <p className="kanban-empty-column">{labels.empty}</p> : null}
                {rows.map((appointment) => (
                  <article
                    aria-label={`${appointment.patient}, ${appointment.service}`}
                    className="appointment-kanban-card"
                    data-dragging={draggedId === appointment.id || undefined}
                    draggable={appointment.moves.length > 0}
                    key={appointment.id}
                    onDragEnd={() => {
                      setDraggedId(undefined);
                      setDropTarget(undefined);
                    }}
                    onDragStart={(event) => {
                      event.dataTransfer.effectAllowed = "move";
                      event.dataTransfer.setData("text/plain", appointment.id);
                      setDraggedId(appointment.id);
                    }}
                  >
                    <Link href={appointment.href}>
                      <time>{appointment.time}</time>
                      <strong>{appointment.patient}</strong>
                      <span>{appointment.service}</span>
                      <small>
                        {appointment.doctor} · {appointment.room}
                      </small>
                    </Link>
                    <div className="kanban-card-actions">
                      {appointment.moves.map((move) => {
                        const targetLabel =
                          columns.find(({ status }) => status === move.target)?.label ??
                          move.target;
                        return (
                          <form
                            action={
                              move.action === "start"
                                ? startAppointmentServiceAction
                                : transitionAppointmentAction
                            }
                            key={move.target}
                            ref={(node) => {
                              const key = moveKey(appointment.id, move.target);
                              if (node) forms.current.set(key, node);
                              else forms.current.delete(key);
                            }}
                          >
                            <input name="locale" type="hidden" value={locale} />
                            <input name="appointmentId" type="hidden" value={appointment.id} />
                            <input
                              name="expectedVersion"
                              type="hidden"
                              value={appointment.version}
                            />
                            <input name="returnTo" type="hidden" value={returnTo} />
                            {move.action === "transition" ? (
                              <input name="toStatus" type="hidden" value={move.target} />
                            ) : null}
                            {move.action === "start" ? (
                              <>
                                <input name="includeCheckIn" type="hidden" value="false" />
                                {move.roomId ? (
                                  <input name="roomId" type="hidden" value={move.roomId} />
                                ) : null}
                              </>
                            ) : null}
                            <button className="kanban-move-button" type="submit">
                              {labels.move} {targetLabel}
                            </button>
                          </form>
                        );
                      })}
                      <Link className="kanban-open-link" href={appointment.href}>
                        {labels.open}
                      </Link>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          );
        })}
      </section>
    </div>
  );
}
