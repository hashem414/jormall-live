"use server";

import { randomUUID } from "node:crypto";

import { requirePermission } from "@jormall/auth/tenant-policy";
import { prisma } from "@jormall/db/client";
import {
  AppointmentStatus,
  CommunicationChannel,
  ConsentChannel,
  ConsentSource,
  ConsentStatus,
  ConversationPriority,
  MembershipStatus,
  MockProviderBehavior,
  OrganizationStatus,
  ResourceStatus,
  SupportedLocale,
  Weekday,
} from "@jormall/db/generated/enums";
import { type AppointmentSource } from "@jormall/db/generated/enums";
import { DomainError } from "@jormall/domain/errors";
import { aiActionNames } from "@jormall/domain/ai-foundation";
import {
  copilotFeedbackTypes,
  copilotInsightTypes,
  semanticMetricKeys,
} from "@jormall/domain/copilot";
import { communicationTemplateKeys } from "@jormall/domain/communications";
import { isPermissionCode } from "@jormall/domain/identity";
import { localDateTimeToUtc } from "@jormall/domain/timezone";
import { revalidatePath } from "next/cache";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { z } from "zod";

import { beautyResourceKinds } from "../../lib/beauty-resource-kinds";
import { auth } from "../../server/auth";
import {
  aiFoundationRepository,
  aiChannelRepository,
  crmAppointmentRepository,
  communicationRepository,
  copilotRepository,
  identityRepository,
  operationalWorkflowsRepository,
  requireTenantAccess,
  requireTenantPermission,
  schedulingRepository,
} from "../../server/identity";
import { staffCopilotService } from "../../server/copilot";
import { requestAuditDetails } from "../../server/request-context";
import { requireSession } from "../../server/session";

const localeSchema = z.enum(["en", "ar"]);
const uuidSchema = z.uuid();
const shortText = z.string().trim().min(2).max(160);
const optionalText = z.string().trim().max(500).optional();
const optionalLongText = z.string().trim().max(10_000).optional();
const optionalHttpsUrl = z
  .string()
  .trim()
  .max(2048)
  .refine((input) => input === "" || (URL.canParse(input) && new URL(input).protocol === "https:"))
  .optional();
const brandColorSchema = z
  .string()
  .trim()
  .toLowerCase()
  .regex(/^#[0-9a-f]{6}$/u);
const brandLogoUrlSchema = z
  .string()
  .trim()
  .max(2048)
  .refine((input) => {
    if (input === "") return true;
    if (input === "/api/workspace/logo") return true;
    try {
      const url = new URL(input);
      return url.protocol === "https:" && /\.(?:jpe?g|png|webp)$/iu.test(url.pathname);
    } catch {
      return false;
    }
  });

function value(formData: FormData, name: string): unknown {
  return formData.get(name);
}

export async function updateNotificationAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({ id: uuidSchema, state: z.enum(["READ", "UNREAD", "DONE"]) })
    .safeParse({ id: value(formData, "id"), state: value(formData, "state") });
  if (!parsed.success)
    redirect(destination(`/${locale}/notifications`, "error", "VALIDATION_FAILED"));
  try {
    await operationalWorkflowsRepository.setNotificationState(
      await requireTenantAccess(locale),
      parsed.data,
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(`/${locale}/notifications`, "error", errorCode(error)));
  }
  const target =
    typeof value(formData, "target") === "string"
      ? String(value(formData, "target"))
      : `/${locale}/notifications`;
  redirect(target.startsWith(`/${locale}/`) ? target : `/${locale}/notifications`);
}

export async function markAllNotificationsDoneAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  try {
    await operationalWorkflowsRepository.markAllNotificationsDone(
      await requireTenantAccess(locale),
      value(formData, "confirmation") === "CONFIRM_HIGH_PRIORITY"
        ? "CONFIRM_HIGH_PRIORITY"
        : undefined,
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(`/${locale}/notifications`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/notifications?tab=done`, "notice", "NOTIFICATIONS_DONE"));
}

export async function updateChatbotEscalationAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      assignedMembershipId: uuidSchema.optional(),
      expectedVersion: z.coerce.number().int().positive(),
      id: uuidSchema,
      reason: z.string().trim().max(2000).optional(),
      status: z.enum(["NEW", "ACKNOWLEDGED", "IN_PROGRESS", "RESOLVED", "DISMISSED"]),
    })
    .safeParse({
      assignedMembershipId: value(formData, "assignedMembershipId") || undefined,
      expectedVersion: value(formData, "expectedVersion"),
      id: value(formData, "id"),
      reason: value(formData, "reason") || undefined,
      status: value(formData, "status"),
    });
  if (!parsed.success)
    redirect(destination(`/${locale}/inbox/escalations`, "error", "VALIDATION_FAILED"));
  try {
    await operationalWorkflowsRepository.updateEscalation(
      await requireTenantAccess(locale),
      parsed.data,
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(`/${locale}/inbox/escalations`, "error", errorCode(error)));
  }
  redirect(
    destination(
      `/${locale}/inbox/escalations?escalation=${parsed.data.id}`,
      "notice",
      "ESCALATION_UPDATED",
    ),
  );
}

export async function createInventoryProposalAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      branchId: uuidSchema,
      category: z.enum([
        "MATERIAL",
        "CONSUMABLE",
        "SKINCARE_PRODUCT",
        "CLEANING_MATERIAL",
        "EQUIPMENT_SUPPLY",
        "RETAIL_PRODUCT",
        "OTHER",
      ]),
      note: optionalLongText,
      proposedName: shortText,
      reasonNeeded: z.string().trim().max(2000).optional().default(""),
      suggestedQuantity: z.coerce.number().positive(),
      unitOfMeasure: z.string().trim().min(1).max(40),
      urgent: z.boolean(),
    })
    .safeParse({
      branchId: value(formData, "branchId"),
      category: value(formData, "category"),
      note: value(formData, "note") || undefined,
      proposedName: value(formData, "proposedName"),
      reasonNeeded: value(formData, "reasonNeeded") || undefined,
      suggestedQuantity: value(formData, "suggestedQuantity"),
      unitOfMeasure: value(formData, "unitOfMeasure"),
      urgent: value(formData, "urgent") === "on",
    });
  if (!parsed.success)
    redirect(
      destination(`/${locale}/business/inventory?tab=requests`, "error", "VALIDATION_FAILED"),
    );
  try {
    await operationalWorkflowsRepository.createItemProposal(
      await requireTenantAccess(locale),
      parsed.data,
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(`/${locale}/business/inventory?tab=requests`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/business/inventory?tab=requests`, "notice", "PROPOSAL_CREATED"));
}

export async function approveInventoryProposalAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      batchTrackingEnabled: z.boolean().optional(),
      defaultSupplierId: uuidSchema.optional(),
      expectedVersion: z.coerce.number().int().positive(),
      expiryTrackingEnabled: z.boolean().optional(),
      id: uuidSchema,
      minimumStock: z.coerce.number().nonnegative(),
      name: shortText,
      notes: optionalLongText,
      reorderQuantity: z.coerce.number().nonnegative().optional(),
      sku: optionalText,
      supplierName: optionalText,
      supplierPhone: z.string().trim().max(40).optional(),
      unitPrice: z.coerce.number().nonnegative().optional(),
    })
    .safeParse({
      batchTrackingEnabled: value(formData, "batchTrackingEnabled") === "on",
      defaultSupplierId: value(formData, "defaultSupplierId") || undefined,
      expectedVersion: value(formData, "expectedVersion"),
      expiryTrackingEnabled: value(formData, "expiryTrackingEnabled") === "on",
      id: value(formData, "id"),
      minimumStock: value(formData, "minimumStock"),
      name: value(formData, "name"),
      notes: value(formData, "notes") || undefined,
      reorderQuantity: value(formData, "reorderQuantity")
        ? Number(value(formData, "reorderQuantity"))
        : undefined,
      sku: value(formData, "sku") || undefined,
      supplierName: value(formData, "supplierName") || undefined,
      supplierPhone: value(formData, "supplierPhone") || undefined,
      unitPrice: value(formData, "unitPrice") ? Number(value(formData, "unitPrice")) : undefined,
    });
  if (!parsed.success)
    redirect(
      destination(`/${locale}/business/inventory?tab=requests`, "error", "VALIDATION_FAILED"),
    );
  try {
    await operationalWorkflowsRepository.approveItemProposal(
      await requireTenantAccess(locale),
      parsed.data,
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(`/${locale}/business/inventory?tab=requests`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/business/inventory?tab=items`, "notice", "PROPOSAL_APPROVED"));
}

export async function reviewInventoryProposalAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      expectedVersion: z.coerce.number().int().positive(),
      id: uuidSchema,
      reason: z.string().trim().max(2000).optional(),
      status: z.enum(["REJECTED", "MORE_INFO_REQUIRED", "CANCELLED"]),
    })
    .safeParse({
      expectedVersion: value(formData, "expectedVersion"),
      id: value(formData, "id"),
      reason: value(formData, "reason") || undefined,
      status: value(formData, "status"),
    });
  if (!parsed.success)
    redirect(
      destination(`/${locale}/business/inventory?tab=requests`, "error", "VALIDATION_FAILED"),
    );
  try {
    await operationalWorkflowsRepository.reviewItemProposal(
      await requireTenantAccess(locale),
      parsed.data,
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(`/${locale}/business/inventory?tab=requests`, "error", errorCode(error)));
  }
  redirect(
    destination(`/${locale}/business/inventory?tab=requests`, "notice", "PROPOSAL_REVIEWED"),
  );
}

export async function createInventoryOrderAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      branchId: uuidSchema,
      itemId: uuidSchema,
      note: optionalLongText,
      quantity: z.coerce.number().positive(),
      reason: z.string().trim().min(2).max(2000),
      urgency: z.enum(["NORMAL", "URGENT"]),
    })
    .safeParse({
      branchId: value(formData, "branchId"),
      itemId: value(formData, "itemId"),
      note: value(formData, "note") || undefined,
      quantity: value(formData, "quantity"),
      reason: value(formData, "reason"),
      urgency: value(formData, "urgency"),
    });
  if (!parsed.success)
    redirect(destination(`/${locale}/business/inventory?tab=orders`, "error", "VALIDATION_FAILED"));
  try {
    await operationalWorkflowsRepository.createOrderRequest(
      await requireTenantAccess(locale),
      parsed.data,
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(`/${locale}/business/inventory?tab=orders`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/business/inventory?tab=orders`, "notice", "ORDER_REQUESTED"));
}

export async function approveInventoryOrderAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      expectedVersion: z.coerce.number().int().positive(),
      id: uuidSchema,
      note: optionalLongText,
    })
    .safeParse({
      expectedVersion: value(formData, "expectedVersion"),
      id: value(formData, "id"),
      note: value(formData, "note") || undefined,
    });
  if (!parsed.success)
    redirect(destination(`/${locale}/business/inventory?tab=orders`, "error", "VALIDATION_FAILED"));
  try {
    await operationalWorkflowsRepository.approveOrder(
      await requireTenantAccess(locale),
      parsed.data,
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(`/${locale}/business/inventory?tab=orders`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/business/inventory?tab=orders`, "notice", "ORDER_APPROVED"));
}

export async function rejectInventoryOrderAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      expectedVersion: z.coerce.number().int().positive(),
      id: uuidSchema,
      reason: z.string().trim().min(1).max(2000),
    })
    .safeParse({
      expectedVersion: value(formData, "expectedVersion"),
      id: value(formData, "id"),
      reason: value(formData, "reason"),
    });
  if (!parsed.success)
    redirect(destination(`/${locale}/business/inventory?tab=orders`, "error", "VALIDATION_FAILED"));
  try {
    await operationalWorkflowsRepository.rejectOrder(
      await requireTenantAccess(locale),
      parsed.data,
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(`/${locale}/business/inventory?tab=orders`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/business/inventory?tab=orders`, "notice", "ORDER_REJECTED"));
}

export async function markInventoryOrderedAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      expectedDeliveryUnit: z.enum(["HOURS", "DAYS"]),
      expectedDeliveryValue: z.coerce.number().int().positive(),
      expectedVersion: z.coerce.number().int().positive(),
      id: uuidSchema,
      orderedAt: z.coerce.date(),
      orderedQuantity: z.coerce.number().positive(),
      supplierName: shortText,
      supplierReference: optionalText,
    })
    .safeParse({
      expectedDeliveryUnit: value(formData, "expectedDeliveryUnit"),
      expectedDeliveryValue: value(formData, "expectedDeliveryValue"),
      expectedVersion: value(formData, "expectedVersion"),
      id: value(formData, "id"),
      orderedAt: value(formData, "orderedAt"),
      orderedQuantity: value(formData, "orderedQuantity"),
      supplierName: value(formData, "supplierName"),
      supplierReference: value(formData, "supplierReference") || undefined,
    });
  if (!parsed.success)
    redirect(
      destination(`/${locale}/business/inventory?tab=receiving`, "error", "VALIDATION_FAILED"),
    );
  try {
    await operationalWorkflowsRepository.markOrderPlaced(
      await requireTenantAccess(locale),
      parsed.data,
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(`/${locale}/business/inventory?tab=receiving`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/business/inventory?tab=receiving`, "notice", "ORDER_PLACED"));
}

export async function receiveInventoryOrderAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      batchNumber: optionalText,
      expiryDate: z.coerce.date().optional(),
      id: uuidSchema,
      locationId: uuidSchema.optional(),
      note: optionalLongText,
      purchaseCost: z.coerce.number().nonnegative().optional(),
      quantity: z.coerce.number().positive(),
      receivedAt: z.coerce.date(),
      requestKey: uuidSchema,
    })
    .safeParse({
      batchNumber: value(formData, "batchNumber") || undefined,
      expiryDate: value(formData, "expiryDate") || undefined,
      id: value(formData, "id"),
      locationId: value(formData, "locationId") || undefined,
      note: value(formData, "note") || undefined,
      purchaseCost: value(formData, "purchaseCost") || undefined,
      quantity: value(formData, "quantity"),
      receivedAt: value(formData, "receivedAt"),
      requestKey: value(formData, "requestKey"),
    });
  if (!parsed.success)
    redirect(
      destination(`/${locale}/business/inventory?tab=receiving`, "error", "VALIDATION_FAILED"),
    );
  try {
    await operationalWorkflowsRepository.receiveOrder(
      await requireTenantAccess(locale),
      parsed.data,
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(`/${locale}/business/inventory?tab=receiving`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/business/inventory?tab=receiving`, "notice", "ORDER_RECEIVED"));
}

export async function createInventoryLocationAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      branchId: uuidSchema,
      code: optionalText,
      isDefault: z.boolean(),
      name: shortText,
    })
    .safeParse({
      branchId: value(formData, "branchId"),
      code: value(formData, "code") || undefined,
      isDefault: value(formData, "isDefault") === "on",
      name: value(formData, "name"),
    });
  if (!parsed.success) {
    redirect(destination(`/${locale}/business/inventory?tab=items`, "error", "VALIDATION_FAILED"));
  }
  try {
    await operationalWorkflowsRepository.createLocation(
      await requireTenantAccess(locale),
      parsed.data,
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(`/${locale}/business/inventory?tab=items`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/business/inventory?tab=items`, "notice", "LOCATION_CREATED"));
}

export async function createInventorySupplierAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      email: z.string().trim().email().optional(),
      name: shortText,
      notes: optionalLongText,
      phone: z.string().trim().min(1).max(40),
    })
    .safeParse({
      email: value(formData, "email") || undefined,
      name: value(formData, "name"),
      notes: value(formData, "notes") || undefined,
      phone: value(formData, "phone"),
    });
  if (!parsed.success) {
    redirect(destination(`/${locale}/business/inventory?tab=orders`, "error", "VALIDATION_FAILED"));
  }
  try {
    await operationalWorkflowsRepository.createSupplier(
      await requireTenantAccess(locale),
      parsed.data,
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(`/${locale}/business/inventory?tab=orders`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/business/inventory?tab=orders`, "notice", "SUPPLIER_CREATED"));
}

