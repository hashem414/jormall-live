import { createHash, randomUUID } from "node:crypto";

import {
  assertAppointmentStartsInFuture,
  assertAppointmentTransition,
  canRescheduleAppointment,
  type AppointmentStatusValue,
} from "@jormall/domain/appointment-state";
import { completionNote } from "@jormall/domain/appointment-completion";
import { DomainError } from "@jormall/domain/errors";
import { normalizeJordanianPhone } from "@jormall/domain/jordan-phone";
import {
  normalizeHealthInformation,
  requiresHealthConsent,
  type HealthInformationState,
} from "@jormall/domain/patient-health";
import {
  localDateForInstant,
  localDateTimePartsForInstant,
  utcRangeForLocalDate,
} from "@jormall/domain/timezone";
import type {
  PermissionCode,
  PermissionScope,
  TenantAccessSnapshot,
} from "@jormall/domain/identity";

import {
  AppointmentHistoryType,
  AppointmentSource,
  AppointmentStatus,
  AppointmentTransitionSource,
  ConsentStatus,
  CustomerContactKind,
  MembershipStatus,
  OrganizationStatus,
  PlatformRole,
  Prisma,
  type PrismaClient,
  type SupportedLocale,
} from "./generated/prisma/client";
import type { ConsentChannel, ConsentSource } from "./generated/prisma/client";
import {
  assertBookableSchedule,
  createAppointmentRows,
  prepareBooking,
  reserveRequiredResources,
  rescheduleAppointmentRows,
  schedulingConflict,
} from "./scheduling-transaction";
import {
  recordAppointmentConsumption,
  releaseStockReservations,
  reserveStockForConfirmedAppointment,
  type AppointmentConsumptionItemInput,
} from "./operational-workflows-repository";
import { runInTenant, type TenantTransaction } from "./tenant-context";

export type RequestAuditDetails = Readonly<{
  ipAddress?: string | undefined;
  userAgent?: string | undefined;
}>;

export type CustomerInput = Readonly<{
  displayName: string;
  emailOriginal?: string | undefined;
  allergyDetails?: string | undefined;
  allergyState?: HealthInformationState | undefined;
  healthConsentConfirmed?: boolean | undefined;
  medicalConditionDetails?: string | undefined;
  medicalConditionState?: HealthInformationState | undefined;
  phoneOriginal?: string | undefined;
  preferredBranchId?: string | undefined;
  preferredLocale?: SupportedLocale | undefined;
  tags?: readonly string[] | undefined;
  rejectDuplicatePhone?: boolean | undefined;
}>;

export type CustomerUpdateInput = CustomerInput &
  Readonly<{
    customerId: string;
    expectedVersion: number;
  }>;

export type ConsentInput = Readonly<{
  channel: ConsentChannel;
  customerId: string;
  evidence?: string | undefined;
  purpose: string;
  source: ConsentSource;
  status: ConsentStatus;
  textVersion: string;
  revokesConsentId?: string | undefined;
}>;

export type AppointmentCreateInput = Readonly<{
  branchId: string;
  customerId: string;
  idempotencyKey?: string | undefined;
  providerId: string;
  roomId?: string | undefined;
  serviceId: string;
  source?: AppointmentSource | undefined;
  startsAtLocal: string;
  status?: Extract<AppointmentStatusValue, "PENDING" | "CONFIRMED"> | undefined;
}>;

export type AppointmentRescheduleInput = Readonly<{
  appointmentId: string;
  expectedVersion: number;
  idempotencyKey?: string | undefined;
  startsAtLocal: string;
}>;

export type AppointmentTransitionInput = Readonly<{
  appointmentId: string;
  expectedVersion: number;
  idempotencyKey?: string | undefined;
  internalNote?: string | undefined;
  notificationChoice?: "SEND" | "SKIP" | undefined;
  reason?: string | undefined;
  recordDetails?: string | undefined;
  recordSummary?: string | undefined;
  toStatus: AppointmentStatusValue;
  transitionSource?: AppointmentTransitionSource | undefined;
  consumptions?: readonly AppointmentConsumptionItemInput[] | undefined;
}>;

export type AppointmentCombinedTransitionInput = Readonly<{
  appointmentId: string;
  command: "CHECK_IN_AND_START" | "CONFIRM_AND_CHECK_IN";
  expectedVersion: number;
  idempotencyKey?: string | undefined;
  roomId?: string | undefined;
}>;

export type AppointmentRoomOperationInput = Readonly<{
  asNext?: boolean | undefined;
  appointmentId: string;
  expectedVersion: number;
  idempotencyKey?: string | undefined;
  roomId: string;
}>;

export type AppointmentStartServiceInput = Readonly<{
  appointmentId: string;
  expectedVersion: number;
  idempotencyKey?: string | undefined;
  roomId?: string | undefined;
  includeCheckIn?: boolean | undefined;
}>;

export type AppointmentChangeServiceInput = Readonly<{
  appointmentId: string;
  expectedVersion: number;
  idempotencyKey?: string | undefined;
  reason?: string | undefined;
  serviceId: string;
}>;

export type AppointmentBulkConfirmInput = Readonly<{
  appointmentId: string;
  expectedVersion: number;
}>;

export type AppointmentBulkConfirmResult = Readonly<{
  appointmentId: string;
  code?: string | undefined;
  succeeded: boolean;
}>;

export type AppointmentFilters = Readonly<{
  branchId?: string | undefined;
  dateFrom?: string | undefined;
  dateTo?: string | undefined;
  day?: string | undefined;
  providerId?: string | undefined;
  q?: string | undefined;
  resourceId?: string | undefined;
  serviceId?: string | undefined;
  source?: AppointmentSource | undefined;
  status?: AppointmentStatus | undefined;
}>;

type Resource = Readonly<{ branchId: string; providerId: string }>;

const permissionScopeRank: Readonly<Record<PermissionScope, number>> = {
  ASSIGNED_BRANCHES: 2,
  ORGANIZATION: 3,
  SELF: 1,
};

function assertActiveOrganization(status: OrganizationStatus): void {
  if (status === OrganizationStatus.SUSPENDED) {
    throw new DomainError({
      code: "ORGANIZATION_SUSPENDED",
      message: "Organization is suspended.",
    });
  }
  if (status !== OrganizationStatus.ACTIVE) {
    throw new DomainError({ code: "FORBIDDEN", message: "Organization is not active." });
  }
}

function requirePermissionScope(
  access: TenantAccessSnapshot,
  permission: PermissionCode,
): PermissionScope {
  const scope = access.grants
    .filter((grant) => grant.code === permission)
    .toSorted(
      (left, right) => permissionScopeRank[right.scope] - permissionScopeRank[left.scope],
    )[0]?.scope;
  if (!scope) {
    throw new DomainError({
      code: "FORBIDDEN",
      message: "The active tenant context does not grant this permission.",
      metadata: { permission },
    });
  }
  return scope;
}

function requireResourcePermission(
  access: TenantAccessSnapshot,
  permission: PermissionCode,
  resource: Resource,
): PermissionScope {
  if (access.activeBranchId && resource.branchId !== access.activeBranchId) {
    throw new DomainError({
      code: "NOT_FOUND",
      message: "The record is not available in the active branch.",
    });
  }
  const scope = requirePermissionScope(access, permission);
  if (scope === "ORGANIZATION") {
    return scope;
  }
  if (scope === "ASSIGNED_BRANCHES" && access.assignedBranchIds.includes(resource.branchId)) {
    return scope;
  }
  if (scope === "SELF" && access.staffProfileId === resource.providerId) {
    return scope;
  }
  throw new DomainError({
    code: "FORBIDDEN",
    message: "The active tenant context cannot access this appointment.",
    metadata: { permission },
  });
}

function resourceWhere(
  access: TenantAccessSnapshot,
  permission: PermissionCode,
): Prisma.AppointmentWhereInput {
  const scope = requirePermissionScope(access, permission);
  const activeBranchWhere = access.activeBranchId ? { branchId: access.activeBranchId } : {};
  if (scope === "ORGANIZATION") {
    return activeBranchWhere;
  }
  if (scope === "ASSIGNED_BRANCHES") {
    return access.activeBranchId
      ? activeBranchWhere
      : { branchId: { in: [...access.assignedBranchIds] } };
  }
  if (!access.staffProfileId) {
    return { id: "00000000-0000-0000-0000-000000000000" };
  }
  return { ...activeBranchWhere, providerId: access.staffProfileId };
}

function customerDirectoryWhere(
  access: TenantAccessSnapshot,
  permission: PermissionCode,
): Prisma.CustomerWhereInput {
  const scope = requirePermissionScope(access, permission);
  const appointmentAccess = resourceWhere(access, permission);
  if (access.activeBranchId && scope !== "SELF") {
    return {
      OR: [
        { preferredBranchId: access.activeBranchId },
        { appointments: { some: appointmentAccess } },
      ],
    };
  }
  return Object.keys(appointmentAccess).length ? { appointments: { some: appointmentAccess } } : {};
}

function requireTrimmed(value: string, field: string, maxLength: number): string {
  const trimmed = value.trim();
  if (!trimmed || trimmed.length > maxLength) {
    throw new DomainError({ code: "VALIDATION_FAILED", message: `Invalid ${field}.` });
  }
  return trimmed;
}

function normalizeCustomerTags(tags: readonly string[] | undefined): string[] {
  const normalized = [...new Set((tags ?? []).map((tag) => tag.trim()).filter(Boolean))];
  if (normalized.length > 10 || normalized.some((tag) => tag.length > 40)) {
    throw new DomainError({ code: "VALIDATION_FAILED", message: "Invalid customer tags." });
  }
  return normalized;
}

async function assertPreferredBranch(
  transaction: TenantTransaction,
  organizationId: string,
  preferredBranchId: string | undefined,
): Promise<void> {
  if (!preferredBranchId) return;
  const branch = await transaction.branch.findFirst({
    select: { id: true },
    where: { id: preferredBranchId, isActive: true, organizationId },
  });
  if (!branch) {
    throw new DomainError({ code: "NOT_FOUND", message: "Preferred branch was not found." });
  }
}

function assertExpectedVersion(version: number): void {
  if (!Number.isInteger(version) || version < 1) {
    throw new DomainError({ code: "VALIDATION_FAILED", message: "Invalid record version." });
  }
}

function isPrismaCode(error: unknown, code: string): boolean {
  return typeof error === "object" && error !== null && "code" in error && error.code === code;
}

function conflict(message: string): DomainError {
  return new DomainError({ code: "CONFLICT", message, retryable: true });
}

function fingerprint(value: unknown): string {
  return createHash("sha256").update(JSON.stringify(value)).digest("hex");
}

function asAppointmentStatus(value: AppointmentStatus): AppointmentStatusValue {
  return value as AppointmentStatusValue;
}

function operationPermission(toStatus: AppointmentStatusValue): PermissionCode {
  const permissions: Readonly<Record<AppointmentStatusValue, PermissionCode>> = {
    CALLED: "appointment.callToRoom",
    CANCELLED: "appointment.cancel",
    CHECKED_IN: "appointment.checkIn",
    COMPLETED: "appointment.complete",
    CONFIRMED: "appointment.confirm",
    IN_PROGRESS: "appointment.startService",
    NO_SHOW: "appointment.noShow",
    PENDING: "appointments.status.correct",
  };
  return permissions[toStatus];
}

async function queueOperationalEvent(
  transaction: TenantTransaction,
  appointment: Readonly<{ id: string; organizationId: string; version: number }>,
  eventType:
    | "APPOINTMENT_CANCELLED"
    | "APPOINTMENT_COMPLETED"
    | "APPOINTMENT_CONFIRMED"
    | "PATIENT_CALLED_TO_ROOM",
  payload: Prisma.InputJsonObject,
  deduplicationSuffix?: string,
): Promise<void> {
  await transaction.outboxEvent.create({
    data: {
      aggregateId: appointment.id,
      aggregateType: "Appointment",
      aggregateVersion: appointment.version,
      deduplicationKey: `appointment:${appointment.id}:${eventType}:v${appointment.version}${deduplicationSuffix ? `:${deduplicationSuffix}` : ""}`,
      eventType,
      organizationId: appointment.organizationId,
      payload,
    },
  });
}

type RoomAppointment = Readonly<{
  branchId: string;
  id: string;
  organizationId: string;
  providerId: string;
  serviceId: string;
}>;

async function lockRoomRows(
  transaction: TenantTransaction,
  organizationId: string,
  roomIds: readonly string[],
): Promise<void> {
  const orderedIds = [...new Set(roomIds)].toSorted();
  for (const roomId of orderedIds) {
    const locked = await transaction.$queryRaw<Array<{ id: string }>>(Prisma.sql`
      SELECT "id"
      FROM "resources"
      WHERE "organization_id" = ${organizationId}::uuid AND "id" = ${roomId}::uuid
      FOR UPDATE
    `);
    if (locked.length !== 1) {
      throw new DomainError({ code: "NOT_FOUND", message: "Room not found." });
    }
  }
}

async function lockAppointmentRow(
  transaction: TenantTransaction,
  organizationId: string,
  appointmentId: string,
): Promise<void> {
  const locked = await transaction.$queryRaw<Array<{ id: string }>>(Prisma.sql`
    SELECT "id"
    FROM "appointments"
    WHERE "organization_id" = ${organizationId}::uuid AND "id" = ${appointmentId}::uuid
    FOR UPDATE
  `);
  if (locked.length !== 1) {
    throw new DomainError({ code: "NOT_FOUND", message: "Appointment not found." });
  }
}

