import { randomUUID } from "node:crypto";

import { DomainError } from "@jormall/domain/errors";
import { assertBranchCanBeDeleted } from "@jormall/domain/branch-policy";
import {
  defaultRolePermissions,
  isPermissionCode,
  permissionCodes,
  type PermissionCode,
  type PermissionScope,
  type TenantAccessSnapshot,
  type TenantRoleKey,
} from "@jormall/domain/identity";

import {
  BusinessSector,
  ConfigurationApprovalStatus,
  InvitationStatus,
  MembershipStatus,
  OrganizationStatus,
  PlatformRole,
  type Prisma,
  type PrismaClient,
  type SupportedLocale,
} from "./generated/prisma/client";
import { createCommunicationDefaults } from "./communication-defaults";
import { createAIFoundationDefaults } from "./ai-defaults";
import { createInvitationToken, hashInvitationToken } from "./invitation-token";
import { createPredictiveDefaults } from "./predictive-defaults";
import { runInTenant, type TenantTransaction } from "./tenant-context";

const permissionLabels: Readonly<Record<PermissionCode, readonly [string, string]>> = {
  "patients.health.read": ["View protected health information", "عرض المعلومات الصحية المحمية"],
  "patients.health.write": [
    "Manage protected health information",
    "إدارة المعلومات الصحية المحمية",
  ],
  "patients.directory.read": ["View patient directory", "عرض دليل المرضى"],
  "patients.profile.read": ["View patient profiles", "عرض ملفات المرضى"],
  "patients.contact.read": ["View patient contact information", "عرض معلومات اتصال المريض"],
  "patients.contact.write": ["Manage patient contact information", "إدارة معلومات اتصال المريض"],
  "patients.doctor_notes.read": ["View protected doctor notes", "عرض ملاحظات الطبيب المحمية"],
  "patients.doctor_notes.write": ["Create protected doctor notes", "إنشاء ملاحظات الطبيب المحمية"],
  "patients.appointments.read": ["View patient appointments", "عرض مواعيد المريض"],
  "doctors.directory.read": ["View doctor directory", "عرض دليل الأطباء"],
  "doctors.profile.read": ["View doctor profiles", "عرض ملفات الأطباء"],
  "doctors.profile.write": ["Manage doctor profiles", "إدارة ملفات الأطباء"],
  "doctors.schedule.read": ["View doctor schedules", "عرض جداول الأطباء"],
  "doctors.schedule.write": ["Manage doctor schedules", "إدارة جداول الأطباء"],
  "doctors.time_off.read": ["View doctor time off", "عرض إجازات الأطباء"],
  "doctors.time_off.write": ["Manage doctor time off", "إدارة إجازات الأطباء"],
  "doctors.services.assign": ["Assign services to doctors", "تعيين الخدمات للأطباء"],
  "doctors.permissions.manage": ["Manage doctor permissions", "إدارة صلاحيات الأطباء"],
  "doctors.appointments.read": ["View doctor appointments", "عرض مواعيد الأطباء"],
  "ai.actions.execute": ["Execute AI gateway actions", "تنفيذ إجراءات بوابة الذكاء الاصطناعي"],
  "ai.configure": ["Configure safe AI", "إعداد الذكاء الاصطناعي الآمن"],
  "audit.read": ["Read audit history", "عرض سجل التدقيق"],
  "appointment_records.read": ["Read appointment records", "عرض سجلات المواعيد"],
  "appointment_records.write": ["Record appointment fulfillment", "تسجيل تنفيذ الموعد"],
  "appointment.confirm": ["Confirm appointments", "تأكيد المواعيد"],
  "appointment.bulkConfirm": ["Bulk confirm appointments", "تأكيد المواعيد المحددة"],
  "appointment.checkIn": ["Check in patients", "تسجيل وصول المرضى"],
  "appointment.callToRoom": ["Call patients to rooms", "استدعاء المرضى إلى الغرف"],
  "appointment.startService": ["Start appointment services", "بدء خدمات المواعيد"],
  "appointment.complete": ["Complete appointment services", "إتمام خدمات المواعيد"],
  "appointment.reschedule": ["Reschedule appointments", "إعادة جدولة المواعيد"],
  "appointment.cancel": ["Cancel appointments", "إلغاء المواعيد"],
  "appointment.noShow": ["Mark appointment no-shows", "تسجيل عدم حضور المواعيد"],
  "room.occupancy.claim": ["Claim operational room capacity", "حجز سعة الغرفة التشغيلية"],
  "room.occupancy.release": ["Release operational room capacity", "تحرير سعة الغرفة التشغيلية"],
  "room.assignment.change": ["Change active room assignments", "تغيير تعيينات الغرف النشطة"],
  "doctor.queue.next": ["Call the next Doctor appointment", "استدعاء موعد الطبيب التالي"],
  "appointments.availability.read": [
    "Find available appointment slots",
    "البحث عن المواعيد المتاحة",
  ],
  "appointments.cancel": ["Cancel appointments", "إلغاء المواعيد"],
  "appointments.create": ["Create appointments", "إنشاء المواعيد"],
  "appointments.read": ["Read appointments", "عرض المواعيد"],
  "appointments.reschedule": ["Reschedule appointments", "إعادة جدولة المواعيد"],
  "appointments.status.correct": ["Correct appointment status", "تصحيح حالة الموعد"],
  "appointments.status.transition": ["Transition appointment status", "تحديث حالة الموعد"],
  "branches.manage": ["Manage branches", "إدارة الفروع"],
  "branches.read": ["Read branches", "عرض الفروع"],
  "consent.read": ["Read consent history", "عرض سجل الموافقات"],
  "consent.record": ["Record consent", "تسجيل الموافقة"],
  "customers.read": ["Read customers", "عرض العملاء"],
  "customers.write": ["Manage customers", "إدارة العملاء"],
  "communication_preferences.manage": ["Manage communication preferences", "إدارة تفضيلات الاتصال"],
  "conversations.handoff": ["Manage human handoffs", "إدارة التحويل إلى موظف"],
  "conversations.read": ["Read AI conversations", "عرض محادثات الذكاء الاصطناعي"],
  "message_templates.manage": ["Manage message templates", "إدارة قوالب الرسائل"],
  "messages.read": ["Read communications", "عرض الاتصالات"],
  "messages.retry": ["Retry failed communications", "إعادة محاولة الاتصالات الفاشلة"],
  "messages.send": ["Send communications", "إرسال الاتصالات"],
  "knowledge.manage": ["Manage knowledge base", "إدارة قاعدة المعرفة"],
  "knowledge.read": ["Read knowledge base", "عرض قاعدة المعرفة"],
  "imports.manage": ["Manage safe data imports", "إدارة استيراد البيانات الآمن"],
  "exports.manage": ["Create protected data exports", "إنشاء تصدير بيانات محمي"],
  "organization.billing.manage": ["Manage organization billing", "إدارة فوترة المؤسسة"],
  "organization.read": ["Read organization", "عرض المؤسسة"],
  "organization.settings.manage": ["Manage organization settings", "إدارة إعدادات المؤسسة"],
  "provider_credentials.manage": ["Manage provider connections", "إدارة اتصالات مزودي الخدمة"],
  "predictions.configure": ["Configure predictive capabilities", "إعداد قدرات التنبؤ"],
  "predictions.feedback": ["Record prediction feedback", "تسجيل ملاحظات التنبؤ"],
  "predictions.read": ["Read predictive insights", "عرض الرؤى التنبؤية"],
  "predictions.run": ["Run predictive jobs", "تشغيل مهام التنبؤ"],
  "recordings.read": ["Read consented call records", "عرض سجلات المكالمات المصرح بها"],
  "reports.read": ["Read operational reports", "عرض التقارير التشغيلية"],
  "roles.manage": ["Manage roles and permissions", "إدارة الأدوار والصلاحيات"],
  "roles.read": ["Read roles and permissions", "عرض الأدوار والصلاحيات"],
  "resources.manage": ["Manage scheduling resources", "إدارة موارد الجدولة"],
  "resources.read": ["Read scheduling resources", "عرض موارد الجدولة"],
  "schedules.manage": ["Manage schedules", "إدارة الجداول"],
  "schedules.read": ["Read schedules", "عرض الجداول"],
  "services.manage": ["Manage services", "إدارة الخدمات"],
  "services.read": ["Read services", "عرض الخدمات"],
  "staff.manage": ["Manage staff and invitations", "إدارة الموظفين والدعوات"],
  "staff.read": ["Read staff", "عرض الموظفين"],
  "slot_offers.manage": ["Manage mocked slot offers", "إدارة عروض المواعيد التجريبية"],
  "waitlist.manage": ["Manage waitlist", "إدارة قائمة الانتظار"],
  "waitlist.read": ["Read waitlist", "عرض قائمة الانتظار"],
  "chatbot.checkin.execute": [
    "Run verified chatbot check-in",
    "تنفيذ تسجيل الوصول الموثق عبر المحادثة",
  ],
  "chatbot_escalations.read": ["Read chatbot escalations", "عرض تصعيدات المساعد الآلي"],
  "chatbot_escalations.manage": ["Manage chatbot escalations", "إدارة تصعيدات المساعد الآلي"],
  "notifications.read": ["Read notifications", "عرض الإشعارات"],
  "notifications.manage": ["Manage notifications", "إدارة الإشعارات"],
  "inventory.items.read": ["Read inventory availability", "عرض توفر المخزون"],
  "inventory.items.createDirect": ["Create inventory items directly", "إنشاء أصناف المخزون مباشرة"],
  "inventory.itemProposal.create": ["Request new inventory items", "طلب أصناف مخزون جديدة"],
  "inventory.itemProposal.approve": [
    "Approve inventory item proposals",
    "الموافقة على مقترحات أصناف المخزون",
  ],
  "inventory.orderRequest.create": ["Create inventory order requests", "إنشاء طلبات توريد المخزون"],
  "inventory.orderRequest.approve": [
    "Approve inventory order requests",
    "الموافقة على طلبات توريد المخزون",
  ],
  "inventory.order.markOrdered": [
    "Mark inventory orders placed",
    "تسجيل طلبات المخزون كطلبات مورّد",
  ],
  "inventory.order.receive": ["Receive inventory orders", "استلام طلبات المخزون"],
  "inventory.supplier.read": ["Read inventory supplier details", "عرض تفاصيل موردي المخزون"],
  "inventory.cost.read": ["Read inventory costs", "عرض تكاليف المخزون"],
  "inventory.stock.adjust": ["Adjust inventory stock", "تعديل رصيد المخزون"],
  "inventory.items.manage": ["Manage inventory items", "إدارة أصناف المخزون"],
  "inventory.stock.transfer": ["Transfer inventory stock", "تحويل رصيد المخزون"],
  "inventory.consumption.read": [
    "Read appointment inventory consumption",
    "عرض استهلاك المخزون في المواعيد",
  ],
  "inventory.consumption.adjust": [
    "Record and adjust inventory consumption",
    "تسجيل وتعديل استهلاك المخزون",
  ],
};

export type SetupReadinessIssueCode =
  | "BRANDING_APPROVAL_REQUIRED"
  | "COMMUNICATION_PROVIDER_REQUIRED"
  | "KNOWLEDGE_APPROVAL_REQUIRED"
  | "LOCATION_APPROVAL_REQUIRED"
  | "OWNER_VERIFICATION_REQUIRED"
  | "POLICY_APPROVAL_REQUIRED"
  | "PROFILE_APPROVAL_REQUIRED"
  | "PROVIDER_SCHEDULE_REQUIRED"
  | "SERVICE_APPROVAL_REQUIRED";

const roleLabels: Readonly<Record<TenantRoleKey, readonly [string, string]>> = {
  ORGANIZATION_MANAGER: ["Manager", "المدير"],
  ORGANIZATION_OWNER: ["Owner", "المالك"],
  PROVIDER: ["Service Provider", "مقدم الخدمة"],
  SECRETARY: ["Secretary", "سكرتير"],
};