export async function createInventoryItemDirectAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      batchTrackingEnabled: z.boolean(),
      branchId: uuidSchema,
      category: z.enum([
        "MATERIAL",
        "CONSUMABLE",
        "SKINCARE_PRODUCT",
        "CLEANING_MATERIAL",
        "EQUIPMENT_SUPPLY",
        "RETAIL_PRODUCT",
        "OTHER",
      ]),
      currentStock: z.coerce.number().nonnegative().optional(),
      defaultSupplierId: uuidSchema.optional(),
      expiryTrackingEnabled: z.boolean(),
      minimumStock: z.coerce.number().nonnegative(),
      name: shortText,
      notes: optionalLongText,
      reorderQuantity: z.coerce.number().nonnegative().optional(),
      sku: optionalText,
      supplierName: optionalText,
      supplierPhone: z.string().trim().max(40).optional(),
      unitOfMeasure: z.string().trim().min(1).max(40),
      unitPrice: z.coerce.number().nonnegative().optional(),
    })
    .safeParse({
      batchTrackingEnabled: value(formData, "batchTrackingEnabled") === "on",
      branchId: value(formData, "branchId"),
      category: value(formData, "category"),
      currentStock: value(formData, "currentStock")
        ? Number(value(formData, "currentStock"))
        : undefined,
      defaultSupplierId: value(formData, "defaultSupplierId") || undefined,
      expiryTrackingEnabled: value(formData, "expiryTrackingEnabled") === "on",
      minimumStock: value(formData, "minimumStock"),
      name: value(formData, "name"),
      notes: value(formData, "notes") || undefined,
      reorderQuantity: value(formData, "reorderQuantity")
        ? Number(value(formData, "reorderQuantity"))
        : undefined,
      sku: value(formData, "sku") || undefined,
      supplierName: value(formData, "supplierName") || undefined,
      supplierPhone: value(formData, "supplierPhone") || undefined,
      unitOfMeasure: value(formData, "unitOfMeasure"),
      unitPrice: value(formData, "unitPrice") ? Number(value(formData, "unitPrice")) : undefined,
    });
  if (!parsed.success) {
    redirect(destination(`/${locale}/business/inventory?tab=items`, "error", "VALIDATION_FAILED"));
  }
  try {
    await operationalWorkflowsRepository.createItemDirect(
      await requireTenantAccess(locale),
      parsed.data,
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(`/${locale}/business/inventory?tab=items`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/business/inventory?tab=items`, "notice", "ITEM_CREATED"));
}

export async function updateInventoryItemAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      batchTrackingEnabled: z.boolean().optional(),
      defaultSupplierId: uuidSchema.optional(),
      expectedVersion: z.coerce.number().int().positive(),
      expiryTrackingEnabled: z.boolean().optional(),
      id: uuidSchema,
      isActive: z.boolean().optional(),
      minimumStock: z.coerce.number().nonnegative().optional(),
      name: shortText.optional(),
      notes: optionalLongText,
      reorderQuantity: z.coerce.number().nonnegative().optional(),
      sku: optionalText,
      unitOfMeasure: z.string().trim().min(1).max(40).optional(),
    })
    .safeParse({
      batchTrackingEnabled: formData.has("batchTrackingEnabled")
        ? value(formData, "batchTrackingEnabled") === "on"
        : undefined,
      defaultSupplierId: value(formData, "defaultSupplierId") || undefined,
      expectedVersion: value(formData, "expectedVersion"),
      expiryTrackingEnabled: formData.has("expiryTrackingEnabled")
        ? value(formData, "expiryTrackingEnabled") === "on"
        : undefined,
      id: value(formData, "id"),
      isActive: formData.has("isActive") ? value(formData, "isActive") === "on" : undefined,
      minimumStock: value(formData, "minimumStock")
        ? Number(value(formData, "minimumStock"))
        : undefined,
      name: value(formData, "name") || undefined,
      notes: value(formData, "notes") || undefined,
      reorderQuantity: value(formData, "reorderQuantity")
        ? Number(value(formData, "reorderQuantity"))
        : undefined,
      sku: value(formData, "sku") || undefined,
      unitOfMeasure: value(formData, "unitOfMeasure") || undefined,
    });
  if (!parsed.success) {
    redirect(destination(`/${locale}/business/inventory?tab=items`, "error", "VALIDATION_FAILED"));
  }
  try {
    await operationalWorkflowsRepository.updateItem(
      await requireTenantAccess(locale),
      parsed.data,
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(`/${locale}/business/inventory?tab=items`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/business/inventory?tab=items`, "notice", "ITEM_UPDATED"));
}

export async function transferInventoryStockAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      batchId: uuidSchema.optional(),
      branchId: uuidSchema,
      fromLocationId: uuidSchema,
      itemId: uuidSchema,
      quantity: z.coerce.number().positive(),
      reason: z.string().trim().min(1).max(2000),
      toLocationId: uuidSchema,
    })
    .safeParse({
      batchId: value(formData, "batchId") || undefined,
      branchId: value(formData, "branchId"),
      fromLocationId: value(formData, "fromLocationId"),
      itemId: value(formData, "itemId"),
      quantity: value(formData, "quantity"),
      reason: value(formData, "reason"),
      toLocationId: value(formData, "toLocationId"),
    });
  if (!parsed.success) {
    redirect(
      destination(`/${locale}/business/inventory?tab=movements`, "error", "VALIDATION_FAILED"),
    );
  }
  try {
    await operationalWorkflowsRepository.transferStock(
      await requireTenantAccess(locale),
      parsed.data,
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(`/${locale}/business/inventory?tab=movements`, "error", errorCode(error)));
  }
  redirect(
    destination(`/${locale}/business/inventory?tab=movements`, "notice", "STOCK_TRANSFERRED"),
  );
}

export async function adjustInventoryStockAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      batchId: uuidSchema.optional(),
      branchId: uuidSchema,
      itemId: uuidSchema,
      locationId: uuidSchema,
      movementType: z.enum([
        "EXPIRED",
        "DAMAGED",
        "LOST",
        "SPILLED",
        "RETURN_TO_SUPPLIER",
        "MANUAL_CORRECTION",
      ]),
      quantityChange: z.coerce.number(),
      reason: z.string().trim().min(1).max(2000),
    })
    .safeParse({
      batchId: value(formData, "batchId") || undefined,
      branchId: value(formData, "branchId"),
      itemId: value(formData, "itemId"),
      locationId: value(formData, "locationId"),
      movementType: value(formData, "movementType"),
      quantityChange: value(formData, "quantityChange"),
      reason: value(formData, "reason"),
    });
  if (!parsed.success) {
    redirect(
      destination(`/${locale}/business/inventory?tab=movements`, "error", "VALIDATION_FAILED"),
    );
  }
  try {
    await operationalWorkflowsRepository.adjustStock(
      await requireTenantAccess(locale),
      parsed.data,
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(`/${locale}/business/inventory?tab=movements`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/business/inventory?tab=movements`, "notice", "STOCK_ADJUSTED"));
}

export async function manageServiceRequirementAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const actionType =
    typeof value(formData, "actionType") === "string" ? String(value(formData, "actionType")) : "";
  const rawReturnTo = value(formData, "returnTo");
  const returnTo =
    typeof rawReturnTo === "string" && rawReturnTo.length > 0
      ? rawReturnTo
      : `/${locale}/business/inventory?tab=items`;
  if (actionType === "REMOVE") {
    const rawId = value(formData, "id");
    const id = typeof rawId === "string" ? rawId : "";
    if (!id) redirect(destination(returnTo, "error", "VALIDATION_FAILED"));
    try {
      await operationalWorkflowsRepository.removeServiceRequirement(
        await requireTenantAccess(locale),
        { id },
        await requestAuditDetails(),
      );
    } catch (error) {
      redirect(destination(returnTo, "error", errorCode(error)));
    }
    redirect(destination(returnTo, "notice", "REQUIREMENT_REMOVED"));
  } else {
    const parsed = z
      .object({
        expectedQuantity: z.coerce.number().positive(),
        isRequired: z.boolean(),
        itemId: uuidSchema,
        reservationMode: z.enum(["NONE", "FORECAST_ONLY", "RESERVE_ON_CONFIRMATION"]),
        serviceId: uuidSchema,
        unitOfMeasure: z.string().trim().min(1).max(40),
      })
      .safeParse({
        expectedQuantity: value(formData, "expectedQuantity"),
        isRequired: value(formData, "isRequired") === "on",
        itemId: value(formData, "itemId"),
        reservationMode: value(formData, "reservationMode"),
        serviceId: value(formData, "serviceId"),
        unitOfMeasure: value(formData, "unitOfMeasure"),
      });
    if (!parsed.success) {
      redirect(destination(returnTo, "error", "VALIDATION_FAILED"));
    }
    try {
      await operationalWorkflowsRepository.addServiceRequirement(
        await requireTenantAccess(locale),
        parsed.data,
        await requestAuditDetails(),
      );
    } catch (error) {
      redirect(destination(returnTo, "error", errorCode(error)));
    }
    redirect(destination(returnTo, "notice", "REQUIREMENT_SAVED"));
  }
}

function localeFrom(formData: FormData): "en" | "ar" {
  return localeSchema.catch("en").parse(value(formData, "locale"));
}

function errorCode(error: unknown): string {
  if (error instanceof DomainError) {
    if (error.metadata?.reason === "APPOINTMENT_TIME_PASSED") {
      return "APPOINTMENT_TIME_PASSED";
    }
    if (error.metadata?.reason === "WAITLIST_TIME_INVALID") {
      return "WAITLIST_TIME_INVALID";
    }
    return error.code;
  }
  return "INTERNAL_ERROR";
}

function destination(path: string, key: "error" | "notice", code: string): string {
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}${key}=${encodeURIComponent(code)}`;
}

function safeScheduleReturn(
  locale: "ar" | "en",
  candidate: string | undefined,
): string | undefined {
  if (!candidate) return undefined;
  try {
    const parsed = new URL(candidate, "https://jormall.invalid");
    return parsed.origin === "https://jormall.invalid" &&
      parsed.pathname.startsWith(`/${locale}/schedule/`)
      ? `${parsed.pathname}${parsed.search}`
      : undefined;
  } catch {
    return undefined;
  }
}

export async function loginAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const requestedReturnTo = z.string().max(500).catch("").parse(value(formData, "returnTo"));
  const returnTo =
    requestedReturnTo.startsWith(`/${locale}/`) && !requestedReturnTo.startsWith(`/${locale}//`)
      ? requestedReturnTo
      : `/${locale}/dashboard`;
  const result = z
    .object({ email: z.email().trim().toLowerCase(), password: z.string().min(1).max(128) })
    .safeParse({ email: value(formData, "email"), password: value(formData, "password") });
  if (!result.success) {
    redirect(destination(`/${locale}/login`, "error", "INVALID_CREDENTIALS"));
  }
  try {
    const signedIn = await auth.api.signInEmail({ body: result.data, headers: await headers() });
    const memberships = await identityRepository.listMembershipChoices(signedIn.user.id);
    const activeMemberships = memberships.filter(
      (membership) =>
        membership.status === MembershipStatus.ACTIVE &&
        membership.organization.status === OrganizationStatus.ACTIVE,
    );
    const onlyMembership = activeMemberships.length === 1 ? activeMemberships[0] : undefined;
    if (onlyMembership) {
      const resolvedMembership = await identityRepository.resolveMembershipForSwitch(
        signedIn.user.id,
        onlyMembership.id,
      );
      await prisma.session.updateMany({
        data: {
          activeBranchId: null,
          activeMembershipId: resolvedMembership.id,
          activeOrganizationId: resolvedMembership.organizationId,
          activeSupportAccessId: null,
        },
        where: { token: signedIn.token, userId: signedIn.user.id },
      });
    }
  } catch {
    redirect(destination(`/${locale}/login`, "error", "INVALID_CREDENTIALS"));
  }
  redirect(returnTo);
}

export async function logoutAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  await auth.api.signOut({ headers: await headers() });
  redirect(destination(`/${locale}/login`, "notice", "SIGNED_OUT"));
}

export async function changePasswordAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      confirmPassword: z.string().min(12).max(128),
      currentPassword: z.string().min(1).max(128),
      newPassword: z.string().min(12).max(128),
    })
    .refine(({ confirmPassword, newPassword }) => confirmPassword === newPassword, {
      path: ["confirmPassword"],
    })
    .refine(({ currentPassword, newPassword }) => currentPassword !== newPassword, {
      path: ["newPassword"],
    })
    .safeParse({
      confirmPassword: value(formData, "confirmPassword"),
      currentPassword: value(formData, "currentPassword"),
      newPassword: value(formData, "newPassword"),
    });
  const target = `/${locale}/account/security`;
  if (!parsed.success) redirect(destination(target, "error", "PASSWORD_CHANGE_INVALID"));
  try {
    const session = await requireSession(locale);
    const changed = await auth.api.changePassword({
      body: {
        currentPassword: parsed.data.currentPassword,
        newPassword: parsed.data.newPassword,
        revokeOtherSessions: true,
      },
      headers: await headers(),
    });
    if (changed.token) {
      await prisma.session.updateMany({
        data: {
          activeBranchId: session.session.activeBranchId ?? null,
          activeMembershipId: session.session.activeMembershipId ?? null,
          activeOrganizationId: session.session.activeOrganizationId ?? null,
          activeSupportAccessId: session.session.activeSupportAccessId ?? null,
        },
        where: { token: changed.token, userId: session.user.id },
      });
    }
  } catch {
    redirect(destination(target, "error", "PASSWORD_CHANGE_FAILED"));
  }
  redirect(destination(target, "notice", "PASSWORD_CHANGED"));
}

