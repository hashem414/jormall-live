import { createHash } from "node:crypto";

import { DomainError } from "@jormall/domain/errors";
import type {
  PermissionCode,
  PermissionScope,
  TenantAccessSnapshot,
} from "@jormall/domain/identity";
import {
  calculateProjectedStock,
  calculateStockHealth,
  computeExpiryAlert,
  recommendFefoBatch,
} from "@jormall/domain/inventory";

import { Prisma } from "./generated/prisma/client";
import type {
  InventoryCategory,
  InventoryReservationMode,
  PrismaClient,
  StockMovementType,
} from "./generated/prisma/client";
import { runInTenant, type TenantTransaction } from "./tenant-context";

export type WorkflowAuditDetails = Readonly<{
  ipAddress?: string | undefined;
  userAgent?: string | undefined;
}>;

const rank: Readonly<Record<PermissionScope, number>> = {
  ASSIGNED_BRANCHES: 2,
  ORGANIZATION: 3,
  SELF: 1,
};

function scopeFor(access: TenantAccessSnapshot, permission: PermissionCode): PermissionScope {
  const scope = access.grants
    .filter((grant) => grant.code === permission)
    .toSorted((a, b) => rank[b.scope] - rank[a.scope])[0]?.scope;
  if (!scope) throw new DomainError({ code: "FORBIDDEN", message: "Permission is required." });
  return scope;
}

function branchWhere(
  scope: PermissionScope,
  access: TenantAccessSnapshot,
): Readonly<{ branchId?: { in: string[] } }> {
  if (access.activeBranchId) return { branchId: { in: [access.activeBranchId] } };
  return scope === "ORGANIZATION" ? {} : { branchId: { in: [...access.assignedBranchIds] } };
}

function requireBranch(
  access: TenantAccessSnapshot,
  permission: PermissionCode,
  branchId: string,
): PermissionScope {
  if (access.activeBranchId && branchId !== access.activeBranchId) {
    throw new DomainError({
      code: "NOT_FOUND",
      message: "The record is not available in the active branch.",
    });
  }
  const scope = scopeFor(access, permission);
  if (scope === "ORGANIZATION" || access.assignedBranchIds.includes(branchId)) return scope;
  throw new DomainError({ code: "FORBIDDEN", message: "The branch is outside the granted scope." });
}

function fingerprint(value: unknown): string {
  return createHash("sha256").update(JSON.stringify(value)).digest("hex");
}

async function audit(
  transaction: TenantTransaction,
  access: TenantAccessSnapshot,
  action: string,
  targetType: string,
  targetId: string,
  details?: WorkflowAuditDetails,
): Promise<void> {
  await transaction.auditEvent.create({
    data: {
      action,
      actorUserId: access.actorUserId,
      ipAddress: details?.ipAddress ?? null,
      organizationId: access.organizationId,
      supportAccessId: access.supportAccessId ?? null,
      targetId,
      targetType,
      userAgent: details?.userAgent ?? null,
    },
  });
}

async function permissionRecipients(
  transaction: TenantTransaction,
  organizationId: string,
  permission: PermissionCode,
): Promise<string[]> {
  const rows = await transaction.$queryRaw<Array<{ userId: string }>>(Prisma.sql`
    SELECT DISTINCT membership."user_id" AS "userId"
    FROM "organization_memberships" membership
    JOIN "membership_roles" membership_role ON membership_role."organization_id"=membership."organization_id" AND membership_role."membership_id"=membership."id"
    JOIN "role_permissions" role_permission ON role_permission."organization_id"=membership."organization_id" AND role_permission."role_id"=membership_role."role_id"
    JOIN "permissions" permission ON permission."id"=role_permission."permission_id"
    WHERE membership."organization_id"=${organizationId}::uuid AND membership."status"='ACTIVE' AND permission."code"=${permission}
  `);
  return rows.map(({ userId }) => userId);
}

type SafeNotification = Readonly<{
  branchId?: string;
  entityId?: string;
  entityType?: string;
  messageAr: string;
  messageEn: string;
  priority?: "LOW" | "NORMAL" | "HIGH" | "URGENT";
  recipientUserId: string;
  route: string;
  titleAr: string;
  titleEn: string;
  type: string;
}>;

async function createNotification(
  transaction: TenantTransaction,
  organizationId: string,
  input: SafeNotification,
) {
  return transaction.notification.createMany({
    data: [
      {
        branchId: input.branchId ?? null,
        messageAr: input.messageAr.slice(0, 300),
        messageEn: input.messageEn.slice(0, 300),
        organizationId,
        priority: input.priority ?? "NORMAL",
        recipientUserId: input.recipientUserId,
        relatedEntityId: input.entityId ?? null,
        relatedEntityType: input.entityType ?? null,
        targetRoute: input.route,
        titleAr: input.titleAr,
        titleEn: input.titleEn,
        type: input.type,
      },
    ],
  });
}

async function createInventoryNotificationOnce(
  transaction: TenantTransaction,
  access: TenantAccessSnapshot,
  input: Omit<SafeNotification, "recipientUserId">,
): Promise<void> {
  const recipients = await permissionRecipients(
    transaction,
    access.organizationId,
    "inventory.orderRequest.approve",
  );
  await Promise.all(
    recipients.map(async (recipientUserId) => {
      const existing = await transaction.notification.findFirst({
        where: {
          doneAt: null,
          organizationId: access.organizationId,
          recipientUserId,
          ...(input.entityId ? { relatedEntityId: input.entityId } : {}),
          type: input.type,
        },
      });
      if (!existing) {
        await createNotification(transaction, access.organizationId, {
          ...input,
          recipientUserId,
        });
      }
    }),
  );
}

async function notifyCurrentStockRisk(
  transaction: TenantTransaction,
  access: TenantAccessSnapshot,
  itemId: string,
): Promise<void> {
  const item = await transaction.inventoryItem.findFirst({
    where: { id: itemId, organizationId: access.organizationId },
  });
  if (!item) return;
  const onHand = Number(item.currentStock);
  const minimum = Number(item.minimumStock);
  if (onHand > minimum) return;
  const out = onHand <= 0;
  await createInventoryNotificationOnce(transaction, access, {
    branchId: item.branchId,
    entityId: item.id,
    entityType: "InventoryItem",
    messageAr: out
      ? `نفد مخزون ${item.name}. الرصيد الحالي 0 ${item.unitOfMeasure}.`
      : `انخفض مخزون ${item.name} إلى ${onHand} ${item.unitOfMeasure} (الحد الأدنى ${minimum}).`,
    messageEn: out
      ? `${item.name} is out of stock (0 ${item.unitOfMeasure}).`
      : `${item.name} is low: ${onHand} ${item.unitOfMeasure} on hand (minimum ${minimum}).`,
    priority: out ? "URGENT" : "HIGH",
    route: `/business/inventory?tab=items&item=${item.id}`,
    titleAr: out ? "نفد المخزون" : "مخزون منخفض",
    titleEn: out ? "Out of Stock" : "Low Stock",
    type: out ? "INVENTORY_OUT_OF_STOCK" : "INVENTORY_LOW_STOCK",
  });
}

async function notifyProjectedStockRisk(
  transaction: TenantTransaction,
  access: TenantAccessSnapshot,
  branchId: string,
): Promise<void> {
  const [appointments, requirements, items] = await Promise.all([
    transaction.appointment.findMany({
      select: { serviceId: true },
      where: {
        branchId,
        organizationId: access.organizationId,
        startsAt: { gte: new Date() },
        status: { in: ["CONFIRMED", "CHECKED_IN", "IN_PROGRESS"] },
      },
    }),
    transaction.serviceInventoryRequirement.findMany({
      where: {
        organizationId: access.organizationId,
        reservationMode: { not: "NONE" },
      },
    }),
    transaction.inventoryItem.findMany({
      where: { branchId, isActive: true, organizationId: access.organizationId },
    }),
  ]);
  const serviceCounts = new Map<string, number>();
  for (const appointment of appointments) {
    serviceCounts.set(appointment.serviceId, (serviceCounts.get(appointment.serviceId) ?? 0) + 1);
  }
  const demand = new Map<string, number>();
  for (const requirement of requirements) {
    const count = serviceCounts.get(requirement.serviceId) ?? 0;
    demand.set(
      requirement.itemId,
      (demand.get(requirement.itemId) ?? 0) + count * Number(requirement.expectedQuantity),
    );
  }
  for (const item of items) {
    const upcoming = demand.get(item.id) ?? 0;
    const available = Number(item.currentStock) - Number(item.reservedQuantity);
    const shortage = Math.max(0, upcoming - available);
    if (shortage <= 0) continue;
    await createInventoryNotificationOnce(transaction, access, {
      branchId,
      entityId: item.id,
      entityType: "InventoryItem",
      messageAr: `الطلب المتوقع على ${item.name} يتجاوز المتاح بمقدار ${shortage} ${item.unitOfMeasure}.`,
      messageEn: `${item.name} has a projected appointment shortage of ${shortage} ${item.unitOfMeasure}.`,
      priority: "HIGH",
      route: `/business/inventory?tab=overview&item=${item.id}`,
      titleAr: "نقص متوقع للمواعيد",
      titleEn: "Projected Appointment Shortage",
      type: "INVENTORY_PROJECTED_SHORTAGE",
    });
  }
}

export type AppointmentConsumptionItemInput = Readonly<{
  itemId: string;
  expectedQuantity?: number | undefined;
  actualQuantity: number;
  batchId?: string | undefined;
  locationId?: string | undefined;
  reconciliationNote?: string | undefined;
}>;

export async function ensureDefaultLocation(
  transaction: TenantTransaction,
  organizationId: string,
  branchId: string,
): Promise<{ id: string; name: string }> {
  const existing = await transaction.inventoryLocation.findFirst({
    where: { organizationId, branchId },
    orderBy: [{ isDefault: "desc" }, { createdAt: "asc" }],
  });
  if (existing) return existing;
  return transaction.inventoryLocation.create({
    data: {
      organizationId,
      branchId,
      name: "Main Store",
      description: "Main Store Default Location",
      isDefault: true,
      isActive: true,
    },
  });
}

