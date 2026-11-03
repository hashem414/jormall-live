import { requirePermission } from "@jormall/auth/tenant-policy";
import { z } from "zod";

import { crmAppointmentRepository } from "../../../../../server/identity";
import {
  requireApiTenantAccess,
  workspaceError,
  workspaceJson,
} from "../../../../../server/workspace-http";

export async function GET(
  _request: Request,
  context: RouteContext<"/api/patients/[patientId]/safety-indicators">,
): Promise<Response> {
  try {
    const parsed = z.uuid().safeParse((await context.params).patientId);
    if (!parsed.success) return workspaceJson({ error: { code: "VALIDATION_FAILED" } }, 400);
    const access = await requireApiTenantAccess();
    requirePermission(access, "patients.health.read");
    // The repository separately enforces tenant, branch/SELF record scope and records the sensitive read.
    return workspaceJson(
      await crmAppointmentRepository.getPatientSafetyIndicators(access, parsed.data),
    );
  } catch (error) {
    return workspaceError(error);
  }
}