export async function switchOrganizationAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = uuidSchema.safeParse(value(formData, "membershipId"));
  if (!parsed.success) {
    redirect(destination(`/${locale}/dashboard`, "error", "VALIDATION_FAILED"));
  }
  const session = await requireSession(locale);
  try {
    const membership = await identityRepository.resolveMembershipForSwitch(
      session.user.id,
      parsed.data,
    );
    await prisma.session.update({
      data: {
        activeBranchId: null,
        activeMembershipId: membership.id,
        activeOrganizationId: membership.organizationId,
        activeSupportAccessId: null,
      },
      where: { id: session.session.id },
    });
    revalidatePath(`/${locale}/dashboard`, "layout");
  } catch (error) {
    redirect(destination(`/${locale}/dashboard`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/dashboard`, "notice", "ORGANIZATION_SWITCHED"));
}

export async function switchBranchAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .strictObject({
      branchId: uuidSchema,
      locale: localeSchema,
      returnTo: z.string().max(500),
    })
    .safeParse(
      Object.fromEntries(
        [...formData.entries()].filter(([fieldName]) => !fieldName.startsWith("$ACTION_")),
      ),
    );
  if (!parsed.success) {
    redirect(destination(`/${locale}/dashboard`, "error", "VALIDATION_FAILED"));
  }
  const returnTo = parsed.data.returnTo.startsWith(`/${locale}/`)
    ? parsed.data.returnTo
    : `/${locale}/dashboard`;
  try {
    const session = await requireSession(locale);
    const access = await requireTenantAccess(locale);
    const permittedBranches = await identityRepository.listBranches(access);
    if (!permittedBranches.some((branch) => branch.id === parsed.data.branchId)) {
      throw new DomainError({ code: "NOT_FOUND", message: "Branch was not found." });
    }
    await prisma.session.update({
      data: { activeBranchId: parsed.data.branchId },
      where: { id: session.session.id, userId: session.user.id },
    });
  } catch (error) {
    redirect(destination(returnTo, "error", errorCode(error)));
  }
  redirect(returnTo);
}

export type InvitationCreationState = Readonly<{
  code?: string | undefined;
  invitationUrl?: string | undefined;
}>;

export async function createOrganizationAction(
  _previousState: InvitationCreationState,
  formData: FormData,
): Promise<InvitationCreationState> {
  const locale = localeFrom(formData);
  const submittedFields = Object.fromEntries(
    [...formData.entries()].filter(([fieldName]) => !fieldName.startsWith("$ACTION_")),
  );
  const parsed = z
    .strictObject({
      locale: localeSchema,
      nameAr: shortText,
      nameEn: shortText,
      ownerEmail: z.email().trim().toLowerCase(),
      slug: z
        .string()
        .trim()
        .toLowerCase()
        .regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/)
        .max(80),
    })
    .safeParse(submittedFields);
  if (!parsed.success) {
    return { code: "VALIDATION_FAILED" };
  }
  const session = await requireSession(locale);
  try {
    await identityRepository.assertSuperAdmin(session.user.id);
    const created = await identityRepository.createOrganization(session.user.id, parsed.data);
    revalidatePath(`/${locale}/platform/organizations`);
    return {
      code: "ORGANIZATION_CREATED",
      invitationUrl: `${process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000"}/${locale}/invitations/${created.invitationToken}`,
    };
  } catch (error) {
    return { code: errorCode(error) };
  }
}

export async function setOrganizationStatusAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      organizationId: uuidSchema,
      reason: optionalText,
      status: z.enum([OrganizationStatus.ACTIVE, OrganizationStatus.SUSPENDED]),
    })
    .safeParse({
      organizationId: value(formData, "organizationId"),
      reason: value(formData, "reason") || undefined,
      status: value(formData, "status"),
    });
  if (!parsed.success) {
    redirect(destination(`/${locale}/platform/organizations`, "error", "VALIDATION_FAILED"));
  }
  const session = await requireSession(locale);
  try {
    await identityRepository.assertSuperAdmin(session.user.id);
    await identityRepository.setOrganizationStatus(
      session.user.id,
      parsed.data.organizationId,
      parsed.data.status,
      parsed.data.reason,
    );
  } catch (error) {
    redirect(destination(`/${locale}/platform/organizations`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/platform/organizations`, "notice", "STATUS_UPDATED"));
}

export async function startSupportAccessAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({ organizationId: uuidSchema, reason: z.string().trim().min(10).max(500) })
    .safeParse({
      organizationId: value(formData, "organizationId"),
      reason: value(formData, "reason"),
    });
  if (!parsed.success) {
    redirect(destination(`/${locale}/platform/organizations`, "error", "VALIDATION_FAILED"));
  }
  const session = await requireSession(locale);
  try {
    const supportAccessId = await identityRepository.startSupportAccess(
      session.user.id,
      parsed.data.organizationId,
      parsed.data.reason,
      await requestAuditDetails(),
    );
    await prisma.session.update({
      data: {
        activeBranchId: null,
        activeMembershipId: null,
        activeOrganizationId: parsed.data.organizationId,
        activeSupportAccessId: supportAccessId,
      },
      where: { id: session.session.id },
    });
  } catch (error) {
    redirect(destination(`/${locale}/platform/organizations`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/dashboard`, "notice", "SUPPORT_STARTED"));
}

export async function endSupportAccessAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const session = await requireSession(locale);
  if (session.session.activeSupportAccessId) {
    await identityRepository.revokeSupportAccess(
      session.user.id,
      session.session.activeSupportAccessId,
      await requestAuditDetails(),
    );
  }
  await prisma.session.update({
    data: {
      activeBranchId: null,
      activeMembershipId: null,
      activeOrganizationId: null,
      activeSupportAccessId: null,
    },
    where: { id: session.session.id },
  });
  redirect(destination(`/${locale}/platform/organizations`, "notice", "SUPPORT_ENDED"));
}

export async function updateSettingsAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      bookingWindowDays: z.preprocess(
        (input) => (input === "" || input === null ? null : input),
        z.coerce.number().int().min(1).max(730).nullable(),
      ),
      brandAccentColor: brandColorSchema,
      brandLogoUrl: brandLogoUrlSchema,
      brandPrimaryColor: brandColorSchema,
      currency: z.string().trim().toUpperCase().length(3),
      defaultLocale: z.enum([SupportedLocale.en, SupportedLocale.ar]),
      cancellationWindowMins: z.coerce.number().int().min(0).max(525_600),
      confirmationEnabled: z.boolean(),
      defaultAppointmentStatus: z.enum([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]),
      noShowPolicyAr: optionalLongText,
      noShowPolicyEn: optionalLongText,
      reminderLeadMins: z.coerce.number().int().min(0).max(525_600),
      secondaryReminderLeadMins: z.preprocess(
        (input) => (input === "" || input === null ? null : input),
        z.coerce.number().int().min(0).max(525_600).nullable(),
      ),
      returnSection: z.enum(["organization", "branding", "booking-rules"]),
      rescheduleWindowMins: z.coerce.number().int().min(0).max(525_600),
      timezone: z.string().trim().min(3).max(100),
    })
    .strict()
    .safeParse({
      bookingWindowDays: value(formData, "bookingWindowDays"),
      brandAccentColor: value(formData, "brandAccentColor"),
      brandLogoUrl: value(formData, "brandLogoUrl"),
      brandPrimaryColor: value(formData, "brandPrimaryColor"),
      currency: value(formData, "currency"),
      defaultLocale: value(formData, "defaultLocale"),
      cancellationWindowMins: value(formData, "cancellationWindowMins"),
      confirmationEnabled: value(formData, "confirmationEnabled") === "on",
      defaultAppointmentStatus: value(formData, "defaultAppointmentStatus"),
      noShowPolicyAr: value(formData, "noShowPolicyAr") || undefined,
      noShowPolicyEn: value(formData, "noShowPolicyEn") || undefined,
      reminderLeadMins: value(formData, "reminderLeadMins"),
      secondaryReminderLeadMins: value(formData, "secondaryReminderLeadMins"),
      returnSection: value(formData, "returnSection"),
      rescheduleWindowMins: value(formData, "rescheduleWindowMins"),
      timezone: value(formData, "timezone"),
    });
  if (!parsed.success) {
    redirect(destination(`/${locale}/settings/organization`, "error", "VALIDATION_FAILED"));
  }
  const { returnSection, ...settings } = parsed.data;
  try {
    const access = await requireTenantPermission(locale, "organization.settings.manage");
    await identityRepository.updateSettings(access, {
      ...settings,
      brandLogoUrl: settings.brandLogoUrl || null,
      noShowPolicyAr: settings.noShowPolicyAr ?? null,
      noShowPolicyEn: settings.noShowPolicyEn ?? null,
    });
  } catch (error) {
    redirect(destination(`/${locale}/settings/${returnSection}`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/settings/${returnSection}`, "notice", "SETTINGS_UPDATED"));
}

export async function createBranchAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      addressAr: optionalText,
      addressEn: optionalText,
      email: z.email().trim().toLowerCase().optional(),
      mapUrl: optionalHttpsUrl,
      mobilePhone: z.string().trim().max(40).optional(),
      nameAr: shortText,
      nameEn: shortText,
      phone: z.string().trim().max(40).optional(),
      timezone: z.string().trim().min(3).max(100),
    })
    .strict()
    .safeParse({
      addressAr: value(formData, "addressAr") || undefined,
      addressEn: value(formData, "addressEn") || undefined,
      email: value(formData, "email") || undefined,
      mapUrl: value(formData, "mapUrl") || undefined,
      mobilePhone: value(formData, "mobilePhone") || undefined,
      nameAr: value(formData, "nameAr"),
      nameEn: value(formData, "nameEn"),
      phone: value(formData, "phone") || undefined,
      timezone: value(formData, "timezone"),
    });
  if (!parsed.success) {
    redirect(destination(`/${locale}/business/branches`, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantPermission(locale, "branches.manage");
    await identityRepository.createBranch(access, parsed.data);
  } catch (error) {
    redirect(destination(`/${locale}/business/branches`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/business/branches`, "notice", "BRANCH_CREATED"));
}