export async function recordStockMovement(
  transaction: TenantTransaction,
  access: TenantAccessSnapshot,
  input: Readonly<{
    branchId: string;
    itemId: string;
    locationId: string;
    batchId?: string | null | undefined;
    movementType: StockMovementType;
    quantityChange: number;
    reason: string;
    relatedAppointmentId?: string | null | undefined;
    relatedOrderId?: string | null | undefined;
    idempotencyKey?: string | null | undefined;
  }>,
): Promise<{ id: string; balanceBefore: number; balanceAfter: number }> {
  if (input.idempotencyKey) {
    const existing = await transaction.inventoryStockMovement.findFirst({
      where: {
        organizationId: access.organizationId,
        requestKey: input.idempotencyKey,
      },
    });
    if (existing) {
      return {
        id: existing.id,
        balanceBefore: Number(existing.balanceBefore),
        balanceAfter: Number(existing.balanceAfter),
      };
    }
  }

  await transaction.$queryRaw(
    Prisma.sql`SELECT "id" FROM "inventory_items" WHERE "organization_id"=${access.organizationId}::uuid AND "id"=${input.itemId}::uuid FOR UPDATE`,
  );

  const item = await transaction.inventoryItem.findFirstOrThrow({
    where: {
      branchId: input.branchId,
      id: input.itemId,
      organizationId: access.organizationId,
    },
  });

  const location = await transaction.inventoryLocation.findFirst({
    where: {
      branchId: input.branchId,
      id: input.locationId,
      isActive: true,
      organizationId: access.organizationId,
    },
  });
  if (!location) {
    throw new DomainError({
      code: "NOT_FOUND",
      message: "The inventory location is not available in this branch.",
    });
  }

  const balanceBefore = Number(item.currentStock);
  const balanceAfter = balanceBefore + input.quantityChange;

  if (balanceAfter < 0) {
    throw new DomainError({
      code: "CONFLICT",
      message: "This movement would make the item stock negative.",
    });
  }

  await transaction.inventoryItem.update({
    where: { id: input.itemId },
    data: {
      currentStock: balanceAfter,
      version: { increment: 1 },
    },
  });

  const locStock = await transaction.itemLocationStock.findUnique({
    where: {
      organizationId_itemId_locationId: {
        organizationId: access.organizationId,
        itemId: input.itemId,
        locationId: input.locationId,
      },
    },
  });

  const locationBalanceAfter = Number(locStock?.quantity ?? 0) + input.quantityChange;
  if (locationBalanceAfter < 0) {
    throw new DomainError({
      code: "CONFLICT",
      message: "This movement would make the location stock negative.",
    });
  }

  if (locStock) {
    await transaction.itemLocationStock.update({
      where: { id: locStock.id },
      data: {
        quantity: { increment: input.quantityChange },
      },
    });
  } else {
    await transaction.itemLocationStock.create({
      data: {
        organizationId: access.organizationId,
        branchId: input.branchId,
        itemId: input.itemId,
        locationId: input.locationId,
        quantity: input.quantityChange,
      },
    });
  }

  if (input.batchId) {
    const batch = await transaction.inventoryBatch.findFirst({
      where: {
        branchId: input.branchId,
        id: input.batchId,
        itemId: input.itemId,
        locationId: input.locationId,
        organizationId: access.organizationId,
      },
    });
    if (!batch) {
      throw new DomainError({
        code: "NOT_FOUND",
        message: "The inventory batch is not available for this item and location.",
      });
    }
    if (Number(batch.quantity) + input.quantityChange < 0) {
      throw new DomainError({
        code: "CONFLICT",
        message: "This movement would make the batch stock negative.",
      });
    }
    await transaction.inventoryBatch.update({
      where: { id: input.batchId },
      data: {
        quantity: { increment: input.quantityChange },
      },
    });
  }

  const movement = await transaction.inventoryStockMovement.create({
    data: {
      organizationId: access.organizationId,
      branchId: input.branchId,
      itemId: input.itemId,
      locationId: input.locationId,
      batchId: input.batchId ?? null,
      type: input.movementType,
      quantity: input.quantityChange,
      balanceBefore,
      balanceAfter,
      reason: input.reason.trim(),
      appointmentId: input.relatedAppointmentId ?? null,
      orderRequestId: input.relatedOrderId ?? null,
      actorUserId: access.actorUserId,
      requestKey: input.idempotencyKey ?? null,
    },
  });

  return {
    id: movement.id,
    balanceBefore,
    balanceAfter,
  };
}

export async function reserveStockForConfirmedAppointment(
  transaction: TenantTransaction,
  access: TenantAccessSnapshot,
  appointmentId: string,
): Promise<void> {
  const appointment = await transaction.appointment.findFirstOrThrow({
    where: { id: appointmentId, organizationId: access.organizationId },
  });
  const serviceRequirements = await transaction.serviceInventoryRequirement.findMany({
    where: {
      organizationId: access.organizationId,
      serviceId: appointment.serviceId,
      reservationMode: { not: "NONE" },
    },
  });
  if (serviceRequirements.length === 0) return;
  const requirements = serviceRequirements.filter(
    ({ reservationMode }) => reservationMode === "RESERVE_ON_CONFIRMATION",
  );

  const defaultLoc =
    requirements.length > 0
      ? await ensureDefaultLocation(transaction, access.organizationId, appointment.branchId)
      : null;

  for (const req of requirements) {
    if (!defaultLoc) {
      throw new DomainError({ code: "CONFLICT", message: "Default stock location is missing." });
    }
    const existing = await transaction.inventoryReservation.findFirst({
      where: {
        organizationId: access.organizationId,
        appointmentId: appointment.id,
        itemId: req.itemId,
        releasedAt: null,
        consumedAt: null,
      },
    });
    if (existing) continue;

    await transaction.inventoryReservation.create({
      data: {
        organizationId: access.organizationId,
        branchId: appointment.branchId,
        appointmentId: appointment.id,
        itemId: req.itemId,
        quantity: req.expectedQuantity,
      },
    });

    await transaction.inventoryItem.update({
      where: { id: req.itemId },
      data: {
        reservedQuantity: {
          increment: req.expectedQuantity,
        },
        version: { increment: 1 },
      },
    });

    await recordStockMovement(transaction, access, {
      branchId: appointment.branchId,
      itemId: req.itemId,
      locationId: defaultLoc.id,
      movementType: "RESERVATION",
      quantityChange: 0,
      reason: `Reserved for confirmed appointment #${appointment.id}`,
      relatedAppointmentId: appointment.id,
    });
  }
  await notifyProjectedStockRisk(transaction, access, appointment.branchId);
}

export async function releaseStockReservations(
  transaction: TenantTransaction,
  access: TenantAccessSnapshot,
  appointmentId: string,
  reason: string,
): Promise<void> {
  const reservations = await transaction.inventoryReservation.findMany({
    where: {
      organizationId: access.organizationId,
      appointmentId,
      releasedAt: null,
      consumedAt: null,
    },
  });

  if (reservations.length === 0) return;

  const now = new Date();
  const appointment = await transaction.appointment.findFirstOrThrow({
    where: { id: appointmentId, organizationId: access.organizationId },
  });
  const defaultLoc = await ensureDefaultLocation(
    transaction,
    access.organizationId,
    appointment.branchId,
  );

  for (const res of reservations) {
    await transaction.inventoryReservation.update({
      where: { id: res.id },
      data: { releasedAt: now },
    });

    await transaction.inventoryItem.update({
      where: { id: res.itemId },
      data: {
        reservedQuantity: {
          decrement: res.quantity,
        },
        version: { increment: 1 },
      },
    });

    await recordStockMovement(transaction, access, {
      branchId: res.branchId,
      itemId: res.itemId,
      locationId: defaultLoc.id,
      movementType: "RESERVATION_RELEASE",
      quantityChange: 0,
      reason: `Reservation released (${reason}) for appointment #${appointmentId}`,
      relatedAppointmentId: appointmentId,
    });
  }
}

export async function recordAppointmentConsumption(
  transaction: TenantTransaction,
  access: TenantAccessSnapshot,
  appointmentId: string,
  consumptions?: readonly AppointmentConsumptionItemInput[] | undefined,
  details?: WorkflowAuditDetails,
): Promise<void> {
  const consumptionScope = consumptions?.length
    ? scopeFor(access, "inventory.consumption.adjust")
    : null;
  const existing = await transaction.appointmentInventoryConsumption.findFirst({
    where: { organizationId: access.organizationId, appointmentId },
  });
  if (existing) return;

  const appointment = await transaction.appointment.findFirstOrThrow({
    where: { id: appointmentId, organizationId: access.organizationId },
  });
  if (access.activeBranchId && appointment.branchId !== access.activeBranchId) {
    throw new DomainError({ code: "NOT_FOUND", message: "Appointment not found." });
  }
  if (
    consumptionScope === "ASSIGNED_BRANCHES" &&
    !access.assignedBranchIds.includes(appointment.branchId)
  ) {
    throw new DomainError({ code: "NOT_FOUND", message: "Appointment not found." });
  }
  if (
    consumptionScope === "SELF" &&
    (!access.staffProfileId || appointment.providerId !== access.staffProfileId)
  ) {
    throw new DomainError({ code: "NOT_FOUND", message: "Appointment not found." });
  }

  const defaultLoc = await ensureDefaultLocation(
    transaction,
    access.organizationId,
    appointment.branchId,
  );

  let itemsToConsume: Array<{
    itemId: string;
    expectedQuantity: number;
    actualQuantity: number;
    batchId?: string | undefined;
    locationId?: string | undefined;
    reconciliationNote?: string | undefined;
  }> = [];

  if (consumptions && consumptions.length > 0) {
    itemsToConsume = consumptions.map((c) => ({
      itemId: c.itemId,
      expectedQuantity: c.expectedQuantity ?? c.actualQuantity,
      actualQuantity: c.actualQuantity,
      batchId: c.batchId,
      locationId: c.locationId ?? defaultLoc.id,
      reconciliationNote: c.reconciliationNote,
    }));
  } else {
    const requirements = await transaction.serviceInventoryRequirement.findMany({
      where: { organizationId: access.organizationId, serviceId: appointment.serviceId },
    });
    itemsToConsume = requirements.map((req) => ({
      itemId: req.itemId,
      expectedQuantity: Number(req.expectedQuantity),
      actualQuantity: Number(req.expectedQuantity),
      locationId: defaultLoc.id,
    }));
  }

  if (itemsToConsume.length === 0) return;

  const now = new Date();

  for (const itemUsage of itemsToConsume) {
    const reservation = await transaction.inventoryReservation.findFirst({
      where: {
        organizationId: access.organizationId,
        appointmentId,
        itemId: itemUsage.itemId,
        releasedAt: null,
        consumedAt: null,
      },
    });

    if (reservation) {
      await transaction.inventoryReservation.update({
        where: { id: reservation.id },
        data: { consumedAt: now },
      });
      await transaction.inventoryItem.update({
        where: { id: itemUsage.itemId },
        data: {
          reservedQuantity: {
            decrement: reservation.quantity,
          },
          version: { increment: 1 },
        },
      });
    }

    const item = await transaction.inventoryItem.findFirstOrThrow({
      where: {
        branchId: appointment.branchId,
        id: itemUsage.itemId,
        organizationId: access.organizationId,
      },
    });

    let selectedBatchId = itemUsage.batchId;
    if (!selectedBatchId && item.batchTrackingEnabled) {
      const activeBatches = await transaction.inventoryBatch.findMany({
        where: {
          branchId: appointment.branchId,
          organizationId: access.organizationId,
          itemId: item.id,
          isActive: true,
          quantity: { gt: 0 },
        },
      });
      const recommended = recommendFefoBatch(
        activeBatches.map((b) => ({
          ...b,
          quantity: Number(b.quantity),
          purchaseCost: b.purchaseCost ? Number(b.purchaseCost) : null,
        })),
      );
      selectedBatchId = recommended?.id;
    }

    const selectedBatch = selectedBatchId
      ? await transaction.inventoryBatch.findFirst({
          where: {
            branchId: appointment.branchId,
            id: selectedBatchId,
            itemId: item.id,
            organizationId: access.organizationId,
          },
        })
      : null;
    if (selectedBatchId && !selectedBatch) {
      throw new DomainError({ code: "NOT_FOUND", message: "Inventory batch not found." });
    }

    const locId = selectedBatch?.locationId ?? itemUsage.locationId ?? defaultLoc.id;
    const locationStock = await transaction.itemLocationStock.findUnique({
      where: {
        organizationId_itemId_locationId: {
          itemId: item.id,
          locationId: locId,
          organizationId: access.organizationId,
        },
      },
    });
    const availableQuantity = Math.max(
      0,
      Math.min(
        Number(item.currentStock),
        Number(locationStock?.quantity ?? 0),
        selectedBatch ? Number(selectedBatch.quantity) : Number.POSITIVE_INFINITY,
      ),
    );
    const deductedQuantity = Math.min(itemUsage.actualQuantity, availableQuantity);
    const isShortage = deductedQuantity < itemUsage.actualQuantity;
    const suppliedReconciliationNote = itemUsage.reconciliationNote?.trim() || null;
    const reconciliationNote = isShortage
      ? (suppliedReconciliationNote ??
        `Only ${deductedQuantity} of ${itemUsage.actualQuantity} could be deducted from recorded stock.`)
      : suppliedReconciliationNote;

    if (deductedQuantity > 0) {
      await recordStockMovement(transaction, access, {
        branchId: appointment.branchId,
        itemId: itemUsage.itemId,
        locationId: locId,
        batchId: selectedBatchId,
        movementType: "APPOINTMENT_CONSUMPTION",
        quantityChange: -deductedQuantity,
        reason: `Service completed for appointment #${appointment.id}`,
        relatedAppointmentId: appointment.id,
      });
      await notifyCurrentStockRisk(transaction, access, itemUsage.itemId);
    }

    await transaction.appointmentInventoryConsumption.create({
      data: {
        organizationId: access.organizationId,
        appointmentId: appointment.id,
        itemId: itemUsage.itemId,
        locationId: locId,
        batchId: selectedBatchId ?? null,
        expectedQuantity: itemUsage.expectedQuantity,
        actualQuantity: itemUsage.actualQuantity,
        unitOfMeasure: item.unitOfMeasure,
        isReconciliationRequired: isShortage,
        reconciliationNote,
      },
    });
  }

  const remainingReservations = await transaction.inventoryReservation.findMany({
    where: {
      organizationId: access.organizationId,
      appointmentId,
      releasedAt: null,
      consumedAt: null,
    },
  });
  for (const rem of remainingReservations) {
    await transaction.inventoryReservation.update({
      where: { id: rem.id },
      data: { releasedAt: now },
    });
    await transaction.inventoryItem.update({
      where: { id: rem.itemId },
      data: {
        reservedQuantity: {
          decrement: rem.quantity,
        },
        version: { increment: 1 },
      },
    });
    await recordStockMovement(transaction, access, {
      branchId: rem.branchId,
      itemId: rem.itemId,
      locationId: defaultLoc.id,
      movementType: "RESERVATION_RELEASE",
      quantityChange: 0,
      reason: `Unused reservation release for appointment #${appointment.id}`,
      relatedAppointmentId: appointment.id,
    });
  }

  await audit(
    transaction,
    access,
    "APPOINTMENT_INVENTORY_CONSUMED",
    "Appointment",
    appointment.id,
    details,
  );
}