async function claimOperationalRoom(
  transaction: TenantTransaction,
  access: TenantAccessSnapshot,
  appointment: RoomAppointment,
  roomId: string,
  roomAlreadyLocked = false,
) {
  if (!roomAlreadyLocked) {
    await lockRoomRows(transaction, access.organizationId, [roomId]);
  }
  const room = await transaction.resource.findFirst({
    include: {
      compatibleServices: { select: { serviceId: true } },
      group: { select: { kind: true } },
    },
    where: { id: roomId, organizationId: access.organizationId },
  });
  if (
    !room ||
    room.branchId !== appointment.branchId ||
    room.group.kind !== "ROOM" ||
    room.status !== "ACTIVE" ||
    !room.compatibleServices.some(({ serviceId }) => serviceId === appointment.serviceId)
  ) {
    throw conflict("The selected room is not active and compatible with this appointment.");
  }
  const occupied = await transaction.roomOccupancy.findMany({
    select: { slot: true },
    where: { organizationId: access.organizationId, releasedAt: null, resourceId: room.id },
  });
  const occupiedSlots = new Set(occupied.map(({ slot }) => slot));
  const slot = Array.from({ length: room.capacity }, (_, index) => index + 1).find(
    (candidate) => !occupiedSlots.has(candidate),
  );
  if (!slot) throw conflict("The selected room has no available operational capacity.");
  try {
    const occupancy = await transaction.roomOccupancy.create({
      data: {
        appointmentId: appointment.id,
        claimedByUserId: access.actorUserId,
        organizationId: access.organizationId,
        resourceId: room.id,
        slot,
      },
      include: { resource: { select: { id: true, nameAr: true, nameEn: true } } },
    });
    return occupancy;
  } catch (error) {
    if (isPrismaCode(error, "P2002") || isPrismaCode(error, "P2004")) {
      throw conflict("The room or appointment was claimed by another user. Refresh and try again.");
    }
    throw error;
  }
}

async function createAuditEvent(
  transaction: TenantTransaction,
  access: TenantAccessSnapshot,
  action: string,
  targetType: string,
  targetId: string,
  details?: RequestAuditDetails,
  reason?: string,
): Promise<void> {
  await transaction.auditEvent.create({
    data: {
      action,
      actorUserId: access.actorUserId,
      ipAddress: details?.ipAddress ?? null,
      organizationId: access.organizationId,
      reason: reason ?? null,
      supportAccessId: access.supportAccessId ?? null,
      targetId,
      targetType,
      userAgent: details?.userAgent ?? null,
    },
  });
}

async function createAppointmentNotifications(
  transaction: TenantTransaction,
  appointment: Readonly<{ branchId: string; id: string; organizationId: string }>,
  status: AppointmentStatus,
): Promise<void> {
  const titles: Partial<Record<AppointmentStatus, readonly [string, string]>> = {
    CALLED: ["Patient Called to Room", "تم استدعاء المريض إلى الغرفة"],
    CANCELLED: ["Appointment Cancelled", "تم إلغاء الموعد"],
    CHECKED_IN: ["Patient Checked In", "تم تسجيل وصول المريض"],
    CONFIRMED: ["Appointment Confirmed", "تم تأكيد الموعد"],
  };
  const title = titles[status];
  if (!title) return;
  const appointmentDetails = await transaction.appointment.findFirst({
    select: {
      customer: { select: { displayName: true } },
      referenceCode: true,
      service: { select: { nameAr: true, nameEn: true } },
    },
    where: { id: appointment.id, organizationId: appointment.organizationId },
  });
  if (!appointmentDetails) return;
  const statusMessages: Partial<Record<AppointmentStatus, readonly [string, string]>> = {
    CALLED: ["has been called to a room", "تم استدعاؤه إلى الغرفة"],
    CANCELLED: ["has been cancelled", "تم إلغاؤه"],
    CHECKED_IN: ["has checked in", "تم تسجيل وصوله"],
    CONFIRMED: ["has been confirmed", "تم تأكيده"],
  };
  const statusMessage = statusMessages[status];
  if (!statusMessage) return;
  const recipients = await transaction.$queryRaw<Array<{ userId: string }>>(Prisma.sql`
    SELECT DISTINCT membership."user_id" AS "userId" FROM "organization_memberships" membership
    JOIN "membership_roles" membership_role ON membership_role."organization_id"=membership."organization_id" AND membership_role."membership_id"=membership."id"
    JOIN "role_permissions" role_permission ON role_permission."organization_id"=membership."organization_id" AND role_permission."role_id"=membership_role."role_id"
    JOIN "permissions" permission ON permission."id"=role_permission."permission_id"
    WHERE membership."organization_id"=${appointment.organizationId}::uuid AND membership."status"='ACTIVE' AND permission."code"='notifications.read'
  `);
  if (recipients.length === 0) return;
  await transaction.notification.createMany({
    data: recipients.map(({ userId }) => ({
      branchId: appointment.branchId,
      messageAr: `${appointmentDetails.customer.displayName} — ${appointmentDetails.service.nameAr} (${appointmentDetails.referenceCode}): ${statusMessage[1]}.`,
      messageEn: `${appointmentDetails.customer.displayName}'s ${appointmentDetails.service.nameEn} appointment (${appointmentDetails.referenceCode}) ${statusMessage[0]}.`,
      organizationId: appointment.organizationId,
      recipientUserId: userId,
      relatedEntityId: appointment.id,
      relatedEntityType: "Appointment",
      targetRoute: `/schedule/appointments?appointment=${appointment.id}`,
      titleAr: title[1],
      titleEn: title[0],
      type: `APPOINTMENT_${status}`,
    })),
  });
}

type IdempotencyReservation = Readonly<{ appointmentId: string; replayed: boolean }>;

async function reserveIdempotency(
  transaction: TenantTransaction,
  access: TenantAccessSnapshot,
  input: Readonly<{
    appointmentId: string;
    key?: string | undefined;
    operation: string;
    payload: unknown;
  }>,
): Promise<IdempotencyReservation> {
  if (!input.key) {
    return { appointmentId: input.appointmentId, replayed: false };
  }
  const requestFingerprint = fingerprint(input.payload);
  const inserted = await transaction.$queryRaw<Array<{ appointmentId: string }>>(Prisma.sql`
    INSERT INTO "appointment_idempotencies" (
      "organization_id", "operation", "request_key", "request_fingerprint",
      "appointment_id", "expires_at"
    ) VALUES (
      ${access.organizationId}::uuid, ${input.operation}, ${input.key}::uuid,
      ${requestFingerprint}, ${input.appointmentId}::uuid,
      ${new Date(Date.now() + 24 * 60 * 60 * 1000)}
    )
    ON CONFLICT ("organization_id", "operation", "request_key") DO NOTHING
    RETURNING "appointment_id" AS "appointmentId"
  `);
  if (inserted.length === 1) {
    return { appointmentId: input.appointmentId, replayed: false };
  }
  const prior = await transaction.appointmentIdempotency.findFirst({
    where: {
      operation: input.operation,
      organizationId: access.organizationId,
      requestKey: input.key,
    },
  });
  if (!prior || prior.requestFingerprint !== requestFingerprint) {
    throw new DomainError({
      code: "IDEMPOTENCY_CONFLICT",
      message: "This request key was already used for a different operation.",
    });
  }
  return { appointmentId: prior.appointmentId, replayed: true };
}

export class CrmAppointmentRepository {
  readonly client: PrismaClient;

  constructor(client: PrismaClient) {
    this.client = client;
  }

  private async assertSuperAdmin(userId: string): Promise<void> {
    const user = await this.client.user.findUnique({
      select: { platformRole: true },
      where: { id: userId },
    });
    if (user?.platformRole !== PlatformRole.JORMALL_SUPER_ADMIN) {
      throw new DomainError({ code: "FORBIDDEN", message: "Super Admin access is required." });
    }
  }

  private async runWithAccess<T>(
    access: TenantAccessSnapshot,
    operation: (transaction: TenantTransaction) => Promise<T>,
  ): Promise<T> {
    if (access.supportAccessId) {
      await this.assertSuperAdmin(access.actorUserId);
      const supportAccess = await this.client.platformSupportAccess.findFirst({
        select: { id: true },
        where: {
          expiresAt: { gt: new Date() },
          id: access.supportAccessId,
          organizationId: access.organizationId,
          revokedAt: null,
          userId: access.actorUserId,
        },
      });
      if (!supportAccess) {
        throw new DomainError({
          code: "FORBIDDEN",
          message: "Support access is invalid or expired.",
        });
      }
    }
    return runInTenant(this.client, access, async (transaction) => {
      const organization = await transaction.organization.findUnique({
        select: { status: true },
        where: { id: access.organizationId },
      });
      if (!organization) {
        throw new DomainError({ code: "NOT_FOUND", message: "Organization not found." });
      }
      assertActiveOrganization(organization.status);
      if (access.membershipId) {
        const membership = await transaction.organizationMembership.findFirst({
          select: { status: true },
          where: {
            id: access.membershipId,
            organizationId: access.organizationId,
            userId: access.actorUserId,
          },
        });
        if (!membership) {
          throw new DomainError({ code: "NOT_FOUND", message: "Membership not found." });
        }
        if (membership.status !== MembershipStatus.ACTIVE) {
          throw new DomainError({
            code: "MEMBERSHIP_SUSPENDED",
            message: "Membership is not active.",
          });
        }
      } else if (access.gatewayActionId) {
        const gatewayAction = await transaction.aIAction.findFirst({
          select: { requiredPermission: true },
          where: {
            actorId: access.actorUserId,
            id: access.gatewayActionId,
            organizationId: access.organizationId,
            outcome: { in: ["PENDING", "REQUIRES_CONFIRMATION"] },
          },
        });
        if (
          !gatewayAction ||
          !access.grants.some(({ code }) => code === gatewayAction.requiredPermission)
        ) {
          throw new DomainError({
            code: "FORBIDDEN",
            message: "AI Action Gateway authorization is invalid.",
          });
        }
      } else if (!access.supportAccessId) {
        throw new DomainError({
          code: "TENANT_CONTEXT_REQUIRED",
          message: "An active membership or support access is required.",
        });
      }
      return operation(transaction);
    });
  }

  async listCustomers(access: TenantAccessSnapshot, query?: string) {
    const customerAccess = customerDirectoryWhere(access, "customers.read");
    const searched = query?.trim();
    const normalizedPhone = searched ? normalizeJordanianPhone(searched) : null;
    return this.runWithAccess(access, (transaction) =>
      transaction.customer.findMany({
        include: {
          contacts: {
            orderBy: [{ isPrimary: "desc" }, { createdAt: "asc" }],
            select: {
              id: true,
              isPrimary: true,
              kind: true,
              normalizedPhoneE164: true,
              originalValue: true,
            },
          },
          preferredBranch: { select: { id: true, nameAr: true, nameEn: true } },
        },
        orderBy: [{ isArchived: "asc" }, { displayName: "asc" }, { id: "asc" }],
        take: 100,
        where: {
          organizationId: access.organizationId,
          ...customerAccess,
          ...(searched
            ? {
                OR: [
                  { displayName: { contains: searched, mode: "insensitive" } },
                  { referenceCode: { contains: searched, mode: "insensitive" } },
                  { tags: { has: searched } },
                  ...(normalizedPhone
                    ? [
                        {
                          contacts: {
                            some: { normalizedPhoneE164: { contains: normalizedPhone } },
                          },
                        },
                      ]
                    : []),
                  { contacts: { some: { originalValue: { contains: searched } } } },
                ],
              }
            : {}),
        },
      }),
    );
  }

  async listPatients(
    access: TenantAccessSnapshot,
    input: Readonly<{ page?: number; pageSize?: number; query?: string }> = {},
  ) {
    const customerAccess = customerDirectoryWhere(access, "patients.directory.read");
    const appointmentAccess = resourceWhere(access, "patients.directory.read");
    const canReadContact = access.grants.some(({ code }) => code === "patients.contact.read");
    const page = Math.max(1, input.page ?? 1);
    const pageSize = Math.min(100, Math.max(10, input.pageSize ?? 25));
    const searched = input.query?.trim();
    const digits = searched?.replace(/\D/g, "") ?? "";
    return this.runWithAccess(access, async (transaction) => {
      const where: Prisma.CustomerWhereInput = {
        isArchived: false,
        organizationId: access.organizationId,
        ...customerAccess,
        ...(searched
          ? {
              OR: [
                { displayName: { contains: searched, mode: "insensitive" } },
                { referenceCode: { contains: searched, mode: "insensitive" } },
                ...(digits
                  ? [
                      { contacts: { some: { normalizedPhoneE164: { contains: digits } } } },
                      { contacts: { some: { originalValue: { contains: searched } } } },
                    ]
                  : []),
              ],
            }
          : {}),
      };
      const [rows, total] = await Promise.all([
        transaction.customer.findMany({
          orderBy: [{ displayName: "asc" }, { id: "asc" }],
          select: {
            appointments: {
              orderBy: { startsAt: "desc" },
              select: { startsAt: true, status: true },
              take: 50,
              where: appointmentAccess,
            },
            displayName: true,
            id: true,
            referenceCode: true,
            ...(canReadContact
              ? {
                  contacts: {
                    orderBy: [{ isPrimary: "desc" as const }, { createdAt: "asc" as const }],
                    select: { kind: true, originalValue: true },
                  },
                }
              : {}),
          },
          skip: (page - 1) * pageSize,
          take: pageSize,
          where,
        }),
        transaction.customer.count({ where }),
      ]);
      return { page, pageSize, rows, total };
    });
  }