export async function deleteBranchAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const branchId = uuidSchema.safeParse(value(formData, "branchId"));
  if (!branchId.success) {
    redirect(destination(`/${locale}/dashboard/branches`, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantPermission(locale, "branches.manage");
    const deleted = await identityRepository.deleteBranch(access, branchId.data);
    if (!deleted) {
      throw new DomainError({ code: "NOT_FOUND", message: "Branch not found." });
    }
  } catch (error) {
    redirect(destination(`/${locale}/dashboard/branches`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/dashboard/branches`, "notice", "BRANCH_DELETED"));
}

export async function updateBranchAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      addressAr: optionalText,
      addressEn: optionalText,
      branchId: uuidSchema,
      email: z.email().trim().toLowerCase().optional(),
      mapUrl: optionalHttpsUrl,
      mobilePhone: z.string().trim().max(40).optional(),
      nameAr: shortText,
      nameEn: shortText,
      phone: z.string().trim().max(40).optional(),
      timezone: z.string().trim().min(3).max(100),
    })
    .strict()
    .safeParse({
      addressAr: value(formData, "addressAr") || undefined,
      addressEn: value(formData, "addressEn") || undefined,
      branchId: value(formData, "branchId"),
      email: value(formData, "email") || undefined,
      mapUrl: value(formData, "mapUrl") || undefined,
      mobilePhone: value(formData, "mobilePhone") || undefined,
      nameAr: value(formData, "nameAr"),
      nameEn: value(formData, "nameEn"),
      phone: value(formData, "phone") || undefined,
      timezone: value(formData, "timezone"),
    });
  if (!parsed.success) {
    redirect(destination(`/${locale}/business/branches`, "error", "VALIDATION_FAILED"));
  }
  const { branchId, ...input } = parsed.data;
  try {
    const access = await requireTenantPermission(locale, "branches.manage");
    await identityRepository.updateBranch(access, branchId, input);
  } catch (error) {
    redirect(destination(`/${locale}/business/branches`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/business/branches`, "notice", "BRANCH_UPDATED"));
}

export async function createInvitationAction(
  _previousState: InvitationCreationState,
  formData: FormData,
): Promise<InvitationCreationState> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({ email: z.email().trim().toLowerCase(), roleId: uuidSchema })
    .safeParse({ email: value(formData, "email"), roleId: value(formData, "roleId") });
  if (!parsed.success) {
    return { code: "VALIDATION_FAILED" };
  }
  try {
    const access = await requireTenantPermission(locale, "staff.manage");
    const targetRole = (await identityRepository.listRoles(access)).find(
      (role) => role.id === parsed.data.roleId,
    );
    if (!targetRole) {
      throw new DomainError({ code: "NOT_FOUND", message: "Role not found." });
    }
    if (targetRole.systemKey !== "SECRETARY" && targetRole.systemKey !== "PROVIDER") {
      requirePermission(access, "roles.manage");
    }
    const token = await identityRepository.createInvitation(
      access,
      parsed.data.email,
      parsed.data.roleId,
    );
    revalidatePath(`/${locale}/dashboard/staff`);
    return {
      code: "INVITATION_CREATED",
      invitationUrl: `${process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000"}/${locale}/invitations/${token}`,
    };
  } catch (error) {
    return { code: errorCode(error) };
  }
}

export async function revokeInvitationAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const invitationId = uuidSchema.safeParse(value(formData, "invitationId"));
  if (!invitationId.success) {
    redirect(destination(`/${locale}/dashboard/staff`, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantPermission(locale, "staff.manage");
    await identityRepository.revokeInvitation(access, invitationId.data);
  } catch (error) {
    redirect(destination(`/${locale}/dashboard/staff`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/dashboard/staff`, "notice", "INVITATION_REVOKED"));
}

export async function setMembershipStatusAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      membershipId: uuidSchema,
      status: z.enum([
        MembershipStatus.ACTIVE,
        MembershipStatus.SUSPENDED,
        MembershipStatus.REVOKED,
      ]),
    })
    .safeParse({
      membershipId: value(formData, "membershipId"),
      status: value(formData, "status"),
    });
  if (!parsed.success) {
    redirect(destination(`/${locale}/dashboard/staff`, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantPermission(locale, "staff.manage");
    if (access.membershipId === parsed.data.membershipId) {
      throw new DomainError({ code: "CONFLICT", message: "You cannot suspend yourself." });
    }
    const target = (await identityRepository.listStaff(access)).find(
      (membership) => membership.id === parsed.data.membershipId,
    );
    if (!target) {
      throw new DomainError({ code: "NOT_FOUND", message: "Membership not found." });
    }
    if (target.roles.some(({ role }) => role.systemKey === "ORGANIZATION_OWNER")) {
      requirePermission(access, "roles.manage");
    }
    await identityRepository.setMembershipStatus(
      access,
      parsed.data.membershipId,
      parsed.data.status,
    );
  } catch (error) {
    redirect(destination(`/${locale}/dashboard/staff`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/dashboard/staff`, "notice", "MEMBERSHIP_UPDATED"));
}

export async function replaceMembershipRoleAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z.object({ membershipId: uuidSchema, roleId: uuidSchema }).safeParse({
    membershipId: value(formData, "membershipId"),
    roleId: value(formData, "roleId"),
  });
  if (!parsed.success) {
    redirect(destination(`/${locale}/dashboard/staff`, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantPermission(locale, "roles.manage");
    const [roles, staff] = await Promise.all([
      identityRepository.listRoles(access),
      identityRepository.listStaff(access),
    ]);
    const targetRole = roles.find((role) => role.id === parsed.data.roleId);
    const targetMembership = staff.find((membership) => membership.id === parsed.data.membershipId);
    if (!targetRole || !targetMembership) {
      throw new DomainError({ code: "NOT_FOUND", message: "Role or membership not found." });
    }
    for (const { permission } of targetRole.permissions) {
      if (!isPermissionCode(permission.code)) {
        throw new DomainError({ code: "VALIDATION_FAILED", message: "Unknown permission." });
      }
      requirePermission(access, permission.code);
    }
    const changesOwnerRole =
      targetRole.systemKey === "ORGANIZATION_OWNER" ||
      targetMembership.roles.some(({ role }) => role.systemKey === "ORGANIZATION_OWNER");
    if (changesOwnerRole) {
      throw new DomainError({
        code: "FORBIDDEN",
        message: "The organization owner role cannot be reassigned from this workflow.",
      });
    }
    await identityRepository.replaceMembershipRole(
      access,
      parsed.data.membershipId,
      parsed.data.roleId,
    );
  } catch (error) {
    redirect(destination(`/${locale}/dashboard/staff`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/dashboard/staff`, "notice", "MEMBERSHIP_UPDATED"));
}

export async function createRoleAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      nameAr: shortText,
      nameEn: shortText,
      permissionCodes: z.array(z.string()).min(1),
    })
    .safeParse({
      nameAr: value(formData, "nameAr"),
      nameEn: value(formData, "nameEn"),
      permissionCodes: formData.getAll("permissionCodes"),
    });
  if (!parsed.success) {
    redirect(destination(`/${locale}/business/roles-access`, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantPermission(locale, "roles.manage");
    const delegationResource = {
      ...(access.assignedBranchIds[0] ? { branchId: access.assignedBranchIds[0] } : {}),
      ...(access.staffProfileId ? { staffProfileId: access.staffProfileId } : {}),
    };
    for (const permission of parsed.data.permissionCodes) {
      if (!isPermissionCode(permission)) {
        throw new DomainError({ code: "VALIDATION_FAILED", message: "Unknown permission." });
      }
      requirePermission(access, permission, delegationResource);
    }
    await identityRepository.createRole(access, {
      ...parsed.data,
      key: `CUSTOM_${randomUUID().replaceAll("-", "").slice(0, 20).toUpperCase()}`,
    });
  } catch (error) {
    redirect(destination(`/${locale}/business/roles-access`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/business/roles-access`, "notice", "ROLE_CREATED"));
}

export async function updateRoleAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      nameAr: shortText,
      nameEn: shortText,
      permissionCodes: z.array(z.string()).min(1),
      roleId: uuidSchema,
    })
    .safeParse({
      nameAr: value(formData, "nameAr"),
      nameEn: value(formData, "nameEn"),
      permissionCodes: formData.getAll("permissionCodes"),
      roleId: value(formData, "roleId"),
    });
  const target = `/${locale}/business/roles-access`;
  if (!parsed.success) {
    redirect(destination(target, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantPermission(locale, "roles.manage");
    const delegationResource = {
      ...(access.assignedBranchIds[0] ? { branchId: access.assignedBranchIds[0] } : {}),
      ...(access.staffProfileId ? { staffProfileId: access.staffProfileId } : {}),
    };
    for (const permission of parsed.data.permissionCodes) {
      if (!isPermissionCode(permission)) {
        throw new DomainError({ code: "VALIDATION_FAILED", message: "Unknown permission." });
      }
      requirePermission(access, permission, delegationResource);
    }
    await identityRepository.updateRole(access, parsed.data.roleId, parsed.data);
  } catch (error) {
    redirect(destination(target, "error", errorCode(error)));
  }
  revalidatePath(target);
  redirect(destination(target, "notice", "ROLE_UPDATED"));
}

export async function deleteRoleAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({ confirmation: z.literal("DELETE_CUSTOM_ROLE"), roleId: uuidSchema })
    .safeParse({
      confirmation: value(formData, "confirmation"),
      roleId: value(formData, "roleId"),
    });
  const target = `/${locale}/business/roles-access`;
  if (!parsed.success) {
    redirect(destination(target, "error", "VALIDATION_FAILED"));
  }
  try {
    await identityRepository.deleteRole(
      await requireTenantPermission(locale, "roles.manage"),
      parsed.data.roleId,
    );
  } catch (error) {
    redirect(destination(target, "error", errorCode(error)));
  }
  revalidatePath(target);
  redirect(destination(target, "notice", "ROLE_DELETED"));
}

export async function createServiceAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      currency: z.string().trim().toUpperCase().length(3),
      category: z.string().trim().min(2).max(120),
      defaultDurationMins: z.coerce.number().int().min(1).max(1440),
      defaultPriceMinor: z.coerce.number().int().min(0).optional(),
      descriptionAr: optionalLongText,
      descriptionEn: optionalLongText,
      isOnlineBookable: z.boolean(),
      minimumNoticeMins: z.preprocess(
        (input) => (input === "" || input === null ? null : input),
        z.coerce.number().int().min(0).max(525_600).nullable(),
      ),
      nameAr: shortText,
      nameEn: shortText,
      postTreatmentInstructionsAr: optionalLongText,
      postTreatmentInstructionsEn: optionalLongText,
      preTreatmentInstructionsAr: optionalLongText,
      preTreatmentInstructionsEn: optionalLongText,
    })
    .strict()
    .safeParse({
      currency: value(formData, "currency"),
      category: value(formData, "category"),
      defaultDurationMins: value(formData, "defaultDurationMins"),
      defaultPriceMinor: value(formData, "defaultPriceMinor") || undefined,
      descriptionAr: value(formData, "descriptionAr") || undefined,
      descriptionEn: value(formData, "descriptionEn") || undefined,
      isOnlineBookable: value(formData, "isOnlineBookable") === "on",
      minimumNoticeMins: value(formData, "minimumNoticeMins"),
      nameAr: value(formData, "nameAr"),
      nameEn: value(formData, "nameEn"),
      postTreatmentInstructionsAr: value(formData, "postTreatmentInstructionsAr") || undefined,
      postTreatmentInstructionsEn: value(formData, "postTreatmentInstructionsEn") || undefined,
      preTreatmentInstructionsAr: value(formData, "preTreatmentInstructionsAr") || undefined,
      preTreatmentInstructionsEn: value(formData, "preTreatmentInstructionsEn") || undefined,
    });
  if (!parsed.success) {
    redirect(destination(`/${locale}/business/services`, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantPermission(locale, "services.manage");
    await identityRepository.createService(access, parsed.data);
  } catch (error) {
    redirect(destination(`/${locale}/business/services`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/business/services`, "notice", "SERVICE_CREATED"));
}

export async function updateServiceAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      category: z.string().trim().min(2).max(120),
      configurationStatus: z.enum(["DRAFT", "APPROVED"]),
      defaultDurationMins: z.coerce.number().int().min(1).max(1440),
      descriptionAr: z.string().trim().max(10_000),
      descriptionEn: z.string().trim().max(10_000),
      isActive: z.boolean(),
      isOnlineBookable: z.boolean(),
      minimumNoticeMins: z.preprocess(
        (input) => (input === "" || input === null ? null : input),
        z.coerce.number().int().min(0).max(525_600).nullable(),
      ),
      nameAr: shortText,
      nameEn: shortText,
      postTreatmentInstructionsAr: z.string().trim().max(10_000),
      postTreatmentInstructionsEn: z.string().trim().max(10_000),
      preTreatmentInstructionsAr: z.string().trim().max(10_000),
      preTreatmentInstructionsEn: z.string().trim().max(10_000),
      serviceId: uuidSchema,
    })
    .strict()
    .safeParse({
      category: value(formData, "category"),
      configurationStatus: value(formData, "configurationStatus"),
      defaultDurationMins: value(formData, "defaultDurationMins"),
      descriptionAr: value(formData, "descriptionAr") ?? "",
      descriptionEn: value(formData, "descriptionEn") ?? "",
      isActive: value(formData, "isActive") === "on",
      isOnlineBookable: value(formData, "isOnlineBookable") === "on",
      minimumNoticeMins: value(formData, "minimumNoticeMins"),
      nameAr: value(formData, "nameAr"),
      nameEn: value(formData, "nameEn"),
      postTreatmentInstructionsAr: value(formData, "postTreatmentInstructionsAr") ?? "",
      postTreatmentInstructionsEn: value(formData, "postTreatmentInstructionsEn") ?? "",
      preTreatmentInstructionsAr: value(formData, "preTreatmentInstructionsAr") ?? "",
      preTreatmentInstructionsEn: value(formData, "preTreatmentInstructionsEn") ?? "",
      serviceId: value(formData, "serviceId"),
    });
  const fallback = `/${locale}/business/services`;
  if (!parsed.success) redirect(destination(fallback, "error", "VALIDATION_FAILED"));
  try {
    const { serviceId, ...input } = parsed.data;
    await identityRepository.updateService(
      await requireTenantPermission(locale, "services.manage"),
      serviceId,
      input,
    );
  } catch (error) {
    redirect(destination(fallback, "error", errorCode(error)));
  }
  revalidatePath(fallback);
  redirect(destination(fallback, "notice", "SERVICE_UPDATED"));
}

export async function configureServiceBranchAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      branchId: uuidSchema,
      bookingWindowDays: z.coerce.number().int().min(1).max(730).optional(),
      bufferAfterMins: z.coerce.number().int().min(0).max(1440),
      bufferBeforeMins: z.coerce.number().int().min(0).max(1440),
      durationMins: z.coerce.number().int().min(1).max(1440).optional(),
      isEnabled: z.boolean(),
      priceMinor: z.coerce.number().int().min(0).optional(),
      serviceId: uuidSchema,
    })
    .strict()
    .safeParse({
      branchId: value(formData, "branchId"),
      bookingWindowDays: value(formData, "bookingWindowDays") || undefined,
      bufferAfterMins: value(formData, "bufferAfterMins"),
      bufferBeforeMins: value(formData, "bufferBeforeMins"),
      durationMins: value(formData, "durationMins") || undefined,
      isEnabled: value(formData, "isEnabled") === "on",
      priceMinor: value(formData, "priceMinor") || undefined,
      serviceId: value(formData, "serviceId"),
    });
  if (!parsed.success) {
    redirect(destination(`/${locale}/business/services`, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantPermission(locale, "services.manage");
    await identityRepository.configureServiceBranch(access, parsed.data);
  } catch (error) {
    redirect(destination(`/${locale}/business/services`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/business/services`, "notice", "SERVICE_CONFIGURED"));
}

export async function acceptInvitationAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const token = z.string().min(20).max(200).safeParse(value(formData, "token"));
  if (!token.success) {
    redirect(destination(`/${locale}/login`, "error", "INVITATION_INVALID"));
  }
  const session = await requireSession(locale);
  try {
    const accepted = await identityRepository.acceptInvitation(
      session.user.id,
      session.user.email,
      token.data,
    );
    await prisma.session.update({
      data: {
        activeBranchId: null,
        activeMembershipId: accepted.membershipId,
        activeOrganizationId: accepted.organizationId,
        activeSupportAccessId: null,
      },
      where: { id: session.session.id },
    });
  } catch (error) {
    redirect(destination(`/${locale}/invitations/${token.data}`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/dashboard`, "notice", "INVITATION_ACCEPTED"));
}

export async function registerFromInvitationAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      name: shortText,
      password: z.string().min(12).max(128),
      token: z.string().min(20).max(200),
    })
    .safeParse({
      name: value(formData, "name"),
      password: value(formData, "password"),
      token: value(formData, "token"),
    });
  if (!parsed.success) {
    redirect(destination(`/${locale}/login`, "error", "VALIDATION_FAILED"));
  }
  let registeredUserId: string | undefined;
  try {
    const preview = await identityRepository.previewInvitation(parsed.data.token);
    const existing = await prisma.user.findUnique({ where: { email: preview.email } });
    if (existing) {
      throw new DomainError({
        code: "CONFLICT",
        message: "This email already has an account. Sign in to accept the invitation.",
      });
    }
    const registration = await auth.api.signUpEmail({
      body: { email: preview.email, name: parsed.data.name, password: parsed.data.password },
      headers: await headers(),
    });
    registeredUserId = registration.user.id;
    const accepted = await identityRepository.acceptInvitation(
      registration.user.id,
      registration.user.email,
      parsed.data.token,
      { accountCreated: true },
    );
    if (!registration.token) {
      throw new DomainError({ code: "INTERNAL_ERROR", message: "Session was not created." });
    }
    await prisma.session.updateMany({
      data: {
        activeBranchId: null,
        activeMembershipId: accepted.membershipId,
        activeOrganizationId: accepted.organizationId,
        activeSupportAccessId: null,
      },
      where: { token: registration.token, userId: registration.user.id },
    });
  } catch (error) {
    if (registeredUserId) {
      await prisma.user.deleteMany({
        where: { id: registeredUserId, memberships: { none: {} } },
      });
    }
    redirect(destination(`/${locale}/invitations/${parsed.data.token}`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/dashboard`, "notice", "INVITATION_ACCEPTED"));
}

export async function createCustomerAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      displayName: shortText,
      phoneOriginal: z.string().trim().max(80).optional(),
      preferredBranchId: uuidSchema.optional(),
      preferredLocale: z.enum([SupportedLocale.en, SupportedLocale.ar]),
      tags: z.array(z.string().trim().min(1).max(40)).max(10),
    })
    .strict()
    .safeParse({
      displayName: value(formData, "displayName"),
      phoneOriginal: value(formData, "phoneOriginal") || undefined,
      preferredBranchId: value(formData, "preferredBranchId") || undefined,
      preferredLocale: value(formData, "preferredLocale"),
      tags: String(value(formData, "tags") ?? "")
        .split(",")
        .map((tag) => tag.trim())
        .filter(Boolean),
    });
  if (!parsed.success) {
    redirect(destination(`/${locale}/customers`, "error", "VALIDATION_FAILED"));
  }
  let customerId: string;
  let duplicateCount = 0;
  try {
    const access = await requireTenantAccess(locale);
    const created = await crmAppointmentRepository.createCustomer(
      access,
      parsed.data,
      await requestAuditDetails(),
    );
    customerId = created.customer.id;
    duplicateCount = created.likelyDuplicates.length;
  } catch (error) {
    redirect(destination(`/${locale}/customers`, "error", errorCode(error)));
  }
  redirect(
    `${destination(`/${locale}/customers/${customerId}`, "notice", "CUSTOMER_CREATED")}&duplicates=${duplicateCount}`,
  );
}

export async function updateCustomerAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      customerId: uuidSchema,
      displayName: shortText,
      expectedVersion: z.coerce.number().int().positive(),
      phoneOriginal: z.string().trim().max(80).optional(),
      preferredBranchId: uuidSchema.optional(),
      preferredLocale: z.enum([SupportedLocale.en, SupportedLocale.ar]),
      tags: z.array(z.string().trim().min(1).max(40)).max(10),
    })
    .safeParse({
      customerId: value(formData, "customerId"),
      displayName: value(formData, "displayName"),
      expectedVersion: value(formData, "expectedVersion"),
      phoneOriginal: value(formData, "phoneOriginal") || undefined,
      preferredBranchId: value(formData, "preferredBranchId") || undefined,
      preferredLocale: value(formData, "preferredLocale"),
      tags: String(value(formData, "tags") ?? "")
        .split(",")
        .map((tag) => tag.trim())
        .filter(Boolean),
    });
  const fallback = parsed.success
    ? `/${locale}/customers/${parsed.data.customerId}`
    : `/${locale}/customers`;
  if (!parsed.success) {
    redirect(destination(fallback, "error", "VALIDATION_FAILED"));
  }
  let duplicateCount = 0;
  try {
    const access = await requireTenantAccess(locale);
    const updated = await crmAppointmentRepository.updateCustomer(
      access,
      parsed.data,
      await requestAuditDetails(),
    );
    duplicateCount = updated.likelyDuplicates.length;
  } catch (error) {
    redirect(destination(fallback, "error", errorCode(error)));
  }
  redirect(`${destination(fallback, "notice", "CUSTOMER_UPDATED")}&duplicates=${duplicateCount}`);
}

export async function addCustomerNoteAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({ body: z.string().trim().min(1).max(2_000), customerId: uuidSchema })
    .strict()
    .safeParse({ body: value(formData, "body"), customerId: value(formData, "customerId") });
  const fallback = parsed.success
    ? `/${locale}/customers/${parsed.data.customerId}`
    : `/${locale}/customers`;
  if (!parsed.success) {
    redirect(destination(fallback, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantAccess(locale);
    await crmAppointmentRepository.addCustomerNote(
      access,
      parsed.data,
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(fallback, "error", errorCode(error)));
  }
  redirect(destination(fallback, "notice", "CUSTOMER_NOTE_ADDED"));
}

export async function assignConversationAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      conversationId: uuidSchema,
      membershipId: uuidSchema.optional(),
      priority: z.enum(ConversationPriority),
    })
    .strict()
    .safeParse({
      conversationId: value(formData, "conversationId"),
      membershipId: value(formData, "membershipId") || undefined,
      priority: value(formData, "priority"),
    });
  const fallback = `/${locale}/inbox?tab=messages`;
  if (!parsed.success) redirect(destination(fallback, "error", "VALIDATION_FAILED"));
  try {
    await communicationRepository.assignConversation(
      await requireTenantAccess(locale),
      parsed.data,
    );
  } catch (error) {
    redirect(destination(fallback, "error", errorCode(error)));
  }
  redirect(destination(fallback, "notice", "CONVERSATION_UPDATED"));
}

export async function markConversationReadAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = uuidSchema.safeParse(value(formData, "conversationId"));
  const fallback = `/${locale}/inbox?tab=messages`;
  if (!parsed.success) redirect(destination(fallback, "error", "VALIDATION_FAILED"));
  try {
    await communicationRepository.markConversationRead(
      await requireTenantAccess(locale),
      parsed.data,
    );
  } catch (error) {
    redirect(destination(fallback, "error", errorCode(error)));
  }
  redirect(fallback);
}