export class OperationalWorkflowsRepository {
  constructor(readonly client: PrismaClient) {}

  private run<T>(
    access: TenantAccessSnapshot,
    operation: (transaction: TenantTransaction) => Promise<T>,
  ): Promise<T> {
    return runInTenant(this.client, access, operation);
  }

  async listNotifications(
    access: TenantAccessSnapshot,
    state: "ALL" | "UNREAD" | "READ" | "DONE" = "ALL",
    take = 50,
  ) {
    scopeFor(access, "notifications.read");
    return this.run(access, (transaction) =>
      transaction.notification.findMany({
        orderBy: { createdAt: "desc" },
        take: Math.min(Math.max(take, 1), 100),
        where: {
          ...(access.activeBranchId ? { branchId: access.activeBranchId } : {}),
          organizationId: access.organizationId,
          recipientUserId: access.actorUserId,
          ...(state === "UNREAD"
            ? { readAt: null, doneAt: null }
            : state === "READ"
              ? { readAt: { not: null }, doneAt: null }
              : state === "DONE"
                ? { doneAt: { not: null } }
                : {}),
        },
      }),
    );
  }

  async setNotificationState(
    access: TenantAccessSnapshot,
    input: Readonly<{ id: string; state: "READ" | "UNREAD" | "DONE" }>,
    details?: WorkflowAuditDetails,
  ) {
    scopeFor(access, "notifications.read");
    return this.run(access, async (transaction) => {
      const existing = await transaction.notification.findFirst({
        where: {
          ...(access.activeBranchId ? { branchId: access.activeBranchId } : {}),
          id: input.id,
          organizationId: access.organizationId,
          recipientUserId: access.actorUserId,
        },
      });
      if (!existing)
        throw new DomainError({ code: "NOT_FOUND", message: "Notification not found." });
      const now = new Date();
      const updated = await transaction.notification.update({
        data:
          input.state === "UNREAD"
            ? { doneAt: null, readAt: null }
            : input.state === "DONE"
              ? { doneAt: now, readAt: existing.readAt ?? now }
              : { readAt: existing.readAt ?? now },
        where: { id: existing.id },
      });
      await audit(
        transaction,
        access,
        `NOTIFICATION_${input.state}`,
        "Notification",
        existing.id,
        details,
      );
      return updated;
    });
  }

  async countUnreadNotifications(access: TenantAccessSnapshot): Promise<number> {
    scopeFor(access, "notifications.read");
    return this.run(access, (transaction) =>
      transaction.notification.count({
        where: {
          ...(access.activeBranchId ? { branchId: access.activeBranchId } : {}),
          doneAt: null,
          organizationId: access.organizationId,
          readAt: null,
          recipientUserId: access.actorUserId,
        },
      }),
    );
  }

  async markAllNotificationsDone(
    access: TenantAccessSnapshot,
    confirmation: string | undefined,
    details?: WorkflowAuditDetails,
  ) {
    scopeFor(access, "notifications.manage");
    return this.run(access, async (transaction) => {
      const high = await transaction.notification.count({
        where: {
          ...(access.activeBranchId ? { branchId: access.activeBranchId } : {}),
          doneAt: null,
          organizationId: access.organizationId,
          priority: { in: ["HIGH", "URGENT"] },
          recipientUserId: access.actorUserId,
        },
      });
      if (high > 0 && confirmation !== "CONFIRM_HIGH_PRIORITY")
        throw new DomainError({
          code: "VALIDATION_FAILED",
          message: "High-priority notifications require confirmation.",
        });
      const now = new Date();
      const result = await transaction.notification.updateMany({
        data: { doneAt: now, readAt: now },
        where: {
          ...(access.activeBranchId ? { branchId: access.activeBranchId } : {}),
          doneAt: null,
          organizationId: access.organizationId,
          recipientUserId: access.actorUserId,
        },
      });
      await audit(
        transaction,
        access,
        "NOTIFICATIONS_MARKED_DONE",
        "Notification",
        access.actorUserId,
        details,
      );
      return result.count;
    });
  }

  async listEscalations(access: TenantAccessSnapshot) {
    const scope = scopeFor(access, "chatbot_escalations.read");
    return this.run(access, (transaction) =>
      transaction.chatbotEscalation.findMany({
        include: {
          assignedMembership: { include: { user: { select: { name: true } } } },
          customer: { select: { displayName: true, id: true } },
        },
        orderBy: [{ severity: "desc" }, { createdAt: "asc" }],
        where: { organizationId: access.organizationId, ...branchWhere(scope, access) },
      }),
    );
  }

  async listEscalationAssignees(access: TenantAccessSnapshot) {
    scopeFor(access, "chatbot_escalations.manage");
    return this.run(access, (transaction) =>
      transaction.organizationMembership.findMany({
        orderBy: { user: { name: "asc" } },
        select: { id: true, user: { select: { name: true } } },
        where: { organizationId: access.organizationId, status: "ACTIVE" },
      }),
    );
  }

  async createEscalation(
    access: TenantAccessSnapshot,
    input: Readonly<{
      appointmentId?: string;
      branchId?: string;
      conversationId?: string;
      customerId?: string;
      email?: string;
      emergencySummary: string;
      patientName: string;
      phone?: string;
      relevantMessage: string;
      severity: "HIGH" | "CRITICAL";
      sourceChannel: "EMAIL" | "SMS" | "VOICE" | "WHATSAPP" | "INTERNAL";
      sourceActionId: string;
    }>,
    details?: WorkflowAuditDetails,
  ) {
    scopeFor(access, "chatbot_escalations.manage");
    if (
      !input.patientName.trim() ||
      !input.emergencySummary.trim() ||
      !input.relevantMessage.trim()
    )
      throw new DomainError({
        code: "VALIDATION_FAILED",
        message: "Escalation evidence is required.",
      });
    return this.run(access, async (transaction) => {
      const prior = await transaction.chatbotEscalation.findFirst({
        where: { organizationId: access.organizationId, sourceActionId: input.sourceActionId },
      });
      if (prior) return prior;
      if (input.branchId) requireBranch(access, "chatbot_escalations.manage", input.branchId);
      const escalation = await transaction.chatbotEscalation.create({
        data: {
          appointmentId: input.appointmentId ?? null,
          branchId: input.branchId ?? null,
          conversationId: input.conversationId ?? null,
          customerId: input.customerId ?? null,
          email: input.email?.trim() || null,
          emergencySummary: input.emergencySummary.trim(),
          organizationId: access.organizationId,
          patientName: input.patientName.trim(),
          phone: input.phone?.trim() || null,
          relevantMessage: input.relevantMessage.trim(),
          severity: input.severity,
          sourceActionId: input.sourceActionId,
          sourceChannel: input.sourceChannel,
        },
      });
      await transaction.chatbotEscalationHistory.create({
        data: {
          organizationId: access.organizationId,
          toStatus: "NEW",
          escalationId: escalation.id,
        },
      });
      const recipients = await permissionRecipients(
        transaction,
        access.organizationId,
        "chatbot_escalations.manage",
      );
      await Promise.all(
        recipients.map((recipientUserId) =>
          createNotification(transaction, access.organizationId, {
            ...(input.branchId ? { branchId: input.branchId } : {}),
            entityId: escalation.id,
            entityType: "ChatbotEscalation",
            messageAr: "تم إنشاء تصعيد عاجل من المساعد الآلي للمراجعة.",
            messageEn: "A chatbot emergency escalation requires review.",
            priority: input.severity === "CRITICAL" ? "URGENT" : "HIGH",
            recipientUserId,
            route: `/inbox/escalations?escalation=${escalation.id}`,
            titleAr: "تصعيد طارئ",
            titleEn: "Emergency Escalation",
            type: "EMERGENCY_ESCALATION",
          }),
        ),
      );
      await audit(
        transaction,
        access,
        "CHATBOT_ESCALATION_CREATED",
        "ChatbotEscalation",
        escalation.id,
        details,
      );
      return escalation;
    });
  }