  async getCustomer(access: TenantAccessSnapshot, customerId: string) {
    requirePermissionScope(access, "customers.read");
    requirePermissionScope(access, "consent.read");
    const appointmentAccess = resourceWhere(access, "appointments.read");
    const appointmentScope = requirePermissionScope(access, "appointments.read");
    return this.runWithAccess(access, async (transaction) => {
      const customer = await transaction.customer.findFirst({
        include: {
          appointments: {
            include: {
              branch: { select: { id: true, nameAr: true, nameEn: true, timezone: true } },
              provider: { select: { id: true, displayNameAr: true, displayNameEn: true } },
              room: { select: { id: true, nameAr: true, nameEn: true } },
              service: { select: { id: true, nameAr: true, nameEn: true } },
            },
            orderBy: { startsAt: "desc" },
            take: 50,
            where: appointmentAccess,
          },
          consents: {
            orderBy: { recordedAt: "desc" },
            where: { purpose: { not: "patient_safety_intake" } },
          },
          contacts: { orderBy: [{ isPrimary: "desc" }, { createdAt: "asc" }] },
          notes: {
            include: { author: { select: { id: true, name: true } } },
            orderBy: { createdAt: "desc" },
            take: 50,
          },
          preferredBranch: { select: { id: true, nameAr: true, nameEn: true } },
        },
        where: {
          id: customerId,
          organizationId: access.organizationId,
          ...(access.activeBranchId && appointmentScope !== "SELF"
            ? {
                OR: [
                  { preferredBranchId: access.activeBranchId },
                  { appointments: { some: appointmentAccess } },
                ],
              }
            : Object.keys(appointmentAccess).length
              ? { appointments: { some: appointmentAccess } }
              : {}),
        },
      });
      if (!customer) {
        throw new DomainError({ code: "NOT_FOUND", message: "Customer not found." });
      }
      return customer;
    });
  }

  async createCustomer(
    access: TenantAccessSnapshot,
    input: CustomerInput,
    details?: RequestAuditDetails,
  ) {
    requirePermissionScope(access, "customers.write");
    if (access.activeBranchId && input.preferredBranchId !== access.activeBranchId) {
      throw new DomainError({
        code: "NOT_FOUND",
        message: "The patient must be assigned to the active branch.",
      });
    }
    const hasSafetyIntake =
      (input.allergyState !== undefined && input.allergyState !== "NOT_PROVIDED") ||
      (input.medicalConditionState !== undefined &&
        input.medicalConditionState !== "NOT_PROVIDED") ||
      input.allergyDetails !== undefined ||
      input.medicalConditionDetails !== undefined;
    if (hasSafetyIntake) requirePermissionScope(access, "patients.health.write");
    const displayName = requireTrimmed(input.displayName, "customer name", 160);
    const phoneOriginal = input.phoneOriginal?.trim() || undefined;
    const emailOriginal = input.emailOriginal?.trim().toLowerCase() || undefined;
    const tags = normalizeCustomerTags(input.tags);
    if (phoneOriginal && phoneOriginal.length > 80) {
      throw new DomainError({ code: "VALIDATION_FAILED", message: "Invalid customer phone." });
    }
    return this.runWithAccess(access, async (transaction) => {
      await assertPreferredBranch(transaction, access.organizationId, input.preferredBranchId);
      const normalizedPhone = phoneOriginal ? normalizeJordanianPhone(phoneOriginal) : null;
      if (input.rejectDuplicatePhone && normalizedPhone) {
        const duplicate = await transaction.customerContact.findFirst({
          select: { customerId: true },
          where: { normalizedPhoneE164: normalizedPhone, organizationId: access.organizationId },
        });
        if (duplicate) {
          throw new DomainError({
            code: "CONFLICT",
            message:
              "A patient with this phone number already exists. Review the matching patient.",
            metadata: { duplicateCustomerId: duplicate.customerId },
          });
        }
      }
      const allergy = normalizeHealthInformation(
        input.allergyState ?? "NOT_PROVIDED",
        input.allergyDetails,
      );
      const condition = normalizeHealthInformation(
        input.medicalConditionState ?? "NOT_PROVIDED",
        input.medicalConditionDetails,
      );
      const consentRequired = requiresHealthConsent([allergy.state, condition.state]);
      if (consentRequired && !input.healthConsentConfirmed) {
        throw new DomainError({
          code: "FORBIDDEN",
          message: "Patient consent must be confirmed before recording safety intake information.",
        });
      }
      const customer = await transaction.customer.create({
        data: {
          displayName,
          organizationId: access.organizationId,
          preferredBranchId: input.preferredBranchId ?? null,
          preferredLocale: input.preferredLocale ?? "en",
          tags,
          ...(phoneOriginal || emailOriginal
            ? {
                contacts: {
                  create: [
                    ...(phoneOriginal
                      ? [
                          {
                            isPrimary: true,
                            kind: CustomerContactKind.PHONE,
                            normalizedPhoneE164: normalizedPhone,
                            originalValue: phoneOriginal,
                          },
                        ]
                      : []),
                    ...(emailOriginal
                      ? [
                          {
                            isPrimary: !phoneOriginal,
                            kind: CustomerContactKind.EMAIL,
                            normalizedPhoneE164: null,
                            originalValue: emailOriginal,
                          },
                        ]
                      : []),
                  ],
                },
              }
            : {}),
        },
        include: { contacts: true },
      });
      const consent = consentRequired
        ? await transaction.consent.create({
            data: {
              actorUserId: access.actorUserId,
              channel: "STAFF",
              customerId: customer.id,
              evidence: "Patient authorized staff to record safety intake information.",
              organizationId: access.organizationId,
              purpose: "patient_safety_intake",
              source: "STAFF",
              status: "GRANTED",
              textVersion: "karmalite-safety-intake-v1",
            },
          })
        : null;
      if (hasSafetyIntake) {
        await transaction.patientHealthInformation.create({
          data: {
            allergyDetails: allergy.details,
            allergyState: allergy.state,
            consentId: consent?.id ?? null,
            customerId: customer.id,
            medicalConditionDetails: condition.details,
            medicalConditionState: condition.state,
            organizationId: access.organizationId,
            updatedByUserId: access.actorUserId,
          },
        });
      }
      await createAuditEvent(
        transaction,
        access,
        "CUSTOMER_CREATED",
        "Customer",
        customer.id,
        details,
      );
      return {
        customer,
        likelyDuplicates: await this.findLikelyDuplicatesInTransaction(
          transaction,
          access.organizationId,
          {
            displayName,
            normalizedPhone: phoneOriginal ? normalizeJordanianPhone(phoneOriginal) : null,
            omitCustomerId: customer.id,
          },
        ),
      };
    });
  }

  async updateCustomer(
    access: TenantAccessSnapshot,
    input: CustomerUpdateInput,
    details?: RequestAuditDetails,
  ) {
    requirePermissionScope(access, "customers.write");
    if (access.activeBranchId && input.preferredBranchId !== access.activeBranchId) {
      throw new DomainError({
        code: "NOT_FOUND",
        message: "The patient must be assigned to the active branch.",
      });
    }
    assertExpectedVersion(input.expectedVersion);
    const displayName = requireTrimmed(input.displayName, "customer name", 160);
    const phoneOriginal = input.phoneOriginal?.trim() || undefined;
    const tags = normalizeCustomerTags(input.tags);
    if (phoneOriginal && phoneOriginal.length > 80) {
      throw new DomainError({ code: "VALIDATION_FAILED", message: "Invalid customer phone." });
    }
    return this.runWithAccess(access, async (transaction) => {
      await assertPreferredBranch(transaction, access.organizationId, input.preferredBranchId);
      const current = await transaction.customer.findFirst({
        include: { contacts: { where: { isPrimary: true, kind: CustomerContactKind.PHONE } } },
        where: {
          ...customerDirectoryWhere(access, "customers.write"),
          id: input.customerId,
          organizationId: access.organizationId,
        },
      });
      if (!current) {
        throw new DomainError({ code: "NOT_FOUND", message: "Customer not found." });
      }
      const changed = await transaction.customer.updateMany({
        data: {
          displayName,
          preferredBranchId: input.preferredBranchId ?? null,
          preferredLocale: input.preferredLocale ?? "en",
          tags,
          version: { increment: 1 },
        },
        where: {
          id: input.customerId,
          organizationId: access.organizationId,
          version: input.expectedVersion,
        },
      });
      if (changed.count !== 1) {
        throw conflict("Customer changed by another user. Refresh and try again.");
      }
      const primaryPhone = current.contacts[0];
      if (phoneOriginal) {
        const contact = {
          normalizedPhoneE164: normalizeJordanianPhone(phoneOriginal),
          originalValue: phoneOriginal,
        };
        if (primaryPhone) {
          await transaction.customerContact.update({
            data: contact,
            where: { id: primaryPhone.id },
          });
        } else {
          await transaction.customerContact.create({
            data: {
              ...contact,
              customerId: input.customerId,
              isPrimary: true,
              kind: CustomerContactKind.PHONE,
              organizationId: access.organizationId,
            },
          });
        }
      } else if (primaryPhone) {
        await transaction.customerContact.delete({ where: { id: primaryPhone.id } });
      }
      const customer = await transaction.customer.findFirstOrThrow({
        include: { contacts: true },
        where: { id: input.customerId, organizationId: access.organizationId },
      });
      await createAuditEvent(
        transaction,
        access,
        "CUSTOMER_UPDATED",
        "Customer",
        customer.id,
        details,
      );
      return {
        customer,
        likelyDuplicates: await this.findLikelyDuplicatesInTransaction(
          transaction,
          access.organizationId,
          {
            displayName,
            normalizedPhone: phoneOriginal ? normalizeJordanianPhone(phoneOriginal) : null,
            omitCustomerId: customer.id,
          },
        ),
      };
    });
  }

  async getPatientSafetyIndicators(access: TenantAccessSnapshot, customerId: string) {
    const scope = requirePermissionScope(access, "patients.health.read");
    return this.runWithAccess(access, async (transaction) => {
      const patient = await transaction.customer.findFirst({
        select: {
          healthInformation: { select: { allergyState: true, medicalConditionState: true } },
          id: true,
        },
        where: {
          id: customerId,
          organizationId: access.organizationId,
          ...(scope === "SELF"
            ? {
                appointments: {
                  some: {
                    providerId: access.staffProfileId ?? "00000000-0000-0000-0000-000000000000",
                  },
                },
              }
            : scope === "ASSIGNED_BRANCHES"
              ? { appointments: { some: { branchId: { in: [...access.assignedBranchIds] } } } }
              : {}),
        },
      });
      if (!patient) throw new DomainError({ code: "NOT_FOUND", message: "Patient not found." });
      await createAuditEvent(
        transaction,
        access,
        "PATIENT_SAFETY_INDICATORS_READ",
        "Customer",
        patient.id,
      );
      return {
        allergyInformationAvailable: patient.healthInformation?.allergyState === "PROVIDED",
        conditionInformationAvailable:
          patient.healthInformation?.medicalConditionState === "PROVIDED",
        healthInformationNotProvided:
          !patient.healthInformation ||
          (patient.healthInformation.allergyState === "NOT_PROVIDED" &&
            patient.healthInformation.medicalConditionState === "NOT_PROVIDED"),
      };
    });
  }

  async getPatientSafetyIntake(access: TenantAccessSnapshot, customerId: string) {
    const scope = requirePermissionScope(access, "patients.health.read");
    return this.runWithAccess(access, async (transaction) => {
      const patient = await transaction.customer.findFirst({
        select: {
          healthInformation: {
            include: {
              consent: { select: { channel: true, recordedAt: true, source: true } },
              updatedBy: { select: { id: true, name: true } },
            },
          },
          id: true,
        },
        where: {
          id: customerId,
          organizationId: access.organizationId,
          ...(scope === "SELF"
            ? {
                appointments: {
                  some: {
                    providerId: access.staffProfileId ?? "00000000-0000-0000-0000-000000000000",
                  },
                },
              }
            : scope === "ASSIGNED_BRANCHES"
              ? { appointments: { some: { branchId: { in: [...access.assignedBranchIds] } } } }
              : {}),
        },
      });
      if (!patient) throw new DomainError({ code: "NOT_FOUND", message: "Patient not found." });
      await createAuditEvent(
        transaction,
        access,
        "PATIENT_SAFETY_INTAKE_READ",
        "Customer",
        patient.id,
      );
      return patient.healthInformation;
    });
  }

  async updatePatientSafetyIntake(
    access: TenantAccessSnapshot,
    input: Readonly<{
      allergyDetails?: string | undefined;
      allergyState: HealthInformationState;
      consentConfirmed: boolean;
      customerId: string;
      medicalConditionDetails?: string | undefined;
      medicalConditionState: HealthInformationState;
    }>,
    details?: RequestAuditDetails,
  ) {
    const scope = requirePermissionScope(access, "patients.health.write");
    const allergy = normalizeHealthInformation(input.allergyState, input.allergyDetails);
    const condition = normalizeHealthInformation(
      input.medicalConditionState,
      input.medicalConditionDetails,
    );
    const consentRequired = requiresHealthConsent([allergy.state, condition.state]);
    if (consentRequired && !input.consentConfirmed) {
      throw new DomainError({
        code: "FORBIDDEN",
        message: "Patient consent must be confirmed before recording safety intake information.",
      });
    }
    return this.runWithAccess(access, async (transaction) => {
      const patient = await transaction.customer.findFirst({
        select: { id: true },
        where: {
          id: input.customerId,
          organizationId: access.organizationId,
          ...(scope === "SELF"
            ? {
                appointments: {
                  some: {
                    providerId: access.staffProfileId ?? "00000000-0000-0000-0000-000000000000",
                  },
                },
              }
            : scope === "ASSIGNED_BRANCHES"
              ? { appointments: { some: { branchId: { in: [...access.assignedBranchIds] } } } }
              : {}),
        },
      });
      if (!patient) throw new DomainError({ code: "NOT_FOUND", message: "Patient not found." });
      const consent = consentRequired
        ? await transaction.consent.create({
            data: {
              actorUserId: access.actorUserId,
              channel: "STAFF",
              customerId: patient.id,
              evidence: "Patient authorized staff to record safety intake information.",
              organizationId: access.organizationId,
              purpose: "patient_safety_intake",
              source: "STAFF",
              status: "GRANTED",
              textVersion: "karmalite-safety-intake-v1",
            },
          })
        : null;
      const health = await transaction.patientHealthInformation.upsert({
        create: {
          allergyDetails: allergy.details,
          allergyState: allergy.state,
          customerId: patient.id,
          medicalConditionDetails: condition.details,
          medicalConditionState: condition.state,
          organizationId: access.organizationId,
          consentId: consent?.id ?? null,
          updatedByUserId: access.actorUserId,
        },
        update: {
          allergyDetails: allergy.details,
          allergyState: allergy.state,
          medicalConditionDetails: condition.details,
          medicalConditionState: condition.state,
          consentId: consent?.id ?? null,
          updatedByUserId: access.actorUserId,
        },
        where: {
          organizationId_customerId: {
            customerId: patient.id,
            organizationId: access.organizationId,
          },
        },
      });
      await createAuditEvent(
        transaction,
        access,
        "PATIENT_SAFETY_INTAKE_UPDATED",
        "Customer",
        patient.id,
        details,
      );
      return health;
    });
  }