export async function recordConsentAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      customerId: uuidSchema,
      evidence: z.string().trim().max(2_000).optional(),
      purpose: z.string().trim().min(2).max(120),
      revokesConsentId: uuidSchema.optional(),
      status: z.enum([ConsentStatus.GRANTED, ConsentStatus.REVOKED]),
      textVersion: z.string().trim().min(1).max(80),
    })
    .safeParse({
      customerId: value(formData, "customerId"),
      evidence: value(formData, "evidence") || undefined,
      purpose: value(formData, "purpose"),
      revokesConsentId: value(formData, "revokesConsentId") || undefined,
      status: value(formData, "status"),
      textVersion: value(formData, "textVersion"),
    });
  const fallback = parsed.success
    ? `/${locale}/customers/${parsed.data.customerId}`
    : `/${locale}/customers`;
  if (!parsed.success) {
    redirect(destination(fallback, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantAccess(locale);
    await crmAppointmentRepository.recordConsent(
      access,
      {
        ...parsed.data,
        channel: ConsentChannel.STAFF,
        source: ConsentSource.STAFF,
      },
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(fallback, "error", errorCode(error)));
  }
  redirect(destination(fallback, "notice", "CONSENT_RECORDED"));
}

export async function createAppointmentAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      branchId: uuidSchema,
      customerId: z.string(),
      customerMode: z.enum(["existing", "new"]),
      idempotencyKey: uuidSchema.optional(),
      initialStatus: z.enum(["PENDING", "CONFIRMED"]),
      newAllergyDetails: z.string().trim().max(4_000).optional(),
      newAllergyState: z.enum(["NOT_PROVIDED", "NONE_REPORTED", "PROVIDED", "DECLINED"]),
      newCustomerEmail: z.email().max(320).optional(),
      newCustomerName: z.string().trim().max(160),
      newCustomerPhone: z.string().trim().max(80),
      newHealthConsentConfirmed: z.boolean(),
      newMedicalConditionDetails: z.string().trim().max(4_000).optional(),
      newMedicalConditionState: z.enum(["NOT_PROVIDED", "NONE_REPORTED", "PROVIDED", "DECLINED"]),
      providerId: uuidSchema,
      roomId: uuidSchema.optional(),
      serviceId: uuidSchema,
      startsAtLocal: z.string().regex(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/),
    })
    .strict()
    .superRefine((input, context) => {
      if (input.customerMode === "existing" && !uuidSchema.safeParse(input.customerId).success) {
        context.addIssue({ code: "custom", message: "Select an existing customer." });
      }
      if (
        input.customerMode === "new" &&
        (input.newCustomerName.length < 2 || input.newCustomerPhone.length < 7)
      ) {
        context.addIssue({
          code: "custom",
          message: "A new customer requires a name and valid phone number.",
        });
      }
    })
    .safeParse({
      branchId: value(formData, "branchId"),
      customerId: value(formData, "customerId") ?? "",
      customerMode: value(formData, "customerMode"),
      idempotencyKey: value(formData, "idempotencyKey") || undefined,
      initialStatus: value(formData, "initialStatus") || "PENDING",
      newAllergyDetails: value(formData, "newAllergyDetails") || undefined,
      newAllergyState: value(formData, "newAllergyState") || "NOT_PROVIDED",
      newCustomerEmail: value(formData, "newCustomerEmail") || undefined,
      newCustomerName: value(formData, "newCustomerName") ?? "",
      newCustomerPhone: value(formData, "newCustomerPhone") ?? "",
      newHealthConsentConfirmed: value(formData, "newHealthConsentConfirmed") === "on",
      newMedicalConditionDetails: value(formData, "newMedicalConditionDetails") || undefined,
      newMedicalConditionState: value(formData, "newMedicalConditionState") || "NOT_PROVIDED",
      providerId: value(formData, "providerId"),
      roomId: value(formData, "roomId") || undefined,
      serviceId: value(formData, "serviceId"),
      startsAtLocal: value(formData, "startsAtLocal"),
    });
  if (!parsed.success) {
    redirect(destination(`/${locale}/schedule/calendar`, "error", "VALIDATION_FAILED"));
  }
  let appointmentId: string;
  try {
    const access = await requireTenantAccess(locale);
    if (parsed.data.initialStatus === "CONFIRMED") {
      requirePermission(access, "appointment.confirm", {
        branchId: parsed.data.branchId,
        staffProfileId: parsed.data.providerId,
      });
    }
    const customerId =
      parsed.data.customerMode === "new"
        ? (
            await crmAppointmentRepository.createCustomer(
              access,
              {
                allergyDetails: parsed.data.newAllergyDetails,
                allergyState: parsed.data.newAllergyState,
                displayName: parsed.data.newCustomerName,
                emailOriginal: parsed.data.newCustomerEmail,
                healthConsentConfirmed: parsed.data.newHealthConsentConfirmed,
                medicalConditionDetails: parsed.data.newMedicalConditionDetails,
                medicalConditionState: parsed.data.newMedicalConditionState,
                phoneOriginal: parsed.data.newCustomerPhone,
                preferredBranchId: parsed.data.branchId,
                preferredLocale: locale,
                rejectDuplicatePhone: true,
              },
              await requestAuditDetails(),
            )
          ).customer.id
        : parsed.data.customerId;
    const appointment = await crmAppointmentRepository.createAppointment(
      access,
      {
        branchId: parsed.data.branchId,
        customerId,
        idempotencyKey: parsed.data.idempotencyKey,
        providerId: parsed.data.providerId,
        roomId: parsed.data.roomId,
        serviceId: parsed.data.serviceId,
        source: "STAFF" as AppointmentSource,
        startsAtLocal: parsed.data.startsAtLocal,
        status: parsed.data.initialStatus,
      },
      await requestAuditDetails(),
    );
    appointmentId = appointment.id;
  } catch (error) {
    redirect(destination(`/${locale}/schedule/calendar`, "error", errorCode(error)));
  }
  redirect(
    destination(
      `/${locale}/schedule/appointments?appointment=${appointmentId}`,
      "notice",
      "APPOINTMENT_CREATED",
    ),
  );
}

export async function updatePatientSafetyIntakeAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      allergyDetails: z.string().trim().max(4_000).optional(),
      allergyState: z.enum(["NOT_PROVIDED", "NONE_REPORTED", "PROVIDED", "DECLINED"]),
      consentConfirmed: z.boolean(),
      customerId: uuidSchema,
      medicalConditionDetails: z.string().trim().max(4_000).optional(),
      medicalConditionState: z.enum(["NOT_PROVIDED", "NONE_REPORTED", "PROVIDED", "DECLINED"]),
    })
    .strict()
    .safeParse({
      allergyDetails: value(formData, "allergyDetails") || undefined,
      allergyState: value(formData, "allergyState"),
      consentConfirmed: value(formData, "consentConfirmed") === "on",
      customerId: value(formData, "customerId"),
      medicalConditionDetails: value(formData, "medicalConditionDetails") || undefined,
      medicalConditionState: value(formData, "medicalConditionState"),
    });
  const fallback = parsed.success
    ? `/${locale}/customers/${parsed.data.customerId}?tab=health`
    : `/${locale}/customers`;
  if (!parsed.success) redirect(destination(fallback, "error", "VALIDATION_FAILED"));
  try {
    await crmAppointmentRepository.updatePatientSafetyIntake(
      await requireTenantAccess(locale),
      parsed.data,
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(fallback, "error", errorCode(error)));
  }
  redirect(destination(fallback, "notice", "PATIENT_SAFETY_INTAKE_UPDATED"));
}

export async function configureDoctorAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      branchIds: z.array(uuidSchema).min(1).max(100),
      displayNameAr: shortText,
      displayNameEn: shortText,
      email: z.email().optional(),
      isActive: z.boolean(),
      phone: z.string().trim().max(40).optional(),
      profession: z.string().trim().max(120).optional(),
      serviceIds: z.array(uuidSchema).max(100),
      specialty: z.string().trim().max(160).optional(),
      staffProfileId: uuidSchema,
    })
    .strict()
    .safeParse({
      branchIds: formData.getAll("branchIds"),
      displayNameAr: value(formData, "displayNameAr"),
      displayNameEn: value(formData, "displayNameEn"),
      email: value(formData, "email") || undefined,
      isActive: value(formData, "isActive") === "on",
      phone: value(formData, "phone") || undefined,
      profession: value(formData, "profession") || undefined,
      serviceIds: formData.getAll("serviceIds"),
      specialty: value(formData, "specialty") || undefined,
      staffProfileId: value(formData, "staffProfileId"),
    });
  const fallback = `/${locale}/business/doctors`;
  if (!parsed.success) redirect(destination(fallback, "error", "VALIDATION_FAILED"));
  let access: Awaited<ReturnType<typeof requireTenantAccess>> | undefined;
  try {
    access = await requireTenantAccess(locale);
    await identityRepository.configureDoctor(access, parsed.data);
  } catch (error) {
    if (!(error instanceof DomainError) && access) {
      let persisted = false;
      try {
        const saved = (await identityRepository.listDoctors(access)).find(
          ({ id }) => id === parsed.data.staffProfileId,
        );
        persisted = Boolean(
          saved &&
          saved.displayNameAr === parsed.data.displayNameAr.trim() &&
          saved.displayNameEn === parsed.data.displayNameEn.trim() &&
          (saved.email ?? undefined) === parsed.data.email?.trim().toLowerCase() &&
          saved.isActive === parsed.data.isActive &&
          (saved.phone ?? undefined) === parsed.data.phone?.trim() &&
          (saved.profession ?? undefined) === parsed.data.profession?.trim() &&
          (saved.specialty ?? undefined) === parsed.data.specialty?.trim() &&
          JSON.stringify(saved.branchAssignments.map(({ branchId }) => branchId).toSorted()) ===
            JSON.stringify(parsed.data.branchIds.toSorted()) &&
          JSON.stringify(saved.services.map(({ serviceId }) => serviceId).toSorted()) ===
            JSON.stringify(parsed.data.serviceIds.toSorted()),
        );
      } catch {
        persisted = false;
      }
      if (persisted) {
        revalidatePath(fallback);
        redirect(destination(fallback, "notice", "DOCTOR_SAVED"));
      }
    }
    redirect(destination(fallback, "error", errorCode(error)));
  }
  revalidatePath(fallback);
  redirect(destination(fallback, "notice", "DOCTOR_SAVED"));
}

export async function replaceDoctorScheduleAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      branchId: uuidSchema,
      breakEnd: localTimeSchema.optional(),
      breakStart: localTimeSchema.optional(),
      confirmAffected: z.boolean(),
      end: localTimeSchema,
      staffProfileId: uuidSchema,
      start: localTimeSchema,
      weekdays: z.array(z.enum(Weekday)).min(1).max(7),
    })
    .strict()
    .superRefine((input, context) => {
      if (input.start >= input.end)
        context.addIssue({ code: "custom", message: "Invalid working hours." });
      if ((input.breakStart === undefined) !== (input.breakEnd === undefined))
        context.addIssue({ code: "custom", message: "Both break times are required." });
      if (
        input.breakStart !== undefined &&
        input.breakEnd !== undefined &&
        (input.breakStart >= input.breakEnd ||
          input.breakStart < input.start ||
          input.breakEnd > input.end)
      )
        context.addIssue({ code: "custom", message: "Break must fit within working hours." });
    })
    .safeParse({
      branchId: value(formData, "branchId"),
      breakEnd: value(formData, "breakEnd") || undefined,
      breakStart: value(formData, "breakStart") || undefined,
      confirmAffected: value(formData, "confirmAffected") === "on",
      end: value(formData, "end"),
      staffProfileId: value(formData, "staffProfileId"),
      start: value(formData, "start"),
      weekdays: formData.getAll("weekdays"),
    });
  const fallback = `/${locale}/business/doctors`;
  if (!parsed.success) redirect(destination(fallback, "error", "VALIDATION_FAILED"));
  let updated = false;
  try {
    const periods = parsed.data.weekdays.map((weekday) => ({
      endMinuteLocal: parsed.data.end,
      startMinuteLocal: parsed.data.start,
      weekday,
    }));
    const breaks =
      parsed.data.breakStart === undefined || parsed.data.breakEnd === undefined
        ? []
        : parsed.data.weekdays.map((weekday) => ({
            endMinuteLocal: parsed.data.breakEnd as number,
            label: locale === "ar" ? "استراحة" : "Break",
            startMinuteLocal: parsed.data.breakStart as number,
            weekday,
          }));
    const result = await identityRepository.replaceDoctorSchedule(
      await requireTenantAccess(locale),
      {
        branchId: parsed.data.branchId,
        breaks,
        confirmAffected: parsed.data.confirmAffected,
        periods,
        staffProfileId: parsed.data.staffProfileId,
      },
    );
    updated = result.updated;
  } catch (error) {
    redirect(destination(fallback, "error", errorCode(error)));
  }
  if (!updated)
    redirect(destination(fallback, "error", "AFFECTED_APPOINTMENTS_REQUIRE_CONFIRMATION"));
  revalidatePath(fallback);
  redirect(destination(fallback, "notice", "DOCTOR_SCHEDULE_SAVED"));
}

export async function replaceDoctorIndependentScheduleAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const daySchema = z
    .object({
      breakOneEnd: localTimeSchema.optional(),
      breakOneStart: localTimeSchema.optional(),
      breakTwoEnd: localTimeSchema.optional(),
      breakTwoStart: localTimeSchema.optional(),
      end: localTimeSchema.optional(),
      start: localTimeSchema.optional(),
      weekday: z.enum(Weekday),
      working: z.boolean(),
    })
    .strict()
    .superRefine((day, context) => {
      if (day.working && (day.start === undefined || day.end === undefined || day.start >= day.end))
        context.addIssue({ code: "custom", message: "Working-day times are invalid." });
      for (const [start, end] of [
        [day.breakOneStart, day.breakOneEnd],
        [day.breakTwoStart, day.breakTwoEnd],
      ] as const) {
        if ((start === undefined) !== (end === undefined))
          context.addIssue({ code: "custom", message: "Both break times are required." });
        if (
          start !== undefined &&
          end !== undefined &&
          (day.start === undefined ||
            day.end === undefined ||
            start >= end ||
            start < day.start ||
            end > day.end)
        )
          context.addIssue({ code: "custom", message: "A break is outside working hours." });
      }
      if (
        day.breakOneStart !== undefined &&
        day.breakOneEnd !== undefined &&
        day.breakTwoStart !== undefined &&
        day.breakTwoEnd !== undefined &&
        day.breakOneStart < day.breakTwoEnd &&
        day.breakTwoStart < day.breakOneEnd
      )
        context.addIssue({ code: "custom", message: "Breaks overlap." });
    });
  const asOptional = (name: string): string | undefined => {
    const entry = formData.get(name);
    return typeof entry === "string" && entry ? entry : undefined;
  };
  const parsed = z
    .object({
      branchId: uuidSchema,
      confirmAffected: z.boolean(),
      days: z.array(daySchema).length(7),
      staffProfileId: uuidSchema,
    })
    .strict()
    .safeParse({
      branchId: value(formData, "branchId"),
      confirmAffected: value(formData, "confirmAffected") === "on",
      days: Object.values(Weekday).map((weekday) => ({
        breakOneEnd: asOptional(`breakOneEnd_${weekday}`),
        breakOneStart: asOptional(`breakOneStart_${weekday}`),
        breakTwoEnd: asOptional(`breakTwoEnd_${weekday}`),
        breakTwoStart: asOptional(`breakTwoStart_${weekday}`),
        end: asOptional(`end_${weekday}`),
        start: asOptional(`start_${weekday}`),
        weekday,
        working: value(formData, `working_${weekday}`) === "on",
      })),
      staffProfileId: value(formData, "staffProfileId"),
    });
  const fallback = `/${locale}/business/doctors`;
  if (!parsed.success) redirect(destination(fallback, "error", "VALIDATION_FAILED"));
  let affectedAppointments = 0;
  let updated = false;
  try {
    const periods = parsed.data.days.flatMap((day) =>
      day.working && day.start !== undefined && day.end !== undefined
        ? [{ endMinuteLocal: day.end, startMinuteLocal: day.start, weekday: day.weekday }]
        : [],
    );
    const breaks = parsed.data.days.flatMap((day) =>
      [
        [day.breakOneStart, day.breakOneEnd],
        [day.breakTwoStart, day.breakTwoEnd],
      ].flatMap(([start, end], index) =>
        day.working && start !== undefined && end !== undefined
          ? [
              {
                endMinuteLocal: end,
                label: locale === "ar" ? `استراحة ${index + 1}` : `Break ${index + 1}`,
                startMinuteLocal: start,
                weekday: day.weekday,
              },
            ]
          : [],
      ),
    );
    const result = await identityRepository.replaceDoctorSchedule(
      await requireTenantAccess(locale),
      {
        branchId: parsed.data.branchId,
        breaks,
        confirmAffected: parsed.data.confirmAffected,
        periods,
        staffProfileId: parsed.data.staffProfileId,
      },
    );
    affectedAppointments = result.affectedAppointments.length;
    updated = result.updated;
  } catch (error) {
    redirect(destination(fallback, "error", errorCode(error)));
  }
  if (!updated)
    redirect(
      `${destination(fallback, "error", "AFFECTED_APPOINTMENTS_REQUIRE_CONFIRMATION")}&affected=${affectedAppointments}`,
    );
  revalidatePath(fallback);
  redirect(destination(fallback, "notice", "DOCTOR_SCHEDULE_SAVED"));
}