  async updateEscalation(
    access: TenantAccessSnapshot,
    input: Readonly<{
      assignedMembershipId?: string | undefined;
      expectedVersion: number;
      id: string;
      reason?: string | undefined;
      status: "NEW" | "ACKNOWLEDGED" | "IN_PROGRESS" | "RESOLVED" | "DISMISSED";
    }>,
    details?: WorkflowAuditDetails,
  ) {
    scopeFor(access, "chatbot_escalations.manage");
    if ((input.status === "RESOLVED" || input.status === "DISMISSED") && !input.reason?.trim())
      throw new DomainError({
        code: "VALIDATION_FAILED",
        message: "A resolution or dismissal reason is required.",
      });
    return this.run(access, async (transaction) => {
      const current = await transaction.chatbotEscalation.findFirst({
        where: { id: input.id, organizationId: access.organizationId },
      });
      if (!current) throw new DomainError({ code: "NOT_FOUND", message: "Escalation not found." });
      if (current.branchId) requireBranch(access, "chatbot_escalations.manage", current.branchId);
      let assignedUserId: string | null | undefined;
      if (input.assignedMembershipId) {
        const membership = await transaction.organizationMembership.findFirst({
          where: {
            id: input.assignedMembershipId,
            organizationId: access.organizationId,
            status: "ACTIVE",
          },
        });
        if (!membership)
          throw new DomainError({ code: "NOT_FOUND", message: "Assignee not found." });
        assignedUserId = membership.userId;
      }
      const update: Prisma.ChatbotEscalationUncheckedUpdateManyInput = {
        acknowledgedAt: input.status === "ACKNOWLEDGED" ? new Date() : current.acknowledgedAt,
        resolutionNote: input.reason?.trim() || null,
        resolvedAt: input.status === "RESOLVED" || input.status === "DISMISSED" ? new Date() : null,
        status: input.status,
        version: { increment: 1 },
      };
      if (input.assignedMembershipId && assignedUserId) {
        update.assignedMembershipId = input.assignedMembershipId;
        update.assignedUserId = assignedUserId;
      }
      const changed = await transaction.chatbotEscalation.updateMany({
        data: update,
        where: {
          id: current.id,
          organizationId: access.organizationId,
          version: input.expectedVersion,
        },
      });
      if (changed.count !== 1)
        throw new DomainError({
          code: "CONFLICT",
          message: "Escalation changed. Refresh and retry.",
        });
      await transaction.chatbotEscalationHistory.create({
        data: {
          actorUserId: access.actorUserId,
          escalationId: current.id,
          fromStatus: current.status,
          organizationId: access.organizationId,
          reason: input.reason?.trim() || null,
          toStatus: input.status,
        },
      });
      await audit(
        transaction,
        access,
        `CHATBOT_ESCALATION_${input.status}`,
        "ChatbotEscalation",
        current.id,
        details,
      );
      return transaction.chatbotEscalation.findFirstOrThrow({
        where: { id: current.id, organizationId: access.organizationId },
      });
    });
  }

  async listInventory(access: TenantAccessSnapshot, branchIdFilter?: string) {
    const scope = scopeFor(access, "inventory.items.read");
    const supplier = access.grants.some(({ code }) => code === "inventory.supplier.read");
    const cost = access.grants.some(({ code }) => code === "inventory.cost.read");
    return this.run(access, async (transaction) => {
      if (branchIdFilter) requireBranch(access, "inventory.items.read", branchIdFilter);
      const activeBranch = branchIdFilter ?? access.activeBranchId;
      const branchFilter = activeBranch ? { branchId: activeBranch } : branchWhere(scope, access);

      const [
        items,
        proposals,
        orders,
        locations,
        batches,
        rawMovements,
        suppliers,
        upcomingAppointments,
        requirements,
      ] = await Promise.all([
        transaction.inventoryItem.findMany({
          orderBy: { name: "asc" },
          where: { organizationId: access.organizationId, ...branchFilter },
        }),
        transaction.inventoryItemProposal.findMany({
          orderBy: [{ urgent: "desc" }, { createdAt: "asc" }],
          where: {
            organizationId: access.organizationId,
            ...branchFilter,
            ...(scope === "SELF" ? { createdByUserId: access.actorUserId } : {}),
          },
        }),
        transaction.inventoryOrderRequest.findMany({
          include: { item: true },
          orderBy: [{ urgency: "desc" }, { createdAt: "asc" }],
          where: {
            organizationId: access.organizationId,
            ...branchFilter,
            ...(scope === "SELF" ? { requestedByUserId: access.actorUserId } : {}),
          },
        }),
        transaction.inventoryLocation.findMany({
          orderBy: [{ isDefault: "desc" }, { name: "asc" }],
          where: { organizationId: access.organizationId, ...branchFilter },
        }),
        transaction.inventoryBatch.findMany({
          orderBy: { expiryDate: "asc" },
          where: { organizationId: access.organizationId, isActive: true, ...branchFilter },
        }),
        transaction.inventoryStockMovement.findMany({
          include: {
            batch: { select: { batchNumber: true, expiryDate: true, id: true } },
            item: { select: { id: true, name: true, unitOfMeasure: true } },
            location: { select: { id: true, name: true } },
          },
          orderBy: { createdAt: "desc" },
          take: 100,
          where: { organizationId: access.organizationId, ...branchFilter },
        }),
        supplier
          ? transaction.supplier.findMany({
              orderBy: { name: "asc" },
              where: { organizationId: access.organizationId },
            })
          : Promise.resolve([]),
        transaction.appointment.findMany({
          select: { serviceId: true },
          where: {
            organizationId: access.organizationId,
            startsAt: { gte: new Date() },
            status: { in: ["CONFIRMED", "IN_PROGRESS", "CHECKED_IN"] },
            ...(activeBranch ? { branchId: activeBranch } : {}),
          },
        }),
        transaction.serviceInventoryRequirement.findMany({
          where: {
            organizationId: access.organizationId,
            reservationMode: { not: "NONE" },
          },
        }),
      ]);

      const serviceCounts: Record<string, number> = {};
      for (const appt of upcomingAppointments) {
        serviceCounts[appt.serviceId] = (serviceCounts[appt.serviceId] ?? 0) + 1;
      }
      const demandByItemId: Record<string, number> = {};
      for (const req of requirements) {
        const count = serviceCounts[req.serviceId] ?? 0;
        if (count > 0) {
          demandByItemId[req.itemId] =
            (demandByItemId[req.itemId] ?? 0) + count * Number(req.expectedQuantity);
        }
      }

      const now = new Date();

      const itemsDecorated = items.map((item) => {
        const onHand = Number(item.currentStock);
        const reserved = Number(item.reservedQuantity);
        const available = Math.max(0, onHand - reserved);
        const upcomingDemand = demandByItemId[item.id] ?? 0;
        const projected = calculateProjectedStock(available, upcomingDemand);
        const itemBatches = batches
          .filter((b) => b.itemId === item.id)
          .map((b) => ({
            ...b,
            purchaseCost: b.purchaseCost ? Number(b.purchaseCost) : null,
            quantity: Number(b.quantity),
          }));
        const recommendedBatch = recommendFefoBatch(itemBatches);
        const nearestExpiry = recommendedBatch?.expiryDate ?? null;
        const nearestExpiryAlert = nearestExpiry ? computeExpiryAlert(nearestExpiry, now) : null;
        const health = calculateStockHealth(onHand, Number(item.minimumStock));

        return {
          ...item,
          availableStock: available,
          currentStockNumber: onHand,
          health,
          isShortage: projected.isShortage,
          nearestExpiry,
          nearestExpiryAlert,
          projectedShortage: projected.shortageQuantity,
          projectedStock: projected.projectedStock,
          recommendedBatch: recommendedBatch
            ? {
                batchNumber: recommendedBatch.batchNumber,
                expiryDate: recommendedBatch.expiryDate,
                id: recommendedBatch.id,
                quantity: recommendedBatch.quantity,
              }
            : null,
          supplierName: supplier ? item.supplierName : null,
          supplierPhone: supplier ? item.supplierPhone : null,
          unitPrice: cost ? item.unitPrice : null,
          upcomingDemand,
        };
      });

      const lowStockCount = itemsDecorated.filter((i) => i.health === "LOW_STOCK").length;
      const outOfStockCount = itemsDecorated.filter((i) => i.health === "OUT_OF_STOCK").length;
      const expiringSoonCount = batches.filter((b) => {
        if (!b.expiryDate) return false;
        const alert = computeExpiryAlert(b.expiryDate, now);
        return (
          alert === "CRITICAL_7_DAYS" ||
          alert === "WARNING_30_DAYS" ||
          alert === "NOTICE_60_DAYS" ||
          alert === "INFO_90_DAYS"
        );
      }).length;
      const pendingRequestsCount =
        proposals.filter((p) => p.status === "PENDING_APPROVAL").length +
        orders.filter((o) => o.status === "PENDING_APPROVAL" || o.status === "REQUESTED").length;
      const ordersInTransitCount = orders.filter((o) => o.status === "ORDERED").length;
      const projectedShortagesCount = itemsDecorated.filter((i) => i.isShortage).length;

      const needsAttention = itemsDecorated.filter(
        (i) => i.health === "OUT_OF_STOCK" || i.health === "LOW_STOCK" || i.isShortage,
      );
      const upcomingDemandItems = itemsDecorated.filter((i) => i.upcomingDemand > 0);
      const incomingOrders = orders
        .filter((o) => o.status === "ORDERED" || o.status === "PARTIALLY_RECEIVED")
        .map((order) => {
          const isOverdue = order.expectedArrivalAt ? order.expectedArrivalAt < now : false;
          return {
            ...order,
            isOverdue,
            item: {
              ...order.item,
              supplierName: supplier ? order.item.supplierName : null,
              supplierPhone: supplier ? order.item.supplierPhone : null,
              unitPrice: cost ? order.item.unitPrice : null,
            },
            supplierName: supplier ? order.supplierName : null,
          };
        });

      return {
        batches: batches.map((b) => ({
          ...b,
          purchaseCost: cost ? b.purchaseCost : null,
        })),
        items: itemsDecorated,
        locations,
        movements: rawMovements,
        orders: orders.map((order) => ({
          ...order,
          item: {
            ...order.item,
            supplierName: supplier ? order.item.supplierName : null,
            supplierPhone: supplier ? order.item.supplierPhone : null,
            unitPrice: cost ? order.item.unitPrice : null,
          },
          supplierName: supplier ? order.supplierName : null,
        })),
        overview: {
          expiringSoonCount,
          incomingOrders,
          lowStockCount,
          needsAttention,
          ordersInTransitCount,
          outOfStockCount,
          pendingRequestsCount,
          projectedShortagesCount,
          upcomingDemandItems,
        },
        proposals,
        suppliers,
      };
    });
  }

  async listInventoryBranches(access: TenantAccessSnapshot) {
    const scope = scopeFor(access, "inventory.items.read");
    return this.run(access, (transaction) =>
      transaction.branch.findMany({
        orderBy: { nameEn: "asc" },
        select: { id: true, nameAr: true, nameEn: true },
        where: {
          ...(access.activeBranchId
            ? { id: access.activeBranchId }
            : scope === "ORGANIZATION"
              ? {}
              : { id: { in: [...access.assignedBranchIds] } }),
          isActive: true,
          organizationId: access.organizationId,
        },
      }),
    );
  }

  async listSuppliers(access: TenantAccessSnapshot) {
    scopeFor(access, "inventory.supplier.read");
    return this.run(access, (transaction) =>
      transaction.supplier.findMany({
        orderBy: { name: "asc" },
        where: { organizationId: access.organizationId },
      }),
    );
  }