const allWeekdays = [
  "SUNDAY",
  "MONDAY",
  "TUESDAY",
  "WEDNESDAY",
  "THURSDAY",
  "FRIDAY",
  "SATURDAY",
] as const;

export type SessionTenantSelection = Readonly<{
  activeMembershipId?: string;
  activeOrganizationId?: string;
  activeSupportAccessId?: string;
}>;

export type RequestAuditDetails = Readonly<{
  ipAddress?: string | undefined;
  userAgent?: string | undefined;
}>;

export type OrganizationCreation = Readonly<{
  nameAr: string;
  nameEn: string;
  ownerEmail: string;
  slug: string;
}>;

export type InvitationPreview = Readonly<{
  email: string;
  expiresAt: Date;
  organizationId: string;
  organizationNameAr: string;
  organizationNameEn: string;
  roleNameAr: string;
  roleNameEn: string;
  status: InvitationStatus;
}>;

function normalizedEmail(email: string): string {
  return email.trim().toLowerCase();
}

function assertActiveOrganization(status: OrganizationStatus): void {
  if (status === OrganizationStatus.SUSPENDED) {
    throw new DomainError({
      code: "ORGANIZATION_SUSPENDED",
      message: "The organization is suspended.",
    });
  }
  if (status !== OrganizationStatus.ACTIVE) {
    throw new DomainError({
      code: "FORBIDDEN",
      message: "The organization is not active.",
    });
  }
}

const permissionScopeRank: Readonly<Record<PermissionScope, number>> = {
  ASSIGNED_BRANCHES: 2,
  ORGANIZATION: 3,
  SELF: 1,
};