  async addCustomerNote(
    access: TenantAccessSnapshot,
    input: Readonly<{ body: string; customerId: string }>,
    details?: RequestAuditDetails,
  ) {
    requirePermissionScope(access, "customers.write");
    const body = requireTrimmed(input.body, "customer note", 2_000);
    const customerAccess = customerDirectoryWhere(access, "customers.read");
    return this.runWithAccess(access, async (transaction) => {
      const customer = await transaction.customer.findFirst({
        select: { id: true },
        where: {
          ...customerAccess,
          id: input.customerId,
          organizationId: access.organizationId,
        },
      });
      if (!customer) {
        throw new DomainError({ code: "NOT_FOUND", message: "Customer not found." });
      }
      const note = await transaction.customerNote.create({
        data: {
          authorUserId: access.actorUserId,
          body,
          customerId: customer.id,
          organizationId: access.organizationId,
        },
      });
      await createAuditEvent(
        transaction,
        access,
        "CUSTOMER_NOTE_ADDED",
        "CustomerNote",
        note.id,
        details,
      );
      return note;
    });
  }

  async listPatientDoctorNotes(access: TenantAccessSnapshot, customerId: string) {
    const scope = requirePermissionScope(access, "patients.doctor_notes.read");
    return this.runWithAccess(access, (transaction) =>
      transaction.appointmentNote.findMany({
        include: {
          appointment: { select: { id: true, referenceCode: true } },
          author: { select: { id: true, name: true } },
        },
        orderBy: [{ createdAt: "desc" }, { id: "desc" }],
        where: {
          appointment: {
            customerId,
            ...(scope === "SELF"
              ? { providerId: access.staffProfileId ?? "00000000-0000-0000-0000-000000000000" }
              : scope === "ASSIGNED_BRANCHES"
                ? { branchId: { in: [...access.assignedBranchIds] } }
                : {}),
          },
          organizationId: access.organizationId,
        },
      }),
    );
  }

  async listPatientAudit(access: TenantAccessSnapshot, customerId: string) {
    const scope = requirePermissionScope(access, "audit.read");
    return this.runWithAccess(access, async (transaction) => {
      const patient = await transaction.customer.findFirst({
        select: { id: true },
        where: {
          id: customerId,
          organizationId: access.organizationId,
          ...(scope === "SELF"
            ? {
                appointments: {
                  some: {
                    providerId: access.staffProfileId ?? "00000000-0000-0000-0000-000000000000",
                  },
                },
              }
            : scope === "ASSIGNED_BRANCHES"
              ? { appointments: { some: { branchId: { in: [...access.assignedBranchIds] } } } }
              : {}),
        },
      });
      if (!patient) throw new DomainError({ code: "NOT_FOUND", message: "Patient not found." });
      await createAuditEvent(transaction, access, "PATIENT_AUDIT_VIEWED", "Customer", patient.id);
      return transaction.auditEvent.findMany({
        include: { actor: { select: { id: true, name: true } } },
        orderBy: { createdAt: "desc" },
        take: 100,
        where: {
          organizationId: access.organizationId,
          OR: [
            { targetId: patient.id, targetType: "Customer" },
            { targetId: patient.id, targetType: "PatientHealthInformation" },
          ],
        },
      });
    });
  }

  async recordConsent(
    access: TenantAccessSnapshot,
    input: ConsentInput,
    details?: RequestAuditDetails,
  ) {
    requirePermissionScope(access, "consent.record");
    const purpose = requireTrimmed(input.purpose, "consent purpose", 120);
    const textVersion = requireTrimmed(input.textVersion, "consent version", 80);
    const evidence = input.evidence?.trim() || null;
    if (evidence && evidence.length > 2_000) {
      throw new DomainError({
        code: "VALIDATION_FAILED",
        message: "Consent evidence is too long.",
      });
    }
    return this.runWithAccess(access, async (transaction) => {
      const customer = await transaction.customer.findFirst({
        select: { id: true },
        where: { id: input.customerId, organizationId: access.organizationId },
      });
      if (!customer) {
        throw new DomainError({ code: "NOT_FOUND", message: "Customer not found." });
      }
      if (input.status === ConsentStatus.REVOKED && !input.revokesConsentId) {
        throw new DomainError({
          code: "VALIDATION_FAILED",
          message: "A revoked consent must reference consent.",
        });
      }
      if (input.revokesConsentId) {
        const prior = await transaction.consent.findFirst({
          select: { customerId: true, purpose: true, status: true },
          where: { id: input.revokesConsentId, organizationId: access.organizationId },
        });
        if (
          !prior ||
          prior.customerId !== input.customerId ||
          prior.purpose !== purpose ||
          prior.status !== ConsentStatus.GRANTED
        ) {
          throw new DomainError({ code: "CONFLICT", message: "The consent cannot be revoked." });
        }
      }
      const consent = await transaction.consent.create({
        data: {
          actorUserId: access.actorUserId,
          channel: input.channel,
          customerId: input.customerId,
          evidence,
          organizationId: access.organizationId,
          purpose,
          revokesConsentId: input.revokesConsentId ?? null,
          source: input.source,
          status: input.status,
          textVersion,
        },
      });
      await createAuditEvent(
        transaction,
        access,
        input.status === ConsentStatus.REVOKED ? "CONSENT_REVOKED" : "CONSENT_RECORDED",
        "Consent",
        consent.id,
        details,
      );
      return consent;
    });
  }

  async listAppointmentFormOptions(access: TenantAccessSnapshot) {
    requirePermissionScope(access, "appointments.create");
    requirePermissionScope(access, "customers.read");
    return this.runWithAccess(access, async (transaction) => {
      const [customers, branches, serviceRows, providerRows, roomRows] = await Promise.all([
        transaction.customer.findMany({
          orderBy: { displayName: "asc" },
          select: {
            contacts: {
              select: { kind: true, originalValue: true },
              orderBy: { createdAt: "asc" },
            },
            displayName: true,
            id: true,
            preferredLocale: true,
          },
          take: 100,
          where: {
            ...customerDirectoryWhere(access, "customers.read"),
            isArchived: false,
            organizationId: access.organizationId,
          },
        }),
        transaction.branch.findMany({
          orderBy: { nameEn: "asc" },
          select: {
            hoursRules: {
              orderBy: [{ weekday: "asc" }, { startMinuteLocal: "asc" }],
              select: { endMinuteLocal: true, startMinuteLocal: true, weekday: true },
            },
            id: true,
            nameAr: true,
            nameEn: true,
            timezone: true,
          },
          where: {
            ...(access.activeBranchId ? { id: access.activeBranchId } : {}),
            isActive: true,
            organizationId: access.organizationId,
          },
        }),
        transaction.service.findMany({
          orderBy: { nameEn: "asc" },
          select: {
            branches: {
              select: {
                branchId: true,
                bufferAfterMins: true,
                bufferBeforeMins: true,
                durationMins: true,
                priceMinor: true,
              },
              where: {
                ...(access.activeBranchId ? { branchId: access.activeBranchId } : {}),
                isEnabled: true,
              },
            },
            id: true,
            nameAr: true,
            nameEn: true,
            currency: true,
            defaultDurationMins: true,
            defaultPriceMinor: true,
            postTreatmentInstructionsAr: true,
            postTreatmentInstructionsEn: true,
            preTreatmentInstructionsAr: true,
            preTreatmentInstructionsEn: true,
            resourceRequirements: {
              select: {
                branchId: true,
                quantity: true,
                resourceGroup: { select: { nameAr: true, nameEn: true } },
              },
            },
          },
          where: {
            ...(access.activeBranchId
              ? { branches: { some: { branchId: access.activeBranchId, isEnabled: true } } }
              : {}),
            isActive: true,
            organizationId: access.organizationId,
          },
        }),
        transaction.staffProfile.findMany({
          orderBy: { displayNameEn: "asc" },
          select: {
            branchAssignments: {
              select: { branchId: true },
              ...(access.activeBranchId ? { where: { branchId: access.activeBranchId } } : {}),
            },
            displayNameAr: true,
            displayNameEn: true,
            id: true,
            availabilityRules: {
              orderBy: [{ weekday: "asc" }, { startMinuteLocal: "asc" }],
              select: {
                branchId: true,
                endMinuteLocal: true,
                startMinuteLocal: true,
                weekday: true,
              },
            },
            breaks: {
              orderBy: [{ weekday: "asc" }, { startMinuteLocal: "asc" }],
              select: {
                branchId: true,
                endMinuteLocal: true,
                label: true,
                startMinuteLocal: true,
                weekday: true,
              },
            },
            services: { select: { serviceId: true }, where: { isEnabled: true } },
            timeOffEntries: {
              orderBy: { startsAt: "asc" },
              select: { branchId: true, endsAt: true, reason: true, startsAt: true },
              where: { endsAt: { gt: new Date() } },
            },
          },
          where: {
            ...(access.activeBranchId
              ? { branchAssignments: { some: { branchId: access.activeBranchId } } }
              : {}),
            isActive: true,
            isBookable: true,
            isDoctor: true,
            organizationId: access.organizationId,
          },
        }),
        transaction.resource.findMany({
          orderBy: [{ nameEn: "asc" }, { id: "asc" }],
          select: {
            branchId: true,
            capacity: true,
            compatibleServices: { select: { serviceId: true } },
            id: true,
            nameAr: true,
            nameEn: true,
            status: true,
          },
          where: {
            ...(access.activeBranchId ? { branchId: access.activeBranchId } : {}),
            group: { kind: "ROOM" },
            organizationId: access.organizationId,
            status: "ACTIVE",
          },
        }),
      ]);
      return {
        branches,
        customers,
        providers: providerRows.map(({ branchAssignments, services, ...provider }) => ({
          ...provider,
          branchIds: branchAssignments.map(({ branchId }) => branchId),
          serviceIds: services.map(({ serviceId }) => serviceId),
        })),
        rooms: roomRows.map(({ compatibleServices, ...room }) => ({
          ...room,
          serviceIds: compatibleServices.map(({ serviceId }) => serviceId),
        })),
        services: serviceRows.map(({ branches: serviceBranches, ...service }) => ({
          ...service,
          branchIds: serviceBranches.map(({ branchId }) => branchId),
          branchConfigurations: serviceBranches,
        })),
      };
    });
  }

  async listOperationalRooms(
    access: TenantAccessSnapshot,
    filters: Readonly<{ branchId?: string | undefined; serviceId?: string | undefined }> = {},
  ) {
    const scope = requirePermissionScope(access, "resources.read");
    if (
      scope === "ASSIGNED_BRANCHES" &&
      filters.branchId &&
      !access.assignedBranchIds.includes(filters.branchId)
    ) {
      throw new DomainError({ code: "FORBIDDEN", message: "Branch access is not granted." });
    }
    return this.runWithAccess(access, async (transaction) => {
      const rooms = await transaction.resource.findMany({
        include: {
          compatibleServices: { select: { serviceId: true } },
          roomOccupancies: {
            include: {
              appointment: {
                select: {
                  customer: { select: { displayName: true } },
                  id: true,
                  providerId: true,
                  status: true,
                },
              },
            },
            orderBy: { claimedAt: "asc" },
            where: { releasedAt: null },
          },
        },
        orderBy: [{ nameEn: "asc" }, { id: "asc" }],
        where: {
          ...(access.activeBranchId
            ? { branchId: access.activeBranchId }
            : filters.branchId
              ? { branchId: filters.branchId }
              : {}),
          ...(filters.serviceId
            ? { compatibleServices: { some: { serviceId: filters.serviceId } } }
            : {}),
          ...(scope === "ASSIGNED_BRANCHES"
            ? { branchId: { in: [...access.assignedBranchIds] } }
            : {}),
          group: { kind: "ROOM" },
          organizationId: access.organizationId,
        },
      });
      return rooms.map((room) => ({
        ...room,
        availableCapacity:
          room.status === "ACTIVE" ? Math.max(0, room.capacity - room.roomOccupancies.length) : 0,
        serviceIds: room.compatibleServices.map(({ serviceId }) => serviceId),
      }));
    });
  }

  async createAppointment(
    access: TenantAccessSnapshot,
    input: AppointmentCreateInput,
    details?: RequestAuditDetails,
  ) {
    requireResourcePermission(access, "appointments.create", input);
    const appointmentId = randomUUID();
    return this.runWithAccess(access, async (transaction) => {
      const configuredStatus = input.status
        ? input.status
        : await transaction.organizationSettings
            .findUnique({
              select: { defaultAppointmentStatus: true },
              where: { organizationId: access.organizationId },
            })
            .then((settings) => settings?.defaultAppointmentStatus ?? AppointmentStatus.PENDING);
      const status = configuredStatus === AppointmentStatus.CONFIRMED ? "CONFIRMED" : "PENDING";
      const reservation = await reserveIdempotency(transaction, access, {
        appointmentId,
        key: input.idempotencyKey,
        operation: "CREATE",
        payload: { ...input, status },
      });
      if (reservation.replayed) {
        const prior = await transaction.appointment.findFirst({
          where: { id: reservation.appointmentId, organizationId: access.organizationId },
        });
        if (!prior) {
          throw conflict("The prior appointment request did not complete.");
        }
        return prior;
      }
      const appointment = await createAppointmentRows(transaction, {
        actorUserId: access.actorUserId,
        appointmentId,
        branchId: input.branchId,
        customerId: input.customerId,
        organizationId: access.organizationId,
        providerId: input.providerId,
        selectedRoomId: input.roomId,
        serviceId: input.serviceId,
        source: input.source ?? AppointmentSource.STAFF,
        startsAtLocal: input.startsAtLocal,
        status: status as AppointmentStatus,
      });
      if (status === "CONFIRMED") {
        await reserveStockForConfirmedAppointment(transaction, access, appointment.id);
      }
      await createAuditEvent(
        transaction,
        access,
        "APPOINTMENT_CREATED",
        "Appointment",
        appointment.id,
        details,
      );
      return appointment;
    });
  }

