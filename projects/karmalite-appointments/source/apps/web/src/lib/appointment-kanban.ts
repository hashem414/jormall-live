export type AppointmentKanbanStatus =
  | "PENDING"
  | "CONFIRMED"
  | "CHECKED_IN"
  | "CALLED"
  | "IN_PROGRESS"
  | "COMPLETED"
  | "CANCELLED"
  | "NO_SHOW";

export type AppointmentKanbanMove = Readonly<{
  action: "start" | "transition";
  roomId?: string | undefined;
  target: AppointmentKanbanStatus;
}>;

export function appointmentKanbanMoves(
  input: Readonly<{
    canCheckIn: boolean;
    canClaimRoom: boolean;
    canConfirm: boolean;
    canStartService: boolean;
    renderedAt: Date;
    roomId: string | null;
    startsAt: Date;
    status: AppointmentKanbanStatus;
  }>,
): readonly AppointmentKanbanMove[] {
  if (input.status === "PENDING" && input.startsAt > input.renderedAt && input.canConfirm) {
    return [{ action: "transition", target: "CONFIRMED" }];
  }
  if (input.status === "CONFIRMED" && input.canCheckIn) {
    return [{ action: "transition", target: "CHECKED_IN" }];
  }
  if (
    input.status === "CHECKED_IN" &&
    input.roomId &&
    input.canStartService &&
    input.canClaimRoom
  ) {
    return [{ action: "start", roomId: input.roomId, target: "IN_PROGRESS" }];
  }
  if (input.status === "CALLED" && input.canStartService && input.canClaimRoom) {
    return [{ action: "start", target: "IN_PROGRESS" }];
  }
  return [];
}

export function appointmentKanbanDisplayStatus(
  status: AppointmentKanbanStatus,
): AppointmentKanbanStatus {
  return status === "CALLED" ? "IN_PROGRESS" : status;
}