  async createSupplier(
    access: TenantAccessSnapshot,
    input: Readonly<{
      email?: string | undefined;
      name: string;
      notes?: string | undefined;
      phone: string;
    }>,
    details?: WorkflowAuditDetails,
  ) {
    scopeFor(access, "inventory.items.manage");
    if (!input.name.trim() || !input.phone.trim()) {
      throw new DomainError({
        code: "VALIDATION_FAILED",
        message: "Supplier name and phone are required.",
      });
    }
    return this.run(access, async (transaction) => {
      const supplier = await transaction.supplier.create({
        data: {
          email: input.email?.trim() || null,
          isActive: true,
          name: input.name.trim(),
          notes: input.notes?.trim() || null,
          organizationId: access.organizationId,
          phone: input.phone.trim(),
        },
      });
      await audit(transaction, access, "SUPPLIER_CREATED", "Supplier", supplier.id, details);
      return supplier;
    });
  }

  async listLocations(access: TenantAccessSnapshot, branchId?: string) {
    const scope = scopeFor(access, "inventory.items.read");
    if (branchId) requireBranch(access, "inventory.items.read", branchId);
    return this.run(access, (transaction) =>
      transaction.inventoryLocation.findMany({
        orderBy: [{ isDefault: "desc" }, { name: "asc" }],
        where: {
          organizationId: access.organizationId,
          ...(branchId ? { branchId } : branchWhere(scope, access)),
        },
      }),
    );
  }

  async createLocation(
    access: TenantAccessSnapshot,
    input: Readonly<{
      branchId: string;
      code?: string | undefined;
      isDefault?: boolean | undefined;
      name: string;
    }>,
    details?: WorkflowAuditDetails,
  ) {
    requireBranch(access, "inventory.items.manage", input.branchId);
    if (!input.name.trim()) {
      throw new DomainError({
        code: "VALIDATION_FAILED",
        message: "Location name is required.",
      });
    }
    return this.run(access, async (transaction) => {
      if (input.isDefault) {
        await transaction.inventoryLocation.updateMany({
          data: { isDefault: false },
          where: {
            branchId: input.branchId,
            isDefault: true,
            organizationId: access.organizationId,
          },
        });
      }
      const location = await transaction.inventoryLocation.create({
        data: {
          branchId: input.branchId,
          description: input.code?.trim() || null,
          isActive: true,
          isDefault: input.isDefault ?? false,
          name: input.name.trim(),
          organizationId: access.organizationId,
        },
      });
      await audit(
        transaction,
        access,
        "LOCATION_CREATED",
        "InventoryLocation",
        location.id,
        details,
      );
      return location;
    });
  }

  async createItemDirect(
    access: TenantAccessSnapshot,
    input: Readonly<{
      batchTrackingEnabled?: boolean | undefined;
      branchId: string;
      category: InventoryCategory;
      currentStock?: number | undefined;
      defaultSupplierId?: string | undefined;
      expiryTrackingEnabled?: boolean | undefined;
      minimumStock: number;
      name: string;
      notes?: string | undefined;
      reorderQuantity?: number | undefined;
      sku?: string | undefined;
      supplierName?: string | undefined;
      supplierPhone?: string | undefined;
      unitOfMeasure: string;
      unitPrice?: number | undefined;
    }>,
    details?: WorkflowAuditDetails,
  ) {
    requireBranch(access, "inventory.items.manage", input.branchId);
    if (!input.name.trim() || !input.unitOfMeasure.trim()) {
      throw new DomainError({
        code: "VALIDATION_FAILED",
        message: "Valid item name and unit of measure are required.",
      });
    }
    return this.run(access, async (transaction) => {
      const defaultLoc = await ensureDefaultLocation(
        transaction,
        access.organizationId,
        input.branchId,
      );

      const item = await transaction.inventoryItem.create({
        data: {
          approvedByUserId: access.actorUserId,
          batchTrackingEnabled: input.batchTrackingEnabled ?? false,
          branchId: input.branchId,
          category: input.category,
          createdByUserId: access.actorUserId,
          currentStock: 0,
          defaultSupplierId: input.defaultSupplierId || null,
          expiryTrackingEnabled: input.expiryTrackingEnabled ?? false,
          isActive: true,
          minimumStock: input.minimumStock ?? 0,
          name: input.name.trim(),
          notes: input.notes?.trim() || null,
          organizationId: access.organizationId,
          reorderQuantity: input.reorderQuantity ?? 0,
          reservedQuantity: 0,
          sku: input.sku?.trim() || null,
          supplierName: input.supplierName?.trim() || null,
          supplierPhone: input.supplierPhone?.trim() || null,
          unitOfMeasure: input.unitOfMeasure.trim(),
          unitPrice: input.unitPrice ?? null,
        },
      });

      if (input.currentStock && input.currentStock > 0) {
        await recordStockMovement(transaction, access, {
          branchId: input.branchId,
          itemId: item.id,
          locationId: defaultLoc.id,
          movementType: "PURCHASE_RECEIPT",
          quantityChange: input.currentStock,
          reason: "Initial stock on item creation",
        });
      }

      await audit(transaction, access, "INVENTORY_ITEM_CREATED", "InventoryItem", item.id, details);
      return item;
    });
  }

  async updateItem(
    access: TenantAccessSnapshot,
    input: Readonly<{
      batchTrackingEnabled?: boolean | undefined;
      category?: InventoryCategory | undefined;
      defaultSupplierId?: string | undefined;
      expiryTrackingEnabled?: boolean | undefined;
      expectedVersion: number;
      id: string;
      isActive?: boolean | undefined;
      minimumStock?: number | undefined;
      name?: string | undefined;
      notes?: string | undefined;
      reorderQuantity?: number | undefined;
      sku?: string | undefined;
      supplierName?: string | undefined;
      supplierPhone?: string | undefined;
      unitOfMeasure?: string | undefined;
      unitPrice?: number | undefined;
    }>,
    details?: WorkflowAuditDetails,
  ) {
    scopeFor(access, "inventory.items.manage");
    return this.run(access, async (transaction) => {
      const current = await transaction.inventoryItem.findFirst({
        where: {
          id: input.id,
          organizationId: access.organizationId,
          version: input.expectedVersion,
        },
      });
      if (!current) {
        throw new DomainError({ code: "CONFLICT", message: "Item changed or not found." });
      }
      requireBranch(access, "inventory.items.manage", current.branchId);

      const updateData: Prisma.InventoryItemUncheckedUpdateInput = {
        version: { increment: 1 },
      };
      if (input.name !== undefined) updateData.name = input.name.trim();
      if (input.category !== undefined) updateData.category = input.category;
      if (input.sku !== undefined) updateData.sku = input.sku.trim() || null;
      if (input.unitOfMeasure !== undefined) updateData.unitOfMeasure = input.unitOfMeasure.trim();
      if (input.minimumStock !== undefined) updateData.minimumStock = input.minimumStock;
      if (input.reorderQuantity !== undefined) updateData.reorderQuantity = input.reorderQuantity;
      if (input.batchTrackingEnabled !== undefined)
        updateData.batchTrackingEnabled = input.batchTrackingEnabled;
      if (input.expiryTrackingEnabled !== undefined)
        updateData.expiryTrackingEnabled = input.expiryTrackingEnabled;
      if (input.defaultSupplierId !== undefined)
        updateData.defaultSupplierId = input.defaultSupplierId || null;
      if (input.supplierName !== undefined)
        updateData.supplierName = input.supplierName.trim() || null;
      if (input.supplierPhone !== undefined)
        updateData.supplierPhone = input.supplierPhone.trim() || null;
      if (input.unitPrice !== undefined) updateData.unitPrice = input.unitPrice;
      if (input.notes !== undefined) updateData.notes = input.notes.trim() || null;
      if (input.isActive !== undefined) updateData.isActive = input.isActive;

      const updated = await transaction.inventoryItem.update({
        data: updateData,
        where: { id: current.id },
      });

      await audit(
        transaction,
        access,
        input.isActive === false ? "INVENTORY_ITEM_DEACTIVATED" : "INVENTORY_ITEM_EDITED",
        "InventoryItem",
        current.id,
        details,
      );

      return updated;
    });
  }

  async listServiceRequirements(access: TenantAccessSnapshot, serviceId: string) {
    scopeFor(access, "inventory.items.read");
    return this.run(access, (transaction) =>
      transaction.serviceInventoryRequirement.findMany({
        include: { item: true },
        orderBy: { createdAt: "asc" },
        where: { organizationId: access.organizationId, serviceId },
      }),
    );
  }

  async listAllServiceRequirements(access: TenantAccessSnapshot) {
    const scope = scopeFor(access, "inventory.items.read");
    return this.run(access, (transaction) =>
      transaction.serviceInventoryRequirement.findMany({
        include: { item: true },
        orderBy: [{ serviceId: "asc" }, { createdAt: "asc" }],
        where: {
          item: branchWhere(scope, access),
          organizationId: access.organizationId,
        },
      }),
    );
  }

  async getAppointmentInventoryContext(
    access: TenantAccessSnapshot,
    appointmentId: string,
    serviceId: string,
  ) {
    const scope = access.grants
      .filter(({ code }) =>
        [
          "inventory.items.read",
          "inventory.consumption.read",
          "inventory.consumption.adjust",
        ].includes(code),
      )
      .toSorted((a, b) => rank[b.scope] - rank[a.scope])[0]?.scope;
    if (!scope) {
      throw new DomainError({ code: "FORBIDDEN", message: "Permission is required." });
    }
    return this.run(access, async (transaction) => {
      const appointment = await transaction.appointment.findFirst({
        where: { id: appointmentId, organizationId: access.organizationId },
      });
      if (!appointment || appointment.serviceId !== serviceId) {
        throw new DomainError({ code: "NOT_FOUND", message: "Appointment not found." });
      }
      if (access.activeBranchId && appointment.branchId !== access.activeBranchId) {
        throw new DomainError({ code: "NOT_FOUND", message: "Appointment not found." });
      }
      if (
        scope === "ASSIGNED_BRANCHES" &&
        !access.assignedBranchIds.includes(appointment.branchId)
      ) {
        throw new DomainError({ code: "NOT_FOUND", message: "Appointment not found." });
      }
      if (
        scope === "SELF" &&
        (!access.staffProfileId || appointment.providerId !== access.staffProfileId)
      ) {
        throw new DomainError({ code: "NOT_FOUND", message: "Appointment not found." });
      }

      const [requirements, consumptions, reservations] = await Promise.all([
        transaction.serviceInventoryRequirement.findMany({
          include: { item: true },
          orderBy: { createdAt: "asc" },
          where: { organizationId: access.organizationId, serviceId },
        }),
        transaction.appointmentInventoryConsumption.findMany({
          include: {
            batch: true,
            item: true,
            location: true,
          },
          orderBy: { createdAt: "asc" },
          where: { appointmentId, organizationId: access.organizationId },
        }),
        transaction.inventoryReservation.findMany({
          include: { item: true },
          where: {
            appointmentId,
            consumedAt: null,
            organizationId: access.organizationId,
            releasedAt: null,
          },
        }),
      ]);

      const itemIds = requirements.map((r) => r.itemId);
      const [batches, locations] = await Promise.all([
        itemIds.length > 0
          ? transaction.inventoryBatch.findMany({
              orderBy: { expiryDate: "asc" },
              where: {
                isActive: true,
                branchId: appointment.branchId,
                itemId: { in: itemIds },
                organizationId: access.organizationId,
                quantity: { gt: 0 },
              },
            })
          : Promise.resolve([]),
        transaction.inventoryLocation.findMany({
          orderBy: [{ isDefault: "desc" }, { name: "asc" }],
          where: {
            branchId: appointment.branchId,
            isActive: true,
            organizationId: access.organizationId,
          },
        }),
      ]);

      return {
        batches: batches.map((batch) => ({
          batchNumber: batch.batchNumber,
          expiryDate: batch.expiryDate,
          id: batch.id,
          itemId: batch.itemId,
          quantity: Number(batch.quantity),
        })),
        consumptions: consumptions.map((consumption) => ({
          actualQuantity: Number(consumption.actualQuantity),
          batch: consumption.batch ? { batchNumber: consumption.batch.batchNumber } : null,
          expectedQuantity: Number(consumption.expectedQuantity),
          id: consumption.id,
          isReconciliationRequired: consumption.isReconciliationRequired,
          item: { name: consumption.item.name },
          itemId: consumption.itemId,
          location: consumption.location ? { name: consumption.location.name } : null,
          reconciliationNote: consumption.reconciliationNote,
          unitOfMeasure: consumption.unitOfMeasure,
        })),
        locations: locations.map((location) => ({
          id: location.id,
          isDefault: location.isDefault,
          name: location.name,
        })),
        requirements: requirements.map((requirement) => ({
          expectedQuantity: Number(requirement.expectedQuantity),
          id: requirement.id,
          isRequired: requirement.isRequired,
          item: {
            id: requirement.item.id,
            name: requirement.item.name,
            unitOfMeasure: requirement.item.unitOfMeasure,
          },
          itemId: requirement.itemId,
          reservationMode: requirement.reservationMode,
          unitOfMeasure: requirement.unitOfMeasure,
        })),
        reservations: reservations.map((reservation) => ({
          id: reservation.id,
          itemId: reservation.itemId,
          quantity: Number(reservation.quantity),
        })),
      };
    });
  }