  async listAppointments(access: TenantAccessSnapshot, filters: AppointmentFilters = {}) {
    const accessFilter = resourceWhere(access, "appointments.read");
    return this.runWithAccess(access, async (transaction) => {
      const scope = requirePermissionScope(access, "appointments.read");
      if (
        scope === "ASSIGNED_BRANCHES" &&
        filters.branchId &&
        !access.assignedBranchIds.includes(filters.branchId)
      ) {
        throw new DomainError({ code: "FORBIDDEN", message: "Branch access is not granted." });
      }
      if (scope === "SELF" && filters.providerId && filters.providerId !== access.staffProfileId) {
        throw new DomainError({ code: "FORBIDDEN", message: "Provider access is not granted." });
      }
      let dayRange: Readonly<{ endsAt: Date; startsAt: Date }> | undefined;
      if (filters.day || filters.dateFrom || filters.dateTo) {
        const timezone = filters.branchId
          ? await transaction.branch
              .findFirst({
                select: { timezone: true },
                where: { id: filters.branchId, organizationId: access.organizationId },
              })
              .then((branch) => branch?.timezone)
          : await transaction.organizationSettings
              .findFirst({
                select: { timezone: true },
                where: { organizationId: access.organizationId },
              })
              .then((settings) => settings?.timezone ?? "Asia/Amman");
        if (!timezone) {
          throw new DomainError({ code: "NOT_FOUND", message: "Branch not found." });
        }
        const rangeDay = filters.day ?? filters.dateFrom ?? filters.dateTo;
        if (!rangeDay) {
          throw new DomainError({ code: "VALIDATION_FAILED", message: "Invalid date range." });
        }
        const from = utcRangeForLocalDate(filters.day ?? filters.dateFrom ?? rangeDay, timezone);
        const to = utcRangeForLocalDate(filters.day ?? filters.dateTo ?? rangeDay, timezone);
        if (from.startsAt > to.startsAt) {
          throw new DomainError({ code: "VALIDATION_FAILED", message: "Invalid date range." });
        }
        dayRange = { endsAt: to.endsAt, startsAt: from.startsAt };
      }
      const appointments = await transaction.appointment.findMany({
        include: {
          branch: { select: { id: true, nameAr: true, nameEn: true, timezone: true } },
          createdBy: { select: { name: true } },
          customer: {
            select: {
              contacts: {
                select: { kind: true, normalizedPhoneE164: true, originalValue: true },
                where: { isPrimary: true },
              },
              displayName: true,
              id: true,
              preferredLocale: true,
            },
          },
          messages: {
            orderBy: { createdAt: "desc" },
            select: { channel: true, status: true },
            take: 1,
          },
          actualProvider: { select: { displayNameAr: true, displayNameEn: true, id: true } },
          actualRoom: {
            select: {
              compatibleServices: { select: { serviceId: true } },
              id: true,
              nameAr: true,
              nameEn: true,
              status: true,
            },
          },
          provider: {
            select: { displayNameAr: true, displayNameEn: true, id: true, isDoctor: true },
          },
          room: { select: { id: true, nameAr: true, nameEn: true, status: true } },
          roomOccupancies: {
            include: {
              resource: { select: { id: true, nameAr: true, nameEn: true, status: true } },
            },
            orderBy: { claimedAt: "desc" },
          },
          resourceReservations: {
            select: {
              id: true,
              resource: { select: { nameAr: true, nameEn: true, status: true } },
              resourceGroupId: true,
              resourceId: true,
            },
          },
          service: {
            select: {
              currency: true,
              defaultPriceMinor: true,
              id: true,
              nameAr: true,
              nameEn: true,
            },
          },
        },
        orderBy: [
          { startsAt: "asc" },
          { provider: { displayNameEn: "asc" } },
          { createdAt: "asc" },
        ],
        where: {
          AND: [
            accessFilter,
            ...(filters.q?.trim()
              ? [
                  {
                    OR: [
                      {
                        referenceCode: { contains: filters.q.trim(), mode: "insensitive" as const },
                      },
                      {
                        customer: {
                          is: {
                            OR: [
                              {
                                displayName: {
                                  contains: filters.q.trim(),
                                  mode: "insensitive" as const,
                                },
                              },
                              {
                                contacts: {
                                  some: { originalValue: { contains: filters.q.trim() } },
                                },
                              },
                            ],
                          },
                        },
                      },
                    ],
                  },
                ]
              : []),
          ],
          ...(filters.branchId ? { branchId: filters.branchId } : {}),
          ...(filters.providerId ? { providerId: filters.providerId } : {}),
          ...(filters.resourceId
            ? {
                OR: [
                  { actualRoomId: filters.resourceId },
                  { roomId: filters.resourceId },
                  { resourceReservations: { some: { resourceId: filters.resourceId } } },
                ],
              }
            : {}),
          ...(filters.serviceId ? { serviceId: filters.serviceId } : {}),
          ...(filters.source ? { source: filters.source } : {}),
          ...(filters.status ? { status: filters.status } : {}),
          ...(dayRange ? { startsAt: { gte: dayRange.startsAt, lt: dayRange.endsAt } } : {}),
          organizationId: access.organizationId,
        },
      });
      const requirements = await transaction.serviceResourceRequirement.findMany({
        select: { branchId: true, quantity: true, serviceId: true },
        where: {
          OR: appointments.map(({ branchId, serviceId }) => ({ branchId, serviceId })),
          organizationId: access.organizationId,
        },
      });
      const requiredByServiceBranch = new Map<string, number>();
      for (const requirement of requirements) {
        const key = `${requirement.branchId}:${requirement.serviceId}`;
        requiredByServiceBranch.set(
          key,
          (requiredByServiceBranch.get(key) ?? 0) + requirement.quantity,
        );
      }
      return appointments.map((appointment) => {
        const required =
          requiredByServiceBranch.get(`${appointment.branchId}:${appointment.serviceId}`) ?? 0;
        const released = ["COMPLETED", "CANCELLED", "NO_SHOW"].includes(appointment.status);
        return {
          ...appointment,
          conflictIndicator: released
            ? ("RELEASED" as const)
            : appointment.resourceReservations.length >= required
              ? ("PROTECTED" as const)
              : ("MISSING_RESOURCE" as const),
          requiredResourceCount: required,
        };
      });
    });
  }

  async getAppointment(access: TenantAccessSnapshot, appointmentId: string) {
    const accessFilter = resourceWhere(access, "appointments.read");
    return this.runWithAccess(access, async (transaction) => {
      const appointment = await transaction.appointment.findFirst({
        include: {
          actualProvider: { select: { displayNameAr: true, displayNameEn: true, id: true } },
          actualRoom: {
            select: {
              compatibleServices: { select: { serviceId: true } },
              id: true,
              nameAr: true,
              nameEn: true,
              status: true,
            },
          },
          branch: { select: { id: true, nameAr: true, nameEn: true, timezone: true } },
          createdBy: { select: { name: true } },
          customer: {
            select: {
              contacts: { select: { kind: true, originalValue: true }, where: { isPrimary: true } },
              displayName: true,
              id: true,
              preferredLocale: true,
            },
          },
          history: {
            include: { actor: { select: { name: true } } },
            orderBy: { createdAt: "desc" },
          },
          provider: {
            select: {
              displayNameAr: true,
              displayNameEn: true,
              id: true,
              services: {
                select: { serviceId: true },
                where: { isEnabled: true },
              },
            },
          },
          room: {
            select: {
              compatibleServices: { select: { serviceId: true } },
              id: true,
              nameAr: true,
              nameEn: true,
            },
          },
          roomOccupancies: {
            include: {
              claimedBy: { select: { name: true } },
              releasedBy: { select: { name: true } },
              resource: { select: { id: true, nameAr: true, nameEn: true, status: true } },
            },
            orderBy: { claimedAt: "desc" },
          },
          resourceReservations: {
            include: { resource: { select: { nameAr: true, nameEn: true, status: true } } },
          },
          service: {
            select: {
              currency: true,
              defaultPriceMinor: true,
              id: true,
              nameAr: true,
              nameEn: true,
              postTreatmentInstructionsAr: true,
              postTreatmentInstructionsEn: true,
              preTreatmentInstructionsAr: true,
              preTreatmentInstructionsEn: true,
            },
          },
        },
        where: { ...accessFilter, id: appointmentId, organizationId: access.organizationId },
      });
      if (!appointment) {
        throw new DomainError({ code: "NOT_FOUND", message: "Appointment not found." });
      }
      const operationalEvents = await transaction.outboxEvent.findMany({
        orderBy: { createdAt: "desc" },
        select: {
          createdAt: true,
          eventType: true,
          payload: true,
          processedAt: true,
          status: true,
        },
        where: {
          aggregateId: appointment.id,
          aggregateType: "Appointment",
          eventType: {
            in: [
              "APPOINTMENT_CANCELLED",
              "APPOINTMENT_COMPLETED",
              "APPOINTMENT_CONFIRMED",
              "PATIENT_CALLED_TO_ROOM",
            ],
          },
          organizationId: access.organizationId,
        },
      });
      return { ...appointment, operationalEvents };
    });
  }

  async getAppointmentOperationalDetail(access: TenantAccessSnapshot, appointmentId: string) {
    return this.runWithAccess(access, async (transaction) => {
      const basic = await transaction.appointment.findFirst({
        select: { branchId: true, id: true, providerId: true },
        where: { id: appointmentId, organizationId: access.organizationId },
      });
      if (!basic) {
        throw new DomainError({ code: "NOT_FOUND", message: "Appointment not found." });
      }
      requireResourcePermission(access, "appointment_records.read", basic);
      return transaction.appointment.findFirstOrThrow({
        include: {
          notes: {
            include: { author: { select: { email: true, id: true, name: true } } },
            orderBy: { createdAt: "desc" },
          },
          record: true,
        },
        where: { id: basic.id, organizationId: access.organizationId },
      });
    });
  }

  async listAppointmentAudit(access: TenantAccessSnapshot, appointmentId: string) {
    const accessFilter = resourceWhere(access, "audit.read");
    return this.runWithAccess(access, async (transaction) => {
      const appointment = await transaction.appointment.findFirst({
        select: { id: true },
        where: { ...accessFilter, id: appointmentId, organizationId: access.organizationId },
      });
      if (!appointment)
        throw new DomainError({ code: "NOT_FOUND", message: "Appointment not found." });
      await createAuditEvent(
        transaction,
        access,
        "APPOINTMENT_AUDIT_VIEWED",
        "Appointment",
        appointment.id,
      );
      return transaction.auditEvent.findMany({
        include: { actor: { select: { name: true } } },
        orderBy: { createdAt: "desc" },
        take: 100,
        where: {
          organizationId: access.organizationId,
          targetId: appointment.id,
          targetType: "Appointment",
        },
      });
    });
  }

  /** This intentionally never selects internal notes or operational records. */
  async getPublicAppointmentProjection(access: TenantAccessSnapshot, appointmentId: string) {
    const accessFilter = resourceWhere(access, "appointments.read");
    return this.runWithAccess(access, async (transaction) => {
      const appointment = await transaction.appointment.findFirst({
        select: {
          branch: { select: { nameAr: true, nameEn: true, timezone: true } },
          customer: { select: { displayName: true } },
          endsAt: true,
          id: true,
          provider: { select: { displayNameAr: true, displayNameEn: true } },
          service: { select: { nameAr: true, nameEn: true } },
          startsAt: true,
          status: true,
        },
        where: { ...accessFilter, id: appointmentId, organizationId: access.organizationId },
      });
      if (!appointment) {
        throw new DomainError({ code: "NOT_FOUND", message: "Appointment not found." });
      }
      return appointment;
    });
  }

  async rescheduleAppointment(
    access: TenantAccessSnapshot,
    input: AppointmentRescheduleInput,
    details?: RequestAuditDetails,
  ) {
    assertExpectedVersion(input.expectedVersion);
    return this.runWithAccess(access, async (transaction) => {
      const current = await transaction.appointment.findFirst({
        where: { id: input.appointmentId, organizationId: access.organizationId },
      });
      if (!current) {
        throw new DomainError({ code: "NOT_FOUND", message: "Appointment not found." });
      }
      requireResourcePermission(access, "appointment.reschedule", current);
      if (!canRescheduleAppointment(asAppointmentStatus(current.status))) {
        throw conflict("Only pending or confirmed appointments can be rescheduled.");
      }
      const idempotency = await reserveIdempotency(transaction, access, {
        appointmentId: current.id,
        key: input.idempotencyKey,
        operation: "RESCHEDULE",
        payload: input,
      });
      if (idempotency.replayed) {
        return current;
      }
      const appointment = await rescheduleAppointmentRows(transaction, {
        actorUserId: access.actorUserId,
        appointmentId: current.id,
        expectedVersion: input.expectedVersion,
        organizationId: access.organizationId,
        startsAtLocal: input.startsAtLocal,
      });
      await createAuditEvent(
        transaction,
        access,
        "APPOINTMENT_RESCHEDULED",
        "Appointment",
        current.id,
        details,
      );
      return appointment;
    });
  }