export async function addDoctorTimeOffAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      branchId: uuidSchema,
      confirmAffected: z.boolean(),
      endsAtLocal: z.string().regex(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/u),
      reason: shortText,
      staffProfileId: uuidSchema,
      startsAtLocal: z.string().regex(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/u),
    })
    .strict()
    .safeParse({
      branchId: value(formData, "branchId"),
      confirmAffected: value(formData, "confirmAffected") === "on",
      endsAtLocal: value(formData, "endsAtLocal"),
      reason: value(formData, "reason"),
      staffProfileId: value(formData, "staffProfileId"),
      startsAtLocal: value(formData, "startsAtLocal"),
    });
  const fallback = `/${locale}/business/doctors`;
  if (!parsed.success) redirect(destination(fallback, "error", "VALIDATION_FAILED"));
  let created = false;
  try {
    const access = await requireTenantAccess(locale);
    const branch = (await identityRepository.listBranches(access)).find(
      ({ id }) => id === parsed.data.branchId,
    );
    if (!branch) throw new DomainError({ code: "NOT_FOUND", message: "Branch not found." });
    const result = await identityRepository.addDoctorTimeOff(access, {
      branchId: branch.id,
      confirmAffected: parsed.data.confirmAffected,
      endsAt: localDateTimeToUtc(parsed.data.endsAtLocal, branch.timezone),
      reason: parsed.data.reason,
      staffProfileId: parsed.data.staffProfileId,
      startsAt: localDateTimeToUtc(parsed.data.startsAtLocal, branch.timezone),
    });
    created = result.created;
  } catch (error) {
    redirect(destination(fallback, "error", errorCode(error)));
  }
  if (!created)
    redirect(destination(fallback, "error", "AFFECTED_APPOINTMENTS_REQUIRE_CONFIRMATION"));
  revalidatePath(fallback);
  redirect(destination(fallback, "notice", "DOCTOR_TIME_OFF_SAVED"));
}

const localTimeSchema = z
  .string()
  .regex(/^\d{2}:\d{2}$/u)
  .transform((time, context) => {
    const [hours, minutes] = time.split(":").map(Number);
    if (
      hours === undefined ||
      minutes === undefined ||
      hours < 0 ||
      hours > 23 ||
      minutes < 0 ||
      minutes > 59
    ) {
      context.addIssue({ code: "custom", message: "Invalid local time." });
      return z.NEVER;
    }
    return hours * 60 + minutes;
  });

