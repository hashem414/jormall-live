import { z } from "zod";

import { crmAppointmentRepository } from "../../../server/identity";
import { requestAuditDetails } from "../../../server/request-context";
import {
  requireApiTenantAccess,
  workspaceError,
  workspaceJson,
} from "../../../server/workspace-http";

const healthStateSchema = z.enum(["NOT_PROVIDED", "NONE_REPORTED", "PROVIDED", "DECLINED"]);

const createPatientSchema = z
  .object({
    allergyDetails: z.string().trim().max(4_000).optional(),
    allergyState: healthStateSchema,
    displayName: z.string().trim().min(2).max(160),
    emailOriginal: z.email().max(320).optional(),
    healthConsentConfirmed: z.boolean(),
    medicalConditionDetails: z.string().trim().max(4_000).optional(),
    medicalConditionState: healthStateSchema,
    phoneOriginal: z.string().trim().min(7).max(80),
    preferredBranchId: z.uuid(),
    preferredLocale: z.enum(["en", "ar"]),
  })
  .strict();

export async function POST(request: Request): Promise<Response> {
  try {
    const parsed = createPatientSchema.safeParse(await request.json());
    if (!parsed.success) return workspaceJson({ error: { code: "VALIDATION_FAILED" } }, 400);
    const access = await requireApiTenantAccess();
    const created = await crmAppointmentRepository.createCustomer(
      access,
      { ...parsed.data, rejectDuplicatePhone: true },
      await requestAuditDetails(),
    );
    return workspaceJson(
      {
        patient: {
          contacts: created.customer.contacts.map(({ kind, originalValue }) => ({
            kind,
            originalValue,
          })),
          displayName: created.customer.displayName,
          id: created.customer.id,
          referenceCode: created.customer.referenceCode,
        },
      },
      201,
    );
  } catch (error) {
    return workspaceError(error);
  }
}
