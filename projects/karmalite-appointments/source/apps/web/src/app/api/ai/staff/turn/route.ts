import { copilotInsightTypes } from "@jormall/domain/copilot";
import { z } from "zod";

import { staffCopilotService } from "../../../../../server/copilot";
import {
  requireApiTenantAccess,
  workspaceError,
  workspaceJson,
} from "../../../../../server/workspace-http";

const turnSchema = z
  .object({
    insightType: z.enum(copilotInsightTypes),
    locale: z.enum(["en", "ar"]),
    subjectId: z.uuid().optional(),
  })
  .strict();

export async function POST(request: Request): Promise<Response> {
  try {
    const parsed = turnSchema.safeParse(await request.json());
    if (!parsed.success) return workspaceJson({ error: { code: "VALIDATION_FAILED" } }, 400);
    const access = await requireApiTenantAccess();
    const insight = await staffCopilotService.generate(access, parsed.data);
    return workspaceJson({ insight, mode: "DEVELOPMENT" });
  } catch (error) {
    return workspaceError(error);
  }
}
