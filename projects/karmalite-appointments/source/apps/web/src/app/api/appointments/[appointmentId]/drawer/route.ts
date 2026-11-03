import { canAccessResource } from "@jormall/auth/tenant-policy";
import { z } from "zod";

import { communicationRepository, crmAppointmentRepository } from "../../../../../server/identity";
import {
  requireApiTenantAccess,
  workspaceError,
  workspaceJson,
} from "../../../../../server/workspace-http";

export async function GET(
  _request: Request,
  context: RouteContext<"/api/appointments/[appointmentId]/drawer">,
): Promise<Response> {
  try {
    const parsed = z.uuid().safeParse((await context.params).appointmentId);
    if (!parsed.success) return workspaceJson({ error: { code: "VALIDATION_FAILED" } }, 400);
    const access = await requireApiTenantAccess();
    const appointment = await crmAppointmentRepository.getAppointment(access, parsed.data);
    const resource = { branchId: appointment.branchId, staffProfileId: appointment.providerId };
    const [operational, communications] = await Promise.all([
      canAccessResource(access, "appointment_records.read", resource) &&
      canAccessResource(access, "patients.doctor_notes.read", resource)
        ? crmAppointmentRepository.getAppointmentOperationalDetail(access, appointment.id)
        : Promise.resolve(null),
      canAccessResource(access, "messages.read", resource)
        ? communicationRepository.listAppointmentMessages(access, appointment.id)
        : Promise.resolve([]),
    ]);
    return workspaceJson({ appointment, communications, operational });
  } catch (error) {
    return workspaceError(error);
  }
}