  async callAppointmentToRoom(
    access: TenantAccessSnapshot,
    input: AppointmentRoomOperationInput,
    details?: RequestAuditDetails,
  ) {
    assertExpectedVersion(input.expectedVersion);
    return this.runWithAccess(access, async (transaction) => {
      await lockAppointmentRow(transaction, access.organizationId, input.appointmentId);
      const current = await transaction.appointment.findFirst({
        include: {
          branch: { select: { timezone: true } },
          provider: {
            include: {
              availabilityRules: true,
              timeOffEntries: true,
            },
          },
        },
        where: { id: input.appointmentId, organizationId: access.organizationId },
      });
      if (!current) throw new DomainError({ code: "NOT_FOUND", message: "Appointment not found." });
      requireResourcePermission(access, "appointment.callToRoom", current);
      requireResourcePermission(access, "room.occupancy.claim", current);
      if (input.asNext) {
        requireResourcePermission(access, "doctor.queue.next", current);
        const currentDayRange = utcRangeForLocalDate(
          localDateForInstant(new Date(), current.branch.timezone),
          current.branch.timezone,
        );
        if (
          current.startsAt < currentDayRange.startsAt ||
          current.startsAt >= currentDayRange.endsAt
        ) {
          throw conflict("Only today's appointments can be called from the Doctor queue.");
        }
        const next = await transaction.appointment.findFirst({
          orderBy: [{ startsAt: "asc" }, { checkedInAt: "asc" }, { createdAt: "asc" }],
          select: { id: true },
          where: {
            branchId: current.branchId,
            organizationId: access.organizationId,
            providerId: current.providerId,
            startsAt: { gte: currentDayRange.startsAt, lt: currentDayRange.endsAt },
            status: AppointmentStatus.CHECKED_IN,
          },
        });
        if (next?.id !== current.id) {
          throw conflict("The Doctor queue changed. Review the next eligible appointment.");
        }
        const activeService = await transaction.appointment.findFirst({
          select: { id: true },
          where: {
            id: { not: current.id },
            organizationId: access.organizationId,
            providerId: current.providerId,
            status: { in: [AppointmentStatus.CALLED, AppointmentStatus.IN_PROGRESS] },
          },
        });
        if (activeService) {
          throw conflict("The Doctor already has an active Called or In Service appointment.");
        }
      }
      if (!current.provider.isDoctor || !current.provider.isActive) {
        throw conflict("The assigned Doctor is not available for room calling.");
      }
      if (input.asNext) {
        const localDay = localDateForInstant(new Date(), current.branch.timezone);
        const dayRange = utcRangeForLocalDate(localDay, current.branch.timezone);
        const weekday = [
          "SUNDAY",
          "MONDAY",
          "TUESDAY",
          "WEDNESDAY",
          "THURSDAY",
          "FRIDAY",
          "SATURDAY",
        ][new Date(`${localDay}T00:00:00Z`).getUTCDay()];
        const scheduled = current.provider.availabilityRules.some(
          (rule) =>
            rule.weekday === weekday &&
            (rule.branchId === null || rule.branchId === current.branchId),
        );
        const onLeave = current.provider.timeOffEntries.some(
          (entry) =>
            entry.startsAt < dayRange.endsAt &&
            entry.endsAt > dayRange.startsAt &&
            (entry.branchId === null || entry.branchId === current.branchId),
        );
        if (!scheduled || onLeave) {
          throw conflict("The assigned Doctor is not working at this branch today.");
        }
      }
      const idempotency = await reserveIdempotency(transaction, access, {
        appointmentId: current.id,
        key: input.idempotencyKey,
        operation: "CALL_TO_ROOM",
        payload: input,
      });
      if (idempotency.replayed) return current;
      assertAppointmentTransition(asAppointmentStatus(current.status), "CALLED");
      if (current.version !== input.expectedVersion) {
        throw conflict("Appointment changed by another user. Refresh and try again.");
      }
      const occupancy = await claimOperationalRoom(transaction, access, current, input.roomId);
      const occurredAt = new Date();
      const changed = await transaction.appointment.updateMany({
        data: {
          actualRoomId: occupancy.resourceId,
          calledAt: occurredAt,
          calledByUserId: access.actorUserId,
          status: AppointmentStatus.CALLED,
          version: { increment: 1 },
        },
        where: {
          id: current.id,
          organizationId: access.organizationId,
          status: AppointmentStatus.CHECKED_IN,
          version: input.expectedVersion,
        },
      });
      if (changed.count !== 1) {
        throw conflict("Appointment changed by another user. Refresh and try again.");
      }
      const nextVersion = input.expectedVersion + 1;
      await transaction.appointmentStatusHistory.create({
        data: {
          actorUserId: access.actorUserId,
          appointmentId: current.id,
          endsAt: current.endsAt,
          eventType: AppointmentHistoryType.STATUS_CHANGED,
          fromStatus: current.status,
          organizationId: access.organizationId,
          reason: `Called to room ${occupancy.resource.id}.`,
          source: current.source,
          startsAt: current.startsAt,
          toStatus: AppointmentStatus.CALLED,
          transitionSource: AppointmentTransitionSource.STAFF_UI,
          version: nextVersion,
        },
      });
      await createAuditEvent(
        transaction,
        access,
        "PATIENT_CALLED_TO_ROOM",
        "Appointment",
        current.id,
        details,
        `Room ${occupancy.resource.id}`,
      );
      const updated = await transaction.appointment.findFirstOrThrow({
        where: { id: current.id, organizationId: access.organizationId },
      });
      await createAppointmentNotifications(transaction, updated, AppointmentStatus.CALLED);
      await queueOperationalEvent(transaction, updated, "PATIENT_CALLED_TO_ROOM", {
        appointmentId: current.id,
        communicationMode: "SIMULATED",
        messageAr: `يرجى التوجه إلى الغرفة ${occupancy.resource.nameAr} لبدء الخدمة.`,
        messageEn: `Please go to Room ${occupancy.resource.nameEn} to start your service.`,
        roomId: occupancy.resourceId,
      });
      return updated;
    });
  }

  async changeAppointmentRoom(
    access: TenantAccessSnapshot,
    input: AppointmentRoomOperationInput,
    details?: RequestAuditDetails,
  ) {
    assertExpectedVersion(input.expectedVersion);
    return this.runWithAccess(access, async (transaction) => {
      await lockAppointmentRow(transaction, access.organizationId, input.appointmentId);
      const current = await transaction.appointment.findFirst({
        where: { id: input.appointmentId, organizationId: access.organizationId },
      });
      if (!current) throw new DomainError({ code: "NOT_FOUND", message: "Appointment not found." });
      requireResourcePermission(access, "room.assignment.change", current);
      requireResourcePermission(access, "room.occupancy.release", current);
      requireResourcePermission(access, "room.occupancy.claim", current);
      if (current.status !== AppointmentStatus.CALLED) {
        throw conflict("Only a Called appointment can change rooms.");
      }
      const idempotency = await reserveIdempotency(transaction, access, {
        appointmentId: current.id,
        key: input.idempotencyKey,
        operation: "CHANGE_ROOM",
        payload: input,
      });
      if (idempotency.replayed) return current;
      if (current.version !== input.expectedVersion) {
        throw conflict("Appointment changed by another user. Refresh and try again.");
      }
      const activeOccupancy = await transaction.roomOccupancy.findFirst({
        where: {
          appointmentId: current.id,
          organizationId: access.organizationId,
          releasedAt: null,
        },
      });
      if (!activeOccupancy) throw conflict("The appointment has no active room claim.");
      if (activeOccupancy.resourceId === input.roomId) {
        throw new DomainError({ code: "VALIDATION_FAILED", message: "Select a different room." });
      }
      await lockRoomRows(transaction, access.organizationId, [
        activeOccupancy.resourceId,
        input.roomId,
      ]);
      const occurredAt = new Date();
      await transaction.roomOccupancy.update({
        data: {
          releaseReason: "ROOM_CHANGED",
          releasedAt: occurredAt,
          releasedByUserId: access.actorUserId,
        },
        where: { id: activeOccupancy.id },
      });
      const occupancy = await claimOperationalRoom(
        transaction,
        access,
        current,
        input.roomId,
        true,
      );
      const changed = await transaction.appointment.updateMany({
        data: { actualRoomId: occupancy.resourceId, version: { increment: 1 } },
        where: {
          id: current.id,
          organizationId: access.organizationId,
          status: AppointmentStatus.CALLED,
          version: input.expectedVersion,
        },
      });
      if (changed.count !== 1) throw conflict("Appointment changed by another user.");
      const nextVersion = input.expectedVersion + 1;
      await transaction.appointmentStatusHistory.create({
        data: {
          actorUserId: access.actorUserId,
          appointmentId: current.id,
          endsAt: current.endsAt,
          eventType: AppointmentHistoryType.ROOM_CHANGED,
          fromStatus: current.status,
          organizationId: access.organizationId,
          reason: `Room changed from ${activeOccupancy.resourceId} to ${occupancy.resourceId}.`,
          source: current.source,
          startsAt: current.startsAt,
          toStatus: current.status,
          transitionSource: AppointmentTransitionSource.STAFF_UI,
          version: nextVersion,
        },
      });
      await createAuditEvent(
        transaction,
        access,
        "APPOINTMENT_ROOM_CHANGED",
        "Appointment",
        current.id,
        details,
        `Room changed from ${activeOccupancy.resourceId} to ${occupancy.resourceId}.`,
      );
      const updated = await transaction.appointment.findFirstOrThrow({
        where: { id: current.id, organizationId: access.organizationId },
      });
      await queueOperationalEvent(transaction, updated, "PATIENT_CALLED_TO_ROOM", {
        appointmentId: current.id,
        communicationMode: "SIMULATED",
        messageAr: `يرجى التوجه إلى الغرفة ${occupancy.resource.nameAr} لبدء الخدمة.`,
        messageEn: `Please go to Room ${occupancy.resource.nameEn} to start your service.`,
        roomChanged: true,
        roomId: occupancy.resourceId,
      });
      return updated;
    });
  }

  async resendRoomMessage(
    access: TenantAccessSnapshot,
    input: Omit<AppointmentRoomOperationInput, "asNext" | "roomId">,
    details?: RequestAuditDetails,
  ) {
    assertExpectedVersion(input.expectedVersion);
    return this.runWithAccess(access, async (transaction) => {
      await lockAppointmentRow(transaction, access.organizationId, input.appointmentId);
      const current = await transaction.appointment.findFirst({
        where: { id: input.appointmentId, organizationId: access.organizationId },
      });
      if (!current) throw new DomainError({ code: "NOT_FOUND", message: "Appointment not found." });
      requireResourcePermission(access, "appointment.callToRoom", current);
      if (
        current.status !== AppointmentStatus.CALLED ||
        current.version !== input.expectedVersion
      ) {
        throw conflict("Only the current Called appointment can receive another room message.");
      }
      const reservation = await reserveIdempotency(transaction, access, {
        appointmentId: current.id,
        key: input.idempotencyKey,
        operation: "RESEND_ROOM_MESSAGE",
        payload: input,
      });
      if (reservation.replayed) return current;
      const occupancy = await transaction.roomOccupancy.findFirst({
        include: { resource: { select: { nameAr: true, nameEn: true } } },
        where: {
          appointmentId: current.id,
          organizationId: access.organizationId,
          releasedAt: null,
        },
      });
      if (!occupancy) throw conflict("The appointment has no active room claim.");
      await createAuditEvent(
        transaction,
        access,
        "PATIENT_ROOM_MESSAGE_SENT_AGAIN",
        "Appointment",
        current.id,
        details,
      );
      await queueOperationalEvent(
        transaction,
        current,
        "PATIENT_CALLED_TO_ROOM",
        {
          appointmentId: current.id,
          communicationMode: "SIMULATED",
          messageAr: `يرجى التوجه إلى الغرفة ${occupancy.resource.nameAr} لبدء الخدمة.`,
          messageEn: `Please go to Room ${occupancy.resource.nameEn} to start your service.`,
          resent: true,
          roomId: occupancy.resourceId,
        },
        `resend:${input.idempotencyKey ?? randomUUID()}`,
      );
      return current;
    });
  }