export async function configureProviderBookingAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      branchId: uuidSchema,
      endMinuteLocal: localTimeSchema,
      serviceIds: z.array(uuidSchema).min(1).max(100),
      staffProfileId: uuidSchema,
      startMinuteLocal: localTimeSchema,
      weekdays: z.array(z.enum(Weekday)).min(1).max(7),
    })
    .strict()
    .superRefine((input, context) => {
      if (input.startMinuteLocal >= input.endMinuteLocal) {
        context.addIssue({ code: "custom", message: "End time must be after start time." });
      }
    })
    .safeParse({
      branchId: value(formData, "branchId"),
      endMinuteLocal: value(formData, "endTime"),
      serviceIds: formData.getAll("serviceIds"),
      staffProfileId: value(formData, "staffProfileId"),
      startMinuteLocal: value(formData, "startTime"),
      weekdays: formData.getAll("weekdays"),
    });
  if (!parsed.success) {
    redirect(destination(`/${locale}/business/team`, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantAccess(locale);
    await identityRepository.configureProviderBooking(access, {
      branchId: parsed.data.branchId,
      rules: parsed.data.weekdays.map((weekday) => ({
        endMinuteLocal: parsed.data.endMinuteLocal,
        startMinuteLocal: parsed.data.startMinuteLocal,
        weekday,
      })),
      serviceIds: parsed.data.serviceIds,
      staffProfileId: parsed.data.staffProfileId,
    });
  } catch (error) {
    redirect(destination(`/${locale}/business/team`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/business/team`, "notice", "PROVIDER_SCHEDULE_UPDATED"));
}

export async function rescheduleAppointmentAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      appointmentId: uuidSchema,
      expectedVersion: z.coerce.number().int().positive(),
      idempotencyKey: uuidSchema.optional(),
      returnTo: z.string().trim().max(1_000).optional(),
      startsAtLocal: z.string().regex(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/),
    })
    .strict()
    .safeParse({
      appointmentId: value(formData, "appointmentId"),
      expectedVersion: value(formData, "expectedVersion"),
      idempotencyKey: value(formData, "idempotencyKey") || undefined,
      returnTo: value(formData, "returnTo") || undefined,
      startsAtLocal: value(formData, "startsAtLocal"),
    });
  const fallback = parsed.success
    ? (safeScheduleReturn(locale, parsed.data.returnTo) ??
      `/${locale}/schedule/appointments?appointment=${parsed.data.appointmentId}`)
    : `/${locale}/dashboard/calendar`;
  if (!parsed.success) {
    redirect(destination(fallback, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantAccess(locale);
    await crmAppointmentRepository.rescheduleAppointment(
      access,
      {
        appointmentId: parsed.data.appointmentId,
        expectedVersion: parsed.data.expectedVersion,
        idempotencyKey: parsed.data.idempotencyKey,
        startsAtLocal: parsed.data.startsAtLocal,
      },
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(fallback, "error", errorCode(error)));
  }
  redirect(destination(fallback, "notice", "APPOINTMENT_RESCHEDULED"));
}

const consumptionItemSchema = z.object({
  actualQuantity: z.number().nonnegative(),
  batchId: uuidSchema.optional(),
  expectedQuantity: z.number().nonnegative(),
  itemId: uuidSchema,
  locationId: uuidSchema.optional(),
  reconciliationNote: z.string().optional(),
  unitOfMeasure: z.string().min(1),
});

export async function transitionAppointmentAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      appointmentId: uuidSchema,
      consumptions: z
        .string()
        .optional()
        .transform((val, ctx) => {
          if (!val) return undefined;
          try {
            const parsedJson = JSON.parse(val);
            return z.array(consumptionItemSchema).parse(parsedJson);
          } catch {
            ctx.addIssue({
              code: z.ZodIssueCode.custom,
              message: "Invalid consumptions payload",
            });
            return z.NEVER;
          }
        }),
      expectedVersion: z.coerce.number().int().positive(),
      idempotencyKey: uuidSchema.optional(),
      internalNote: z.string().trim().max(10_000).optional(),
      notificationChoice: z.enum(["SEND", "SKIP"]).optional(),
      reason: z.string().trim().max(500).optional(),
      recordDetails: z.string().trim().max(10_000).optional(),
      recordSummary: z.string().trim().max(5_000).optional(),
      returnTo: z.string().trim().max(1_000).optional(),
      toStatus: z.enum([
        AppointmentStatus.CONFIRMED,
        AppointmentStatus.CHECKED_IN,
        AppointmentStatus.IN_PROGRESS,
        AppointmentStatus.COMPLETED,
        AppointmentStatus.CANCELLED,
        AppointmentStatus.NO_SHOW,
      ]),
    })
    .safeParse({
      appointmentId: value(formData, "appointmentId"),
      consumptions: value(formData, "consumptions") || undefined,
      expectedVersion: value(formData, "expectedVersion"),
      idempotencyKey: value(formData, "idempotencyKey") || undefined,
      internalNote: value(formData, "internalNote") || undefined,
      notificationChoice: value(formData, "notificationChoice") || undefined,
      reason: value(formData, "reason") || undefined,
      recordDetails: value(formData, "recordDetails") || undefined,
      recordSummary: value(formData, "recordSummary") || undefined,
      returnTo: value(formData, "returnTo") || undefined,
      toStatus: value(formData, "toStatus"),
    });
  const fallback = parsed.success
    ? (safeScheduleReturn(locale, parsed.data.returnTo) ??
      `/${locale}/schedule/appointments?appointment=${parsed.data.appointmentId}`)
    : `/${locale}/dashboard/today`;
  if (!parsed.success) {
    redirect(destination(fallback, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantAccess(locale);
    await crmAppointmentRepository.transitionAppointment(
      access,
      {
        appointmentId: parsed.data.appointmentId,
        consumptions: parsed.data.consumptions,
        expectedVersion: parsed.data.expectedVersion,
        idempotencyKey: parsed.data.idempotencyKey,
        internalNote: parsed.data.internalNote,
        notificationChoice: parsed.data.notificationChoice,
        reason: parsed.data.reason,
        recordDetails: parsed.data.recordDetails,
        recordSummary: parsed.data.recordSummary,
        toStatus: parsed.data.toStatus,
      },
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(fallback, "error", errorCode(error)));
  }
  redirect(
    destination(
      fallback,
      "notice",
      parsed.data.toStatus === AppointmentStatus.COMPLETED
        ? "SERVICE_COMPLETED"
        : "APPOINTMENT_UPDATED",
    ),
  );
}

export async function combinedAppointmentTransitionAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      appointmentId: uuidSchema,
      command: z.enum(["CONFIRM_AND_CHECK_IN", "CHECK_IN_AND_START"]),
      expectedVersion: z.coerce.number().int().positive(),
      idempotencyKey: uuidSchema.optional(),
      roomId: uuidSchema.optional(),
      returnTo: z.string().trim().max(1_000).optional(),
    })
    .strict()
    .safeParse({
      appointmentId: value(formData, "appointmentId"),
      command: value(formData, "command"),
      expectedVersion: value(formData, "expectedVersion"),
      idempotencyKey: value(formData, "idempotencyKey") || undefined,
      roomId: value(formData, "roomId") || undefined,
      returnTo: value(formData, "returnTo") || undefined,
    });
  const fallback = parsed.success
    ? (safeScheduleReturn(locale, parsed.data.returnTo) ??
      `/${locale}/schedule/appointments?appointment=${parsed.data.appointmentId}`)
    : `/${locale}/schedule/today`;
  if (!parsed.success) {
    redirect(destination(fallback, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantAccess(locale);
    await crmAppointmentRepository.transitionAppointmentCombined(
      access,
      {
        appointmentId: parsed.data.appointmentId,
        command: parsed.data.command,
        expectedVersion: parsed.data.expectedVersion,
        idempotencyKey: parsed.data.idempotencyKey,
        roomId: parsed.data.roomId,
      },
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(fallback, "error", errorCode(error)));
  }
  redirect(destination(fallback, "notice", "APPOINTMENT_UPDATED"));
}

const appointmentRoomOperationSchema = z
  .object({
    asNext: z.enum(["true", "false"]).default("false"),
    appointmentId: uuidSchema,
    expectedVersion: z.coerce.number().int().positive(),
    idempotencyKey: uuidSchema.optional(),
    returnTo: z.string().trim().max(1_000).optional(),
    roomId: uuidSchema,
  })
  .strict();

function appointmentOperationInput(formData: FormData) {
  return {
    asNext: value(formData, "asNext") || "false",
    appointmentId: value(formData, "appointmentId"),
    expectedVersion: value(formData, "expectedVersion"),
    idempotencyKey: value(formData, "idempotencyKey") || undefined,
    returnTo: value(formData, "returnTo") || undefined,
    roomId: value(formData, "roomId"),
  };
}

export async function callAppointmentToRoomAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = appointmentRoomOperationSchema.safeParse(appointmentOperationInput(formData));
  const fallback = parsed.success
    ? (safeScheduleReturn(locale, parsed.data.returnTo) ??
      `/${locale}/schedule/appointments?appointment=${parsed.data.appointmentId}`)
    : `/${locale}/schedule/today`;
  if (!parsed.success) redirect(destination(fallback, "error", "VALIDATION_FAILED"));
  try {
    const access = await requireTenantAccess(locale);
    await crmAppointmentRepository.callAppointmentToRoom(
      access,
      {
        asNext: parsed.data.asNext === "true",
        appointmentId: parsed.data.appointmentId,
        expectedVersion: parsed.data.expectedVersion,
        idempotencyKey: parsed.data.idempotencyKey,
        roomId: parsed.data.roomId,
      },
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(fallback, "error", errorCode(error)));
  }
  redirect(destination(fallback, "notice", "PATIENT_CALLED_TO_ROOM"));
}

export async function changeAppointmentRoomAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = appointmentRoomOperationSchema.safeParse(appointmentOperationInput(formData));
  const fallback = parsed.success
    ? (safeScheduleReturn(locale, parsed.data.returnTo) ??
      `/${locale}/schedule/appointments?appointment=${parsed.data.appointmentId}`)
    : `/${locale}/schedule/today`;
  if (!parsed.success) redirect(destination(fallback, "error", "VALIDATION_FAILED"));
  try {
    const access = await requireTenantAccess(locale);
    await crmAppointmentRepository.changeAppointmentRoom(
      access,
      {
        appointmentId: parsed.data.appointmentId,
        expectedVersion: parsed.data.expectedVersion,
        idempotencyKey: parsed.data.idempotencyKey,
        roomId: parsed.data.roomId,
      },
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(fallback, "error", errorCode(error)));
  }
  redirect(destination(fallback, "notice", "APPOINTMENT_ROOM_CHANGED"));
}

export async function startAppointmentServiceAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = appointmentRoomOperationSchema
    .extend({
      includeCheckIn: z.enum(["true", "false"]).default("false"),
      roomId: uuidSchema.optional(),
    })
    .safeParse({
      ...appointmentOperationInput(formData),
      includeCheckIn: value(formData, "includeCheckIn") || "false",
      roomId: value(formData, "roomId") || undefined,
    });
  const fallback = parsed.success
    ? (safeScheduleReturn(locale, parsed.data.returnTo) ??
      `/${locale}/schedule/appointments?appointment=${parsed.data.appointmentId}`)
    : `/${locale}/schedule/today`;
  if (!parsed.success) redirect(destination(fallback, "error", "VALIDATION_FAILED"));
  try {
    const access = await requireTenantAccess(locale);
    await crmAppointmentRepository.startAppointmentService(
      access,
      {
        appointmentId: parsed.data.appointmentId,
        expectedVersion: parsed.data.expectedVersion,
        idempotencyKey: parsed.data.idempotencyKey,
        includeCheckIn: parsed.data.includeCheckIn === "true",
        roomId: parsed.data.roomId,
      },
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(fallback, "error", errorCode(error)));
  }
  redirect(destination(fallback, "notice", "SERVICE_STARTED"));
}

export async function changeAppointmentServiceAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      appointmentId: uuidSchema,
      expectedVersion: z.coerce.number().int().positive(),
      idempotencyKey: uuidSchema.optional(),
      reason: z.string().trim().max(500).optional(),
      returnTo: z.string().trim().max(1_000).optional(),
      serviceId: uuidSchema,
    })
    .strict()
    .safeParse({
      appointmentId: value(formData, "appointmentId"),
      expectedVersion: value(formData, "expectedVersion"),
      idempotencyKey: value(formData, "idempotencyKey") || undefined,
      reason: value(formData, "reason") || undefined,
      returnTo: value(formData, "returnTo") || undefined,
      serviceId: value(formData, "serviceId"),
    });
  const fallback = parsed.success
    ? (safeScheduleReturn(locale, parsed.data.returnTo) ??
      `/${locale}/schedule/appointments?appointment=${parsed.data.appointmentId}`)
    : `/${locale}/schedule/today`;
  if (!parsed.success) redirect(destination(fallback, "error", "VALIDATION_FAILED"));
  try {
    await crmAppointmentRepository.changeAppointmentService(
      await requireTenantAccess(locale),
      {
        appointmentId: parsed.data.appointmentId,
        expectedVersion: parsed.data.expectedVersion,
        idempotencyKey: parsed.data.idempotencyKey,
        reason: parsed.data.reason,
        serviceId: parsed.data.serviceId,
      },
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(fallback, "error", errorCode(error)));
  }
  redirect(destination(fallback, "notice", "APPOINTMENT_SERVICE_CHANGED"));
}

export async function resendRoomMessageAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      appointmentId: uuidSchema,
      expectedVersion: z.coerce.number().int().positive(),
      idempotencyKey: uuidSchema.optional(),
      returnTo: z.string().trim().max(1_000).optional(),
    })
    .strict()
    .safeParse({
      appointmentId: value(formData, "appointmentId"),
      expectedVersion: value(formData, "expectedVersion"),
      idempotencyKey: value(formData, "idempotencyKey") || undefined,
      returnTo: value(formData, "returnTo") || undefined,
    });
  const fallback = parsed.success
    ? (safeScheduleReturn(locale, parsed.data.returnTo) ??
      `/${locale}/schedule/appointments?appointment=${parsed.data.appointmentId}`)
    : `/${locale}/schedule/today`;
  if (!parsed.success) redirect(destination(fallback, "error", "VALIDATION_FAILED"));
  try {
    const access = await requireTenantAccess(locale);
    await crmAppointmentRepository.resendRoomMessage(
      access,
      {
        appointmentId: parsed.data.appointmentId,
        expectedVersion: parsed.data.expectedVersion,
        idempotencyKey: parsed.data.idempotencyKey,
      },
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(fallback, "error", errorCode(error)));
  }
  redirect(destination(fallback, "notice", "ROOM_MESSAGE_QUEUED"));
}

export async function bulkConfirmAppointmentsAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const requestedReturnTo = value(formData, "returnTo");
  const fallback =
    safeScheduleReturn(
      locale,
      typeof requestedReturnTo === "string" ? requestedReturnTo : undefined,
    ) ?? `/${locale}/schedule/today`;
  const itemSchema = z.string().transform((item, context) => {
    const [appointmentId, rawVersion, extra] = item.split(":");
    const parsed = z
      .object({ appointmentId: uuidSchema, expectedVersion: z.coerce.number().int().positive() })
      .safeParse({ appointmentId, expectedVersion: rawVersion });
    if (!parsed.success || extra !== undefined) {
      context.addIssue({ code: "custom", message: "Invalid appointment selection." });
      return z.NEVER;
    }
    return parsed.data;
  });
  const parsed = z.array(itemSchema).min(1).max(100).safeParse(formData.getAll("appointments"));
  if (!parsed.success) {
    redirect(destination(fallback, "error", "VALIDATION_FAILED"));
  }
  let succeeded = 0;
  let failed = 0;
  try {
    const access = await requireTenantAccess(locale);
    const results = await crmAppointmentRepository.bulkConfirmAppointments(
      access,
      parsed.data,
      await requestAuditDetails(),
    );
    succeeded = results.filter((result) => result.succeeded).length;
    failed = results.length - succeeded;
  } catch (error) {
    redirect(destination(fallback, "error", errorCode(error)));
  }
  const result = destination(fallback, "notice", "BULK_CONFIRM_COMPLETED");
  redirect(`${result}&succeeded=${succeeded}&failed=${failed}`);
}

export async function addAppointmentNoteAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({ appointmentId: uuidSchema, body: z.string().trim().min(1).max(10_000) })
    .safeParse({ appointmentId: value(formData, "appointmentId"), body: value(formData, "body") });
  const fallback = parsed.success
    ? `/${locale}/dashboard/appointments/${parsed.data.appointmentId}`
    : `/${locale}/dashboard/today`;
  if (!parsed.success) {
    redirect(destination(fallback, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantAccess(locale);
    await crmAppointmentRepository.addInternalNote(
      access,
      parsed.data,
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(fallback, "error", errorCode(error)));
  }
  redirect(destination(fallback, "notice", "NOTE_ADDED"));
}

export async function recordAppointmentPaymentAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      amountMinor: z.coerce.number().int().min(0),
      appointmentId: uuidSchema,
      currency: z.string().trim().max(10).optional(),
      method: z.enum(["CASH", "CARD", "TRANSFER", "INSURANCE"]),
      notes: z.string().trim().max(500).optional(),
      reference: z.string().trim().max(100).optional(),
      status: z.enum(["PAID", "PARTIAL", "WAIVED"]),
    })
    .safeParse({
      amountMinor: value(formData, "amountMinor"),
      appointmentId: value(formData, "appointmentId"),
      currency: value(formData, "currency") || undefined,
      method: value(formData, "method"),
      notes: value(formData, "notes") || undefined,
      reference: value(formData, "reference") || undefined,
      status: value(formData, "status"),
    });

  const fallback = parsed.success
    ? `/${locale}/dashboard/appointments/${parsed.data.appointmentId}`
    : `/${locale}/dashboard/today`;

  if (!parsed.success) {
    redirect(destination(fallback, "error", "VALIDATION_FAILED"));
  }

  try {
    const access = await requireTenantAccess(locale);
    await crmAppointmentRepository.recordPayment(access, parsed.data, await requestAuditDetails());
  } catch (error) {
    redirect(destination(fallback, "error", errorCode(error)));
  }

  redirect(destination(fallback, "notice", "PAYMENT_RECORDED"));
}

const resourceKinds = z.enum(beautyResourceKinds);
const resourceStatuses = z.enum(ResourceStatus);
const weekdays = z.enum(Weekday);

export async function createResourceGroupAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({ branchId: uuidSchema, kind: resourceKinds, nameAr: shortText, nameEn: shortText })
    .strict()
    .safeParse({
      branchId: value(formData, "branchId"),
      kind: value(formData, "kind"),
      nameAr: value(formData, "nameAr"),
      nameEn: value(formData, "nameEn"),
    });
  if (!parsed.success) {
    redirect(destination(`/${locale}/business/resources`, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantAccess(locale);
    await schedulingRepository.createResourceGroup(
      access,
      parsed.data,
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(`/${locale}/business/resources`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/business/resources`, "notice", "RESOURCE_GROUP_CREATED"));
}

export async function createResourceAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      allowedServiceIds: z.array(uuidSchema).max(100),
      capacity: z.coerce.number().int().min(1).max(100),
      groupId: uuidSchema,
      nameAr: shortText,
      nameEn: shortText,
      notes: z.string().trim().max(2_000).optional(),
      staffProfileId: uuidSchema.optional(),
    })
    .strict()
    .safeParse({
      allowedServiceIds: formData.getAll("allowedServiceIds"),
      capacity: value(formData, "capacity") || "1",
      groupId: value(formData, "groupId"),
      nameAr: value(formData, "nameAr"),
      nameEn: value(formData, "nameEn"),
      notes: value(formData, "notes") || undefined,
      staffProfileId: value(formData, "staffProfileId") || undefined,
    });
  if (!parsed.success) {
    redirect(destination(`/${locale}/business/resources`, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantAccess(locale);
    await schedulingRepository.createResource(access, parsed.data, await requestAuditDetails());
  } catch (error) {
    redirect(destination(`/${locale}/business/resources`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/business/resources`, "notice", "RESOURCE_CREATED"));
}

export async function updateRoomAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      allowedServiceIds: z.array(uuidSchema).max(100),
      capacity: z.coerce.number().int().min(1).max(100),
      confirmAffected: z.boolean(),
      nameAr: shortText,
      nameEn: shortText,
      notes: z.string().trim().max(2_000).optional(),
      resourceId: uuidSchema,
    })
    .strict()
    .safeParse({
      allowedServiceIds: formData.getAll("allowedServiceIds"),
      capacity: value(formData, "capacity"),
      confirmAffected: value(formData, "confirmAffected") === "on",
      nameAr: value(formData, "nameAr"),
      nameEn: value(formData, "nameEn"),
      notes: value(formData, "notes") || undefined,
      resourceId: value(formData, "resourceId"),
    });
  const fallback = `/${locale}/business/resources`;
  if (!parsed.success) redirect(destination(fallback, "error", "VALIDATION_FAILED"));
  try {
    const result = await schedulingRepository.updateRoom(
      await requireTenantAccess(locale),
      parsed.data,
      await requestAuditDetails(),
    );
    if (!result.updated)
      redirect(destination(fallback, "error", "AFFECTED_APPOINTMENTS_REQUIRE_CONFIRMATION"));
  } catch (error) {
    redirect(destination(fallback, "error", errorCode(error)));
  }
  revalidatePath(fallback);
  redirect(destination(fallback, "notice", "ROOM_UPDATED"));
}

export async function setResourceStatusAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      reason: z.string().trim().min(2).max(500),
      resourceId: uuidSchema,
      status: resourceStatuses,
    })
    .strict()
    .safeParse({
      reason: value(formData, "reason"),
      resourceId: value(formData, "resourceId"),
      status: value(formData, "status"),
    });
  if (!parsed.success) {
    redirect(destination(`/${locale}/business/resources`, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantAccess(locale);
    await schedulingRepository.setResourceStatus(access, parsed.data, await requestAuditDetails());
  } catch (error) {
    redirect(destination(`/${locale}/business/resources`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/business/resources`, "notice", "RESOURCE_UPDATED"));
}

export async function createBranchHoursRuleAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      branchId: uuidSchema,
      endMinuteLocal: localTimeSchema,
      startMinuteLocal: localTimeSchema,
      weekday: weekdays,
    })
    .safeParse({
      branchId: value(formData, "branchId"),
      endMinuteLocal: value(formData, "endTime"),
      startMinuteLocal: value(formData, "startTime"),
      weekday: value(formData, "weekday"),
    });
  if (!parsed.success) {
    redirect(destination(`/${locale}/business/resources`, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantAccess(locale);
    await schedulingRepository.createBranchHoursRule(access, parsed.data);
  } catch (error) {
    redirect(destination(`/${locale}/business/resources`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/business/resources`, "notice", "HOURS_ADDED"));
}

export async function createResourceAvailabilityRuleAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      endMinuteLocal: localTimeSchema,
      resourceId: uuidSchema,
      startMinuteLocal: localTimeSchema,
      weekday: weekdays,
    })
    .safeParse({
      endMinuteLocal: value(formData, "endTime"),
      resourceId: value(formData, "resourceId"),
      startMinuteLocal: value(formData, "startTime"),
      weekday: value(formData, "weekday"),
    });
  if (!parsed.success) {
    redirect(destination(`/${locale}/business/resources`, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantAccess(locale);
    await schedulingRepository.createResourceAvailabilityRule(access, parsed.data);
  } catch (error) {
    redirect(destination(`/${locale}/business/resources`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/business/resources`, "notice", "HOURS_ADDED"));
}

export async function setServiceResourceRequirementAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      branchId: uuidSchema,
      quantity: z.coerce.number().int().min(1).max(20),
      resourceGroupId: uuidSchema,
      serviceId: uuidSchema,
    })
    .safeParse({
      branchId: value(formData, "branchId"),
      quantity: value(formData, "quantity"),
      resourceGroupId: value(formData, "resourceGroupId"),
      serviceId: value(formData, "serviceId"),
    });
  if (!parsed.success) {
    redirect(destination(`/${locale}/dashboard/resources`, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantAccess(locale);
    await schedulingRepository.setServiceResourceRequirement(
      access,
      parsed.data,
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(`/${locale}/dashboard/resources`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/dashboard/resources`, "notice", "REQUIREMENT_SAVED"));
}

export async function createWaitlistEntryAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      appointmentId: uuidSchema.optional(),
      branchIds: z.array(uuidSchema).min(1).max(10),
      customerId: uuidSchema,
      notes: z.string().trim().max(500).optional(),
      preferredEndDate: z.iso.date(),
      preferredEndMinute: localTimeSchema,
      preferredStartDate: z.iso.date(),
      preferredStartMinute: localTimeSchema,
      priority: z.coerce.number().int().min(1).max(4),
      priorityReason: z.string().trim().max(500).optional(),
      providerIds: z.array(uuidSchema).length(1),
      serviceId: uuidSchema,
    })
    .superRefine((input, context) => {
      if (input.preferredStartMinute >= input.preferredEndMinute) {
        context.addIssue({
          code: "custom",
          message: "The preferred end time must be after the start time.",
          path: ["preferredEndMinute"],
        });
      }
    })
    .safeParse({
      appointmentId: value(formData, "appointmentId") || undefined,
      branchIds: formData.getAll("branchIds"),
      customerId: value(formData, "customerId"),
      notes: value(formData, "notes") || undefined,
      preferredEndDate: value(formData, "preferredEndDate"),
      preferredEndMinute: value(formData, "preferredEndTime"),
      preferredStartDate: value(formData, "preferredStartDate"),
      preferredStartMinute: value(formData, "preferredStartTime"),
      priority: value(formData, "priority"),
      priorityReason: value(formData, "priorityReason") || undefined,
      providerIds: formData.getAll("providerIds"),
      serviceId: value(formData, "serviceId"),
    });
  if (!parsed.success) {
    redirect(destination(`/${locale}/dashboard/waitlist`, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantAccess(locale);
    await schedulingRepository.createWaitlistEntry(
      access,
      parsed.data,
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(`/${locale}/dashboard/waitlist`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/dashboard/waitlist`, "notice", "WAITLIST_ADDED"));
}

export async function cancelWaitlistEntryAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({ entryId: uuidSchema, expectedVersion: z.coerce.number().int().positive() })
    .safeParse({
      entryId: value(formData, "entryId"),
      expectedVersion: value(formData, "expectedVersion"),
    });
  if (!parsed.success) {
    redirect(destination(`/${locale}/dashboard/waitlist`, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantAccess(locale);
    await schedulingRepository.cancelWaitlistEntry(
      access,
      parsed.data,
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(`/${locale}/dashboard/waitlist`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/dashboard/waitlist`, "notice", "WAITLIST_CANCELLED"));
}

export async function sendMockSlotOfferAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      branchId: uuidSchema,
      expiresInHours: z.coerce.number().int().min(1).max(168),
      providerId: uuidSchema,
      startsAtLocal: z.string().regex(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/),
      waitlistEntryId: uuidSchema,
    })
    .safeParse({
      branchId: value(formData, "branchId"),
      expiresInHours: value(formData, "expiresInHours"),
      providerId: value(formData, "providerId"),
      startsAtLocal: value(formData, "startsAtLocal"),
      waitlistEntryId: value(formData, "waitlistEntryId"),
    });
  if (!parsed.success) {
    redirect(destination(`/${locale}/dashboard/waitlist`, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantAccess(locale);
    await schedulingRepository.sendMockSlotOffer(
      access,
      {
        ...parsed.data,
        expiresAt: new Date(Date.now() + parsed.data.expiresInHours * 60 * 60 * 1000),
      },
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(`/${locale}/dashboard/waitlist`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/dashboard/waitlist`, "notice", "MOCK_OFFER_SENT"));
}

export async function bookWaitlistOpeningAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      cancelledAppointmentId: uuidSchema,
      requestKey: uuidSchema,
      waitlistEntryId: uuidSchema,
    })
    .safeParse({
      cancelledAppointmentId: value(formData, "cancelledAppointmentId"),
      requestKey: value(formData, "requestKey"),
      waitlistEntryId: value(formData, "waitlistEntryId"),
    });
  if (!parsed.success)
    redirect(
      destination(`/${locale}/schedule/waitlist?tab=openings`, "error", "VALIDATION_FAILED"),
    );
  try {
    const access = await requireTenantAccess(locale);
    await schedulingRepository.bookWaitlistOpening(
      access,
      parsed.data,
      await requestAuditDetails(),
    );
  } catch (error) {
    redirect(destination(`/${locale}/schedule/waitlist?tab=openings`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/schedule/appointments`, "notice", "WAITLIST_CONVERTED"));
}

async function resolveSlotOfferAction(
  formData: FormData,
  operation: "accept" | "decline" | "expire",
): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z.object({ offerId: uuidSchema, requestKey: uuidSchema.optional() }).safeParse({
    offerId: value(formData, "offerId"),
    requestKey: value(formData, "requestKey") || undefined,
  });
  if (!parsed.success || (operation !== "expire" && !parsed.data.requestKey)) {
    redirect(destination(`/${locale}/dashboard/waitlist`, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantAccess(locale);
    const details = await requestAuditDetails();
    if (operation === "accept") {
      const requestKey = parsed.data.requestKey;
      if (!requestKey) {
        redirect(destination(`/${locale}/dashboard/waitlist`, "error", "VALIDATION_FAILED"));
      }
      await schedulingRepository.acceptSlotOffer(
        access,
        { offerId: parsed.data.offerId, requestKey },
        details,
      );
    } else if (operation === "decline") {
      const requestKey = parsed.data.requestKey;
      if (!requestKey) {
        redirect(destination(`/${locale}/dashboard/waitlist`, "error", "VALIDATION_FAILED"));
      }
      await schedulingRepository.declineSlotOffer(
        access,
        { offerId: parsed.data.offerId, requestKey },
        details,
      );
    } else {
      await schedulingRepository.expireSlotOffer(access, parsed.data.offerId, new Date(), details);
    }
  } catch (error) {
    redirect(destination(`/${locale}/dashboard/waitlist`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/dashboard/waitlist`, "notice", "OFFER_UPDATED"));
}

export async function acceptSlotOfferAction(formData: FormData): Promise<never> {
  return resolveSlotOfferAction(formData, "accept");
}

export async function declineSlotOfferAction(formData: FormData): Promise<never> {
  return resolveSlotOfferAction(formData, "decline");
}

export async function expireSlotOfferAction(formData: FormData): Promise<never> {
  return resolveSlotOfferAction(formData, "expire");
}

export async function setCommunicationPreferenceAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      channel: z.enum([CommunicationChannel.SMS, CommunicationChannel.WHATSAPP]),
      customerId: uuidSchema,
      enabled: z.enum(["true", "false"]).transform((item) => item === "true"),
      reason: optionalText,
    })
    .safeParse({
      channel: value(formData, "channel"),
      customerId: value(formData, "customerId"),
      enabled: value(formData, "enabled"),
      reason: value(formData, "reason") || undefined,
    });
  if (!parsed.success)
    redirect(destination(`/${locale}/dashboard/customers`, "error", "VALIDATION_FAILED"));
  try {
    const access = await requireTenantPermission(locale, "communication_preferences.manage");
    await communicationRepository.setCommunicationPreference(access, parsed.data);
  } catch (error) {
    redirect(
      destination(
        `/${locale}/dashboard/customers/${parsed.data.customerId}`,
        "error",
        errorCode(error),
      ),
    );
  }
  redirect(
    destination(
      `/${locale}/dashboard/customers/${parsed.data.customerId}`,
      "notice",
      "PREFERENCE_UPDATED",
    ),
  );
}