function requireAccessPermission(
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

async function createAuditEvent(
  transaction: TenantTransaction,
  input: Readonly<{
    action: string;
    actorUserId: string;
    details?: RequestAuditDetails | undefined;
    metadata?: Prisma.InputJsonValue | undefined;
    organizationId: string;
    reason?: string | undefined;
    supportAccessId?: string | undefined;
    targetId?: string | undefined;
    targetType?: string | undefined;
  }>,
): Promise<void> {
  await transaction.auditEvent.create({
    data: {
      action: input.action,
      actorUserId: input.actorUserId,
      ipAddress: input.details?.ipAddress ?? null,
      ...(input.metadata === undefined ? {} : { metadata: input.metadata }),
      organizationId: input.organizationId,
      reason: input.reason ?? null,
      supportAccessId: input.supportAccessId ?? null,
      targetId: input.targetId ?? null,
      targetType: input.targetType ?? null,
      userAgent: input.details?.userAgent ?? null,
    },
  });
}

export class IdentityRepository {
  readonly client: PrismaClient;

  constructor(client: PrismaClient) {
    this.client = client;
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
            message: "The membership is not active.",
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

  async ensurePermissionRegistry(): Promise<void> {
    await this.client.$transaction(
      permissionCodes.map((code) => {
        const labels = permissionLabels[code];
        return this.client.permission.upsert({
          create: { code, nameAr: labels[1], nameEn: labels[0] },
          update: { nameAr: labels[1], nameEn: labels[0] },
          where: { code },
        });
      }),
    );
  }

  async assertSuperAdmin(userId: string): Promise<void> {
    const user = await this.client.user.findUnique({
      select: { platformRole: true },
      where: { id: userId },
    });
    if (user?.platformRole !== PlatformRole.JORMALL_SUPER_ADMIN) {
      throw new DomainError({ code: "FORBIDDEN", message: "Super Admin access is required." });
    }
  }

  async listOrganizations(actorUserId: string) {
    await this.assertSuperAdmin(actorUserId);
    return this.client.organization.findMany({
      orderBy: { createdAt: "desc" },
      select: {
        createdAt: true,
        id: true,
        nameAr: true,
        nameEn: true,
        settings: { select: { businessSector: true } },
        slug: true,
        status: true,
        suspendedAt: true,
        suspensionReason: true,
      },
    });
  }

  async createOrganization(
    actorUserId: string,
    input: OrganizationCreation,
  ): Promise<Readonly<{ invitationToken: string; organizationId: string }>> {
    await this.assertSuperAdmin(actorUserId);
    await this.ensurePermissionRegistry();
    const organizationId = randomUUID();
    const invitationToken = createInvitationToken();
    const permissionRows = await this.client.permission.findMany({
      where: { code: { in: [...permissionCodes] } },
    });

    await this.client.$transaction(async (transaction) => {
      await transaction.organization.create({
        data: {
          createdByUserId: actorUserId,
          id: organizationId,
          nameAr: input.nameAr,
          nameEn: input.nameEn,
          settings: { create: { businessSector: BusinessSector.BEAUTY_CENTER } },
          slug: input.slug,
        },
      });

      const roles: Array<{ id: string; systemKey: TenantRoleKey | null }> = [];
      for (const roleKey of Object.keys(roleLabels) as TenantRoleKey[]) {
        const labels = roleLabels[roleKey];
        roles.push(
          await transaction.role.create({
            data: {
              isSystem: true,
              key: roleKey,
              nameAr: labels[1],
              nameEn: labels[0],
              organizationId,
              systemKey: roleKey,
            },
          }),
        );
      }

      for (const role of roles) {
        const roleKey = role.systemKey;
        if (!roleKey) {
          continue;
        }
        const grants = defaultRolePermissions[roleKey];
        for (const grant of grants) {
          const permission = permissionRows.find((row) => row.code === grant.code);
          if (!permission) {
            throw new DomainError({
              code: "INTERNAL_ERROR",
              message: `Permission ${grant.code} is missing from the registry.`,
            });
          }
          await transaction.rolePermission.create({
            data: {
              organizationId,
              permissionId: permission.id,
              roleId: role.id,
              scope: grant.scope,
            },
          });
        }
      }

      await createCommunicationDefaults(transaction, organizationId);
      await createAIFoundationDefaults(transaction, organizationId);
      await createPredictiveDefaults(transaction, organizationId, actorUserId);

      const ownerRole = roles.find((role) => role.systemKey === "ORGANIZATION_OWNER");
      if (!ownerRole) {
        throw new DomainError({ code: "INTERNAL_ERROR", message: "Owner role was not created." });
      }
      await transaction.organizationInvitation.create({
        data: {
          email: normalizedEmail(input.ownerEmail),
          expiresAt: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000),
          invitedByUserId: actorUserId,
          organizationId,
          roleId: ownerRole.id,
          tokenHash: hashInvitationToken(invitationToken),
        },
      });
      await transaction.auditEvent.create({
        data: {
          action: "ORGANIZATION_CREATED",
          actorUserId,
          metadata: { businessSector: BusinessSector.BEAUTY_CENTER },
          organizationId,
          targetId: organizationId,
          targetType: "Organization",
        },
      });
    });

    return { invitationToken, organizationId };
  }

  async ensureOwnerInvitation(
    actorUserId: string,
    organizationId: string,
    ownerEmail: string,
    reason: string,
    replacePending = false,
  ): Promise<string | null> {
    await this.assertSuperAdmin(actorUserId);
    if (reason.trim().length < 10) {
      throw new DomainError({
        code: "VALIDATION_FAILED",
        message: "An owner-invitation reason of at least 10 characters is required.",
      });
    }
    const token = createInvitationToken();
    return runInTenant(this.client, { actorUserId, organizationId }, async (transaction) => {
      const normalizedOwnerEmail = normalizedEmail(ownerEmail);
      const [organization, ownerRole, activeOwnerCount, pendingOwnerInvitation] = await Promise.all(
        [
          transaction.organization.findUnique({
            select: { status: true },
            where: { id: organizationId },
          }),
          transaction.role.findFirst({
            select: { id: true },
            where: { organizationId, systemKey: "ORGANIZATION_OWNER" },
          }),
          transaction.organizationMembership.count({
            where: {
              organizationId,
              roles: { some: { role: { systemKey: "ORGANIZATION_OWNER" } } },
              status: MembershipStatus.ACTIVE,
            },
          }),
          transaction.organizationInvitation.findFirst({
            select: { id: true },
            where: {
              email: normalizedOwnerEmail,
              expiresAt: { gt: new Date() },
              organizationId,
              role: { systemKey: "ORGANIZATION_OWNER" },
              status: InvitationStatus.PENDING,
            },
          }),
        ],
      );
      if (!organization || !ownerRole) {
        throw new DomainError({ code: "NOT_FOUND", message: "Organization was not found." });
      }
      assertActiveOrganization(organization.status);
      if (activeOwnerCount > 0) return null;
      if (pendingOwnerInvitation && !replacePending) return null;
      await transaction.organizationInvitation.updateMany({
        data: { status: InvitationStatus.REVOKED },
        where: {
          organizationId,
          roleId: ownerRole.id,
          status: InvitationStatus.PENDING,
        },
      });
      const invitation = await transaction.organizationInvitation.create({
        data: {
          email: normalizedOwnerEmail,
          expiresAt: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000),
          invitedByUserId: actorUserId,
          organizationId,
          roleId: ownerRole.id,
          tokenHash: hashInvitationToken(token),
        },
      });
      await createAuditEvent(transaction, {
        action: "OWNER_INVITATION_ISSUED",
        actorUserId,
        organizationId,
        reason: reason.trim(),
        targetId: invitation.id,
        targetType: "OrganizationInvitation",
      });
      return token;
    });
  }

  async setOrganizationStatus(
    actorUserId: string,
    organizationId: string,
    status: OrganizationStatus,
    reason?: string,
  ): Promise<void> {
    await this.assertSuperAdmin(actorUserId);
    if (status === OrganizationStatus.SUSPENDED && (!reason || reason.trim().length < 10)) {
      throw new DomainError({
        code: "VALIDATION_FAILED",
        message: "A suspension reason of at least 10 characters is required.",
      });
    }
    await this.client.organization.update({
      data: {
        status,
        suspendedAt: status === OrganizationStatus.SUSPENDED ? new Date() : null,
        suspensionReason: status === OrganizationStatus.SUSPENDED ? (reason?.trim() ?? null) : null,
      },
      where: { id: organizationId },
    });
    await runInTenant(this.client, { actorUserId, organizationId }, async (transaction) => {
      await createAuditEvent(transaction, {
        action: `ORGANIZATION_${status}`,
        actorUserId,
        organizationId,
        reason,
        targetId: organizationId,
        targetType: "Organization",
      });
    });
  }

  async startSupportAccess(
    actorUserId: string,
    organizationId: string,
    reason: string,
    details: RequestAuditDetails,
  ): Promise<string> {
    await this.assertSuperAdmin(actorUserId);
    if (reason.trim().length < 10) {
      throw new DomainError({
        code: "VALIDATION_FAILED",
        message: "A support-access reason of at least 10 characters is required.",
      });
    }
    const organization = await this.client.organization.findUnique({
      select: { status: true },
      where: { id: organizationId },
    });
    if (!organization) {
      throw new DomainError({ code: "NOT_FOUND", message: "Organization not found." });
    }
    assertActiveOrganization(organization.status);
    const access = await this.client.platformSupportAccess.create({
      data: {
        expiresAt: new Date(Date.now() + 30 * 60 * 1000),
        organizationId,
        permissionCodes: [...permissionCodes],
        reason: reason.trim(),
        userId: actorUserId,
      },
    });
    try {
      await runInTenant(
        this.client,
        { actorUserId, organizationId, supportAccessId: access.id },
        async (transaction) => {
          const currentOrganization = await transaction.organization.findUnique({
            select: { id: true, status: true },
            where: { id: organizationId },
          });
          if (!currentOrganization) {
            throw new DomainError({ code: "NOT_FOUND", message: "Organization not found." });
          }
          assertActiveOrganization(currentOrganization.status);
          await createAuditEvent(transaction, {
            action: "SUPER_ADMIN_SUPPORT_STARTED",
            actorUserId,
            details,
            organizationId,
            reason: reason.trim(),
            supportAccessId: access.id,
            targetId: organizationId,
            targetType: "Organization",
          });
        },
      );
    } catch (error) {
      await this.client.platformSupportAccess.delete({ where: { id: access.id } });
      throw error;
    }
    return access.id;
  }

  async revokeSupportAccess(
    actorUserId: string,
    supportAccessId: string,
    details: RequestAuditDetails,
  ): Promise<void> {
    await this.assertSuperAdmin(actorUserId);
    const access = await this.client.platformSupportAccess.findFirst({
      where: { id: supportAccessId, userId: actorUserId },
    });
    if (!access) {
      return;
    }
    await this.client.platformSupportAccess.update({
      data: { revokedAt: new Date() },
      where: { id: access.id },
    });
    await runInTenant(
      this.client,
      {
        actorUserId,
        organizationId: access.organizationId,
        supportAccessId: access.id,
      },
      async (transaction) => {
        await createAuditEvent(transaction, {
          action: "SUPER_ADMIN_SUPPORT_ENDED",
          actorUserId,
          details,
          organizationId: access.organizationId,
          reason: access.reason,
          supportAccessId: access.id,
          targetId: access.organizationId,
          targetType: "Organization",
        });
      },
    );
  }

  async listMembershipChoices(userId: string) {
    return this.client.organizationMembership.findMany({
      orderBy: { organization: { nameEn: "asc" } },
      select: {
        id: true,
        organization: { select: { id: true, nameAr: true, nameEn: true, status: true } },
        roles: { select: { role: { select: { nameAr: true, nameEn: true, systemKey: true } } } },
        status: true,
      },
      where: { userId },
    });
  }

  async resolveMembershipForSwitch(userId: string, membershipId: string) {
    const membership = await this.client.organizationMembership.findFirst({
      select: { id: true, organizationId: true, status: true },
      where: { id: membershipId, userId },
    });
    if (!membership) {
      throw new DomainError({ code: "NOT_FOUND", message: "Membership not found." });
    }
    if (membership.status !== MembershipStatus.ACTIVE) {
      throw new DomainError({
        code: "MEMBERSHIP_SUSPENDED",
        message: "The membership is not active.",
      });
    }
    const organization = await runInTenant(
      this.client,
      { actorUserId: userId, organizationId: membership.organizationId },
      (transaction) =>
        transaction.organization.findUnique({
          select: { status: true },
          where: { id: membership.organizationId },
        }),
    );
    if (!organization) {
      throw new DomainError({ code: "NOT_FOUND", message: "Organization not found." });
    }
    assertActiveOrganization(organization.status);
    return membership;
  }

  async loadTenantAccess(
    userId: string,
    selection: SessionTenantSelection,
    details: RequestAuditDetails,
  ): Promise<TenantAccessSnapshot> {
    if (!selection.activeOrganizationId) {
      throw new DomainError({
        code: "TENANT_CONTEXT_REQUIRED",
        message: "Select an organization before continuing.",
      });
    }
    const organizationId = selection.activeOrganizationId;

    if (selection.activeSupportAccessId) {
      return this.loadSupportAccess(
        userId,
        organizationId,
        selection.activeSupportAccessId,
        details,
      );
    }
    if (!selection.activeMembershipId) {
      throw new DomainError({
        code: "TENANT_CONTEXT_REQUIRED",
        message: "An active membership is required.",
      });
    }
    return this.loadMemberAccess(userId, organizationId, selection.activeMembershipId);
  }

  private async loadMemberAccess(
    userId: string,
    organizationId: string,
    membershipId: string,
  ): Promise<TenantAccessSnapshot> {
    return runInTenant(
      this.client,
      { actorUserId: userId, organizationId },
      async (transaction) => {
        const organization = await transaction.organization.findUnique({
          select: { status: true },
          where: { id: organizationId },
        });
        if (!organization) {
          throw new DomainError({ code: "NOT_FOUND", message: "Organization not found." });
        }
        assertActiveOrganization(organization.status);

        const membership = await transaction.organizationMembership.findFirst({
          include: {
            roles: {
              include: {
                role: {
                  include: { permissions: { include: { permission: true } } },
                },
              },
            },
            staffProfile: { include: { branchAssignments: true } },
          },
          where: { id: membershipId, organizationId, userId },
        });
        if (!membership) {
          throw new DomainError({ code: "NOT_FOUND", message: "Membership not found." });
        }
        if (membership.status !== MembershipStatus.ACTIVE) {
          throw new DomainError({
            code: "MEMBERSHIP_SUSPENDED",
            message: "The membership is not active.",
          });
        }

        const grants = membership.roles.flatMap(({ role }) =>
          role.permissions.flatMap(({ permission, scope }) =>
            isPermissionCode(permission.code) ? [{ code: permission.code, scope }] : [],
          ),
        );
        return {
          actorUserId: userId,
          assignedBranchIds:
            membership.staffProfile?.branchAssignments.map(({ branchId }) => branchId) ?? [],
          grants,
          membershipId: membership.id,
          organizationId,
          ...(membership.staffProfile ? { staffProfileId: membership.staffProfile.id } : {}),
        };
      },
    );
  }

  private async loadSupportAccess(
    userId: string,
    organizationId: string,
    supportAccessId: string,
    details: RequestAuditDetails,
  ): Promise<TenantAccessSnapshot> {
    await this.assertSuperAdmin(userId);
    const supportAccess = await this.client.platformSupportAccess.findFirst({
      where: {
        expiresAt: { gt: new Date() },
        id: supportAccessId,
        organizationId,
        revokedAt: null,
        userId,
      },
    });
    if (!supportAccess) {
      throw new DomainError({
        code: "FORBIDDEN",
        message: "Support access is invalid or expired.",
      });
    }

    return runInTenant(
      this.client,
      { actorUserId: userId, organizationId, supportAccessId },
      async (transaction) => {
        const organization = await transaction.organization.findUnique({
          select: { status: true },
          where: { id: organizationId },
        });
        if (!organization) {
          throw new DomainError({ code: "NOT_FOUND", message: "Organization not found." });
        }
        if (organization.status === OrganizationStatus.SUSPENDED) {
          throw new DomainError({
            code: "ORGANIZATION_SUSPENDED",
            message: "Support access to a suspended organization is blocked.",
          });
        }
        await createAuditEvent(transaction, {
          action: "SUPER_ADMIN_TENANT_ACCESS",
          actorUserId: userId,
          details,
          organizationId,
          reason: supportAccess.reason,
          supportAccessId,
          targetId: organizationId,
          targetType: "Organization",
        });
        return {
          actorUserId: userId,
          assignedBranchIds: [],
          grants: supportAccess.permissionCodes.flatMap((code) =>
            isPermissionCode(code) ? [{ code, scope: "ORGANIZATION" as const }] : [],
          ),
          organizationId,
          supportAccessId,
        };
      },
    );
  }

  async listTenantOverview(access: TenantAccessSnapshot) {
    requireAccessPermission(access, "organization.read");
    return this.runWithAccess(access, async (transaction) => {
      const organization = await transaction.organization.findUnique({
        select: {
          id: true,
          nameAr: true,
          nameEn: true,
          settings: { select: { brandLogoUrl: true, businessSector: true, currency: true } },
          slug: true,
          status: true,
        },
        where: { id: access.organizationId },
      });
      const branches = await transaction.branch.count({
        where: {
          ...(access.activeBranchId ? { id: access.activeBranchId } : {}),
          organizationId: access.organizationId,
        },
      });
      const staff = await transaction.organizationMembership.count({
        where: {
          ...(access.activeBranchId
            ? { staffProfile: { branchAssignments: { some: { branchId: access.activeBranchId } } } }
            : {}),
          organizationId: access.organizationId,
          status: MembershipStatus.ACTIVE,
        },
      });
      const services = await transaction.service.count({
        where: {
          ...(access.activeBranchId
            ? { branches: { some: { branchId: access.activeBranchId, isEnabled: true } } }
            : {}),
          organizationId: access.organizationId,
        },
      });
      return { branches, organization, services, staff };
    });
  }

  async getSettings(access: TenantAccessSnapshot) {
    requireAccessPermission(access, "organization.settings.manage");
    return this.runWithAccess(access, (transaction) =>
      transaction.organizationSettings.findUnique({
        include: { organization: { select: { nameAr: true, nameEn: true } } },
        where: { organizationId: access.organizationId },
      }),
    );
  }

  async getSetupReadiness(
    access: TenantAccessSnapshot,
  ): Promise<readonly SetupReadinessIssueCode[]> {
    requireAccessPermission(access, "organization.settings.manage");
    return this.runWithAccess(access, async (transaction) => {
      const [
        organization,
        draftLocations,
        draftServices,
        readyProviders,
        verifiedOwners,
        productionConnections,
        activeKnowledge,
      ] = await Promise.all([
        transaction.organization.findUnique({
          select: {
            profileStatus: true,
            settings: {
              select: {
                bookingPolicyStatus: true,
                brandLogoUrl: true,
              },
            },
          },
          where: { id: access.organizationId },
        }),
        transaction.branch.count({
          where: {
            isActive: true,
            locationStatus: ConfigurationApprovalStatus.DRAFT,
            organizationId: access.organizationId,
          },
        }),
        transaction.service.count({
          where: {
            configurationStatus: ConfigurationApprovalStatus.DRAFT,
            isActive: true,
            organizationId: access.organizationId,
          },
        }),
        transaction.staffProfile.count({
          where: {
            availabilityRules: { some: {} },
            branchAssignments: { some: {} },
            isBookable: true,
            organizationId: access.organizationId,
            services: { some: { isEnabled: true } },
          },
        }),
        transaction.organizationMembership.count({
          where: {
            organizationId: access.organizationId,
            roles: { some: { role: { systemKey: "ORGANIZATION_OWNER" } } },
            status: MembershipStatus.ACTIVE,
            user: { emailVerified: true },
          },
        }),
        transaction.providerConnection.count({
          where: {
            integrationMode: "PRODUCTION",
            organizationId: access.organizationId,
            status: "ACTIVE",
          },
        }),
        transaction.knowledgeSource.count({
          where: { activeVersionId: { not: null }, organizationId: access.organizationId },
        }),
      ]);
      if (!organization?.settings) {
        throw new DomainError({ code: "NOT_FOUND", message: "Organization settings not found." });
      }
      const issues: SetupReadinessIssueCode[] = [];
      if (organization.profileStatus === ConfigurationApprovalStatus.DRAFT) {
        issues.push("PROFILE_APPROVAL_REQUIRED");
      }
      if (draftLocations > 0) issues.push("LOCATION_APPROVAL_REQUIRED");
      if (draftServices > 0) issues.push("SERVICE_APPROVAL_REQUIRED");
      if (readyProviders === 0) issues.push("PROVIDER_SCHEDULE_REQUIRED");
      if (organization.settings.bookingPolicyStatus === ConfigurationApprovalStatus.DRAFT) {
        issues.push("POLICY_APPROVAL_REQUIRED");
      }
      if (!organization.settings.brandLogoUrl) issues.push("BRANDING_APPROVAL_REQUIRED");
      if (verifiedOwners === 0) issues.push("OWNER_VERIFICATION_REQUIRED");
      if (productionConnections === 0) issues.push("COMMUNICATION_PROVIDER_REQUIRED");
      if (activeKnowledge === 0) issues.push("KNOWLEDGE_APPROVAL_REQUIRED");
      return issues;
    });
  }

  async updateOrganizationProfile(
    access: TenantAccessSnapshot,
    input: Readonly<{
      descriptionAr: string | null;
      descriptionEn: string | null;
      nameAr: string;
      nameEn: string;
      profileStatus?: ConfigurationApprovalStatus | undefined;
      subtitleAr: string | null;
    }>,
  ): Promise<void> {
    requireAccessPermission(access, "organization.settings.manage");
    await this.runWithAccess(access, async (transaction) => {
      await transaction.organization.update({
        data: {
          descriptionAr: input.descriptionAr,
          descriptionEn: input.descriptionEn,
          nameAr: input.nameAr,
          nameEn: input.nameEn,
          ...(input.profileStatus === undefined ? {} : { profileStatus: input.profileStatus }),
          subtitleAr: input.subtitleAr,
        },
        where: { id: access.organizationId },
      });
      await createAuditEvent(transaction, {
        action: "ORGANIZATION_PROFILE_UPDATED",
        actorUserId: access.actorUserId,
        organizationId: access.organizationId,
        supportAccessId: access.supportAccessId,
        targetId: access.organizationId,
        targetType: "Organization",
      });
    });
  }

  async getWorkspaceBranding(access: TenantAccessSnapshot) {
    requireAccessPermission(access, "organization.read");
    return this.runWithAccess(access, (transaction) =>
      transaction.organization.findUnique({
        select: {
          id: true,
          nameAr: true,
          nameEn: true,
          settings: {
            select: {
              brandAccentColor: true,
              brandLogoUrl: true,
              brandPrimaryColor: true,
            },
          },
        },
        where: { id: access.organizationId },
      }),
    );
  }

  async updateSettings(
    access: TenantAccessSnapshot,
    input: Readonly<{
      bookingPolicyStatus?: ConfigurationApprovalStatus | undefined;
      bookingWindowDays: number | null;
      brandAccentColor: string;
      brandLogoUrl: string | null;
      brandPrimaryColor: string;
      cancellationWindowMins?: number | undefined;
      confirmationEnabled?: boolean | undefined;
      currency: string;
      defaultAppointmentStatus?: "PENDING" | "CONFIRMED" | undefined;
      defaultLocale: SupportedLocale;
      noShowPolicyAr?: string | null | undefined;
      noShowPolicyEn?: string | null | undefined;
      reminderLeadMins?: number | undefined;
      secondaryReminderLeadMins: number | null;
      rescheduleWindowMins?: number | undefined;
      timezone: string;
    }>,
  ): Promise<void> {
    requireAccessPermission(access, "organization.settings.manage");
    await this.runWithAccess(access, async (transaction) => {
      await transaction.organizationSettings.update({
        data: {
          ...(input.bookingPolicyStatus === undefined
            ? {}
            : { bookingPolicyStatus: input.bookingPolicyStatus }),
          bookingWindowDays: input.bookingWindowDays,
          brandAccentColor: input.brandAccentColor,
          brandLogoUrl: input.brandLogoUrl,
          brandPrimaryColor: input.brandPrimaryColor,
          currency: input.currency,
          defaultLocale: input.defaultLocale,
          timezone: input.timezone,
          ...(input.cancellationWindowMins === undefined
            ? {}
            : { cancellationWindowMins: input.cancellationWindowMins }),
          ...(input.confirmationEnabled === undefined
            ? {}
            : { confirmationEnabled: input.confirmationEnabled }),
          ...(input.defaultAppointmentStatus === undefined
            ? {}
            : { defaultAppointmentStatus: input.defaultAppointmentStatus }),
          ...(input.noShowPolicyAr === undefined ? {} : { noShowPolicyAr: input.noShowPolicyAr }),
          ...(input.noShowPolicyEn === undefined ? {} : { noShowPolicyEn: input.noShowPolicyEn }),
          ...(input.reminderLeadMins === undefined
            ? {}
            : { reminderLeadMins: input.reminderLeadMins }),
          secondaryReminderLeadMins: input.secondaryReminderLeadMins,
          ...(input.rescheduleWindowMins === undefined
            ? {}
            : { rescheduleWindowMins: input.rescheduleWindowMins }),
        },
        where: { organizationId: access.organizationId },
      });
      await createAuditEvent(transaction, {
        action: "ORGANIZATION_SETTINGS_UPDATED",
        actorUserId: access.actorUserId,
        organizationId: access.organizationId,
        supportAccessId: access.supportAccessId,
      });
    });
  }

  async listBranches(access: TenantAccessSnapshot) {
    const scope = requireAccessPermission(access, "branches.read");
    return this.runWithAccess(access, (transaction) =>
      transaction.branch.findMany({
        include: { hoursRules: { orderBy: { weekday: "asc" } } },
        orderBy: { nameEn: "asc" },
        where: {
          organizationId: access.organizationId,
          ...(scope === "ORGANIZATION" ? {} : { id: { in: [...access.assignedBranchIds] } }),
        },
      }),
    );
  }

  async createBranch(
    access: TenantAccessSnapshot,
    input: Readonly<{
      addressAr?: string | undefined;
      addressEn?: string | undefined;
      email?: string | undefined;
      mapUrl?: string | undefined;
      locationStatus?: ConfigurationApprovalStatus | undefined;
      mobilePhone?: string | undefined;
      nameAr: string;
      nameEn: string;
      phone?: string | undefined;
      timezone: string;
    }>,
  ): Promise<void> {
    requireAccessPermission(access, "branches.manage");
    await this.runWithAccess(access, async (transaction) => {
      const branch = await transaction.branch.create({
        data: {
          addressAr: input.addressAr ?? null,
          addressEn: input.addressEn ?? null,
          email: input.email ?? null,
          mapUrl: input.mapUrl ?? null,
          locationStatus: input.locationStatus ?? ConfigurationApprovalStatus.DRAFT,
          mobilePhone: input.mobilePhone ?? null,
          nameAr: input.nameAr,
          nameEn: input.nameEn,
          organizationId: access.organizationId,
          phone: input.phone ?? null,
          timezone: input.timezone,
        },
      });
      await transaction.branchHoursRule.createMany({
        data: allWeekdays.map((weekday) => ({
          branchId: branch.id,
          endMinuteLocal: 1440,
          organizationId: access.organizationId,
          startMinuteLocal: 0,
          weekday,
        })),
      });
      await createAuditEvent(transaction, {
        action: "BRANCH_CREATED",
        actorUserId: access.actorUserId,
        organizationId: access.organizationId,
        supportAccessId: access.supportAccessId,
        targetId: branch.id,
        targetType: "Branch",
      });
    });
  }

  async updateBranch(
    access: TenantAccessSnapshot,
    branchId: string,
    input: Readonly<{
      addressAr?: string | undefined;
      addressEn?: string | undefined;
      email?: string | undefined;
      mapUrl?: string | undefined;
      locationStatus?: ConfigurationApprovalStatus | undefined;
      mobilePhone?: string | undefined;
      nameAr: string;
      nameEn: string;
      phone?: string | undefined;
      timezone: string;
    }>,
  ): Promise<void> {
    requireAccessPermission(access, "branches.manage");
    await this.runWithAccess(access, async (transaction) => {
      const updated = await transaction.branch.updateMany({
        data: {
          addressAr: input.addressAr ?? null,
          addressEn: input.addressEn ?? null,
          email: input.email ?? null,
          mapUrl: input.mapUrl ?? null,
          ...(input.locationStatus === undefined ? {} : { locationStatus: input.locationStatus }),
          mobilePhone: input.mobilePhone ?? null,
          nameAr: input.nameAr,
          nameEn: input.nameEn,
          phone: input.phone ?? null,
          timezone: input.timezone,
        },
        where: { id: branchId, organizationId: access.organizationId },
      });
      if (updated.count !== 1) {
        throw new DomainError({ code: "NOT_FOUND", message: "Branch not found." });
      }
      await createAuditEvent(transaction, {
        action: "BRANCH_UPDATED",
        actorUserId: access.actorUserId,
        organizationId: access.organizationId,
        supportAccessId: access.supportAccessId,
        targetId: branchId,
        targetType: "Branch",
      });
    });
  }

  async deleteBranch(access: TenantAccessSnapshot, branchId: string): Promise<boolean> {
    requireAccessPermission(access, "branches.manage");
    return this.runWithAccess(access, async (transaction) => {
      const branch = await transaction.branch.findFirst({
        select: { id: true },
        where: { id: branchId, organizationId: access.organizationId },
      });
      if (!branch) return false;
      const branchCount = await transaction.branch.count({
        where: { organizationId: access.organizationId },
      });
      assertBranchCanBeDeleted(branchCount);
      const result = await transaction.branch.deleteMany({
        where: { id: branchId, organizationId: access.organizationId },
      });
      if (result.count > 0) {
        await createAuditEvent(transaction, {
          action: "BRANCH_DELETED",
          actorUserId: access.actorUserId,
          organizationId: access.organizationId,
          supportAccessId: access.supportAccessId,
          targetId: branchId,
          targetType: "Branch",
        });
      }
      return result.count === 1;
    });
  }

  async listRoles(access: TenantAccessSnapshot, filterByMembershipId?: string) {
    requireAccessPermission(access, "roles.read");
    return this.runWithAccess(access, (transaction) =>
      transaction.role.findMany({
        include: { permissions: { include: { permission: true } } },
        orderBy: { nameEn: "asc" },
        where: {
          organizationId: access.organizationId,
          ...(filterByMembershipId
            ? { memberships: { some: { membershipId: filterByMembershipId } } }
            : {}),
        },
      }),
    );
  }

  async listPermissions() {
    return this.client.permission.findMany({ orderBy: { code: "asc" } });
  }

  async createRole(
    access: TenantAccessSnapshot,
    input: Readonly<{
      key: string;
      nameAr: string;
      nameEn: string;
      permissionCodes: readonly string[];
    }>,
  ): Promise<void> {
    requireAccessPermission(access, "roles.manage");
    const selected = await this.client.permission.findMany({
      where: { code: { in: [...input.permissionCodes] } },
    });
    if (selected.length !== new Set(input.permissionCodes).size) {
      throw new DomainError({ code: "VALIDATION_FAILED", message: "Unknown permission selected." });
    }
    await this.runWithAccess(access, async (transaction) => {
      const role = await transaction.role.create({
        data: {
          key: input.key,
          nameAr: input.nameAr,
          nameEn: input.nameEn,
          organizationId: access.organizationId,
        },
      });
      await transaction.rolePermission.createMany({
        data: selected.map((permission) => {
          if (!isPermissionCode(permission.code)) {
            throw new DomainError({
              code: "VALIDATION_FAILED",
              message: "Unknown permission selected.",
            });
          }
          return {
            organizationId: access.organizationId,
            permissionId: permission.id,
            roleId: role.id,
            scope: requireAccessPermission(access, permission.code),
          };
        }),
      });
      await createAuditEvent(transaction, {
        action: "ROLE_CREATED",
        actorUserId: access.actorUserId,
        organizationId: access.organizationId,
        supportAccessId: access.supportAccessId,
        targetId: role.id,
        targetType: "Role",
      });
    });
  }

  async updateRole(
    access: TenantAccessSnapshot,
    roleId: string,
    input: Readonly<{
      nameAr: string;
      nameEn: string;
      permissionCodes: readonly string[];
    }>,
  ): Promise<void> {
    requireAccessPermission(access, "roles.manage");
    const selected = await this.client.permission.findMany({
      where: { code: { in: [...input.permissionCodes] } },
    });
    if (selected.length !== new Set(input.permissionCodes).size) {
      throw new DomainError({ code: "VALIDATION_FAILED", message: "Unknown permission selected." });
    }
    for (const permission of selected) {
      if (!isPermissionCode(permission.code)) {
        throw new DomainError({
          code: "VALIDATION_FAILED",
          message: "Unknown permission selected.",
        });
      }
      requireAccessPermission(access, permission.code);
    }
    await this.runWithAccess(access, async (transaction) => {
      const role = await transaction.role.findFirst({
        where: { id: roleId, organizationId: access.organizationId },
      });
      if (!role) {
        throw new DomainError({ code: "NOT_FOUND", message: "Role not found." });
      }
      if (role.isSystem || role.systemKey) {
        const actorIsOwner = access.membershipId
          ? await transaction.organizationMembership.count({
              where: {
                id: access.membershipId,
                organizationId: access.organizationId,
                roles: { some: { role: { systemKey: "ORGANIZATION_OWNER" } } },
              },
            })
          : 0;
        if (actorIsOwner === 0) {
          throw new DomainError({
            code: "FORBIDDEN",
            message: "Only an organization owner can edit default roles.",
          });
        }
      }
      if (role.systemKey === "ORGANIZATION_OWNER") {
        const requiredOwnerPermissions = [
          "organization.read",
          "staff.read",
          "staff.manage",
          "roles.read",
          "roles.manage",
        ] as const;
        if (requiredOwnerPermissions.some((code) => !input.permissionCodes.includes(code))) {
          throw new DomainError({
            code: "VALIDATION_FAILED",
            message: "The Owner role must retain essential organization and access permissions.",
          });
        }
      }
      await transaction.role.update({
        data: { nameAr: input.nameAr, nameEn: input.nameEn },
        where: { id: role.id },
      });
      await transaction.rolePermission.deleteMany({
        where: { organizationId: access.organizationId, roleId: role.id },
      });
      await transaction.rolePermission.createMany({
        data: selected.map((permission) => {
          if (!isPermissionCode(permission.code)) {
            throw new DomainError({
              code: "VALIDATION_FAILED",
              message: "Unknown permission selected.",
            });
          }
          return {
            organizationId: access.organizationId,
            permissionId: permission.id,
            roleId: role.id,
            scope: requireAccessPermission(access, permission.code),
          };
        }),
      });
      await createAuditEvent(transaction, {
        action: "ROLE_UPDATED",
        actorUserId: access.actorUserId,
        organizationId: access.organizationId,
        supportAccessId: access.supportAccessId,
        targetId: role.id,
        targetType: "Role",
      });
    });
  }

  async deleteRole(access: TenantAccessSnapshot, roleId: string): Promise<void> {
    requireAccessPermission(access, "roles.manage");
    await this.runWithAccess(access, async (transaction) => {
      const role = await transaction.role.findFirst({
        include: { _count: { select: { invitations: true, memberships: true } } },
        where: { id: roleId, organizationId: access.organizationId },
      });
      if (!role) {
        throw new DomainError({ code: "NOT_FOUND", message: "Role not found." });
      }
      if (role.isSystem || role.systemKey) {
        throw new DomainError({ code: "FORBIDDEN", message: "System roles cannot be deleted." });
      }
      if (role._count.memberships > 0 || role._count.invitations > 0) {
        throw new DomainError({
          code: "CONFLICT",
          message: "Remove this role from staff and invitations before deleting it.",
        });
      }
      await transaction.role.delete({ where: { id: role.id } });
      await createAuditEvent(transaction, {
        action: "ROLE_DELETED",
        actorUserId: access.actorUserId,
        organizationId: access.organizationId,
        supportAccessId: access.supportAccessId,
        targetId: role.id,
        targetType: "Role",
      });
    });
  }

  async listStaff(access: TenantAccessSnapshot) {
    requireAccessPermission(access, "staff.read");
    return this.runWithAccess(access, (transaction) =>
      transaction.organizationMembership.findMany({
        include: {
          roles: { include: { role: true } },
          staffProfile: {
            include: {
              availabilityRules: true,
              branchAssignments: { include: { branch: true } },
              services: { include: { service: true } },
            },
          },
          user: { select: { email: true, name: true } },
        },
        orderBy: { createdAt: "desc" },
        where: { organizationId: access.organizationId },
      }),
    );
  }

  async listDoctors(access: TenantAccessSnapshot) {
    const scope = requireAccessPermission(access, "doctors.directory.read");
    return this.runWithAccess(access, (transaction) =>
      transaction.staffProfile.findMany({
        include: {
          availabilityRules: {
            orderBy: [{ weekday: "asc" }, { startMinuteLocal: "asc" }],
            ...(access.activeBranchId
              ? { where: { OR: [{ branchId: access.activeBranchId }, { branchId: null }] } }
              : {}),
          },
          branchAssignments: { include: { branch: true } },
          breaks: {
            orderBy: [{ weekday: "asc" }, { startMinuteLocal: "asc" }],
            ...(access.activeBranchId ? { where: { branchId: access.activeBranchId } } : {}),
          },
          membership: { include: { roles: { include: { role: true } }, user: true } },
          services: { include: { service: true }, where: { isEnabled: true } },
          timeOffEntries: {
            include: { createdBy: { select: { name: true } } },
            orderBy: { startsAt: "asc" },
            where: {
              endsAt: { gt: new Date() },
              ...(access.activeBranchId
                ? { OR: [{ branchId: access.activeBranchId }, { branchId: null }] }
                : {}),
            },
          },
        },
        orderBy: [{ displayNameEn: "asc" }, { id: "asc" }],
        where: {
          isDoctor: true,
          organizationId: access.organizationId,
          ...(access.activeBranchId
            ? { branchAssignments: { some: { branchId: access.activeBranchId } } }
            : scope === "ASSIGNED_BRANCHES"
              ? { branchAssignments: { some: { branchId: { in: [...access.assignedBranchIds] } } } }
              : {}),
          ...(scope === "SELF"
            ? { id: access.staffProfileId ?? "00000000-0000-0000-0000-000000000000" }
            : {}),
        },
      }),
    );
  }

  async loadDoctorsWorkspace(
    access: TenantAccessSnapshot,
    options: Readonly<{
      includeBranches: boolean;
      includeServices: boolean;
      includeStaff: boolean;
    }>,
  ) {
    const doctorScope = requireAccessPermission(access, "doctors.directory.read");
    const branchScope = options.includeBranches
      ? requireAccessPermission(access, "branches.read")
      : undefined;
    if (options.includeServices) requireAccessPermission(access, "services.read");
    if (options.includeStaff) requireAccessPermission(access, "staff.read");

    return this.runWithAccess(access, async (transaction) => {
      const [doctors, staff, branches, services] = await Promise.all([
        transaction.staffProfile.findMany({
          include: {
            availabilityRules: {
              orderBy: [{ weekday: "asc" }, { startMinuteLocal: "asc" }],
              ...(access.activeBranchId
                ? { where: { OR: [{ branchId: access.activeBranchId }, { branchId: null }] } }
                : {}),
            },
            branchAssignments: { include: { branch: true } },
            breaks: {
              orderBy: [{ weekday: "asc" }, { startMinuteLocal: "asc" }],
              ...(access.activeBranchId ? { where: { branchId: access.activeBranchId } } : {}),
            },
            membership: { include: { roles: { include: { role: true } }, user: true } },
            services: { include: { service: true }, where: { isEnabled: true } },
            timeOffEntries: {
              include: { createdBy: { select: { name: true } } },
              orderBy: { startsAt: "asc" },
              where: {
                endsAt: { gt: new Date() },
                ...(access.activeBranchId
                  ? { OR: [{ branchId: access.activeBranchId }, { branchId: null }] }
                  : {}),
              },
            },
          },
          orderBy: [{ displayNameEn: "asc" }, { id: "asc" }],
          where: {
            isDoctor: true,
            organizationId: access.organizationId,
            ...(access.activeBranchId
              ? { branchAssignments: { some: { branchId: access.activeBranchId } } }
              : doctorScope === "ASSIGNED_BRANCHES"
                ? {
                    branchAssignments: {
                      some: { branchId: { in: [...access.assignedBranchIds] } },
                    },
                  }
                : {}),
            ...(doctorScope === "SELF"
              ? { id: access.staffProfileId ?? "00000000-0000-0000-0000-000000000000" }
              : {}),
          },
        }),
        options.includeStaff
          ? transaction.organizationMembership.findMany({
              orderBy: { createdAt: "desc" },
              select: {
                staffProfile: { select: { id: true } },
                user: { select: { name: true } },
              },
              where: { organizationId: access.organizationId },
            })
          : Promise.resolve([]),
        options.includeBranches
          ? transaction.branch.findMany({
              orderBy: { nameEn: "asc" },
              select: { id: true, nameAr: true, nameEn: true },
              where: {
                organizationId: access.organizationId,
                ...(access.activeBranchId
                  ? { id: access.activeBranchId }
                  : branchScope === "ORGANIZATION"
                    ? {}
                    : { id: { in: [...access.assignedBranchIds] } }),
              },
            })
          : Promise.resolve([]),
        options.includeServices
          ? transaction.service.findMany({
              orderBy: { nameEn: "asc" },
              select: { id: true, nameAr: true, nameEn: true },
              where: {
                ...(access.activeBranchId
                  ? { branches: { some: { branchId: access.activeBranchId, isEnabled: true } } }
                  : {}),
                organizationId: access.organizationId,
              },
            })
          : Promise.resolve([]),
      ]);
      return { branches, doctors, services, staff };
    });
  }

  async configureDoctor(
    access: TenantAccessSnapshot,
    input: Readonly<{
      branchIds: readonly string[];
      displayNameAr: string;
      displayNameEn: string;
      email?: string | undefined;
      isActive: boolean;
      phone?: string | undefined;
      profession?: string | undefined;
      serviceIds: readonly string[];
      specialty?: string | undefined;
      staffProfileId: string;
    }>,
  ) {
    const profileScope = requireAccessPermission(access, "doctors.profile.write");
    if (input.serviceIds.length > 0) requireAccessPermission(access, "doctors.services.assign");
    const branchIds = [...new Set(input.branchIds)];
    const serviceIds = [...new Set(input.serviceIds)];
    if (
      access.activeBranchId &&
      (branchIds.length !== 1 || branchIds[0] !== access.activeBranchId)
    ) {
      throw new DomainError({
        code: "NOT_FOUND",
        message: "Doctor configuration must use the active branch.",
      });
    }
    if (
      (profileScope === "SELF" && input.staffProfileId !== access.staffProfileId) ||
      (profileScope === "ASSIGNED_BRANCHES" &&
        branchIds.some((branchId) => !access.assignedBranchIds.includes(branchId)))
    ) {
      throw new DomainError({ code: "FORBIDDEN", message: "Doctor profile scope is invalid." });
    }
    if (!input.displayNameEn.trim() || !input.displayNameAr.trim() || branchIds.length === 0) {
      throw new DomainError({
        code: "VALIDATION_FAILED",
        message: "Doctor profile is incomplete.",
      });
    }
    return this.runWithAccess(access, async (transaction) => {
      const [profile, branches, services] = await Promise.all([
        transaction.staffProfile.findFirst({
          select: { id: true },
          where: { id: input.staffProfileId, organizationId: access.organizationId },
        }),
        transaction.branch.findMany({
          select: { id: true },
          where: { id: { in: branchIds }, isActive: true, organizationId: access.organizationId },
        }),
        transaction.service.findMany({
          select: { id: true },
          where: { id: { in: serviceIds }, isActive: true, organizationId: access.organizationId },
        }),
      ]);
      if (
        !profile ||
        branches.length !== branchIds.length ||
        services.length !== serviceIds.length
      ) {
        throw new DomainError({
          code: "NOT_FOUND",
          message: "Doctor configuration references are invalid.",
        });
      }
      await transaction.staffProfile.update({
        data: {
          displayNameAr: input.displayNameAr.trim(),
          displayNameEn: input.displayNameEn.trim(),
          email: input.email?.trim().toLowerCase() || null,
          isActive: input.isActive,
          isBookable: input.isActive,
          isDoctor: true,
          phone: input.phone?.trim() || null,
          profession: input.profession?.trim() || null,
          specialty: input.specialty?.trim() || null,
        },
        where: { id: profile.id },
      });
      await transaction.staffBranchAssignment.deleteMany({
        where: {
          ...(access.activeBranchId ? { branchId: access.activeBranchId } : {}),
          organizationId: access.organizationId,
          staffProfileId: profile.id,
        },
      });
      await transaction.staffBranchAssignment.createMany({
        data: branchIds.map((branchId) => ({
          branchId,
          organizationId: access.organizationId,
          staffProfileId: profile.id,
        })),
      });
      await transaction.staffService.updateMany({
        data: { isEnabled: false },
        where: { organizationId: access.organizationId, staffProfileId: profile.id },
      });
      for (const serviceId of serviceIds) {
        await transaction.staffService.upsert({
          create: {
            isEnabled: true,
            organizationId: access.organizationId,
            serviceId,
            staffProfileId: profile.id,
          },
          update: { isEnabled: true },
          where: {
            organizationId_staffProfileId_serviceId: {
              organizationId: access.organizationId,
              serviceId,
              staffProfileId: profile.id,
            },
          },
        });
      }
      await createAuditEvent(transaction, {
        action: "DOCTOR_PROFILE_CONFIGURED",
        actorUserId: access.actorUserId,
        metadata: { active: input.isActive, branchIds, serviceIds },
        organizationId: access.organizationId,
        supportAccessId: access.supportAccessId,
        targetId: profile.id,
        targetType: "StaffProfile",
      });
      return profile;
    });
  }

  async replaceDoctorSchedule(
    access: TenantAccessSnapshot,
    input: Readonly<{
      branchId: string;
      breaks: readonly Readonly<{
        endMinuteLocal: number;
        label?: string | undefined;
        startMinuteLocal: number;
        weekday: Prisma.AvailabilityRuleCreateInput["weekday"];
      }>[];
      confirmAffected: boolean;
      periods: readonly Readonly<{
        endMinuteLocal: number;
        startMinuteLocal: number;
        weekday: Prisma.AvailabilityRuleCreateInput["weekday"];
      }>[];
      staffProfileId: string;
    }>,
  ) {
    const scheduleScope = requireAccessPermission(access, "doctors.schedule.write");
    if (
      (access.activeBranchId && input.branchId !== access.activeBranchId) ||
      (scheduleScope === "SELF" && input.staffProfileId !== access.staffProfileId) ||
      (scheduleScope === "ASSIGNED_BRANCHES" && !access.assignedBranchIds.includes(input.branchId))
    ) {
      throw new DomainError({ code: "FORBIDDEN", message: "Doctor schedule scope is invalid." });
    }
    const invalidPeriod = input.periods.some(
      (period) =>
        !Number.isInteger(period.startMinuteLocal) ||
        !Number.isInteger(period.endMinuteLocal) ||
        period.startMinuteLocal < 0 ||
        period.endMinuteLocal > 1440 ||
        period.startMinuteLocal >= period.endMinuteLocal,
    );
    const overlappingPeriods = input.periods.some((period, index) =>
      input.periods.some(
        (other, otherIndex) =>
          index !== otherIndex &&
          period.weekday === other.weekday &&
          period.startMinuteLocal < other.endMinuteLocal &&
          period.endMinuteLocal > other.startMinuteLocal,
      ),
    );
    const invalidBreak = input.breaks.some(
      (entry, index) =>
        entry.startMinuteLocal >= entry.endMinuteLocal ||
        !input.periods.some(
          (period) =>
            period.weekday === entry.weekday &&
            period.startMinuteLocal <= entry.startMinuteLocal &&
            period.endMinuteLocal >= entry.endMinuteLocal,
        ) ||
        input.breaks.some(
          (other, otherIndex) =>
            index !== otherIndex &&
            entry.weekday === other.weekday &&
            entry.startMinuteLocal < other.endMinuteLocal &&
            entry.endMinuteLocal > other.startMinuteLocal,
        ),
    );
    if (invalidPeriod || overlappingPeriods || invalidBreak) {
      throw new DomainError({
        code: "VALIDATION_FAILED",
        message: "Doctor schedule or breaks are invalid.",
      });
    }
    return this.runWithAccess(access, async (transaction) => {
      const [doctor, branch] = await Promise.all([
        transaction.staffProfile.findFirst({
          select: { id: true },
          where: {
            id: input.staffProfileId,
            isDoctor: true,
            organizationId: access.organizationId,
          },
        }),
        transaction.branch.findFirst({
          include: { hoursRules: true },
          where: { id: input.branchId, isActive: true, organizationId: access.organizationId },
        }),
      ]);
      if (!doctor || !branch)
        throw new DomainError({ code: "NOT_FOUND", message: "Doctor or branch not found." });
      if (
        !input.periods.every((period) =>
          branch.hoursRules.some(
            (hours) =>
              hours.weekday === period.weekday &&
              hours.startMinuteLocal <= period.startMinuteLocal &&
              hours.endMinuteLocal >= period.endMinuteLocal,
          ),
        )
      ) {
        throw new DomainError({
          code: "VALIDATION_FAILED",
          message: "Doctor hours must fit within branch hours.",
        });
      }
      const future = await transaction.appointment.findMany({
        orderBy: { startsAt: "asc" },
        select: { id: true, referenceCode: true, startsAt: true },
        take: 100,
        where: {
          branchId: input.branchId,
          organizationId: access.organizationId,
          providerId: doctor.id,
          startsAt: { gt: new Date() },
          status: { in: ["PENDING", "CONFIRMED", "CHECKED_IN"] },
        },
      });
      if (future.length > 0 && !input.confirmAffected)
        return { affectedAppointments: future, updated: false };
      await transaction.availabilityRule.deleteMany({
        where: {
          branchId: input.branchId,
          organizationId: access.organizationId,
          staffProfileId: doctor.id,
        },
      });
      await transaction.doctorBreak.deleteMany({
        where: {
          branchId: input.branchId,
          organizationId: access.organizationId,
          staffProfileId: doctor.id,
        },
      });
      if (input.periods.length > 0)
        await transaction.availabilityRule.createMany({
          data: input.periods.map((period) => ({
            ...period,
            branchId: input.branchId,
            organizationId: access.organizationId,
            staffProfileId: doctor.id,
          })),
        });
      if (input.breaks.length > 0)
        await transaction.doctorBreak.createMany({
          data: input.breaks.map((entry) => ({
            ...entry,
            branchId: input.branchId,
            label: entry.label ?? null,
            organizationId: access.organizationId,
            staffProfileId: doctor.id,
          })),
        });
      await createAuditEvent(transaction, {
        action: "DOCTOR_SCHEDULE_REPLACED",
        actorUserId: access.actorUserId,
        metadata: { affectedAppointmentIds: future.map(({ id }) => id), branchId: input.branchId },
        organizationId: access.organizationId,
        supportAccessId: access.supportAccessId,
        targetId: doctor.id,
        targetType: "StaffProfile",
      });
      return { affectedAppointments: future, updated: true };
    });
  }

  async addDoctorTimeOff(
    access: TenantAccessSnapshot,
    input: Readonly<{
      branchId?: string | undefined;
      confirmAffected: boolean;
      endsAt: Date;
      reason: string;
      staffProfileId: string;
      startsAt: Date;
    }>,
  ) {
    const timeOffScope = requireAccessPermission(access, "doctors.time_off.write");
    if (
      (access.activeBranchId && input.branchId !== access.activeBranchId) ||
      (timeOffScope === "SELF" && input.staffProfileId !== access.staffProfileId) ||
      (timeOffScope === "ASSIGNED_BRANCHES" &&
        (!input.branchId || !access.assignedBranchIds.includes(input.branchId)))
    ) {
      throw new DomainError({ code: "FORBIDDEN", message: "Doctor time-off scope is invalid." });
    }
    if (input.endsAt <= input.startsAt || !input.reason.trim())
      throw new DomainError({ code: "VALIDATION_FAILED", message: "Doctor time off is invalid." });
    return this.runWithAccess(access, async (transaction) => {
      const doctor = await transaction.staffProfile.findFirst({
        select: { id: true },
        where: { id: input.staffProfileId, isDoctor: true, organizationId: access.organizationId },
      });
      if (!doctor) throw new DomainError({ code: "NOT_FOUND", message: "Doctor not found." });
      const affectedAppointments = await transaction.appointment.findMany({
        orderBy: { startsAt: "asc" },
        select: { id: true, referenceCode: true, startsAt: true },
        where: {
          ...(input.branchId ? { branchId: input.branchId } : {}),
          endsAt: { gt: input.startsAt },
          providerId: doctor.id,
          startsAt: { lt: input.endsAt },
          status: { in: ["PENDING", "CONFIRMED", "CHECKED_IN"] },
        },
      });
      if (affectedAppointments.length > 0 && !input.confirmAffected)
        return { affectedAppointments, created: false };
      const entry = await transaction.timeOff.create({
        data: {
          branchId: input.branchId ?? null,
          createdByUserId: access.actorUserId,
          endsAt: input.endsAt,
          organizationId: access.organizationId,
          reason: input.reason.trim(),
          staffProfileId: doctor.id,
          startsAt: input.startsAt,
        },
      });
      await createAuditEvent(transaction, {
        action: "DOCTOR_TIME_OFF_CREATED",
        actorUserId: access.actorUserId,
        metadata: { affectedAppointmentIds: affectedAppointments.map(({ id }) => id) },
        organizationId: access.organizationId,
        supportAccessId: access.supportAccessId,
        targetId: entry.id,
        targetType: "TimeOff",
      });
      return { affectedAppointments, created: true };
    });
  }

  async listInvitations(access: TenantAccessSnapshot) {
    requireAccessPermission(access, "staff.manage");
    return this.runWithAccess(access, (transaction) =>
      transaction.organizationInvitation.findMany({
        orderBy: { createdAt: "desc" },
        select: {
          createdAt: true,
          email: true,
          expiresAt: true,
          id: true,
          role: { select: { nameAr: true, nameEn: true } },
          status: true,
        },
        where: { organizationId: access.organizationId },
      }),
    );
  }

  async createInvitation(
    access: TenantAccessSnapshot,
    email: string,
    roleId: string,
  ): Promise<string> {
    requireAccessPermission(access, "staff.manage");
    const token = createInvitationToken();
    await this.runWithAccess(access, async (transaction) => {
      const role = await transaction.role.findFirst({
        select: { id: true, systemKey: true },
        where: { id: roleId, organizationId: access.organizationId },
      });
      if (!role) {
        throw new DomainError({ code: "NOT_FOUND", message: "Role not found." });
      }
      if (role.systemKey === "ORGANIZATION_OWNER") {
        const actorIsOwner = access.membershipId
          ? await transaction.organizationMembership.count({
              where: {
                id: access.membershipId,
                organizationId: access.organizationId,
                roles: { some: { role: { systemKey: "ORGANIZATION_OWNER" } } },
                status: MembershipStatus.ACTIVE,
              },
            })
          : 0;
        if (actorIsOwner === 0) {
          throw new DomainError({
            code: "FORBIDDEN",
            message: "Only an active organization owner can invite another owner.",
          });
        }
      }
      if (role.systemKey !== "SECRETARY" && role.systemKey !== "PROVIDER") {
        requireAccessPermission(access, "roles.manage");
      }
      await transaction.organizationInvitation.updateMany({
        data: { status: InvitationStatus.EXPIRED },
        where: {
          email: normalizedEmail(email),
          expiresAt: { lte: new Date() },
          organizationId: access.organizationId,
          status: InvitationStatus.PENDING,
        },
      });
      const invitation = await transaction.organizationInvitation.create({
        data: {
          email: normalizedEmail(email),
          expiresAt: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000),
          invitedByUserId: access.actorUserId,
          organizationId: access.organizationId,
          roleId,
          tokenHash: hashInvitationToken(token),
        },
      });
      await createAuditEvent(transaction, {
        action: "STAFF_INVITED",
        actorUserId: access.actorUserId,
        organizationId: access.organizationId,
        supportAccessId: access.supportAccessId,
        targetId: invitation.id,
        targetType: "OrganizationInvitation",
      });
    });
    return token;
  }

  async revokeInvitation(access: TenantAccessSnapshot, invitationId: string): Promise<void> {
    requireAccessPermission(access, "staff.manage");
    await this.runWithAccess(access, async (transaction) => {
      await transaction.organizationInvitation.updateMany({
        data: { status: InvitationStatus.REVOKED },
        where: {
          id: invitationId,
          organizationId: access.organizationId,
          status: InvitationStatus.PENDING,
        },
      });
      await createAuditEvent(transaction, {
        action: "INVITATION_REVOKED",
        actorUserId: access.actorUserId,
        organizationId: access.organizationId,
        supportAccessId: access.supportAccessId,
        targetId: invitationId,
        targetType: "OrganizationInvitation",
      });
    });
  }

  async previewInvitation(token: string): Promise<InvitationPreview> {
    const invitation = await this.client.organizationInvitation.findUnique({
      include: { organization: true, role: true },
      where: { tokenHash: hashInvitationToken(token) },
    });
    if (!invitation) {
      throw new DomainError({ code: "INVITATION_INVALID", message: "Invitation is invalid." });
    }
    if (invitation.status !== InvitationStatus.PENDING) {
      throw new DomainError({
        code: "INVITATION_ALREADY_USED",
        message: "Invitation has already been used or revoked.",
      });
    }
    if (invitation.expiresAt <= new Date()) {
      throw new DomainError({ code: "INVITATION_EXPIRED", message: "Invitation has expired." });
    }
    if (invitation.organization.status === OrganizationStatus.SUSPENDED) {
      throw new DomainError({
        code: "ORGANIZATION_SUSPENDED",
        message: "The organization is suspended.",
      });
    }
    return {
      email: invitation.email,
      expiresAt: invitation.expiresAt,
      organizationId: invitation.organizationId,
      organizationNameAr: invitation.organization.nameAr,
      organizationNameEn: invitation.organization.nameEn,
      roleNameAr: invitation.role.nameAr,
      roleNameEn: invitation.role.nameEn,
      status: invitation.status,
    };
  }

  async acceptInvitation(
    userId: string,
    userEmail: string,
    token: string,
    options: Readonly<{ accountCreated?: boolean }> = {},
  ): Promise<Readonly<{ membershipId: string; organizationId: string }>> {
    const tokenHash = hashInvitationToken(token);
    const invitation = await this.client.organizationInvitation.findUnique({
      include: { role: true },
      where: { tokenHash },
    });
    if (!invitation || invitation.email !== normalizedEmail(userEmail)) {
      throw new DomainError({ code: "INVITATION_INVALID", message: "Invitation is invalid." });
    }
    if (invitation.status !== InvitationStatus.PENDING) {
      throw new DomainError({
        code: "INVITATION_ALREADY_USED",
        message: "Invitation has already been used or revoked.",
      });
    }
    if (invitation.expiresAt <= new Date()) {
      throw new DomainError({ code: "INVITATION_EXPIRED", message: "Invitation has expired." });
    }

    return runInTenant(
      this.client,
      { actorUserId: userId, organizationId: invitation.organizationId },
      async (transaction) => {
        const organization = await transaction.organization.findUnique({
          select: { status: true },
          where: { id: invitation.organizationId },
        });
        if (!organization) {
          throw new DomainError({ code: "NOT_FOUND", message: "Organization not found." });
        }
        if (organization.status === OrganizationStatus.SUSPENDED) {
          throw new DomainError({
            code: "ORGANIZATION_SUSPENDED",
            message: "The organization is suspended.",
          });
        }
        const consumed = await transaction.organizationInvitation.updateMany({
          data: {
            acceptedAt: new Date(),
            acceptedByUserId: userId,
            status: InvitationStatus.ACCEPTED,
          },
          where: {
            expiresAt: { gt: new Date() },
            id: invitation.id,
            organizationId: invitation.organizationId,
            status: InvitationStatus.PENDING,
            tokenHash,
          },
        });
        if (consumed.count !== 1) {
          throw new DomainError({
            code: "INVITATION_ALREADY_USED",
            message: "Invitation has already been used.",
          });
        }

        const existing = await transaction.organizationMembership.findUnique({
          where: {
            organizationId_userId: { organizationId: invitation.organizationId, userId },
          },
        });
        if (existing && existing.status !== MembershipStatus.ACTIVE) {
          throw new DomainError({
            code: "MEMBERSHIP_SUSPENDED",
            message: "A suspended or revoked membership cannot be restored by invitation.",
          });
        }
        const membership =
          existing ??
          (await transaction.organizationMembership.create({
            data: { organizationId: invitation.organizationId, userId },
          }));
        await transaction.membershipRole.upsert({
          create: {
            membershipId: membership.id,
            organizationId: invitation.organizationId,
            roleId: invitation.roleId,
          },
          update: {},
          where: {
            organizationId_membershipId_roleId: {
              membershipId: membership.id,
              organizationId: invitation.organizationId,
              roleId: invitation.roleId,
            },
          },
        });
        if (options.accountCreated) {
          await createAuditEvent(transaction, {
            action: "ACCOUNT_CREATED_FROM_INVITATION",
            actorUserId: userId,
            organizationId: invitation.organizationId,
            targetId: userId,
            targetType: "User",
          });
        }
        await createAuditEvent(transaction, {
          action: "MEMBERSHIP_ROLE_ASSIGNED",
          actorUserId: userId,
          metadata: {
            invitationId: invitation.id,
            roleId: invitation.roleId,
            systemRole: invitation.role.systemKey,
          },
          organizationId: invitation.organizationId,
          targetId: membership.id,
          targetType: "OrganizationMembership",
        });
        if (
          invitation.role.systemKey === "ORGANIZATION_MANAGER" ||
          invitation.role.systemKey === "SECRETARY" ||
          invitation.role.systemKey === "PROVIDER"
        ) {
          const [user, activeBranches] = await Promise.all([
            transaction.user.findUnique({ where: { id: userId } }),
            transaction.branch.findMany({
              select: { id: true },
              take: 2,
              where: { isActive: true, organizationId: invitation.organizationId },
            }),
          ]);
          if (!user) {
            throw new DomainError({ code: "NOT_FOUND", message: "User not found." });
          }
          const profile = await transaction.staffProfile.upsert({
            create: {
              displayNameAr: user.name,
              displayNameEn: user.name,
              isBookable: invitation.role.systemKey === "PROVIDER",
              membershipId: membership.id,
              organizationId: invitation.organizationId,
            },
            update: {},
            where: { membershipId: membership.id },
          });
          if (activeBranches.length === 1 && activeBranches[0]) {
            await transaction.staffBranchAssignment.upsert({
              create: {
                branchId: activeBranches[0].id,
                organizationId: invitation.organizationId,
                staffProfileId: profile.id,
              },
              update: {},
              where: {
                organizationId_staffProfileId_branchId: {
                  branchId: activeBranches[0].id,
                  organizationId: invitation.organizationId,
                  staffProfileId: profile.id,
                },
              },
            });
          }
        }
        await createAuditEvent(transaction, {
          action: "INVITATION_ACCEPTED",
          actorUserId: userId,
          organizationId: invitation.organizationId,
          targetId: invitation.id,
          targetType: "OrganizationInvitation",
        });
        return { membershipId: membership.id, organizationId: invitation.organizationId };
      },
    );
  }

  async setMembershipStatus(
    access: TenantAccessSnapshot,
    membershipId: string,
    status: MembershipStatus,
  ): Promise<void> {
    requireAccessPermission(access, "staff.manage");
    if (membershipId === access.membershipId && status !== MembershipStatus.ACTIVE) {
      throw new DomainError({ code: "CONFLICT", message: "You cannot suspend yourself." });
    }
    await this.runWithAccess(access, async (transaction) => {
      const target = await transaction.organizationMembership.findFirst({
        include: { roles: { include: { role: true } } },
        where: { id: membershipId, organizationId: access.organizationId },
      });
      if (!target) {
        throw new DomainError({ code: "NOT_FOUND", message: "Membership not found." });
      }
      const isOwner = target.roles.some(({ role }) => role.systemKey === "ORGANIZATION_OWNER");
      if (isOwner) {
        requireAccessPermission(access, "roles.manage");
        if (status !== MembershipStatus.ACTIVE) {
          const otherOwners = await transaction.organizationMembership.count({
            where: {
              id: { not: membershipId },
              organizationId: access.organizationId,
              roles: { some: { role: { systemKey: "ORGANIZATION_OWNER" } } },
              status: MembershipStatus.ACTIVE,
            },
          });
          if (otherOwners === 0) {
            throw new DomainError({
              code: "CONFLICT",
              message: "The organization must retain at least one active owner.",
            });
          }
        }
      }
      const updated = await transaction.organizationMembership.updateMany({
        data: {
          status,
          suspendedAt: status === MembershipStatus.SUSPENDED ? new Date() : null,
        },
        where: { id: membershipId, organizationId: access.organizationId },
      });
      if (updated.count !== 1) {
        throw new DomainError({ code: "NOT_FOUND", message: "Membership not found." });
      }
      await createAuditEvent(transaction, {
        action: `MEMBERSHIP_${status}`,
        actorUserId: access.actorUserId,
        organizationId: access.organizationId,
        supportAccessId: access.supportAccessId,
        targetId: membershipId,
        targetType: "OrganizationMembership",
      });
    });
  }

  async replaceMembershipRole(
    access: TenantAccessSnapshot,
    membershipId: string,
    roleId: string,
  ): Promise<void> {
    requireAccessPermission(access, "roles.manage");
    await this.runWithAccess(access, async (transaction) => {
      const [membership, role] = await Promise.all([
        transaction.organizationMembership.findFirst({
          include: { roles: { include: { role: true } } },
          where: { id: membershipId, organizationId: access.organizationId },
        }),
        transaction.role.findFirst({
          where: { id: roleId, organizationId: access.organizationId },
        }),
      ]);
      if (!membership || !role) {
        throw new DomainError({ code: "NOT_FOUND", message: "Membership or role not found." });
      }
      const wasOwner = membership.roles.some(
        ({ role: currentRole }) => currentRole.systemKey === "ORGANIZATION_OWNER",
      );
      if (wasOwner && role.systemKey !== "ORGANIZATION_OWNER") {
        const otherOwners = await transaction.organizationMembership.count({
          where: {
            id: { not: membershipId },
            organizationId: access.organizationId,
            roles: { some: { role: { systemKey: "ORGANIZATION_OWNER" } } },
            status: MembershipStatus.ACTIVE,
          },
        });
        if (otherOwners === 0) {
          throw new DomainError({
            code: "CONFLICT",
            message: "The organization must retain at least one active owner.",
          });
        }
      }
      await transaction.membershipRole.deleteMany({
        where: { membershipId, organizationId: access.organizationId },
      });
      await transaction.membershipRole.create({
        data: { membershipId, organizationId: access.organizationId, roleId },
      });
      await createAuditEvent(transaction, {
        action: "MEMBERSHIP_ROLE_REPLACED",
        actorUserId: access.actorUserId,
        organizationId: access.organizationId,
        supportAccessId: access.supportAccessId,
        targetId: membershipId,
        targetType: "OrganizationMembership",
      });
    });
  }

  async listServices(access: TenantAccessSnapshot) {
    requireAccessPermission(access, "services.read");
    return this.runWithAccess(access, (transaction) =>
      transaction.service.findMany({
        include: {
          branches: {
            include: { branch: true },
            ...(access.activeBranchId ? { where: { branchId: access.activeBranchId } } : {}),
          },
          roomCompatibilities: {
            include: { resource: true },
            ...(access.activeBranchId
              ? { where: { resource: { branchId: access.activeBranchId } } }
              : {}),
          },
          staffServices: {
            include: { staffProfile: true },
            where: {
              isEnabled: true,
              staffProfile: {
                isActive: true,
                isDoctor: true,
                ...(access.activeBranchId
                  ? { branchAssignments: { some: { branchId: access.activeBranchId } } }
                  : {}),
              },
            },
          },
        },
        orderBy: { nameEn: "asc" },
        where: { organizationId: access.organizationId },
      }),
    );
  }

  async createService(
    access: TenantAccessSnapshot,
    input: Readonly<{
      currency: string;
      category?: string | undefined;
      configurationStatus?: ConfigurationApprovalStatus | undefined;
      defaultDurationMins: number;
      defaultPriceMinor?: number | undefined;
      descriptionAr?: string | undefined;
      descriptionEn?: string | undefined;
      isOnlineBookable?: boolean | undefined;
      minimumNoticeMins?: number | null | undefined;
      nameAr: string;
      nameEn: string;
      postTreatmentInstructionsAr?: string | undefined;
      postTreatmentInstructionsEn?: string | undefined;
      preTreatmentInstructionsAr?: string | undefined;
      preTreatmentInstructionsEn?: string | undefined;
    }>,
  ): Promise<void> {
    requireAccessPermission(access, "services.manage");
    await this.runWithAccess(access, async (transaction) => {
      const service = await transaction.service.create({
        data: {
          currency: input.currency,
          category: input.category ?? "Beauty Treatment",
          configurationStatus: input.configurationStatus ?? ConfigurationApprovalStatus.DRAFT,
          defaultDurationMins: input.defaultDurationMins,
          defaultPriceMinor: input.defaultPriceMinor ?? null,
          descriptionAr: input.descriptionAr ?? null,
          descriptionEn: input.descriptionEn ?? null,
          isOnlineBookable: input.isOnlineBookable ?? false,
          minimumNoticeMins: input.minimumNoticeMins === undefined ? 0 : input.minimumNoticeMins,
          nameAr: input.nameAr,
          nameEn: input.nameEn,
          organizationId: access.organizationId,
          postTreatmentInstructionsAr: input.postTreatmentInstructionsAr ?? null,
          postTreatmentInstructionsEn: input.postTreatmentInstructionsEn ?? null,
          preTreatmentInstructionsAr: input.preTreatmentInstructionsAr ?? null,
          preTreatmentInstructionsEn: input.preTreatmentInstructionsEn ?? null,
        },
      });
      await createAuditEvent(transaction, {
        action: "SERVICE_CREATED",
        actorUserId: access.actorUserId,
        organizationId: access.organizationId,
        supportAccessId: access.supportAccessId,
        targetId: service.id,
        targetType: "Service",
      });
    });
  }

  async updateService(
    access: TenantAccessSnapshot,
    serviceId: string,
    input: Readonly<{
      category: string;
      configurationStatus: ConfigurationApprovalStatus;
      defaultDurationMins: number;
      descriptionAr: string;
      descriptionEn: string;
      isOnlineBookable: boolean;
      isActive: boolean;
      minimumNoticeMins: number | null;
      nameAr: string;
      nameEn: string;
      postTreatmentInstructionsAr: string;
      postTreatmentInstructionsEn: string;
      preTreatmentInstructionsAr: string;
      preTreatmentInstructionsEn: string;
    }>,
  ): Promise<void> {
    requireAccessPermission(access, "services.manage");
    await this.runWithAccess(access, async (transaction) => {
      const updated = await transaction.service.updateMany({
        data: input,
        where: { id: serviceId, organizationId: access.organizationId },
      });
      if (updated.count !== 1) {
        throw new DomainError({ code: "NOT_FOUND", message: "Service not found." });
      }
      await createAuditEvent(transaction, {
        action: "SERVICE_UPDATED",
        actorUserId: access.actorUserId,
        organizationId: access.organizationId,
        supportAccessId: access.supportAccessId,
        targetId: serviceId,
        targetType: "Service",
      });
    });
  }

  async configureServiceBranch(
    access: TenantAccessSnapshot,
    input: Readonly<{
      branchId: string;
      bookingWindowDays?: number | undefined;
      bufferAfterMins?: number | undefined;
      bufferBeforeMins?: number | undefined;
      durationMins?: number | undefined;
      isEnabled: boolean;
      priceMinor?: number | undefined;
      serviceId: string;
    }>,
  ): Promise<void> {
    requireAccessPermission(access, "services.manage");
    if (access.activeBranchId && input.branchId !== access.activeBranchId) {
      throw new DomainError({
        code: "NOT_FOUND",
        message: "Service configuration must use the active branch.",
      });
    }
    await this.runWithAccess(access, async (transaction) => {
      const [branch, service] = await Promise.all([
        transaction.branch.findFirst({
          where: { id: input.branchId, organizationId: access.organizationId },
        }),
        transaction.service.findFirst({
          where: { id: input.serviceId, organizationId: access.organizationId },
        }),
      ]);
      if (!branch || !service) {
        throw new DomainError({ code: "NOT_FOUND", message: "Branch or service not found." });
      }
      await transaction.serviceBranch.upsert({
        create: {
          branchId: input.branchId,
          bookingWindowDays: input.bookingWindowDays ?? null,
          bufferAfterMins: input.bufferAfterMins ?? 0,
          bufferBeforeMins: input.bufferBeforeMins ?? 0,
          durationMins: input.durationMins ?? null,
          isEnabled: input.isEnabled,
          organizationId: access.organizationId,
          priceMinor: input.priceMinor ?? null,
          serviceId: input.serviceId,
        },
        update: {
          bookingWindowDays: input.bookingWindowDays ?? null,
          ...(input.bufferAfterMins === undefined
            ? {}
            : { bufferAfterMins: input.bufferAfterMins }),
          ...(input.bufferBeforeMins === undefined
            ? {}
            : { bufferBeforeMins: input.bufferBeforeMins }),
          durationMins: input.durationMins ?? null,
          isEnabled: input.isEnabled,
          priceMinor: input.priceMinor ?? null,
        },
        where: {
          organizationId_serviceId_branchId: {
            branchId: input.branchId,
            organizationId: access.organizationId,
            serviceId: input.serviceId,
          },
        },
      });
      await createAuditEvent(transaction, {
        action: "SERVICE_BRANCH_CONFIGURED",
        actorUserId: access.actorUserId,
        organizationId: access.organizationId,
        supportAccessId: access.supportAccessId,
        targetId: input.serviceId,
        targetType: "Service",
      });
    });
  }

  async listAvailabilityRules(access: TenantAccessSnapshot, staffProfileId?: string) {
    const scope = requireAccessPermission(access, "schedules.read");
    if (scope === "SELF" && staffProfileId && staffProfileId !== access.staffProfileId) {
      throw new DomainError({ code: "FORBIDDEN", message: "Schedule access is self-scoped." });
    }
    const effectiveStaffProfileId = scope === "SELF" ? access.staffProfileId : staffProfileId;
    if (scope === "SELF" && !effectiveStaffProfileId) {
      throw new DomainError({ code: "FORBIDDEN", message: "A staff profile is required." });
    }
    return this.runWithAccess(access, (transaction) =>
      transaction.availabilityRule.findMany({
        include: { branch: true, staffProfile: true },
        orderBy: [{ staffProfileId: "asc" }, { weekday: "asc" }, { startMinuteLocal: "asc" }],
        where: {
          organizationId: access.organizationId,
          ...(effectiveStaffProfileId ? { staffProfileId: effectiveStaffProfileId } : {}),
          ...(scope === "ASSIGNED_BRANCHES"
            ? { branchId: { in: [...access.assignedBranchIds] } }
            : {}),
        },
      }),
    );
  }

  async configureProviderBooking(
    access: TenantAccessSnapshot,
    input: Readonly<{
      branchId: string;
      rules: readonly Readonly<{
        endMinuteLocal: number;
        startMinuteLocal: number;
        weekday: Prisma.AvailabilityRuleCreateInput["weekday"];
      }>[];
      serviceIds: readonly string[];
      staffProfileId: string;
    }>,
  ): Promise<void> {
    requireAccessPermission(access, "staff.manage");
    requireAccessPermission(access, "schedules.manage");
    const weekdays = new Set<string>();
    if (
      input.serviceIds.length === 0 ||
      input.serviceIds.length > 100 ||
      input.rules.length === 0 ||
      input.rules.length > 7 ||
      input.rules.some((rule) => {
        const invalid =
          !Number.isInteger(rule.startMinuteLocal) ||
          !Number.isInteger(rule.endMinuteLocal) ||
          rule.startMinuteLocal < 0 ||
          rule.startMinuteLocal >= rule.endMinuteLocal ||
          rule.endMinuteLocal > 1440 ||
          weekdays.has(rule.weekday);
        weekdays.add(rule.weekday);
        return invalid;
      })
    ) {
      throw new DomainError({
        code: "VALIDATION_FAILED",
        message: "The service provider schedule is invalid.",
      });
    }
    await this.runWithAccess(access, async (transaction) => {
      const [provider, branch, services] = await Promise.all([
        transaction.staffProfile.findFirst({
          select: { id: true },
          where: {
            id: input.staffProfileId,
            isBookable: true,
            organizationId: access.organizationId,
          },
        }),
        transaction.branch.findFirst({
          include: { hoursRules: true },
          where: { id: input.branchId, isActive: true, organizationId: access.organizationId },
        }),
        transaction.service.findMany({
          select: { id: true },
          where: {
            branches: { some: { branchId: input.branchId, isEnabled: true } },
            id: { in: [...new Set(input.serviceIds)] },
            isActive: true,
            organizationId: access.organizationId,
          },
        }),
      ]);
      if (!provider || !branch || services.length !== new Set(input.serviceIds).size) {
        throw new DomainError({
          code: "NOT_FOUND",
          message: "The provider, branch, or service configuration was not found.",
        });
      }
      const scheduleFitsBranch = input.rules.every((rule) =>
        branch.hoursRules.some(
          (hours) =>
            hours.weekday === rule.weekday &&
            hours.startMinuteLocal <= rule.startMinuteLocal &&
            hours.endMinuteLocal >= rule.endMinuteLocal,
        ),
      );
      if (!scheduleFitsBranch) {
        throw new DomainError({
          code: "VALIDATION_FAILED",
          message: "Provider working hours must fit within branch working hours.",
        });
      }
      await transaction.staffBranchAssignment.upsert({
        create: {
          branchId: input.branchId,
          organizationId: access.organizationId,
          staffProfileId: input.staffProfileId,
        },
        update: {},
        where: {
          organizationId_staffProfileId_branchId: {
            branchId: input.branchId,
            organizationId: access.organizationId,
            staffProfileId: input.staffProfileId,
          },
        },
      });
      for (const service of services) {
        await transaction.staffService.upsert({
          create: {
            isEnabled: true,
            organizationId: access.organizationId,
            serviceId: service.id,
            staffProfileId: input.staffProfileId,
          },
          update: { isEnabled: true },
          where: {
            organizationId_staffProfileId_serviceId: {
              organizationId: access.organizationId,
              serviceId: service.id,
              staffProfileId: input.staffProfileId,
            },
          },
        });
      }
      await transaction.availabilityRule.deleteMany({
        where: {
          branchId: input.branchId,
          organizationId: access.organizationId,
          staffProfileId: input.staffProfileId,
        },
      });
      await transaction.availabilityRule.createMany({
        data: input.rules.map((rule) => ({
          ...rule,
          branchId: input.branchId,
          organizationId: access.organizationId,
          staffProfileId: input.staffProfileId,
        })),
      });
      await createAuditEvent(transaction, {
        action: "PROVIDER_BOOKING_CONFIGURATION_UPDATED",
        actorUserId: access.actorUserId,
        metadata: {
          branchId: input.branchId,
          serviceIds: services.map(({ id }) => id),
          weekdays: input.rules.map(({ weekday }) => weekday),
        },
        organizationId: access.organizationId,
        supportAccessId: access.supportAccessId,
        targetId: input.staffProfileId,
        targetType: "StaffProfile",
      });
    });
  }

  async createAvailabilityRule(
    access: TenantAccessSnapshot,
    input: Readonly<{
      branchId?: string;
      endMinuteLocal: number;
      staffProfileId: string;
      startMinuteLocal: number;
      weekday: Prisma.AvailabilityRuleCreateInput["weekday"];
    }>,
  ): Promise<void> {
    const scope = requireAccessPermission(access, "schedules.manage");
    if (scope === "SELF" && input.staffProfileId !== access.staffProfileId) {
      throw new DomainError({ code: "FORBIDDEN", message: "Schedule access is self-scoped." });
    }
    if (
      scope !== "ORGANIZATION" &&
      (!input.branchId || !access.assignedBranchIds.includes(input.branchId))
    ) {
      throw new DomainError({
        code: "FORBIDDEN",
        message: "Schedule access is limited to assigned branches.",
      });
    }
    await this.runWithAccess(access, async (transaction) => {
      await transaction.availabilityRule.create({
        data: { ...input, organizationId: access.organizationId },
      });
    });
  }
}