  async addServiceRequirement(
    access: TenantAccessSnapshot,
    input: Readonly<{
      expectedQuantity: number;
      isRequired: boolean;
      itemId: string;
      reservationMode: InventoryReservationMode;
      serviceId: string;
      unitOfMeasure: string;
    }>,
    details?: WorkflowAuditDetails,
  ) {
    scopeFor(access, "inventory.items.manage");
    if (input.expectedQuantity <= 0) {
      throw new DomainError({
        code: "VALIDATION_FAILED",
        message: "Expected quantity must be greater than zero.",
      });
    }
    return this.run(access, async (transaction) => {
      const [item, service] = await Promise.all([
        transaction.inventoryItem.findFirst({
          where: { id: input.itemId, organizationId: access.organizationId },
        }),
        transaction.service.findFirst({
          where: { id: input.serviceId, organizationId: access.organizationId },
        }),
      ]);
      if (!item || !service) {
        throw new DomainError({ code: "NOT_FOUND", message: "Item or service not found." });
      }
      requireBranch(access, "inventory.items.manage", item.branchId);
      const existing = await transaction.serviceInventoryRequirement.findUnique({
        where: {
          organizationId_serviceId_itemId: {
            itemId: input.itemId,
            organizationId: access.organizationId,
            serviceId: input.serviceId,
          },
        },
      });
      let result;
      if (existing) {
        result = await transaction.serviceInventoryRequirement.update({
          data: {
            expectedQuantity: input.expectedQuantity,
            isRequired: input.isRequired,
            reservationMode: input.reservationMode,
            unitOfMeasure: input.unitOfMeasure.trim(),
          },
          where: { id: existing.id },
        });
      } else {
        result = await transaction.serviceInventoryRequirement.create({
          data: {
            expectedQuantity: input.expectedQuantity,
            isRequired: input.isRequired,
            itemId: input.itemId,
            organizationId: access.organizationId,
            reservationMode: input.reservationMode,
            serviceId: input.serviceId,
            unitOfMeasure: input.unitOfMeasure.trim(),
          },
        });
      }
      await audit(
        transaction,
        access,
        "SERVICE_INVENTORY_REQUIREMENT_SAVED",
        "ServiceInventoryRequirement",
        result.id,
        details,
      );
      return result;
    });
  }

  async removeServiceRequirement(
    access: TenantAccessSnapshot,
    input: Readonly<{ id: string }>,
    details?: WorkflowAuditDetails,
  ) {
    scopeFor(access, "inventory.items.manage");
    return this.run(access, async (transaction) => {
      const req = await transaction.serviceInventoryRequirement.findFirst({
        include: { item: { select: { branchId: true } } },
        where: { id: input.id, organizationId: access.organizationId },
      });
      if (!req) return;
      requireBranch(access, "inventory.items.manage", req.item.branchId);
      await transaction.serviceInventoryRequirement.delete({ where: { id: req.id } });
      await audit(
        transaction,
        access,
        "SERVICE_INVENTORY_REQUIREMENT_REMOVED",
        "ServiceInventoryRequirement",
        req.id,
        details,
      );
    });
  }

  async transferStock(
    access: TenantAccessSnapshot,
    input: Readonly<{
      batchId?: string | undefined;
      branchId: string;
      fromLocationId: string;
      itemId: string;
      quantity: number;
      reason: string;
      toLocationId: string;
    }>,
    details?: WorkflowAuditDetails,
  ) {
    requireBranch(access, "inventory.stock.transfer", input.branchId);
    if (input.quantity <= 0 || !input.reason.trim()) {
      throw new DomainError({
        code: "VALIDATION_FAILED",
        message: "Valid transfer quantity and reason are required.",
      });
    }
    if (input.fromLocationId === input.toLocationId) {
      throw new DomainError({
        code: "VALIDATION_FAILED",
        message: "Source and destination locations must be different.",
      });
    }
    return this.run(access, async (transaction) => {
      const sourceBatch = input.batchId
        ? await transaction.inventoryBatch.findFirst({
            where: {
              branchId: input.branchId,
              id: input.batchId,
              itemId: input.itemId,
              locationId: input.fromLocationId,
              organizationId: access.organizationId,
            },
          })
        : null;
      if (input.batchId && (!sourceBatch || Number(sourceBatch.quantity) < input.quantity)) {
        throw new DomainError({
          code: "CONFLICT",
          message: "Insufficient batch stock in source location.",
        });
      }

      const sourceStock = await transaction.itemLocationStock.findUnique({
        where: {
          organizationId_itemId_locationId: {
            itemId: input.itemId,
            locationId: input.fromLocationId,
            organizationId: access.organizationId,
          },
        },
      });
      if (!sourceStock || Number(sourceStock.quantity) < input.quantity) {
        throw new DomainError({
          code: "CONFLICT",
          message: "Insufficient stock in source location.",
        });
      }

      const destinationBatch = sourceBatch
        ? await transaction.inventoryBatch.upsert({
            create: {
              batchNumber: sourceBatch.batchNumber,
              branchId: input.branchId,
              expiryDate: sourceBatch.expiryDate,
              isActive: sourceBatch.isActive,
              itemId: input.itemId,
              locationId: input.toLocationId,
              organizationId: access.organizationId,
              purchaseCost: sourceBatch.purchaseCost,
              quantity: 0,
              receivedDate: sourceBatch.receivedDate,
            },
            update: {},
            where: {
              organizationId_itemId_locationId_batchNumber: {
                batchNumber: sourceBatch.batchNumber,
                itemId: input.itemId,
                locationId: input.toLocationId,
                organizationId: access.organizationId,
              },
            },
          })
        : null;

      await recordStockMovement(transaction, access, {
        batchId: input.batchId,
        branchId: input.branchId,
        itemId: input.itemId,
        locationId: input.fromLocationId,
        movementType: "TRANSFER_OUT",
        quantityChange: -input.quantity,
        reason: input.reason.trim(),
      });

      await recordStockMovement(transaction, access, {
        batchId: destinationBatch?.id,
        branchId: input.branchId,
        itemId: input.itemId,
        locationId: input.toLocationId,
        movementType: "TRANSFER_IN",
        quantityChange: input.quantity,
        reason: input.reason.trim(),
      });

      await audit(transaction, access, "STOCK_TRANSFERRED", "InventoryItem", input.itemId, details);
    });
  }

  async adjustStock(
    access: TenantAccessSnapshot,
    input: Readonly<{
      batchId?: string | undefined;
      branchId: string;
      itemId: string;
      locationId: string;
      movementType:
        "EXPIRED" | "DAMAGED" | "LOST" | "SPILLED" | "RETURN_TO_SUPPLIER" | "MANUAL_CORRECTION";
      quantityChange: number;
      reason: string;
    }>,
    details?: WorkflowAuditDetails,
  ) {
    requireBranch(access, "inventory.stock.adjust", input.branchId);
    if (!input.reason.trim() || input.quantityChange === 0) {
      throw new DomainError({
        code: "VALIDATION_FAILED",
        message: "A non-zero adjustment quantity and reason are required.",
      });
    }

    const negativeTypes = ["EXPIRED", "DAMAGED", "LOST", "SPILLED", "RETURN_TO_SUPPLIER"];
    const delta =
      negativeTypes.includes(input.movementType) && input.quantityChange > 0
        ? -input.quantityChange
        : input.quantityChange;

    return this.run(access, async (transaction) => {
      const movement = await recordStockMovement(transaction, access, {
        batchId: input.batchId,
        branchId: input.branchId,
        itemId: input.itemId,
        locationId: input.locationId,
        movementType: input.movementType,
        quantityChange: delta,
        reason: input.reason.trim(),
      });
      await notifyCurrentStockRisk(transaction, access, input.itemId);

      await audit(transaction, access, "STOCK_ADJUSTED", "InventoryItem", input.itemId, details);

      return movement;
    });
  }

  async createItemProposal(
    access: TenantAccessSnapshot,
    input: Readonly<{
      branchId: string;
      category: InventoryCategory;
      note?: string | undefined;
      proposedName: string;
      reasonNeeded?: string | undefined;
      suggestedQuantity: number;
      unitOfMeasure: string;
      urgent: boolean;
    }>,
    details?: WorkflowAuditDetails,
  ) {
    requireBranch(access, "inventory.itemProposal.create", input.branchId);
    if (!input.proposedName.trim() || !input.unitOfMeasure.trim() || input.suggestedQuantity <= 0)
      throw new DomainError({
        code: "VALIDATION_FAILED",
        message: "Valid proposal details are required.",
      });
    return this.run(access, async (transaction) => {
      const proposal = await transaction.inventoryItemProposal.create({
        data: {
          branchId: input.branchId,
          category: input.category,
          createdByUserId: access.actorUserId,
          note: input.note?.trim() || null,
          organizationId: access.organizationId,
          proposedName: input.proposedName.trim(),
          reasonNeeded: input.reasonNeeded?.trim() ?? "",
          suggestedQuantity: input.suggestedQuantity,
          unitOfMeasure: input.unitOfMeasure.trim(),
          urgent: input.urgent,
        },
      });
      const recipients = await permissionRecipients(
        transaction,
        access.organizationId,
        "inventory.itemProposal.approve",
      );
      await Promise.all(
        recipients.map((recipientUserId) =>
          createNotification(transaction, access.organizationId, {
            branchId: input.branchId,
            entityId: proposal.id,
            entityType: "InventoryItemProposal",
            messageAr: "مقترح صنف مخزون جديد بانتظار المراجعة.",
            messageEn: "A new inventory item proposal awaits review.",
            priority: input.urgent ? "HIGH" : "NORMAL",
            recipientUserId,
            route: `/business/inventory?tab=requests&proposal=${proposal.id}`,
            titleAr: "موافقة صنف مخزون جديد",
            titleEn: "New Inventory Item Approval",
            type: "INVENTORY_ITEM_APPROVAL",
          }),
        ),
      );
      await audit(
        transaction,
        access,
        "INVENTORY_ITEM_PROPOSAL_CREATED",
        "InventoryItemProposal",
        proposal.id,
        details,
      );
      return proposal;
    });
  }

