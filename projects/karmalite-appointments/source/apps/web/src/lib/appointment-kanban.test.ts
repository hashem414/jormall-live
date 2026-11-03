import { describe, expect, it } from "vitest";

import { appointmentKanbanDisplayStatus, appointmentKanbanMoves } from "./appointment-kanban";

const now = new Date("2026-09-13T08:00:00.000Z");
const base = {
  canCheckIn: true,
  canClaimRoom: true,
  canConfirm: true,
  canStartService: true,
  renderedAt: now,
  roomId: "room-1",
  startsAt: new Date("2026-09-13T09:00:00.000Z"),
} as const;

describe("appointment Kanban moves", () => {
  it("allows only the protected next operational stage", () => {
    expect(appointmentKanbanMoves({ ...base, status: "PENDING" })).toEqual([
      { action: "transition", target: "CONFIRMED" },
    ]);
    expect(appointmentKanbanMoves({ ...base, status: "CONFIRMED" })).toEqual([
      { action: "transition", target: "CHECKED_IN" },
    ]);
    expect(appointmentKanbanMoves({ ...base, status: "CHECKED_IN" })).toEqual([
      { action: "start", roomId: "room-1", target: "IN_PROGRESS" },
    ]);
    expect(appointmentKanbanMoves({ ...base, status: "CALLED" })).toEqual([
      { action: "start", target: "IN_PROGRESS" },
    ]);
  });

  it("shows historical called appointments in the in-service column", () => {
    expect(appointmentKanbanDisplayStatus("CALLED")).toBe("IN_PROGRESS");
    expect(appointmentKanbanDisplayStatus("CHECKED_IN")).toBe("CHECKED_IN");
  });

  it("does not offer moves without permission, a room, or a future confirmation time", () => {
    expect(appointmentKanbanMoves({ ...base, canConfirm: false, status: "PENDING" })).toEqual([]);
    expect(appointmentKanbanMoves({ ...base, startsAt: now, status: "PENDING" })).toEqual([]);
    expect(appointmentKanbanMoves({ ...base, roomId: null, status: "CHECKED_IN" })).toEqual([]);
    expect(appointmentKanbanMoves({ ...base, status: "COMPLETED" })).toEqual([]);
  });
});
