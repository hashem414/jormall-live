import { z } from "zod";

import { crmAppointmentRepository } from "../../../../server/identity";
import {
  requireApiTenantAccess,
  workspaceError,
  workspaceJson,
} from "../../../../server/workspace-http";

const querySchema = z
  .object({
    q: z.string().trim().max(160),
    page: z.coerce.number().int().min(1).max(10_000).default(1),
  })
  .strict();

export async function GET(request: Request): Promise<Response> {
  try {
    const url = new URL(request.url);
    const parsed = querySchema.safeParse({
      page: url.searchParams.get("page") ?? "1",
      q: url.searchParams.get("q") ?? "",
    });
    if (!parsed.success) return workspaceJson({ error: { code: "VALIDATION_FAILED" } }, 400);
    const access = await requireApiTenantAccess();
    return workspaceJson(
      await crmAppointmentRepository.listPatients(access, {
        page: parsed.data.page,
        pageSize: 25,
        query: parsed.data.q,
      }),
    );
  } catch (error) {
    return workspaceError(error);
  }
}