  async startAppointmentService(
    access: TenantAccessSnapshot,
    input: AppointmentStartServiceInput,
    details?: RequestAuditDetails,
  ) {
    assertExpectedVersion(input.expectedVersion);
    return this.runWithAccess(access, async (transaction) => {
      await lockAppointmentRow(transaction, access.organizationId, input.appointmentId);
      const current = await transaction.appointment.findFirst({
        where: { id: input.appointmentId, organizationId: access.organizationId },
      });
      if (!current) throw new DomainError({ code: "NOT_FOUND", message: "Appointment not found." });
      requireResourcePermission(access, "appointment.startService", current);
      if (input.includeCheckIn) requireResourcePermission(access, "appointment.checkIn", current);
      requireResourcePermission(access, "room.occupancy.claim", current);
      const statuses: readonly AppointmentStatusValue[] = input.includeCheckIn
        ? ["CHECKED_IN", "IN_PROGRESS"]
        : ["IN_PROGRESS"];
      let previousStatus = asAppointmentStatus(current.status);
      for (const status of statuses) {
        assertAppointmentTransition(previousStatus, status);
        previousStatus = status;
      }
      if (current.version !== input.expectedVersion)
        throw conflict("Appointment changed by another user.");
      const idempotency = await reserveIdempotency(transaction, access, {
        appointmentId: current.id,
        key: input.idempotencyKey,
        operation: input.includeCheckIn ? "CHECK_IN_AND_START" : "START_SERVICE",
        payload: input,
      });
      if (idempotency.replayed) return current;
      const selectedRoomId = input.roomId ?? current.roomId ?? undefined;
      let occupancy = await transaction.roomOccupancy.findFirst({
        include: { resource: { select: { id: true } } },
        where: {
          appointmentId: current.id,
          organizationId: access.organizationId,
          releasedAt: null,
        },
      });
      if (!occupancy) {
        if (!selectedRoomId)
          throw conflict("Select an available compatible room before starting service.");
        occupancy = await claimOperationalRoom(transaction, access, current, selectedRoomId);
      } else if (selectedRoomId && occupancy.resourceId !== selectedRoomId) {
        throw conflict("The appointment already occupies a different room.");
      }
      const occurredAt = new Date();
      const changed = await transaction.appointment.updateMany({
        data: {
          actualProviderId: current.providerId,
          actualRoomId: occupancy.resourceId,
          checkedInAt: input.includeCheckIn ? occurredAt : current.checkedInAt,
          checkedInByUserId: input.includeCheckIn ? access.actorUserId : current.checkedInByUserId,
          serviceStartedAt: occurredAt,
          serviceStartedByUserId: access.actorUserId,
          status: AppointmentStatus.IN_PROGRESS,
          version: { increment: statuses.length },
        },
        where: {
          id: current.id,
          organizationId: access.organizationId,
          status: current.status,
          version: input.expectedVersion,
        },
      });
      if (changed.count !== 1) throw conflict("Appointment changed by another user.");
      let fromStatus = current.status;
      for (const [index, toStatus] of statuses.entries()) {
        await transaction.appointmentStatusHistory.create({
          data: {
            actorUserId: access.actorUserId,
            appointmentId: current.id,
            endsAt: current.endsAt,
            eventType: AppointmentHistoryType.STATUS_CHANGED,
            fromStatus,
            organizationId: access.organizationId,
            source: current.source,
            startsAt: current.startsAt,
            toStatus: toStatus as AppointmentStatus,
            transitionSource: AppointmentTransitionSource.STAFF_UI,
            version: input.expectedVersion + index + 1,
          },
        });
        await createAuditEvent(
          transaction,
          access,
          `APPOINTMENT_${toStatus}`,
          "Appointment",
          current.id,
          details,
        );
        fromStatus = toStatus as AppointmentStatus;
      }
      return transaction.appointment.findFirstOrThrow({
        where: { id: current.id, organizationId: access.organizationId },
      });
    });
  }

  async changeAppointmentService(
    access: TenantAccessSnapshot,
    input: AppointmentChangeServiceInput,
    details?: RequestAuditDetails,
  ) {
    assertExpectedVersion(input.expectedVersion);
    const reason = input.reason?.trim() || undefined;
    if (reason && reason.length > 500) {
      throw new DomainError({ code: "VALIDATION_FAILED", message: "Reason is too long." });
    }
    return this.runWithAccess(access, async (transaction) => {
      await lockAppointmentRow(transaction, access.organizationId, input.appointmentId);
      const current = await transaction.appointment.findFirst({
        where: { id: input.appointmentId, organizationId: access.organizationId },
      });
      if (!current) {
        throw new DomainError({ code: "NOT_FOUND", message: "Appointment not found." });
      }
      requireResourcePermission(access, "appointment.startService", current);
      if (current.status !== AppointmentStatus.IN_PROGRESS) {
        throw conflict("The service can only be changed while the appointment is in progress.");
      }
      if (current.version !== input.expectedVersion) {
        throw conflict("Appointment changed by another user. Refresh and try again.");
      }
      if (current.serviceId === input.serviceId) {
        throw new DomainError({
          code: "VALIDATION_FAILED",
          message: "Select a different service.",
        });
      }
      const idempotency = await reserveIdempotency(transaction, access, {
        appointmentId: current.id,
        key: input.idempotencyKey,
        operation: "CHANGE_SERVICE",
        payload: input,
      });
      if (idempotency.replayed) return current;

      const nextService = await transaction.service.findFirst({
        include: {
          branches: {
            where: { branchId: current.branchId, isEnabled: true },
          },
          resourceRequirements: {
            where: { branchId: current.branchId },
          },
          staffServices: {
            where: { isEnabled: true, staffProfileId: current.providerId },
          },
        },
        where: {
          id: input.serviceId,
          isActive: true,
          organizationId: access.organizationId,
        },
      });
      if (!nextService || nextService.branches.length === 0) {
        throw conflict("The selected service is not enabled at this branch.");
      }
      if (nextService.staffServices.length === 0) {
        throw conflict("The assigned doctor is not configured to perform the selected service.");
      }

      const activeOccupancy = await transaction.roomOccupancy.findFirst({
        include: {
          resource: {
            include: { compatibleServices: { select: { serviceId: true } }, group: true },
          },
        },
        where: {
          appointmentId: current.id,
          organizationId: access.organizationId,
          releasedAt: null,
        },
      });
      if (
        !activeOccupancy ||
        activeOccupancy.resource.status !== "ACTIVE" ||
        !activeOccupancy.resource.compatibleServices.some(
          ({ serviceId }) => serviceId === nextService.id,
        )
      ) {
        throw conflict("The occupied room is not compatible with the selected service.");
      }

      const reservedResources = await transaction.appointmentResource.findMany({
        include: { resource: { select: { status: true } } },
        where: { appointmentId: current.id, organizationId: access.organizationId },
      });
      const resourceCounts = new Map<string, number>();
      for (const reservation of reservedResources) {
        if (reservation.resource.status === "ACTIVE") {
          resourceCounts.set(
            reservation.resourceGroupId,
            (resourceCounts.get(reservation.resourceGroupId) ?? 0) + 1,
          );
        }
      }
      resourceCounts.set(
        activeOccupancy.resource.groupId,
        Math.max(resourceCounts.get(activeOccupancy.resource.groupId) ?? 0, 1),
      );
      for (const requirement of nextService.resourceRequirements) {
        if ((resourceCounts.get(requirement.resourceGroupId) ?? 0) < requirement.quantity) {
          throw conflict(
            "The appointment does not have all resources required by the selected service.",
          );
        }
      }

      await releaseStockReservations(transaction, access, current.id, "SERVICE_CHANGED");
      const changed = await transaction.appointment.updateMany({
        data: { serviceId: nextService.id, version: { increment: 1 } },
        where: {
          id: current.id,
          organizationId: access.organizationId,
          status: AppointmentStatus.IN_PROGRESS,
          version: input.expectedVersion,
        },
      });
      if (changed.count !== 1) throw conflict("Appointment changed by another user.");
      await reserveStockForConfirmedAppointment(transaction, access, current.id);
      const historyReason = (
        reason
          ? `Service changed from ${current.serviceId} to ${nextService.id}. ${reason}`
          : `Service changed from ${current.serviceId} to ${nextService.id}.`
      ).slice(0, 500);
      await transaction.appointmentStatusHistory.create({
        data: {
          actorUserId: access.actorUserId,
          appointmentId: current.id,
          endsAt: current.endsAt,
          eventType: AppointmentHistoryType.SERVICE_CHANGED,
          fromStatus: current.status,
          organizationId: access.organizationId,
          reason: historyReason,
          serviceSnapshotId: nextService.id,
          source: current.source,
          startsAt: current.startsAt,
          toStatus: current.status,
          transitionSource: AppointmentTransitionSource.STAFF_UI,
          version: input.expectedVersion + 1,
        },
      });
      await createAuditEvent(
        transaction,
        access,
        "APPOINTMENT_SERVICE_CHANGED",
        "Appointment",
        current.id,
        details,
        historyReason,
      );
      return transaction.appointment.findFirstOrThrow({
        where: { id: current.id, organizationId: access.organizationId },
      });
    });
  }

  async transitionAppointment(
    access: TenantAccessSnapshot,
    input: AppointmentTransitionInput,
    details?: RequestAuditDetails,
  ) {
    assertExpectedVersion(input.expectedVersion);
    const note = completionNote(input);
    const reason = input.reason?.trim() || undefined;
    const internalNote = input.internalNote?.trim() || undefined;
    if (reason && reason.length > 500) {
      throw new DomainError({ code: "VALIDATION_FAILED", message: "Reason is too long." });
    }
    if (internalNote && internalNote.length > 10_000) {
      throw new DomainError({ code: "VALIDATION_FAILED", message: "Internal note is too long." });
    }
    return this.runWithAccess(access, async (transaction) => {
      const current = await transaction.appointment.findFirst({
        include: { reservation: true },
        where: { id: input.appointmentId, organizationId: access.organizationId },
      });
      if (!current) {
        throw new DomainError({ code: "NOT_FOUND", message: "Appointment not found." });
      }
      // Reauthorize note writes even on an idempotent retry after grants changed.
      if (note || internalNote) {
        requireResourcePermission(access, "appointment_records.write", current);
      }
      const idempotency = await reserveIdempotency(transaction, access, {
        appointmentId: current.id,
        key: input.idempotencyKey,
        operation: `TRANSITION:${input.toStatus}`,
        payload: input,
      });
      if (idempotency.replayed) {
        requireResourcePermission(access, operationPermission(input.toStatus), current);
        return current;
      }
      const permission = operationPermission(input.toStatus);
      requireResourcePermission(access, permission, current);
      assertAppointmentTransition(asAppointmentStatus(current.status), input.toStatus);
      if (input.toStatus === AppointmentStatus.CONFIRMED) {
        assertAppointmentStartsInFuture(current.startsAt);
      }
      if (input.toStatus === "CANCELLED" && !reason) {
        throw new DomainError({ code: "VALIDATION_FAILED", message: "A reason is required." });
      }
      const restoringNoShowReservation =
        current.status === AppointmentStatus.NO_SHOW && input.toStatus === "CHECKED_IN";
      const localParts = restoringNoShowReservation
        ? localDateTimePartsForInstant(current.startsAt, current.timezone)
        : null;
      const restorationBooking = localParts
        ? await prepareBooking(transaction, {
            branchId: current.branchId,
            organizationId: access.organizationId,
            providerId: current.providerId,
            serviceId: current.serviceId,
            startsAtLocal: `${localParts.year.toString().padStart(4, "0")}-${localParts.month
              .toString()
              .padStart(2, "0")}-${localParts.day.toString().padStart(2, "0")}T${localParts.hour
              .toString()
              .padStart(2, "0")}:${localParts.minute.toString().padStart(2, "0")}`,
          })
        : null;
      if (restorationBooking) {
        await assertBookableSchedule(transaction, restorationBooking, current.id);
      }
      if (input.toStatus === "CALLED") {
        throw new DomainError({
          code: "VALIDATION_FAILED",
          message: "Calling a patient requires an explicit compatible room.",
        });
      }
      let activeOccupancy = await transaction.roomOccupancy.findFirst({
        where: {
          appointmentId: current.id,
          organizationId: access.organizationId,
          releasedAt: null,
        },
      });
      if (input.toStatus === "IN_PROGRESS" && !activeOccupancy) {
        requireResourcePermission(access, "room.occupancy.claim", current);
        const selectedRoomId = current.roomId ?? undefined;
        if (!selectedRoomId) {
          throw conflict("A compatible room must be claimed before service starts.");
        }
        activeOccupancy = await claimOperationalRoom(transaction, access, current, selectedRoomId);
      }
      if (["COMPLETED", "CANCELLED", "NO_SHOW"].includes(input.toStatus) && activeOccupancy) {
        requireResourcePermission(access, "room.occupancy.release", current);
      }
      const occurredAt = new Date();
      const changed = await transaction.appointment.updateMany({
        data: {
          actualDurationMins:
            input.toStatus === "COMPLETED" && current.serviceStartedAt
              ? Math.max(
                  0,
                  Math.round((occurredAt.getTime() - current.serviceStartedAt.getTime()) / 60_000),
                )
              : current.actualDurationMins,
          actualProviderId:
            input.toStatus === "IN_PROGRESS" ? current.providerId : current.actualProviderId,
          actualRoomId:
            input.toStatus === "IN_PROGRESS" && activeOccupancy
              ? activeOccupancy.resourceId
              : current.actualRoomId,
          checkedInAt: input.toStatus === "CHECKED_IN" ? occurredAt : current.checkedInAt,
          checkedInByUserId:
            input.toStatus === "CHECKED_IN" ? access.actorUserId : current.checkedInByUserId,
          completedAt: input.toStatus === "COMPLETED" ? occurredAt : current.completedAt,
          completedByUserId:
            input.toStatus === "COMPLETED" ? access.actorUserId : current.completedByUserId,
          confirmedAt: input.toStatus === "CONFIRMED" ? occurredAt : current.confirmedAt,
          confirmedByUserId:
            input.toStatus === "CONFIRMED" ? access.actorUserId : current.confirmedByUserId,
          cancelledAt: input.toStatus === "CANCELLED" ? occurredAt : current.cancelledAt,
          cancelledByUserId:
            input.toStatus === "CANCELLED" ? access.actorUserId : current.cancelledByUserId,
          noShowAt: input.toStatus === "NO_SHOW" ? occurredAt : current.noShowAt,
          noShowByUserId:
            input.toStatus === "NO_SHOW" ? access.actorUserId : current.noShowByUserId,
          serviceStartedAt:
            input.toStatus === "IN_PROGRESS" ? occurredAt : current.serviceStartedAt,
          serviceStartedByUserId:
            input.toStatus === "IN_PROGRESS" ? access.actorUserId : current.serviceStartedByUserId,
          status: input.toStatus as AppointmentStatus,
          version: { increment: 1 },
        },
        where: {
          id: current.id,
          organizationId: access.organizationId,
          status: current.status,
          version: input.expectedVersion,
        },
      });
      if (changed.count !== 1) {
        throw conflict("Appointment changed by another user. Refresh and try again.");
      }
      if (note) {
        // Preserve an earlier author's legacy record; new feedback is append-only.
        await transaction.appointmentRecord.upsert({
          create: {
            appointmentId: current.id,
            authoredByUserId: access.actorUserId,
            details: note.details,
            organizationId: access.organizationId,
            summary: note.summary,
          },
          update: {},
          where: { appointmentId: current.id },
        });
        await transaction.appointmentNote.create({
          data: {
            appointmentId: current.id,
            authorUserId: access.actorUserId,
            body: note.body,
            organizationId: access.organizationId,
          },
        });
        await createAuditEvent(
          transaction,
          access,
          "APPOINTMENT_NOTE_ADDED",
          "Appointment",
          current.id,
          details,
        );
      }
      if (internalNote) {
        await transaction.appointmentNote.create({
          data: {
            appointmentId: current.id,
            authorUserId: access.actorUserId,
            body: internalNote,
            organizationId: access.organizationId,
          },
        });
        await createAuditEvent(
          transaction,
          access,
          "APPOINTMENT_NOTE_ADDED",
          "Appointment",
          current.id,
          details,
        );
      }
      if (["COMPLETED", "CANCELLED", "NO_SHOW"].includes(input.toStatus)) {
        await Promise.all([
          transaction.appointmentStaffReservation.deleteMany({
            where: { appointmentId: current.id, organizationId: access.organizationId },
          }),
          transaction.appointmentResource.deleteMany({
            where: { appointmentId: current.id, organizationId: access.organizationId },
          }),
          transaction.roomOccupancy.updateMany({
            data: {
              releaseReason: input.toStatus,
              releasedAt: occurredAt,
              releasedByUserId: access.actorUserId,
            },
            where: {
              appointmentId: current.id,
              organizationId: access.organizationId,
              releasedAt: null,
            },
          }),
        ]);
      } else if (restoringNoShowReservation && restorationBooking) {
        try {
          await transaction.appointmentStaffReservation.create({
            data: {
              appointmentId: current.id,
              endsAt: restorationBooking.reservationEndsAt,
              organizationId: access.organizationId,
              providerId: current.providerId,
              startsAt: restorationBooking.reservationStartsAt,
            },
          });
          await reserveRequiredResources(transaction, restorationBooking, current.id, current.id);
        } catch (error) {
          if (isPrismaCode(error, "P2010")) {
            throw schedulingConflict("The provider or resource is no longer available.");
          }
          throw error;
        }
      }
      await transaction.appointmentStatusHistory.create({
        data: {
          actorUserId: access.actorUserId,
          appointmentId: current.id,
          endsAt: current.endsAt,
          eventType: AppointmentHistoryType.STATUS_CHANGED,
          fromStatus: current.status,
          organizationId: access.organizationId,
          reason: reason ?? null,
          source: current.source,
          startsAt: current.startsAt,
          toStatus: input.toStatus as AppointmentStatus,
          transitionSource: input.transitionSource ?? AppointmentTransitionSource.STAFF_UI,
          version: input.expectedVersion + 1,
        },
      });
      await createAuditEvent(
        transaction,
        access,
        `APPOINTMENT_${input.toStatus}`,
        "Appointment",
        current.id,
        details,
        reason,
      );
      const updated = await transaction.appointment.findFirstOrThrow({
        where: { id: current.id, organizationId: access.organizationId },
      });
      await createAppointmentNotifications(
        transaction,
        updated,
        input.toStatus as AppointmentStatus,
      );
      if (input.toStatus === "CONFIRMED") {
        await reserveStockForConfirmedAppointment(transaction, access, updated.id);
        await queueOperationalEvent(transaction, updated, "APPOINTMENT_CONFIRMED", {
          appointmentId: updated.id,
          communicationMode: "SIMULATED",
        });
      }
      if (input.toStatus === "COMPLETED") {
        await recordAppointmentConsumption(
          transaction,
          access,
          updated.id,
          input.consumptions,
          details,
        );
        await queueOperationalEvent(transaction, updated, "APPOINTMENT_COMPLETED", {
          appointmentId: updated.id,
          actualDurationMins: updated.actualDurationMins,
        });
      }
      if (input.toStatus === "CANCELLED" || input.toStatus === "NO_SHOW") {
        await releaseStockReservations(transaction, access, updated.id, input.toStatus);
      }
      if (input.toStatus === "CANCELLED" && input.notificationChoice === "SEND") {
        await queueOperationalEvent(transaction, updated, "APPOINTMENT_CANCELLED", {
          appointmentId: updated.id,
          communicationMode: "SIMULATED",
        });
      }
      return updated;
    });
  }