export async function sendTemplateMessageAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      appointmentId: z.union([uuidSchema, z.literal("")]).transform((item) => item || undefined),
      channel: z.enum([CommunicationChannel.SMS, CommunicationChannel.WHATSAPP]),
      customerId: uuidSchema,
      messageLocale: z.enum(["en", "ar"]),
      templateKey: z.enum(communicationTemplateKeys),
    })
    .safeParse({
      appointmentId: value(formData, "appointmentId") ?? "",
      channel: value(formData, "channel"),
      customerId: value(formData, "customerId"),
      messageLocale: value(formData, "messageLocale"),
      templateKey: value(formData, "templateKey"),
    });
  if (!parsed.success)
    redirect(destination(`/${locale}/dashboard/communications`, "error", "VALIDATION_FAILED"));
  try {
    const access = await requireTenantAccess(locale);
    await communicationRepository.createOutboundMessage(access, {
      ...(parsed.data.appointmentId ? { appointmentId: parsed.data.appointmentId } : {}),
      channel: parsed.data.channel,
      customerId: parsed.data.customerId,
      locale: parsed.data.messageLocale,
      templateKey: parsed.data.templateKey,
    });
  } catch (error) {
    redirect(destination(`/${locale}/dashboard/communications`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/dashboard/communications`, "notice", "MESSAGE_QUEUED"));
}

export async function retryMessageAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const messageId = uuidSchema.safeParse(value(formData, "messageId"));
  if (!messageId.success)
    redirect(destination(`/${locale}/dashboard/communications`, "error", "VALIDATION_FAILED"));
  try {
    const access = await requireTenantPermission(locale, "messages.retry");
    await communicationRepository.retryMessage(access, messageId.data);
  } catch (error) {
    redirect(destination(`/${locale}/dashboard/communications`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/dashboard/communications`, "notice", "MESSAGE_RETRY_QUEUED"));
}

export async function setMockProviderBehaviorAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      behavior: z.enum([
        MockProviderBehavior.SUCCESS,
        MockProviderBehavior.TRANSIENT_ONCE,
        MockProviderBehavior.TIMEOUT,
        MockProviderBehavior.PERMANENT_FAILURE,
      ]),
      connectionId: uuidSchema,
    })
    .safeParse({
      behavior: value(formData, "behavior"),
      connectionId: value(formData, "connectionId"),
    });
  if (!parsed.success) {
    redirect(destination(`/${locale}/dashboard/communications`, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantPermission(locale, "provider_credentials.manage");
    await communicationRepository.setMockProviderBehavior(
      access,
      parsed.data.connectionId,
      parsed.data.behavior,
    );
  } catch (error) {
    redirect(destination(`/${locale}/dashboard/communications`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/dashboard/communications`, "notice", "PROVIDER_UPDATED"));
}

export async function ingestKnowledgeAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const upload = value(formData, "upload");
  const parsed = z
    .object({
      name: z.string().trim().min(2).max(180),
      sourceId: z.union([uuidSchema, z.literal("")]).transform((item) => item || undefined),
      textContent: z.string().max(200_000),
      title: z.string().trim().min(2).max(220),
    })
    .safeParse({
      name: value(formData, "name"),
      sourceId: value(formData, "sourceId") ?? "",
      textContent: value(formData, "textContent") ?? "",
      title: value(formData, "title"),
    });
  if (!parsed.success) {
    redirect(destination(`/${locale}/dashboard/knowledge`, "error", "VALIDATION_FAILED"));
  }
  let content = parsed.data.textContent;
  let originalFilename: string | undefined;
  if (upload instanceof File && upload.size > 0) {
    const safeType = ["text/markdown", "text/plain", ""].includes(upload.type);
    const safeName = /\.(md|markdown|txt)$/i.test(upload.name);
    if (!safeType || !safeName || upload.size > 200_000 || upload.name.length > 255) {
      redirect(destination(`/${locale}/dashboard/knowledge`, "error", "VALIDATION_FAILED"));
    }
    content = await upload.text();
    originalFilename = upload.name;
  }
  if (!content.trim()) {
    redirect(destination(`/${locale}/dashboard/knowledge`, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantPermission(locale, "knowledge.manage");
    await aiFoundationRepository.ingestKnowledge(access, {
      content,
      name: parsed.data.name,
      ...(originalFilename ? { originalFilename } : {}),
      ...(parsed.data.sourceId ? { sourceId: parsed.data.sourceId } : {}),
      title: parsed.data.title,
    });
    revalidatePath(`/${locale}/dashboard/knowledge`);
  } catch (error) {
    redirect(destination(`/${locale}/dashboard/knowledge`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/dashboard/knowledge`, "notice", "KNOWLEDGE_INGESTED"));
}

export async function activateKnowledgeVersionAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({ sourceId: uuidSchema, versionId: uuidSchema })
    .safeParse({ sourceId: value(formData, "sourceId"), versionId: value(formData, "versionId") });
  if (!parsed.success) {
    redirect(destination(`/${locale}/dashboard/knowledge`, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantPermission(locale, "knowledge.manage");
    await aiFoundationRepository.activateKnowledgeVersion(
      access,
      parsed.data.sourceId,
      parsed.data.versionId,
    );
    revalidatePath(`/${locale}/dashboard/knowledge`);
  } catch (error) {
    redirect(destination(`/${locale}/dashboard/knowledge`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/dashboard/knowledge`, "notice", "KNOWLEDGE_ACTIVATED"));
}

export async function updateAIConfigurationAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      allowedActionNames: z.array(z.enum(aiActionNames)).min(1),
      businessGuidance: z.string().trim().max(2_000).optional(),
      expectedVersion: z.coerce.number().int().min(1),
      minimumConfidence: z.coerce.number().min(0.5).max(1),
      monthlyActionLimit: z.coerce.number().int().min(0).max(1_000_000),
      monthlyCostLimitMicros: z.coerce.number().int().min(0),
      monthlyTokenLimit: z.coerce.number().int().min(0).max(1_000_000_000),
    })
    .safeParse({
      allowedActionNames: formData.getAll("allowedActionNames"),
      businessGuidance: value(formData, "businessGuidance") || undefined,
      expectedVersion: value(formData, "expectedVersion"),
      minimumConfidence: value(formData, "minimumConfidence"),
      monthlyActionLimit: value(formData, "monthlyActionLimit"),
      monthlyCostLimitMicros: value(formData, "monthlyCostLimitMicros"),
      monthlyTokenLimit: value(formData, "monthlyTokenLimit"),
    });
  if (!parsed.success) {
    redirect(destination(`/${locale}/dashboard/ai-settings`, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantPermission(locale, "ai.configure");
    await aiFoundationRepository.updatePromptConfiguration(access, parsed.data);
    revalidatePath(`/${locale}/dashboard/ai-settings`);
  } catch (error) {
    redirect(destination(`/${locale}/dashboard/ai-settings`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/dashboard/ai-settings`, "notice", "AI_CONFIGURATION_UPDATED"));
}

export async function updateHumanHandoffAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      assignedMembershipId: z
        .union([uuidSchema, z.literal("")])
        .transform((item) => item || undefined),
      handoffId: uuidSchema,
      status: z.enum(["ASSIGNED", "CLOSED", "RESOLVED"]),
    })
    .safeParse({
      assignedMembershipId: value(formData, "assignedMembershipId") ?? "",
      handoffId: value(formData, "handoffId"),
      status: value(formData, "status"),
    });
  if (!parsed.success) {
    redirect(destination(`/${locale}/dashboard/ai-handoffs`, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantPermission(locale, "conversations.handoff");
    await aiFoundationRepository.updateHumanHandoff(
      access,
      parsed.data.handoffId,
      parsed.data.status,
      parsed.data.assignedMembershipId,
    );
    revalidatePath(`/${locale}/dashboard/ai-handoffs`);
  } catch (error) {
    redirect(destination(`/${locale}/dashboard/ai-handoffs`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/dashboard/ai-handoffs`, "notice", "HANDOFF_UPDATED"));
}

export async function createWidgetConfigurationAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      accentColor: z.string().regex(/^#[0-9a-f]{6}$/i),
      allowedOrigins: z
        .string()
        .max(10_000)
        .transform((item) =>
          item
            .split(/\r?\n/u)
            .map((origin) => origin.trim())
            .filter(Boolean),
        )
        .pipe(z.array(z.string().url()).min(1).max(20)),
      defaultLocale: z.enum(["en", "ar"]),
      displayNameAr: z.string().trim().min(2).max(160),
      displayNameEn: z.string().trim().min(2).max(160),
      name: z.string().trim().min(2).max(120),
      primaryColor: z.string().regex(/^#[0-9a-f]{6}$/i),
    })
    .safeParse({
      accentColor: value(formData, "accentColor"),
      allowedOrigins: value(formData, "allowedOrigins"),
      defaultLocale: value(formData, "defaultLocale"),
      displayNameAr: value(formData, "displayNameAr"),
      displayNameEn: value(formData, "displayNameEn"),
      name: value(formData, "name"),
      primaryColor: value(formData, "primaryColor"),
    });
  if (!parsed.success) {
    redirect(destination(`/${locale}/dashboard/ai-channels`, "error", "VALIDATION_FAILED"));
  }
  try {
    const access = await requireTenantPermission(locale, "ai.configure");
    await aiChannelRepository.createWidgetConfiguration(access, parsed.data);
    revalidatePath(`/${locale}/dashboard/ai-channels`);
  } catch (error) {
    redirect(destination(`/${locale}/dashboard/ai-channels`, "error", errorCode(error)));
  }
  redirect(destination(`/${locale}/dashboard/ai-channels`, "notice", "AI_WIDGET_CREATED"));
}

export async function generateCopilotInsightAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const parsed = z
    .object({
      branchId: z.union([uuidSchema, z.literal("")]).transform((entry) => entry || undefined),
      endsOn: z.iso.date().optional(),
      insightType: z.enum(copilotInsightTypes),
      metric: z.enum(semanticMetricKeys).optional(),
      startsOn: z.iso.date().optional(),
      subjectId: z.union([uuidSchema, z.literal("")]).transform((entry) => entry || undefined),
    })
    .safeParse({
      branchId: value(formData, "branchId") ?? "",
      endsOn: value(formData, "endsOn") || undefined,
      insightType: value(formData, "insightType"),
      metric: value(formData, "metric") || undefined,
      startsOn: value(formData, "startsOn") || undefined,
      subjectId: value(formData, "subjectId") ?? "",
    });
  const fallbackPath = `/${locale}/dashboard/copilot`;
  if (!parsed.success) {
    redirect(destination(fallbackPath, "error", "VALIDATION_FAILED"));
  }
  const subjectPath =
    parsed.data.insightType === "CUSTOMER_SUMMARY" && parsed.data.subjectId
      ? `/${locale}/dashboard/customers/${parsed.data.subjectId}`
      : fallbackPath;
  try {
    const access = await requireTenantAccess(locale);
    const metricQuery =
      parsed.data.insightType === "ANALYTICS" &&
      parsed.data.metric &&
      parsed.data.startsOn &&
      parsed.data.endsOn
        ? {
            ...(parsed.data.branchId ? { branchId: parsed.data.branchId } : {}),
            endsAt: new Date(`${parsed.data.endsOn}T23:59:59.999Z`).toISOString(),
            metric: parsed.data.metric,
            startsAt: new Date(`${parsed.data.startsOn}T00:00:00.000Z`).toISOString(),
          }
        : undefined;
    await staffCopilotService.generate(access, {
      insightType: parsed.data.insightType,
      locale,
      ...(metricQuery ? { metricQuery } : {}),
      ...(parsed.data.subjectId ? { subjectId: parsed.data.subjectId } : {}),
    });
    revalidatePath(subjectPath);
  } catch (error) {
    redirect(destination(subjectPath, "error", errorCode(error)));
  }
  redirect(destination(subjectPath, "notice", "COPILOT_INSIGHT_GENERATED"));
}

export async function recordCopilotFeedbackAction(formData: FormData): Promise<never> {
  const locale = localeFrom(formData);
  const path = `/${locale}/dashboard/copilot`;
  const parsed = z
    .object({
      comment: z.string().trim().max(500).optional(),
      feedbackType: z.enum(copilotFeedbackTypes),
      insightId: uuidSchema,
    })
    .safeParse({
      comment: value(formData, "comment") || undefined,
      feedbackType: value(formData, "feedbackType"),
      insightId: value(formData, "insightId"),
    });
  if (!parsed.success) redirect(destination(path, "error", "VALIDATION_FAILED"));
  try {
    const access = await requireTenantAccess(locale);
    await copilotRepository.recordFeedback(
      access,
      parsed.data.insightId,
      parsed.data.feedbackType,
      parsed.data.comment,
    );
    revalidatePath(path);
  } catch (error) {
    redirect(destination(path, "error", errorCode(error)));
  }
  redirect(destination(path, "notice", "COPILOT_FEEDBACK_RECORDED"));
}