  async approveItemProposal(
    access: TenantAccessSnapshot,
    input: Readonly<{
      batchTrackingEnabled?: boolean | undefined;
      defaultSupplierId?: string | undefined;
      expectedVersion: number;
      expiryTrackingEnabled?: boolean | undefined;
      id: string;
      minimumStock: number;
      name: string;
      notes?: string | undefined;
      reorderQuantity?: number | undefined;
      sku?: string | undefined;
      supplierName?: string | undefined;
      supplierPhone?: string | undefined;
      unitPrice?: number | undefined;
    }>,
    details?: WorkflowAuditDetails,
  ) {
    scopeFor(access, "inventory.itemProposal.approve");
    const maySupplier = access.grants.some(({ code }) => code === "inventory.supplier.read");
    const mayCost = access.grants.some(({ code }) => code === "inventory.cost.read");
    if ((input.supplierName || input.supplierPhone) && !maySupplier)
      throw new DomainError({ code: "FORBIDDEN", message: "Supplier permission is required." });
    if (input.unitPrice !== undefined && !mayCost)
      throw new DomainError({ code: "FORBIDDEN", message: "Cost permission is required." });
    return this.run(access, async (transaction) => {
      const proposal = await transaction.inventoryItemProposal.findFirst({
        where: {
          id: input.id,
          organizationId: access.organizationId,
          status: "PENDING_APPROVAL",
          version: input.expectedVersion,
        },
      });
      if (!proposal)
        throw new DomainError({
          code: "CONFLICT",
          message: "Proposal changed or is no longer pending.",
        });
      requireBranch(access, "inventory.itemProposal.approve", proposal.branchId);

      await ensureDefaultLocation(transaction, access.organizationId, proposal.branchId);

      const item = await transaction.inventoryItem.create({
        data: {
          approvedByUserId: access.actorUserId,
          batchTrackingEnabled: input.batchTrackingEnabled ?? false,
          branchId: proposal.branchId,
          category: proposal.category,
          createdByUserId: proposal.createdByUserId,
          defaultSupplierId: input.defaultSupplierId || null,
          expiryTrackingEnabled: input.expiryTrackingEnabled ?? false,
          minimumStock: input.minimumStock,
          name: input.name.trim(),
          notes: input.notes?.trim() || null,
          organizationId: access.organizationId,
          reorderQuantity: input.reorderQuantity ?? 0,
          sku: input.sku?.trim() || null,
          supplierName: input.supplierName?.trim() || null,
          supplierPhone: input.supplierPhone?.trim() || null,
          unitOfMeasure: proposal.unitOfMeasure,
          unitPrice: input.unitPrice ?? null,
        },
      });
      await transaction.inventoryItemProposal.update({
        data: {
          createdItemId: item.id,
          reviewedByUserId: access.actorUserId,
          status: "APPROVED",
          version: { increment: 1 },
        },
        where: { id: proposal.id },
      });
      await createNotification(transaction, access.organizationId, {
        branchId: proposal.branchId,
        entityId: proposal.id,
        entityType: "InventoryItemProposal",
        messageAr: "تمت الموافقة على مقترح صنف المخزون.",
        messageEn: "Your inventory item proposal was approved.",
        recipientUserId: proposal.createdByUserId,
        route: `/business/inventory?tab=requests&proposal=${proposal.id}`,
        titleAr: "تمت الموافقة على مقترح الصنف",
        titleEn: "Item Proposal Approved",
        type: "INVENTORY_ITEM_APPROVED",
      });
      await audit(
        transaction,
        access,
        "INVENTORY_ITEM_PROPOSAL_APPROVED",
        "InventoryItemProposal",
        proposal.id,
        details,
      );
      return item;
    });
  }

  async reviewItemProposal(
    access: TenantAccessSnapshot,
    input: Readonly<{
      expectedVersion: number;
      id: string;
      reason?: string | undefined;
      status: "REJECTED" | "MORE_INFO_REQUIRED" | "CANCELLED";
    }>,
    details?: WorkflowAuditDetails,
  ) {
    scopeFor(access, "inventory.itemProposal.approve");
    return this.run(access, async (transaction) => {
      const proposal = await transaction.inventoryItemProposal.findFirst({
        where: {
          id: input.id,
          organizationId: access.organizationId,
          status: "PENDING_APPROVAL",
          version: input.expectedVersion,
        },
      });
      if (!proposal)
        throw new DomainError({
          code: "CONFLICT",
          message: "Proposal changed or is no longer pending.",
        });
      requireBranch(access, "inventory.itemProposal.approve", proposal.branchId);
      const updated = await transaction.inventoryItemProposal.update({
        data: {
          reviewNote: input.reason?.trim() || null,
          reviewedByUserId: access.actorUserId,
          status: input.status,
          version: { increment: 1 },
        },
        where: { id: proposal.id },
      });
      await createNotification(transaction, access.organizationId, {
        branchId: proposal.branchId,
        entityId: proposal.id,
        entityType: "InventoryItemProposal",
        messageAr:
          input.status === "MORE_INFO_REQUIRED"
            ? "يحتاج مقترح صنف المخزون إلى معلومات إضافية."
            : "تم رفض مقترح صنف المخزون.",
        messageEn:
          input.status === "MORE_INFO_REQUIRED"
            ? "Your inventory item proposal needs more information."
            : "Your inventory item proposal was rejected.",
        recipientUserId: proposal.createdByUserId,
        route: `/business/inventory?tab=requests&proposal=${proposal.id}`,
        titleAr:
          input.status === "MORE_INFO_REQUIRED" ? "مطلوب معلومات إضافية" : "تم رفض مقترح الصنف",
        titleEn:
          input.status === "MORE_INFO_REQUIRED"
            ? "More Information Required"
            : "Item Proposal Rejected",
        type:
          input.status === "MORE_INFO_REQUIRED"
            ? "INVENTORY_ITEM_MORE_INFO"
            : "INVENTORY_ITEM_REJECTED",
      });
      await audit(
        transaction,
        access,
        `INVENTORY_ITEM_PROPOSAL_${input.status}`,
        "InventoryItemProposal",
        proposal.id,
        details,
      );
      return updated;
    });
  }

  async createOrderRequest(
    access: TenantAccessSnapshot,
    input: Readonly<{
      branchId: string;
      itemId: string;
      note?: string | undefined;
      quantity: number;
      reason: string;
      urgency: "NORMAL" | "URGENT";
    }>,
    details?: WorkflowAuditDetails,
  ) {
    requireBranch(access, "inventory.orderRequest.create", input.branchId);
    if (input.quantity <= 0 || !input.reason.trim())
      throw new DomainError({
        code: "VALIDATION_FAILED",
        message: "Valid order details are required.",
      });
    return this.run(access, async (transaction) => {
      const item = await transaction.inventoryItem.findFirst({
        where: {
          branchId: input.branchId,
          id: input.itemId,
          isActive: true,
          organizationId: access.organizationId,
        },
      });
      if (!item) throw new DomainError({ code: "NOT_FOUND", message: "Inventory item not found." });
      const order = await transaction.inventoryOrderRequest.create({
        data: {
          branchId: input.branchId,
          itemId: item.id,
          note: input.note?.trim() || null,
          organizationId: access.organizationId,
          reason: input.reason.trim(),
          requestedByUserId: access.actorUserId,
          requestedQuantity: input.quantity,
          urgency: input.urgency,
        },
      });
      const recipients = await permissionRecipients(
        transaction,
        access.organizationId,
        "inventory.orderRequest.approve",
      );
      await Promise.all(
        recipients.map((recipientUserId) =>
          createNotification(transaction, access.organizationId, {
            branchId: input.branchId,
            entityId: order.id,
            entityType: "InventoryOrderRequest",
            messageAr: "طلب توريد مخزون بانتظار المراجعة.",
            messageEn: "An inventory order request awaits review.",
            priority: input.urgency === "URGENT" ? "URGENT" : "NORMAL",
            recipientUserId,
            route: `/business/inventory?tab=orders&order=${order.id}`,
            titleAr: input.urgency === "URGENT" ? "طلب توريد مخزون عاجل" : "طلب توريد مخزون جديد",
            titleEn:
              input.urgency === "URGENT"
                ? "Urgent Inventory Order Request"
                : "New Inventory Order Request",
            type: "INVENTORY_ORDER_REQUEST",
          }),
        ),
      );
      await audit(
        transaction,
        access,
        "INVENTORY_ORDER_REQUESTED",
        "InventoryOrderRequest",
        order.id,
        details,
      );
      return order;
    });
  }

  async approveOrder(
    access: TenantAccessSnapshot,
    input: Readonly<{ expectedVersion: number; id: string; note?: string | undefined }>,
    details?: WorkflowAuditDetails,
  ) {
    scopeFor(access, "inventory.orderRequest.approve");
    return this.run(access, async (transaction) => {
      const order = await transaction.inventoryOrderRequest.findFirst({
        where: {
          id: input.id,
          organizationId: access.organizationId,
          status: "PENDING_APPROVAL",
          version: input.expectedVersion,
        },
      });
      if (!order)
        throw new DomainError({
          code: "CONFLICT",
          message: "Order changed or is no longer pending.",
        });
      requireBranch(access, "inventory.orderRequest.approve", order.branchId);
      const updated = await transaction.inventoryOrderRequest.update({
        data: {
          reviewNote: input.note?.trim() || null,
          reviewedByUserId: access.actorUserId,
          status: "APPROVED",
          version: { increment: 1 },
        },
        where: { id: order.id },
      });
      await createNotification(transaction, access.organizationId, {
        branchId: order.branchId,
        entityId: order.id,
        entityType: "InventoryOrderRequest",
        messageAr: "تمت الموافقة على طلب التوريد.",
        messageEn: "Your inventory order request was approved.",
        recipientUserId: order.requestedByUserId,
        route: `/business/inventory?tab=orders&order=${order.id}`,
        titleAr: "تمت الموافقة على طلب التوريد",
        titleEn: "Order Approved",
        type: "INVENTORY_ORDER_APPROVED",
      });
      await audit(
        transaction,
        access,
        "INVENTORY_ORDER_APPROVED",
        "InventoryOrderRequest",
        order.id,
        details,
      );
      return updated;
    });
  }