  async transitionAppointmentCombined(
    access: TenantAccessSnapshot,
    input: AppointmentCombinedTransitionInput,
    details?: RequestAuditDetails,
  ) {
    assertExpectedVersion(input.expectedVersion);
    if (input.command === "CHECK_IN_AND_START") {
      return this.startAppointmentService(
        access,
        {
          appointmentId: input.appointmentId,
          expectedVersion: input.expectedVersion,
          idempotencyKey: input.idempotencyKey,
          includeCheckIn: true,
          roomId: input.roomId,
        },
        details,
      );
    }
    const statuses: readonly AppointmentStatusValue[] = ["CONFIRMED", "CHECKED_IN"];
    return this.runWithAccess(access, async (transaction) => {
      const current = await transaction.appointment.findFirst({
        where: { id: input.appointmentId, organizationId: access.organizationId },
      });
      if (!current) {
        throw new DomainError({ code: "NOT_FOUND", message: "Appointment not found." });
      }
      const idempotency = await reserveIdempotency(transaction, access, {
        appointmentId: current.id,
        key: input.idempotencyKey,
        operation: `TRANSITION:${input.command}`,
        payload: input,
      });
      if (idempotency.replayed) {
        requireResourcePermission(access, "appointment.confirm", current);
        requireResourcePermission(access, "appointment.checkIn", current);
        return current;
      }
      requireResourcePermission(access, "appointment.confirm", current);
      requireResourcePermission(access, "appointment.checkIn", current);
      let previousStatus = asAppointmentStatus(current.status);
      for (const status of statuses) {
        assertAppointmentTransition(previousStatus, status);
        previousStatus = status;
      }
      const occurredAt = new Date();
      const changed = await transaction.appointment.updateMany({
        data: {
          checkedInAt: occurredAt,
          checkedInByUserId: access.actorUserId,
          confirmedAt: input.command === "CONFIRM_AND_CHECK_IN" ? occurredAt : current.confirmedAt,
          confirmedByUserId: access.actorUserId,
          status: statuses[1] as AppointmentStatus,
          version: { increment: statuses.length },
        },
        where: {
          id: current.id,
          organizationId: access.organizationId,
          status: current.status,
          version: input.expectedVersion,
        },
      });
      if (changed.count !== 1) {
        throw conflict("Appointment changed by another user. Refresh and try again.");
      }
      let fromStatus = current.status;
      for (const [index, toStatus] of statuses.entries()) {
        await transaction.appointmentStatusHistory.create({
          data: {
            actorUserId: access.actorUserId,
            appointmentId: current.id,
            endsAt: current.endsAt,
            eventType: AppointmentHistoryType.STATUS_CHANGED,
            fromStatus,
            organizationId: access.organizationId,
            source: current.source,
            startsAt: current.startsAt,
            toStatus: toStatus as AppointmentStatus,
            transitionSource: AppointmentTransitionSource.STAFF_UI,
            version: input.expectedVersion + index + 1,
          },
        });
        await createAuditEvent(
          transaction,
          access,
          `APPOINTMENT_${toStatus}`,
          "Appointment",
          current.id,
          details,
        );
        fromStatus = toStatus as AppointmentStatus;
      }
      const updated = await transaction.appointment.findFirstOrThrow({
        where: { id: current.id, organizationId: access.organizationId },
      });
      await queueOperationalEvent(transaction, updated, "APPOINTMENT_CONFIRMED", {
        appointmentId: updated.id,
        communicationMode: "SIMULATED",
      });
      return updated;
    });
  }

  async bulkConfirmAppointments(
    access: TenantAccessSnapshot,
    inputs: readonly AppointmentBulkConfirmInput[],
    details?: RequestAuditDetails,
  ): Promise<readonly AppointmentBulkConfirmResult[]> {
    requirePermissionScope(access, "appointment.bulkConfirm");
    const results: AppointmentBulkConfirmResult[] = [];
    for (const input of inputs) {
      try {
        const selected = await this.runWithAccess(access, (transaction) =>
          transaction.appointment.findFirst({
            select: { branchId: true, id: true, providerId: true },
            where: { id: input.appointmentId, organizationId: access.organizationId },
          }),
        );
        if (!selected) {
          throw new DomainError({ code: "NOT_FOUND", message: "Appointment not found." });
        }
        requireResourcePermission(access, "appointment.bulkConfirm", selected);
        await this.transitionAppointment(
          access,
          {
            appointmentId: input.appointmentId,
            expectedVersion: input.expectedVersion,
            idempotencyKey: randomUUID(),
            toStatus: "CONFIRMED",
          },
          details,
        );
        results.push({ appointmentId: input.appointmentId, succeeded: true });
      } catch (error) {
        results.push({
          appointmentId: input.appointmentId,
          code: error instanceof DomainError ? error.code : "INTERNAL_ERROR",
          succeeded: false,
        });
      }
    }
    return results;
  }

  async addInternalNote(
    access: TenantAccessSnapshot,
    input: Readonly<{ appointmentId: string; body: string }>,
    details?: RequestAuditDetails,
  ) {
    const body = requireTrimmed(input.body, "note", 10_000);
    return this.runWithAccess(access, async (transaction) => {
      const appointment = await transaction.appointment.findFirst({
        select: { branchId: true, id: true, providerId: true },
        where: { id: input.appointmentId, organizationId: access.organizationId },
      });
      if (!appointment) {
        throw new DomainError({ code: "NOT_FOUND", message: "Appointment not found." });
      }
      requireResourcePermission(access, "appointment_records.write", appointment);
      const note = await transaction.appointmentNote.create({
        data: {
          appointmentId: appointment.id,
          authorUserId: access.actorUserId,
          body,
          organizationId: access.organizationId,
        },
      });
      await createAuditEvent(
        transaction,
        access,
        "APPOINTMENT_NOTE_ADDED",
        "Appointment",
        appointment.id,
        details,
      );
      return note;
    });
  }

  async recordPayment(
    access: TenantAccessSnapshot,
    input: Readonly<{
      appointmentId: string;
      amountMinor: number;
      currency?: string | undefined;
      method: "CASH" | "CARD" | "TRANSFER" | "INSURANCE";
      notes?: string | undefined;
      reference?: string | undefined;
      status: "PAID" | "PARTIAL" | "WAIVED";
    }>,
    details?: RequestAuditDetails,
  ) {
    return this.runWithAccess(access, async (transaction) => {
      const appointment = await transaction.appointment.findFirst({
        include: {
          service: {
            select: { currency: true, defaultPriceMinor: true, nameAr: true, nameEn: true },
          },
        },
        where: { id: input.appointmentId, organizationId: access.organizationId },
      });
      if (!appointment) {
        throw new DomainError({ code: "NOT_FOUND", message: "Appointment not found." });
      }
      requireResourcePermission(access, "appointment_records.write", appointment);

      const currency = input.currency || appointment.service.currency || "JOD";
      const paymentData = {
        amountMinor: input.amountMinor,
        currency,
        method: input.method,
        notes: input.notes?.trim() || undefined,
        paidAt: new Date().toISOString(),
        reference: input.reference?.trim() || undefined,
        status: input.status,
        type: "PAYMENT_RECEIPT",
      };
      const noteBody = `[PAYMENT_RECEIPT] ${input.status} | ${(input.amountMinor / 1000).toFixed(3)} ${currency} | ${input.method}${input.reference ? ` | Ref: ${input.reference}` : ""}${input.notes ? `\n${input.notes}` : ""}\n<!--DATA:${JSON.stringify(paymentData)}-->`;

      const note = await transaction.appointmentNote.create({
        data: {
          appointmentId: appointment.id,
          authorUserId: access.actorUserId,
          body: noteBody,
          organizationId: access.organizationId,
        },
      });

      const auditReason = `Payment of ${(input.amountMinor / 1000).toFixed(3)} ${currency} (${input.status}) via ${input.method}`;
      await createAuditEvent(
        transaction,
        access,
        "APPOINTMENT_PAYMENT_RECORDED",
        "Appointment",
        appointment.id,
        details,
        auditReason,
      );

      return note;
    });
  }

  async listTodayOperations(
    access: TenantAccessSnapshot,
    filters: Omit<AppointmentFilters, "day"> = {},
  ) {
    const timezone = await this.runWithAccess(access, async (transaction) => {
      if (filters.branchId) {
        const branch = await transaction.branch.findFirst({
          select: { timezone: true },
          where: { id: filters.branchId, organizationId: access.organizationId },
        });
        if (!branch) {
          throw new DomainError({ code: "NOT_FOUND", message: "Branch not found." });
        }
        return branch.timezone;
      }
      const settings = await transaction.organizationSettings.findFirst({
        select: { timezone: true },
        where: { organizationId: access.organizationId },
      });
      return settings?.timezone ?? "Asia/Amman";
    });
    return this.listAppointments(access, {
      ...filters,
      day: localDateForInstant(new Date(), timezone),
    });
  }

  private async findLikelyDuplicatesInTransaction(
    transaction: TenantTransaction,
    organizationId: string,
    input: Readonly<{
      displayName: string;
      normalizedPhone: string | null;
      omitCustomerId: string;
    }>,
  ) {
    const duplicateWhere: Prisma.CustomerWhereInput = {
      id: { not: input.omitCustomerId },
      organizationId,
      OR: [
        { displayName: { equals: input.displayName, mode: "insensitive" } },
        ...(input.normalizedPhone
          ? [{ contacts: { some: { normalizedPhoneE164: input.normalizedPhone } } }]
          : []),
      ],
    };
    return transaction.customer.findMany({
      include: { contacts: { select: { normalizedPhoneE164: true, originalValue: true } } },
      orderBy: { displayName: "asc" },
      take: 10,
      where: duplicateWhere,
    });
  }
}
