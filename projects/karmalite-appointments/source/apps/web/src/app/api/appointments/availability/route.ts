import { z } from "zod";

import { schedulingRepository } from "../../../../server/identity";
import {
  requireApiTenantAccess,
  workspaceError,
  workspaceJson,
} from "../../../../server/workspace-http";

const querySchema = z.object({
  branchId: z.uuid(),
  customerId: z.uuid().optional(),
  endsOn: z.iso.date(),
  providerId: z.uuid().optional(),
  serviceId: z.uuid(),
  startsOn: z.iso.date(),
});

export async function GET(request: Request): Promise<Response> {
  try {
    const url = new URL(request.url);
    const parsed = querySchema.safeParse({
      branchId: url.searchParams.get("branchId"),
      customerId: url.searchParams.get("customerId") || undefined,
      endsOn: url.searchParams.get("endsOn"),
      providerId: url.searchParams.get("providerId") || undefined,
      serviceId: url.searchParams.get("serviceId"),
      startsOn: url.searchParams.get("startsOn"),
    });
    if (!parsed.success) return workspaceJson({ error: { code: "VALIDATION_FAILED" } }, 400);
    const access = await requireApiTenantAccess();
    const slots = await schedulingRepository.findAvailableSlots(access, parsed.data);
    return workspaceJson({ slots });
  } catch (error) {
    return workspaceError(error);
  }
}