  async rejectOrder(
    access: TenantAccessSnapshot,
    input: Readonly<{ expectedVersion: number; id: string; reason: string }>,
    details?: WorkflowAuditDetails,
  ) {
    scopeFor(access, "inventory.orderRequest.approve");
    if (!input.reason.trim())
      throw new DomainError({
        code: "VALIDATION_FAILED",
        message: "A rejection reason is required.",
      });
    return this.run(access, async (transaction) => {
      const order = await transaction.inventoryOrderRequest.findFirst({
        where: {
          id: input.id,
          organizationId: access.organizationId,
          status: "PENDING_APPROVAL",
          version: input.expectedVersion,
        },
      });
      if (!order)
        throw new DomainError({
          code: "CONFLICT",
          message: "Order changed or is no longer pending.",
        });
      requireBranch(access, "inventory.orderRequest.approve", order.branchId);
      const updated = await transaction.inventoryOrderRequest.update({
        data: {
          reviewNote: input.reason.trim(),
          reviewedByUserId: access.actorUserId,
          status: "REJECTED",
          version: { increment: 1 },
        },
        where: { id: order.id },
      });
      await createNotification(transaction, access.organizationId, {
        branchId: order.branchId,
        entityId: order.id,
        entityType: "InventoryOrderRequest",
        messageAr: "تم رفض طلب توريد المخزون.",
        messageEn: "Your inventory order request was rejected.",
        recipientUserId: order.requestedByUserId,
        route: `/business/inventory?tab=orders&order=${order.id}`,
        titleAr: "تم رفض طلب التوريد",
        titleEn: "Order Rejected",
        type: "INVENTORY_ORDER_REJECTED",
      });
      await audit(
        transaction,
        access,
        "INVENTORY_ORDER_REJECTED",
        "InventoryOrderRequest",
        order.id,
        details,
      );
      return updated;
    });
  }

  async markOrderPlaced(
    access: TenantAccessSnapshot,
    input: Readonly<{
      expectedDeliveryUnit: "HOURS" | "DAYS";
      expectedDeliveryValue: number;
      expectedVersion: number;
      id: string;
      orderedAt: Date;
      orderedQuantity: number;
      supplierName: string;
      supplierReference?: string | undefined;
    }>,
    details?: WorkflowAuditDetails,
  ) {
    scopeFor(access, "inventory.order.markOrdered");
    if (
      !input.supplierName.trim() ||
      input.orderedQuantity <= 0 ||
      input.expectedDeliveryValue <= 0
    )
      throw new DomainError({
        code: "VALIDATION_FAILED",
        message: "Valid order placement details are required.",
      });
    return this.run(access, async (transaction) => {
      const current = await transaction.inventoryOrderRequest.findFirst({
        where: {
          id: input.id,
          organizationId: access.organizationId,
          status: "APPROVED",
          version: input.expectedVersion,
        },
      });
      if (!current)
        throw new DomainError({ code: "CONFLICT", message: "Order changed or is not approved." });
      requireBranch(access, "inventory.order.markOrdered", current.branchId);
      const milliseconds =
        input.expectedDeliveryValue *
        (input.expectedDeliveryUnit === "HOURS" ? 3_600_000 : 86_400_000);
      const updated = await transaction.inventoryOrderRequest.update({
        data: {
          expectedArrivalAt: new Date(input.orderedAt.getTime() + milliseconds),
          expectedDeliveryUnit: input.expectedDeliveryUnit,
          expectedDeliveryValue: input.expectedDeliveryValue,
          orderedAt: input.orderedAt,
          orderedByUserId: access.actorUserId,
          orderedQuantity: input.orderedQuantity,
          status: "ORDERED",
          supplierName: input.supplierName.trim(),
          supplierReference: input.supplierReference?.trim() || null,
          version: { increment: 1 },
        },
        where: { id: current.id },
      });
      await createNotification(transaction, access.organizationId, {
        branchId: current.branchId,
        entityId: current.id,
        entityType: "InventoryOrderRequest",
        messageAr: "تم تقديم طلب المخزون وتحديد موعد الوصول المتوقع.",
        messageEn: "The inventory order was placed with an expected arrival time.",
        recipientUserId: current.requestedByUserId,
        route: `/business/inventory?tab=receiving&order=${current.id}`,
        titleAr: "تم تقديم طلب المخزون",
        titleEn: "Inventory Order Placed",
        type: "INVENTORY_ORDER_PLACED",
      });
      await audit(
        transaction,
        access,
        "INVENTORY_ORDER_PLACED",
        "InventoryOrderRequest",
        current.id,
        details,
      );
      return updated;
    });
  }

  async receiveOrder(
    access: TenantAccessSnapshot,
    input: Readonly<{
      batchNumber?: string | undefined;
      expiryDate?: Date | undefined;
      id: string;
      locationId?: string | undefined;
      note?: string | undefined;
      purchaseCost?: number | undefined;
      quantity: number;
      receivedAt: Date;
      requestKey: string;
    }>,
    details?: WorkflowAuditDetails,
  ) {
    scopeFor(access, "inventory.order.receive");
    if (input.quantity <= 0)
      throw new DomainError({
        code: "VALIDATION_FAILED",
        message: "Received quantity must be positive.",
      });
    const requestFingerprint = fingerprint({
      batchNumber: input.batchNumber,
      id: input.id,
      locationId: input.locationId,
      quantity: input.quantity,
      receivedAt: input.receivedAt.toISOString(),
    });
    return this.run(access, async (transaction) => {
      await transaction.$queryRaw(
        Prisma.sql`SELECT pg_advisory_xact_lock(hashtextextended(${`${access.organizationId}:${input.requestKey}`}, 0))::text AS "lock"`,
      );
      const prior = await transaction.stockTransaction.findFirst({
        where: { organizationId: access.organizationId, requestKey: input.requestKey },
      });
      if (prior) {
        if (prior.requestFingerprint !== requestFingerprint)
          throw new DomainError({
            code: "IDEMPOTENCY_CONFLICT",
            message: "Request key was already used for different receipt data.",
          });
        return prior;
      }
      await transaction.$queryRaw(
        Prisma.sql`SELECT "id" FROM "inventory_order_requests" WHERE "organization_id"=${access.organizationId}::uuid AND "id"=${input.id}::uuid FOR UPDATE`,
      );
      const order = await transaction.inventoryOrderRequest.findFirst({
        include: { item: true },
        where: {
          id: input.id,
          organizationId: access.organizationId,
          status: { in: ["ORDERED", "PARTIALLY_RECEIVED"] },
        },
      });
      if (!order)
        throw new DomainError({ code: "CONFLICT", message: "Order cannot receive stock." });
      requireBranch(access, "inventory.order.receive", order.branchId);
      const ordered = Number(order.orderedQuantity ?? order.requestedQuantity);
      const received = Number(order.receivedQuantity);
      if (received + input.quantity > ordered)
        throw new DomainError({
          code: "VALIDATION_FAILED",
          message: "Receipt exceeds ordered quantity.",
        });

      const complete = received + input.quantity === ordered;

      const targetLocationId =
        input.locationId ??
        (await ensureDefaultLocation(transaction, access.organizationId, order.branchId)).id;

      let batchId: string | null = null;
      if (input.batchNumber?.trim()) {
        const batchNumberTrimmed = input.batchNumber.trim();
        const existingBatch = await transaction.inventoryBatch.findFirst({
          where: {
            batchNumber: batchNumberTrimmed,
            branchId: order.branchId,
            itemId: order.itemId,
            locationId: targetLocationId,
            organizationId: access.organizationId,
          },
        });
        if (existingBatch) {
          batchId = existingBatch.id;
        } else {
          const newBatch = await transaction.inventoryBatch.create({
            data: {
              batchNumber: batchNumberTrimmed,
              branchId: order.branchId,
              expiryDate: input.expiryDate ?? null,
              isActive: true,
              itemId: order.itemId,
              locationId: targetLocationId,
              organizationId: access.organizationId,
              purchaseCost: input.purchaseCost ?? null,
              quantity: 0,
              receivedDate: input.receivedAt,
            },
          });
          batchId = newBatch.id;
        }
      }

      const movement = await recordStockMovement(transaction, access, {
        batchId,
        branchId: order.branchId,
        idempotencyKey: input.requestKey,
        itemId: order.itemId,
        locationId: targetLocationId,
        movementType: "PURCHASE_RECEIPT",
        quantityChange: input.quantity,
        reason: input.note?.trim() || `Receipt for order #${order.id}`,
        relatedOrderId: order.id,
      });

      if (batchId && input.expiryDate) {
        const expiryAlert = computeExpiryAlert(input.expiryDate, new Date());
        if (expiryAlert) {
          const expired = expiryAlert === "EXPIRED";
          await createInventoryNotificationOnce(transaction, access, {
            branchId: order.branchId,
            entityId: batchId,
            entityType: "InventoryBatch",
            messageAr: expired
              ? `التشغيلة ${input.batchNumber ?? ""} للصنف ${order.item.name} منتهية الصلاحية.`
              : `التشغيلة ${input.batchNumber ?? ""} للصنف ${order.item.name} تقترب من تاريخ الانتهاء.`,
            messageEn: expired
              ? `Batch ${input.batchNumber ?? ""} for ${order.item.name} is expired.`
              : `Batch ${input.batchNumber ?? ""} for ${order.item.name} is approaching expiry.`,
            priority: expired ? "URGENT" : "HIGH",
            route: `/business/inventory?tab=items&item=${order.itemId}&batch=${batchId}`,
            titleAr: expired ? "تشغيلة منتهية الصلاحية" : "تشغيلة تقترب من الانتهاء",
            titleEn: expired ? "Expired Inventory Batch" : "Inventory Batch Expiring Soon",
            type: expired ? "INVENTORY_BATCH_EXPIRED" : "INVENTORY_BATCH_EXPIRING",
          });
        }
      }

      await transaction.inventoryOrderRequest.update({
        data: {
          receivedQuantity: received + input.quantity,
          status: complete ? "RECEIVED" : "PARTIALLY_RECEIVED",
          version: { increment: 1 },
        },
        where: { id: order.id },
      });

      const receipt = await transaction.stockTransaction.create({
        data: {
          branchId: order.branchId,
          itemId: order.itemId,
          note: input.note?.trim() || null,
          orderRequestId: order.id,
          organizationId: access.organizationId,
          quantity: input.quantity,
          receivedAt: input.receivedAt,
          recordedByUserId: access.actorUserId,
          requestFingerprint,
          requestKey: input.requestKey,
          resultingStock: movement.balanceAfter,
          type: "RECEIPT",
        },
      });

      await createNotification(transaction, access.organizationId, {
        branchId: order.branchId,
        entityId: order.id,
        entityType: "InventoryOrderRequest",
        messageAr: complete ? "تم استلام طلب المخزون بالكامل." : "تم استلام جزء من طلب المخزون.",
        messageEn: complete
          ? "The inventory order was received."
          : "The inventory order was partially received.",
        recipientUserId: order.requestedByUserId,
        route: `/business/inventory?tab=receiving&order=${order.id}`,
        titleAr: complete ? "تم استلام طلب المخزون" : "تم استلام جزء من الطلب",
        titleEn: complete ? "Inventory Order Received" : "Order Partially Received",
        type: complete ? "INVENTORY_ORDER_RECEIVED" : "INVENTORY_ORDER_PARTIAL",
      });

      await audit(
        transaction,
        access,
        complete ? "INVENTORY_ORDER_RECEIVED" : "INVENTORY_ORDER_PARTIALLY_RECEIVED",
        "InventoryOrderRequest",
        order.id,
        details,
      );

      return receipt;
    });
  }
}
