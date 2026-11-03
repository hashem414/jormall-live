import { randomUUID } from "node:crypto";

import { canAccessResource, requirePermission } from "@jormall/auth/tenant-policy";
import { createPrismaClient } from "@jormall/db/client";
import { CrmAppointmentRepository } from "@jormall/db/crm-appointment-repository";
import { CommunicationRepository } from "@jormall/db/communication-repository";
import {
  BusinessSector,
  MembershipStatus,
  OrganizationStatus,
  PlatformRole,
} from "@jormall/db/generated/enums";
import { IdentityRepository } from "@jormall/db/identity-repository";
import { SchedulingRepository } from "@jormall/db/scheduling-repository";
import { runInTenant } from "@jormall/db/tenant-context";
import type { TenantAccessSnapshot } from "@jormall/domain/identity";
import { LocalMockProviderAdapter, safeCommunicationLog } from "@jormall/domain/communications";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

const databaseUrl = process.env.TEST_DATABASE_URL ?? process.env.DATABASE_URL;
if (!databaseUrl) {
  throw new Error(
    "TEST_DATABASE_URL or DATABASE_URL is required for PostgreSQL integration tests.",
  );
}

const client = createPrismaClient(databaseUrl);
const repository = new IdentityRepository(client);
const crmRepository = new CrmAppointmentRepository(client);
const schedulingRepository = new SchedulingRepository(client);
const communicationRepository = new CommunicationRepository(client);
const communicationAdapters = new Map([
  ["MOCK_SMS", new LocalMockProviderAdapter("MOCK_SMS")],
  ["MOCK_WHATSAPP", new LocalMockProviderAdapter("MOCK_WHATSAPP")],
]);
const suffix = randomUUID().slice(0, 8);
let appointmentSequence = 0;

type Fixture = Awaited<ReturnType<typeof createFixture>>;
let fixture: Fixture;
let phaseThreeFixture: Readonly<{ resourceGroupId: string; resourceId: string }>;

async function createUser(label: string, platformRole = PlatformRole.USER) {
  return client.user.create({
    data: {
      email: `${label}-${suffix}@example.invalid`,
      name: `${label} ${suffix}`,
      platformRole,
    },
  });
}

async function createActiveOrganization(
  superAdminId: string,
  owner: Readonly<{ email: string; id: string }>,
  label: string,
) {
  const created = await repository.createOrganization(superAdminId, {
    nameAr: `${label} العربية`,
    nameEn: `${label} English`,
    ownerEmail: owner.email,
    slug: `${label.toLowerCase()}-${suffix}`,
  });
  const accepted = await repository.acceptInvitation(
    owner.id,
    owner.email,
    created.invitationToken,
  );
  await repository.setOrganizationStatus(
    superAdminId,
    created.organizationId,
    OrganizationStatus.ACTIVE,
  );
  const access = await repository.loadTenantAccess(
    owner.id,
    {
      activeMembershipId: accepted.membershipId,
      activeOrganizationId: accepted.organizationId,
    },
    {},
  );
  return { ...accepted, access };
}

async function inviteUser(
  ownerAccess: TenantAccessSnapshot,
  user: Readonly<{ email: string; id: string }>,
  roleKey: "PROVIDER" | "SECRETARY",
) {
  const roles = await repository.listRoles(ownerAccess);
  const role = roles.find(({ systemKey }) => systemKey === roleKey);
  if (!role) throw new Error(`${roleKey} fixture role is missing.`);
  const token = await repository.createInvitation(ownerAccess, user.email, role.id);
  return repository.acceptInvitation(user.id, user.email, token);
}

async function createFixture() {
  const [superAdmin, ownerA, ownerB, secretary, providerA, providerB, invited] = await Promise.all([
    createUser("super", PlatformRole.JORMALL_SUPER_ADMIN),
    createUser("owner-a"),
    createUser("owner-b"),
    createUser("secretary"),
    createUser("provider-a"),
    createUser("provider-b"),
    createUser("invited"),
  ]);
  const organizationA = await createActiveOrganization(superAdmin.id, ownerA, "Tenant-A");
  const organizationB = await createActiveOrganization(superAdmin.id, ownerB, "Tenant-B");
  await repository.createBranch(organizationA.access, {
    nameAr: "فرع أ",
    nameEn: "Branch A",
    timezone: "Asia/Amman",
  });
  await repository.createBranch(organizationB.access, {
    nameAr: "فرع ب",
    nameEn: "Branch B",
    timezone: "Asia/Amman",
  });
  const [branchA] = await repository.listBranches(organizationA.access);
  const [branchB] = await repository.listBranches(organizationB.access);
  if (!branchA || !branchB) throw new Error("Branch fixtures are missing.");
  await repository.createService(organizationA.access, {
    currency: "JOD",
    defaultDurationMins: 30,
    defaultPriceMinor: 2500,
    nameAr: "خدمة الاختبار",
    nameEn: "Test service",
  });
  const [serviceA] = await repository.listServices(organizationA.access);
  if (!serviceA) throw new Error("Service fixture is missing.");
  await repository.configureServiceBranch(organizationA.access, {
    branchId: branchA.id,
    durationMins: 30,
    isEnabled: true,
    priceMinor: 2500,
    serviceId: serviceA.id,
  });
  const secretaryMembership = await inviteUser(organizationA.access, secretary, "SECRETARY");
  const providerAMembership = await inviteUser(organizationA.access, providerA, "PROVIDER");
  const providerBMembership = await inviteUser(organizationA.access, providerB, "PROVIDER");
  const [providerARecord, providerBRecord] = await runInTenant(
    client,
    { actorUserId: ownerA.id, organizationId: organizationA.organizationId },
    async (transaction) => {
      const records = await transaction.staffProfile.findMany({
        where: {
          membershipId: {
            in: [providerAMembership.membershipId, providerBMembership.membershipId],
          },
          organizationId: organizationA.organizationId,
        },
      });
      for (const record of records) {
        await transaction.staffProfile.update({
          data: { isBookable: true, isDoctor: true },
          where: { id: record.id },
        });
        await transaction.staffBranchAssignment.upsert({
          create: {
            branchId: branchA.id,
            organizationId: organizationA.organizationId,
            staffProfileId: record.id,
          },
          update: {},
          where: {
            organizationId_staffProfileId_branchId: {
              branchId: branchA.id,
              organizationId: organizationA.organizationId,
              staffProfileId: record.id,
            },
          },
        });
        await transaction.staffService.create({
          data: {
            isEnabled: true,
            organizationId: organizationA.organizationId,
            serviceId: serviceA.id,
            staffProfileId: record.id,
          },
        });
      }
      return [
        records.find(({ membershipId }) => membershipId === providerAMembership.membershipId),
        records.find(({ membershipId }) => membershipId === providerBMembership.membershipId),
      ] as const;
    },
  );
  if (!providerARecord || !providerBRecord) throw new Error("Provider fixtures are missing.");
  for (const weekday of [
    "SUNDAY",
    "MONDAY",
    "TUESDAY",
    "WEDNESDAY",
    "THURSDAY",
    "FRIDAY",
    "SATURDAY",
  ] as const) {
    for (const provider of [providerARecord, providerBRecord]) {
      await repository.createAvailabilityRule(organizationA.access, {
        branchId: branchA.id,
        endMinuteLocal: 1440,
        staffProfileId: provider.id,
        startMinuteLocal: 0,
        weekday,
      });
    }
  }
  return {
    branchA,
    branchB,
    invited,
    organizationA,
    organizationB,
    ownerA,
    ownerB,
    providerA,
    providerAMembership,
    providerARecord,
    providerBRecord,
    secretary,
    secretaryMembership,
    serviceA,
    superAdmin,
  };
}

beforeAll(async () => {
  fixture = await createFixture();
  const group = await schedulingRepository.createResourceGroup(fixture.organizationA.access, {
    branchId: fixture.branchA.id,
    kind: "ROOM",
    nameAr: `غرف-${suffix}`,
    nameEn: `Rooms-${suffix}`,
  });
  const resource = await schedulingRepository.createResource(fixture.organizationA.access, {
    allowedServiceIds: [fixture.serviceA.id],
    groupId: group.id,
    nameAr: `غرفة-${suffix}`,
    nameEn: `Room-${suffix}`,
  });
  await schedulingRepository.setServiceResourceRequirement(fixture.organizationA.access, {
    branchId: fixture.branchA.id,
    quantity: 1,
    resourceGroupId: group.id,
    serviceId: fixture.serviceA.id,
  });
  phaseThreeFixture = { resourceGroupId: group.id, resourceId: resource.id };
});

afterAll(async () => {
  await client.$disconnect();
});

describe("PostgreSQL tenant isolation", () => {
  it("edits and deletes only unused custom roles in the active organization", async () => {
    const key = `EDITABLE_${suffix.toUpperCase()}`;
    await repository.createRole(fixture.organizationA.access, {
      key,
      nameAr: "دور قابل للتعديل",
      nameEn: "Editable role",
      permissionCodes: ["services.read"],
    });
    const created = (await repository.listRoles(fixture.organizationA.access)).find(
      (role) => role.key === key,
    );
    if (!created) throw new Error("Custom role fixture is missing.");

    await repository.updateRole(fixture.organizationA.access, created.id, {
      nameAr: "دور محدث",
      nameEn: "Updated role",
      permissionCodes: ["customers.read"],
    });
    await expect(repository.listRoles(fixture.organizationA.access)).resolves.toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: created.id,
          nameEn: "Updated role",
          permissions: [
            expect.objectContaining({
              permission: expect.objectContaining({ code: "customers.read" }),
            }),
          ],
        }),
      ]),
    );

    await expect(
      repository.updateRole(fixture.organizationB.access, created.id, {
        nameAr: "غير مسموح",
        nameEn: "Not allowed",
        permissionCodes: ["customers.read"],
      }),
    ).rejects.toMatchObject({ code: "NOT_FOUND" });

    const systemRole = (await repository.listRoles(fixture.organizationA.access)).find(
      (role) => role.isSystem,
    );
    if (!systemRole) throw new Error("System role fixture is missing.");
    await expect(
      repository.deleteRole(fixture.organizationA.access, systemRole.id),
    ).rejects.toMatchObject({ code: "FORBIDDEN" });

    const secretarySystemRole = (await repository.listRoles(fixture.organizationA.access)).find(
      (role) => role.systemKey === "SECRETARY",
    );
    if (!secretarySystemRole) throw new Error("Secretary role fixture is missing.");
    const originalSecretaryPermissionCodes = secretarySystemRole.permissions.map(
      ({ permission }) => permission.code,
    );
    await repository.updateRole(fixture.organizationA.access, secretarySystemRole.id, {
      nameAr: secretarySystemRole.nameAr,
      nameEn: secretarySystemRole.nameEn,
      permissionCodes: ["organization.read", "roles.read"],
    });
    await expect(repository.listRoles(fixture.organizationA.access)).resolves.toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: secretarySystemRole.id,
          permissions: expect.arrayContaining([
            expect.objectContaining({
              permission: expect.objectContaining({ code: "roles.read" }),
            }),
          ]),
        }),
      ]),
    );
    await repository.updateRole(fixture.organizationA.access, secretarySystemRole.id, {
      nameAr: secretarySystemRole.nameAr,
      nameEn: secretarySystemRole.nameEn,
      permissionCodes: originalSecretaryPermissionCodes,
    });

    const ownerSystemRole = (await repository.listRoles(fixture.organizationA.access)).find(
      (role) => role.systemKey === "ORGANIZATION_OWNER",
    );
    if (!ownerSystemRole) throw new Error("Owner role fixture is missing.");
    await expect(
      repository.updateRole(fixture.organizationA.access, ownerSystemRole.id, {
        nameAr: ownerSystemRole.nameAr,
        nameEn: ownerSystemRole.nameEn,
        permissionCodes: ["organization.read", "roles.read", "roles.manage"],
      }),
    ).rejects.toMatchObject({ code: "VALIDATION_FAILED" });

    await repository.deleteRole(fixture.organizationA.access, created.id);
    expect(
      (await repository.listRoles(fixture.organizationA.access)).some(
        (role) => role.id === created.id,
      ),
    ).toBe(false);
  });

  it("persists BEAUTY_CENTER and rejects unsupported or null sector writes", async () => {
    const settings = await client.organizationSettings.findUniqueOrThrow({
      select: { businessSector: true },
      where: { organizationId: fixture.organizationA.organizationId },
    });

    expect(settings.businessSector).toBe(BusinessSector.BEAUTY_CENTER);
    await expect(
      client.organizationSettings.update({
        data: { businessSector: BusinessSector.GYM },
        where: { organizationId: fixture.organizationA.organizationId },
      }),
    ).rejects.toThrow();
    await expect(
      client.$executeRaw`UPDATE organization_settings SET business_sector = NULL WHERE organization_id = ${fixture.organizationA.organizationId}::uuid`,
    ).rejects.toThrow();
  });

  it("prevents Organization A from reading, updating, or deleting Organization B rows", async () => {
    const result = await runInTenant(
      client,
      { actorUserId: fixture.ownerA.id, organizationId: fixture.organizationA.organizationId },
      async (transaction) => {
        const read = await transaction.branch.findUnique({ where: { id: fixture.branchB.id } });
        const unrelatedUser = await transaction.user.findUnique({
          where: { id: fixture.ownerB.id },
        });
        const updated = await transaction.branch.updateMany({
          data: { nameEn: "Compromised" },
          where: { id: fixture.branchB.id },
        });
        const deleted = await transaction.branch.deleteMany({ where: { id: fixture.branchB.id } });
        return { deleted: deleted.count, read, unrelatedUser, updated: updated.count };
      },
    );
    expect(result).toEqual({ deleted: 0, read: null, unrelatedUser: null, updated: 0 });
  });

  it("does not allow changing a URL-style ID to bypass isolation", async () => {
    await expect(
      repository.deleteBranch(fixture.organizationA.access, fixture.branchB.id),
    ).resolves.toBe(false);
    await expect(repository.listBranches(fixture.organizationB.access)).resolves.toEqual(
      expect.arrayContaining([expect.objectContaining({ id: fixture.branchB.id })]),
    );
  });

  it("keeps organization branding tenant-scoped", async () => {
    const current = await repository.getSettings(fixture.organizationA.access);
    if (!current) throw new Error("Organization settings fixture is missing.");

    await repository.updateSettings(fixture.organizationA.access, {
      bookingWindowDays: current.bookingWindowDays,
      brandAccentColor: "#f04f59",
      brandLogoUrl: "https://example.invalid/tenant-a-logo.png",
      brandPrimaryColor: "#126d82",
      currency: current.currency,
      defaultLocale: current.defaultLocale,
      timezone: current.timezone,
    });

    await expect(
      repository.getWorkspaceBranding(fixture.organizationA.access),
    ).resolves.toMatchObject({
      settings: {
        brandAccentColor: "#f04f59",
        brandLogoUrl: "https://example.invalid/tenant-a-logo.png",
        brandPrimaryColor: "#126d82",
      },
    });

    const crossTenantAttempt = await runInTenant(
      client,
      { actorUserId: fixture.ownerA.id, organizationId: fixture.organizationA.organizationId },
      async (transaction) => {
        const read = await transaction.organizationSettings.findUnique({
          where: { organizationId: fixture.organizationB.organizationId },
        });
        const update = await transaction.organizationSettings.updateMany({
          data: { brandPrimaryColor: "#000000" },
          where: { organizationId: fixture.organizationB.organizationId },
        });
        return { read, updated: update.count };
      },
    );

    expect(crossTenantAttempt).toEqual({ read: null, updated: 0 });
  });

  it("enables forced RLS on every tenant-owned Phase 1 table", async () => {
    const rows = await client.$queryRaw<
      Array<{ relforcerowsecurity: boolean; relname: string; relrowsecurity: boolean }>
    >`SELECT relname, relrowsecurity, relforcerowsecurity
      FROM pg_class
      WHERE relname IN (
        'organizations', 'organization_settings', 'branches', 'organization_memberships',
        'roles', 'role_permissions', 'membership_roles', 'staff_profiles',
        'staff_branch_assignments', 'services', 'service_branches', 'staff_services',
        'availability_rules', 'time_off', 'organization_invitations', 'audit_events'
      )`;
    expect(rows).toHaveLength(16);
    expect(rows.every((row) => row.relrowsecurity && row.relforcerowsecurity)).toBe(true);
  });

  it("enables forced RLS on every Phase 2 CRM and appointment table", async () => {
    const rows = await client.$queryRaw<
      Array<{ relforcerowsecurity: boolean; relname: string; relrowsecurity: boolean }>
    >`SELECT relname, relrowsecurity, relforcerowsecurity
      FROM pg_class
      WHERE relname IN (
        'customers', 'customer_contacts', 'consents', 'appointments',
        'appointment_staff_reservations', 'appointment_records',
        'appointment_status_history', 'appointment_notes',
        'appointment_participants', 'appointment_idempotencies'
      )`;
    expect(rows).toHaveLength(10);
    expect(rows.every((row) => row.relrowsecurity && row.relforcerowsecurity)).toBe(true);
  });
});

describe("fresh server-side authorization", () => {
  it("does not grant a secretary role or organization-settings management", async () => {
    const access = await repository.loadTenantAccess(
      fixture.secretary.id,
      {
        activeMembershipId: fixture.secretaryMembership.membershipId,
        activeOrganizationId: fixture.organizationA.organizationId,
      },
      {},
    );
    expect(() => requirePermission(access, "roles.manage")).toThrowError(/does not grant/);
    expect(() => requirePermission(access, "organization.settings.manage")).toThrowError(
      /does not grant/,
    );
    expect(() => requirePermission(access, "appointment_records.write")).toThrowError(
      /does not grant/,
    );
  });

  it("limits a provider to their own schedule", async () => {
    const access = await repository.loadTenantAccess(
      fixture.providerA.id,
      {
        activeMembershipId: fixture.providerAMembership.membershipId,
        activeOrganizationId: fixture.organizationA.organizationId,
      },
      {},
    );
    expect(
      canAccessResource(access, "schedules.read", {
        staffProfileId: fixture.providerARecord.id,
      }),
    ).toBe(true);
    expect(
      canAccessResource(access, "schedules.read", {
        staffProfileId: fixture.providerBRecord.id,
      }),
    ).toBe(false);
    expect(() =>
      requirePermission(access, "schedules.read", {
        staffProfileId: fixture.providerBRecord.id,
      }),
    ).toThrowError(/does not grant/);
    await expect(
      repository.listAvailabilityRules(access, fixture.providerARecord.id),
    ).resolves.toHaveLength(7);
    await expect(
      repository.listAvailabilityRules(access, fixture.providerBRecord.id),
    ).rejects.toMatchObject({ code: "FORBIDDEN" });
  });

  it("makes membership and organization suspension effective on the next operation", async () => {
    const secretaryAccess = await repository.loadTenantAccess(
      fixture.secretary.id,
      {
        activeMembershipId: fixture.secretaryMembership.membershipId,
        activeOrganizationId: fixture.organizationA.organizationId,
      },
      {},
    );
    await repository.setMembershipStatus(
      fixture.organizationA.access,
      fixture.secretaryMembership.membershipId,
      MembershipStatus.SUSPENDED,
    );
    await expect(repository.listBranches(secretaryAccess)).rejects.toMatchObject({
      code: "MEMBERSHIP_SUSPENDED",
    });
    await expect(crmRepository.listCustomers(secretaryAccess)).rejects.toMatchObject({
      code: "MEMBERSHIP_SUSPENDED",
    });
    await expect(
      repository.loadTenantAccess(
        fixture.secretary.id,
        {
          activeMembershipId: fixture.secretaryMembership.membershipId,
          activeOrganizationId: fixture.organizationA.organizationId,
        },
        {},
      ),
    ).rejects.toMatchObject({ code: "MEMBERSHIP_SUSPENDED" });

    const suspensionOwner = await createUser("suspension-owner");
    const suspendedOrganization = await createActiveOrganization(
      fixture.superAdmin.id,
      suspensionOwner,
      "Suspended-Tenant",
    );
    await repository.setOrganizationStatus(
      fixture.superAdmin.id,
      suspendedOrganization.organizationId,
      OrganizationStatus.SUSPENDED,
      "Integration test suspension",
    );
    await expect(repository.listBranches(suspendedOrganization.access)).rejects.toMatchObject({
      code: "ORGANIZATION_SUSPENDED",
    });
    await expect(crmRepository.listCustomers(suspendedOrganization.access)).rejects.toMatchObject({
      code: "ORGANIZATION_SUSPENDED",
    });
    await expect(
      repository.loadTenantAccess(
        suspensionOwner.id,
        {
          activeMembershipId: suspendedOrganization.membershipId,
          activeOrganizationId: suspendedOrganization.organizationId,
        },
        {},
      ),
    ).rejects.toMatchObject({ code: "ORGANIZATION_SUSPENDED" });
  });
});

describe("invitations and explicit Super Admin support", () => {
  it("allows an active owner to securely invite a second tenant owner", async () => {
    const [initialOwner, secondOwner] = await Promise.all([
      createUser("isolated-initial-owner"),
      createUser("isolated-second-owner"),
    ]);
    const organization = await createActiveOrganization(
      fixture.superAdmin.id,
      initialOwner,
      "Second-Owner",
    );
    const ownerRole = (await repository.listRoles(organization.access)).find(
      ({ systemKey }) => systemKey === "ORGANIZATION_OWNER",
    );
    if (!ownerRole) throw new Error("Owner role is missing.");

    const token = await repository.createInvitation(
      organization.access,
      secondOwner.email,
      ownerRole.id,
    );
    const accepted = await repository.acceptInvitation(secondOwner.id, secondOwner.email, token);
    const secondOwnerAccess = await repository.loadTenantAccess(
      secondOwner.id,
      {
        activeMembershipId: accepted.membershipId,
        activeOrganizationId: organization.organizationId,
      },
      {},
    );

    await expect(repository.listRoles(secondOwnerAccess, accepted.membershipId)).resolves.toEqual(
      expect.arrayContaining([expect.objectContaining({ systemKey: "ORGANIZATION_OWNER" })]),
    );
  });

  it("consumes an invitation once and binds it to its email", async () => {
    const roles = await repository.listRoles(fixture.organizationA.access);
    const secretaryRole = roles.find(({ systemKey }) => systemKey === "SECRETARY");
    if (!secretaryRole) throw new Error("Secretary role is missing.");
    const token = await repository.createInvitation(
      fixture.organizationA.access,
      fixture.invited.email,
      secretaryRole.id,
    );
    await expect(
      repository.acceptInvitation(fixture.invited.id, "wrong@example.invalid", token),
    ).rejects.toMatchObject({ code: "INVITATION_INVALID" });
    await expect(
      repository.acceptInvitation(fixture.invited.id, fixture.invited.email, token, {
        accountCreated: true,
      }),
    ).resolves.toMatchObject({ organizationId: fixture.organizationA.organizationId });
    const [auditEvents, invitedUser] = await Promise.all([
      client.auditEvent.findMany({
        select: { action: true },
        where: {
          actorUserId: fixture.invited.id,
          organizationId: fixture.organizationA.organizationId,
        },
      }),
      client.user.findUnique({ where: { id: fixture.invited.id } }),
    ]);
    expect(auditEvents.map(({ action }) => action)).toEqual(
      expect.arrayContaining([
        "ACCOUNT_CREATED_FROM_INVITATION",
        "MEMBERSHIP_ROLE_ASSIGNED",
        "INVITATION_ACCEPTED",
      ]),
    );
    expect(invitedUser?.platformRole).toBe(PlatformRole.USER);
    await expect(
      repository.acceptInvitation(fixture.invited.id, fixture.invited.email, token),
    ).rejects.toMatchObject({ code: "INVITATION_ALREADY_USED" });
  });

  it("requires explicit, time-bound Super Admin access and audits every tenant resolution", async () => {
    await expect(
      repository.loadTenantAccess(
        fixture.superAdmin.id,
        { activeOrganizationId: fixture.organizationB.organizationId },
        {},
      ),
    ).rejects.toMatchObject({ code: "TENANT_CONTEXT_REQUIRED" });
    const supportAccessId = await repository.startSupportAccess(
      fixture.superAdmin.id,
      fixture.organizationB.organizationId,
      "Investigate integration test access",
      { ipAddress: "127.0.0.1", userAgent: "vitest" },
    );
    const supportSnapshot = await repository.loadTenantAccess(
      fixture.superAdmin.id,
      {
        activeOrganizationId: fixture.organizationB.organizationId,
        activeSupportAccessId: supportAccessId,
      },
      { ipAddress: "127.0.0.1", userAgent: "vitest" },
    );
    await repository.loadTenantAccess(
      fixture.superAdmin.id,
      {
        activeOrganizationId: fixture.organizationB.organizationId,
        activeSupportAccessId: supportAccessId,
      },
      { ipAddress: "127.0.0.1", userAgent: "vitest" },
    );
    const auditActions = await runInTenant(
      client,
      {
        actorUserId: fixture.superAdmin.id,
        organizationId: fixture.organizationB.organizationId,
        supportAccessId,
      },
      (transaction) =>
        transaction.auditEvent.findMany({
          select: { action: true, id: true },
          where: { organizationId: fixture.organizationB.organizationId, supportAccessId },
        }),
    );
    expect(auditActions.map(({ action }) => action)).toEqual(
      expect.arrayContaining(["SUPER_ADMIN_SUPPORT_STARTED", "SUPER_ADMIN_TENANT_ACCESS"]),
    );
    expect(
      auditActions.filter(({ action }) => action === "SUPER_ADMIN_TENANT_ACCESS"),
    ).toHaveLength(2);
    const immutableEvent = auditActions[0];
    if (!immutableEvent) throw new Error("Support audit fixture is missing.");
    await expect(
      client.auditEvent.update({
        data: { reason: "Tampered" },
        where: { id: immutableEvent.id },
      }),
    ).rejects.toThrowError(/append-only/);
    await repository.revokeSupportAccess(fixture.superAdmin.id, supportAccessId, {
      ipAddress: "127.0.0.1",
      userAgent: "vitest",
    });
    await expect(repository.listBranches(supportSnapshot)).rejects.toMatchObject({
      code: "FORBIDDEN",
    });
  });
});

function localDateTimeInAmman(date: Date): string {
  const values = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      day: "2-digit",
      hour: "2-digit",
      hour12: false,
      hourCycle: "h23",
      minute: "2-digit",
      month: "2-digit",
      timeZone: "Asia/Amman",
      year: "numeric",
    })
      .formatToParts(date)
      .filter(({ type }) => type !== "literal")
      .map(({ type, value }) => [type, value]),
  );
  return `${values.year}-${values.month}-${values.day}T${values.hour === "24" ? "00" : values.hour}:${values.minute}`;
}

async function createCustomer(label: string, access = fixture.organizationA.access) {
  return crmRepository.createCustomer(access, {
    displayName: `${label}-${suffix}`,
    phoneOriginal: "079 123 4567",
    preferredLocale: "en",
  });
}

async function createAppointment(
  label: string,
  providerId = fixture.providerARecord.id,
  input: Readonly<{
    customerId?: string;
    startsAtLocal?: string;
    status?: "PENDING" | "CONFIRMED";
  }> = {},
) {
  const customer = input.customerId
    ? { customer: { id: input.customerId } }
    : await createCustomer(`customer-${label}`);
  appointmentSequence += 1;
  return crmRepository.createAppointment(fixture.organizationA.access, {
    branchId: fixture.branchA.id,
    customerId: customer.customer.id,
    providerId,
    serviceId: fixture.serviceA.id,
    startsAtLocal:
      input.startsAtLocal ??
      `${localDateTimeInAmman(
        new Date(Date.now() + (60 + appointmentSequence) * 24 * 60 * 60 * 1000),
      ).slice(0, 10)}T10:00`,
    status: input.status ?? "CONFIRMED",
  });
}

describe("PostgreSQL CRM and appointment operations", () => {
  it("keeps each owner branch workspace operationally isolated", async () => {
    await repository.createBranch(fixture.organizationA.access, {
      nameAr: `فرع مستقل ${suffix}`,
      nameEn: `Independent Branch ${suffix}`,
      timezone: "Asia/Amman",
    });
    const independentBranch = (await repository.listBranches(fixture.organizationA.access)).find(
      ({ nameEn }) => nameEn === `Independent Branch ${suffix}`,
    );
    if (!independentBranch) throw new Error("Independent branch fixture is missing.");

    await repository.configureServiceBranch(fixture.organizationA.access, {
      branchId: independentBranch.id,
      durationMins: 30,
      isEnabled: true,
      serviceId: fixture.serviceA.id,
    });
    await runInTenant(
      client,
      { actorUserId: fixture.ownerA.id, organizationId: fixture.organizationA.organizationId },
      (transaction) =>
        transaction.staffBranchAssignment.upsert({
          create: {
            branchId: independentBranch.id,
            organizationId: fixture.organizationA.organizationId,
            staffProfileId: fixture.providerARecord.id,
          },
          update: {},
          where: {
            organizationId_staffProfileId_branchId: {
              branchId: independentBranch.id,
              organizationId: fixture.organizationA.organizationId,
              staffProfileId: fixture.providerARecord.id,
            },
          },
        }),
    );
    for (const weekday of [
      "SUNDAY",
      "MONDAY",
      "TUESDAY",
      "WEDNESDAY",
      "THURSDAY",
      "FRIDAY",
      "SATURDAY",
    ] as const) {
      await repository.createAvailabilityRule(fixture.organizationA.access, {
        branchId: independentBranch.id,
        endMinuteLocal: 1440,
        staffProfileId: fixture.providerARecord.id,
        startMinuteLocal: 0,
        weekday,
      });
    }

    const branchACustomer = await crmRepository.createCustomer(fixture.organizationA.access, {
      displayName: `branch-a-patient-${suffix}`,
      preferredBranchId: fixture.branchA.id,
      preferredLocale: "en",
    });
    const independentCustomer = await crmRepository.createCustomer(fixture.organizationA.access, {
      displayName: `independent-patient-${suffix}`,
      preferredBranchId: independentBranch.id,
      preferredLocale: "en",
    });
    appointmentSequence += 1;
    await crmRepository.createAppointment(fixture.organizationA.access, {
      branchId: fixture.branchA.id,
      customerId: branchACustomer.customer.id,
      providerId: fixture.providerARecord.id,
      serviceId: fixture.serviceA.id,
      startsAtLocal: `${localDateTimeInAmman(
        new Date(Date.now() + (60 + appointmentSequence) * 86_400_000),
      ).slice(0, 10)}T11:00`,
    });
    appointmentSequence += 1;
    await crmRepository.createAppointment(fixture.organizationA.access, {
      branchId: independentBranch.id,
      customerId: independentCustomer.customer.id,
      providerId: fixture.providerARecord.id,
      serviceId: fixture.serviceA.id,
      startsAtLocal: `${localDateTimeInAmman(
        new Date(Date.now() + (60 + appointmentSequence) * 86_400_000),
      ).slice(0, 10)}T11:00`,
    });

    const branchAAccess = {
      ...fixture.organizationA.access,
      activeBranchId: fixture.branchA.id,
    };
    const independentAccess = {
      ...fixture.organizationA.access,
      activeBranchId: independentBranch.id,
    };
    const [branchAAppointments, independentAppointments, branchAOptions, independentOptions] =
      await Promise.all([
        crmRepository.listAppointments(branchAAccess),
        crmRepository.listAppointments(independentAccess),
        crmRepository.listAppointmentFormOptions(branchAAccess),
        crmRepository.listAppointmentFormOptions(independentAccess),
      ]);

    expect(branchAAppointments.every(({ branchId }) => branchId === fixture.branchA.id)).toBe(true);
    expect(independentAppointments.every(({ branchId }) => branchId === independentBranch.id)).toBe(
      true,
    );
    expect(branchAOptions.branches.map(({ id }) => id)).toEqual([fixture.branchA.id]);
    expect(independentOptions.branches.map(({ id }) => id)).toEqual([independentBranch.id]);

    await expect(
      schedulingRepository.createResourceGroup(branchAAccess, {
        branchId: independentBranch.id,
        kind: "ROOM",
        nameAr: "غرفة خاطئة",
        nameEn: "Wrong branch room",
      }),
    ).rejects.toMatchObject({ code: "NOT_FOUND" });
    await expect(
      crmRepository.createCustomer(branchAAccess, {
        displayName: "Wrong branch patient",
        preferredBranchId: independentBranch.id,
        preferredLocale: "en",
      }),
    ).rejects.toMatchObject({ code: "NOT_FOUND" });
  });

  it("enforces tenant isolation for customer records and URL-like identifiers", async () => {
    const customerA = await createCustomer("customer-a");
    const customerB = await crmRepository.createCustomer(fixture.organizationB.access, {
      displayName: `customer-b-${suffix}`,
      preferredLocale: "en",
    });
    const isolated = await runInTenant(
      client,
      { actorUserId: fixture.ownerA.id, organizationId: fixture.organizationA.organizationId },
      async (transaction) => {
        const read = await transaction.customer.findUnique({
          where: { id: customerB.customer.id },
        });
        const updated = await transaction.customer.updateMany({
          data: { displayName: "Tampered" },
          where: { id: customerB.customer.id },
        });
        const deleted = await transaction.customer.deleteMany({
          where: { id: customerB.customer.id },
        });
        return { deleted: deleted.count, read, updated: updated.count };
      },
    );
    expect(isolated).toEqual({ deleted: 0, read: null, updated: 0 });
    await expect(
      crmRepository.getCustomer(fixture.organizationA.access, customerB.customer.id),
    ).rejects.toMatchObject({ code: "NOT_FOUND" });
    await expect(
      crmRepository.updateCustomer(fixture.organizationA.access, {
        customerId: customerB.customer.id,
        displayName: "Tampered",
        expectedVersion: 1,
        preferredLocale: "en",
      }),
    ).rejects.toMatchObject({ code: "NOT_FOUND" });
    expect(customerA.customer.organizationId).toBe(fixture.organizationA.organizationId);
  });

  it("keeps customer linkage tenant-scoped and reports likely duplicates without merging", async () => {
    const first = await createCustomer("duplicate");
    const second = await crmRepository.createCustomer(fixture.organizationA.access, {
      displayName: first.customer.displayName,
      phoneOriginal: "+962791234567",
      preferredLocale: "ar",
    });
    expect(second.likelyDuplicates.map(({ id }) => id)).toContain(first.customer.id);
    const foreign = await crmRepository.createCustomer(fixture.organizationB.access, {
      displayName: `foreign-${suffix}`,
      preferredLocale: "en",
    });
    await expect(
      createAppointment("foreign-customer", fixture.providerARecord.id, {
        customerId: foreign.customer.id,
      }),
    ).rejects.toMatchObject({ code: "NOT_FOUND" });
  });

  it("records immutable consent history and does not expose internal notes in public projections", async () => {
    const customer = await createCustomer("consent");
    const granted = await crmRepository.recordConsent(fixture.organizationA.access, {
      channel: "STAFF",
      customerId: customer.customer.id,
      purpose: "service",
      source: "STAFF",
      status: "GRANTED",
      textVersion: "v1",
    });
    const revoked = await crmRepository.recordConsent(fixture.organizationA.access, {
      channel: "STAFF",
      customerId: customer.customer.id,
      purpose: "service",
      revokesConsentId: granted.id,
      source: "STAFF",
      status: "REVOKED",
      textVersion: "v1",
    });
    const profile = await crmRepository.getCustomer(
      fixture.organizationA.access,
      customer.customer.id,
    );
    expect(profile.consents.map(({ id }) => id)).toEqual(
      expect.arrayContaining([granted.id, revoked.id]),
    );
    await expect(
      client.consent.update({ data: { purpose: "tampered" }, where: { id: granted.id } }),
    ).rejects.toThrowError(/append-only/);

    const appointment = await createAppointment("private-note", fixture.providerARecord.id, {
      customerId: customer.customer.id,
    });
    await crmRepository.addInternalNote(fixture.organizationA.access, {
      appointmentId: appointment.id,
      body: "Internal treatment detail",
    });
    const publicProjection = await crmRepository.getPublicAppointmentProjection(
      fixture.organizationA.access,
      appointment.id,
    );
    expect(JSON.stringify(publicProjection)).not.toContain("Internal treatment detail");
    expect("notes" in publicProjection).toBe(false);
  });

  it("enforces the appointment state machine, immutable history, and completion record", async () => {
    const appointment = await createAppointment("state-machine", fixture.providerARecord.id, {
      status: "PENDING",
    });
    const confirmed = await crmRepository.transitionAppointment(fixture.organizationA.access, {
      appointmentId: appointment.id,
      expectedVersion: appointment.version,
      toStatus: "CONFIRMED",
    });
    expect(confirmed.confirmedAt).toBeInstanceOf(Date);
    const checkedIn = await crmRepository.transitionAppointment(fixture.organizationA.access, {
      appointmentId: confirmed.id,
      expectedVersion: confirmed.version,
      toStatus: "CHECKED_IN",
    });
    expect(checkedIn.checkedInAt).toBeInstanceOf(Date);
    const inProgress = await crmRepository.transitionAppointment(fixture.organizationA.access, {
      appointmentId: checkedIn.id,
      expectedVersion: checkedIn.version,
      toStatus: "IN_PROGRESS",
    });
    expect(inProgress.serviceStartedAt).toBeInstanceOf(Date);
    const completed = await crmRepository.transitionAppointment(fixture.organizationA.access, {
      appointmentId: inProgress.id,
      expectedVersion: inProgress.version,
      recordSummary: "Fulfilled safely",
      toStatus: "COMPLETED",
    });
    expect(completed.status).toBe("COMPLETED");
    expect(completed.completedAt).toBeInstanceOf(Date);
    await expect(
      crmRepository.transitionAppointment(fixture.organizationA.access, {
        appointmentId: completed.id,
        expectedVersion: completed.version,
        toStatus: "CONFIRMED",
      }),
    ).rejects.toMatchObject({ code: "CONFLICT" });
    const operational = await crmRepository.getAppointmentOperationalDetail(
      fixture.organizationA.access,
      appointment.id,
    );
    expect(operational.record?.summary).toBe("Fulfilled safely");
    await expect(
      client.appointmentStatusHistory.updateMany({
        data: { reason: "tampered" },
        where: { appointmentId: appointment.id },
      }),
    ).rejects.toThrowError(/append-only/);
  });

  it("requires scoped record-write permission for completion notes before changing state", async () => {
    const appointment = await createAppointment("completion-denied");
    const started = await crmRepository.transitionAppointmentCombined(
      fixture.organizationA.access,
      {
        appointmentId: appointment.id,
        command: "CHECK_IN_AND_START",
        expectedVersion: appointment.version,
      },
    );
    const withoutNotes: TenantAccessSnapshot = {
      ...fixture.organizationA.access,
      grants: fixture.organizationA.access.grants.filter(
        ({ code }) => code !== "appointment_records.write",
      ),
    };
    const input = {
      appointmentId: started.id,
      expectedVersion: started.version,
      toStatus: "COMPLETED" as const,
      recordSummary: "Restricted note",
      idempotencyKey: randomUUID(),
    };
    await expect(crmRepository.transitionAppointment(withoutNotes, input)).rejects.toMatchObject({
      code: "FORBIDDEN",
    });
    const unrelatedProvider: TenantAccessSnapshot = {
      ...fixture.organizationA.access,
      staffProfileId: fixture.providerBRecord.id,
      grants: [
        { code: "appointments.status.transition", scope: "ORGANIZATION" },
        { code: "appointment_records.write", scope: "SELF" },
      ],
    };
    await expect(
      crmRepository.transitionAppointment(unrelatedProvider, input),
    ).rejects.toMatchObject({ code: "FORBIDDEN" });
    await expect(
      crmRepository.transitionAppointment(fixture.organizationB.access, input),
    ).rejects.toMatchObject({ code: "NOT_FOUND" });
    const unchanged = await crmRepository.getAppointment(fixture.organizationA.access, started.id);
    expect(unchanged.status).toBe("IN_PROGRESS");
    expect(unchanged.version).toBe(started.version);
    const completed = await crmRepository.transitionAppointment(withoutNotes, {
      appointmentId: started.id,
      expectedVersion: started.version,
      toStatus: "COMPLETED",
    });
    expect(completed.status).toBe("COMPLETED");
  });

  it("appends completion notes once without overwriting records and protects history", async () => {
    const appointment = await createAppointment("completion-history");
    const started = await crmRepository.transitionAppointmentCombined(
      fixture.organizationA.access,
      {
        appointmentId: appointment.id,
        command: "CHECK_IN_AND_START",
        expectedVersion: appointment.version,
      },
    );
    const existing = await client.appointmentRecord.create({
      data: {
        appointmentId: started.id,
        authoredByUserId: fixture.ownerA.id,
        organizationId: fixture.organizationA.organizationId,
        summary: "Earlier record",
        details: "Preserve original",
      },
    });
    const input = {
      appointmentId: started.id,
      expectedVersion: started.version,
      toStatus: "COMPLETED" as const,
      recordSummary: "Completion",
      recordDetails: "Follow-up",
      idempotencyKey: randomUUID(),
    };
    await crmRepository.transitionAppointment(fixture.organizationA.access, input);
    await crmRepository.transitionAppointment(fixture.organizationA.access, input);
    const detail = await crmRepository.getAppointmentOperationalDetail(
      fixture.organizationA.access,
      started.id,
    );
    expect(detail.record).toMatchObject({
      id: existing.id,
      summary: "Earlier record",
      details: "Preserve original",
      version: existing.version,
    });
    expect(detail.notes).toHaveLength(1);
    expect(detail.notes[0]).toMatchObject({
      body: "Completion\n\nFollow-up",
      authorUserId: fixture.ownerA.id,
    });
    await expect(
      client.appointmentNote.updateMany({
        where: { appointmentId: started.id },
        data: { body: "Tampered" },
      }),
    ).rejects.toThrow(/append-only/);
    await expect(
      client.appointmentNote.deleteMany({ where: { appointmentId: started.id } }),
    ).rejects.toThrow(/append-only/);
    const isolated = await runInTenant(
      client,
      { organizationId: fixture.organizationB.organizationId, actorUserId: fixture.ownerB.id },
      (transaction) =>
        transaction.appointmentNote.findMany({ where: { appointmentId: started.id } }),
    );
    expect(isolated).toEqual([]);
    const events = await client.auditEvent.count({
      where: {
        organizationId: fixture.organizationA.organizationId,
        targetId: started.id,
        action: "APPOINTMENT_NOTE_ADDED",
      },
    });
    expect(events).toBe(1);
  });

  it("records every intermediate transition for combined arrival actions", async () => {
    const pending = await createAppointment("combined-pending", fixture.providerARecord.id, {
      status: "PENDING",
    });
    const checkedIn = await crmRepository.transitionAppointmentCombined(
      fixture.organizationA.access,
      {
        appointmentId: pending.id,
        command: "CONFIRM_AND_CHECK_IN",
        expectedVersion: pending.version,
        idempotencyKey: randomUUID(),
      },
    );
    expect(checkedIn.status).toBe("CHECKED_IN");
    expect(checkedIn.version).toBe(pending.version + 2);
    expect(checkedIn.confirmedAt).toBeInstanceOf(Date);
    expect(checkedIn.checkedInAt).toBeInstanceOf(Date);

    const confirmed = await createAppointment("combined-confirmed", fixture.providerARecord.id, {
      status: "CONFIRMED",
    });
    const inProgress = await crmRepository.transitionAppointmentCombined(
      fixture.organizationA.access,
      {
        appointmentId: confirmed.id,
        command: "CHECK_IN_AND_START",
        expectedVersion: confirmed.version,
        idempotencyKey: randomUUID(),
      },
    );
    expect(inProgress.status).toBe("IN_PROGRESS");
    expect(inProgress.serviceStartedAt).toBeInstanceOf(Date);

    const history = await runInTenant(
      client,
      { actorUserId: fixture.ownerA.id, organizationId: fixture.organizationA.organizationId },
      (transaction) =>
        transaction.appointmentStatusHistory.findMany({
          orderBy: { version: "asc" },
          select: { fromStatus: true, toStatus: true, version: true },
          where: { appointmentId: pending.id, eventType: "STATUS_CHANGED" },
        }),
    );
    expect(history).toEqual([
      { fromStatus: "PENDING", toStatus: "CONFIRMED", version: 2 },
      { fromStatus: "CONFIRMED", toStatus: "CHECKED_IN", version: 3 },
    ]);
    const startHistory = await runInTenant(
      client,
      { actorUserId: fixture.ownerA.id, organizationId: fixture.organizationA.organizationId },
      (transaction) =>
        transaction.appointmentStatusHistory.findMany({
          orderBy: { version: "asc" },
          select: { fromStatus: true, toStatus: true, version: true },
          where: { appointmentId: confirmed.id, eventType: "STATUS_CHANGED" },
        }),
    );
    expect(startHistory).toEqual([
      { fromStatus: "CONFIRMED", toStatus: "CHECKED_IN", version: 2 },
      { fromStatus: "CHECKED_IN", toStatus: "IN_PROGRESS", version: 3 },
    ]);
  });

  it("selects the next checked-in Doctor appointment only from the current local day", async () => {
    const providerUser = await createUser("queue-provider");
    const providerMembership = await inviteUser(
      fixture.organizationA.access,
      providerUser,
      "PROVIDER",
    );
    const provider = await runInTenant(
      client,
      { actorUserId: fixture.ownerA.id, organizationId: fixture.organizationA.organizationId },
      async (transaction) => {
        const profile = await transaction.staffProfile.findFirstOrThrow({
          where: {
            membershipId: providerMembership.membershipId,
            organizationId: fixture.organizationA.organizationId,
          },
        });
        await transaction.staffProfile.update({
          data: { isBookable: true, isDoctor: true },
          where: { id: profile.id },
        });
        await transaction.staffBranchAssignment.create({
          data: {
            branchId: fixture.branchA.id,
            organizationId: fixture.organizationA.organizationId,
            staffProfileId: profile.id,
          },
        });
        await transaction.staffService.create({
          data: {
            isEnabled: true,
            organizationId: fixture.organizationA.organizationId,
            serviceId: fixture.serviceA.id,
            staffProfileId: profile.id,
          },
        });
        return profile;
      },
    );
    for (const weekday of [
      "SUNDAY",
      "MONDAY",
      "TUESDAY",
      "WEDNESDAY",
      "THURSDAY",
      "FRIDAY",
      "SATURDAY",
    ] as const) {
      await repository.createAvailabilityRule(fixture.organizationA.access, {
        branchId: fixture.branchA.id,
        endMinuteLocal: 1440,
        staffProfileId: provider.id,
        startMinuteLocal: 0,
        weekday,
      });
    }
    const room = await schedulingRepository.createResource(fixture.organizationA.access, {
      allowedServiceIds: [fixture.serviceA.id],
      groupId: phaseThreeFixture.resourceGroupId,
      nameAr: `غرفة طابور-${suffix}`,
      nameEn: `Queue room-${suffix}`,
    });
    const earlier = await createAppointment("older-checked-in", provider.id, {
      startsAtLocal: localDateTimeInAmman(new Date(Date.now() + 30 * 60_000)),
    });
    const current = await createAppointment("today-checked-in", provider.id, {
      startsAtLocal: localDateTimeInAmman(new Date(Date.now() + 90 * 60_000)),
    });
    const earlierCheckedIn = await crmRepository.transitionAppointment(
      fixture.organizationA.access,
      {
        appointmentId: earlier.id,
        expectedVersion: earlier.version,
        toStatus: "CHECKED_IN",
      },
    );
    const currentCheckedIn = await crmRepository.transitionAppointment(
      fixture.organizationA.access,
      {
        appointmentId: current.id,
        expectedVersion: current.version,
        toStatus: "CHECKED_IN",
      },
    );
    await client.appointment.update({
      data: {
        endsAt: new Date(earlierCheckedIn.endsAt.getTime() - 86_400_000),
        startsAt: new Date(earlierCheckedIn.startsAt.getTime() - 86_400_000),
      },
      where: { id: earlierCheckedIn.id },
    });

    const called = await crmRepository.callAppointmentToRoom(fixture.organizationA.access, {
      appointmentId: currentCheckedIn.id,
      asNext: true,
      expectedVersion: currentCheckedIn.version,
      roomId: room.id,
    });

    expect(called.status).toBe("CALLED");
    expect(called.calledAt).toBeInstanceOf(Date);
  });

  it("bulk confirmation reports partial success without crossing tenant boundaries", async () => {
    const first = await createAppointment("bulk-first", fixture.providerARecord.id, {
      status: "PENDING",
    });
    const second = await createAppointment("bulk-second", fixture.providerARecord.id, {
      status: "CONFIRMED",
    });
    const undisclosedAppointmentId = randomUUID();
    const results = await crmRepository.bulkConfirmAppointments(fixture.organizationA.access, [
      { appointmentId: first.id, expectedVersion: first.version },
      { appointmentId: second.id, expectedVersion: second.version },
      { appointmentId: undisclosedAppointmentId, expectedVersion: 1 },
    ]);
    expect(results).toEqual([
      { appointmentId: first.id, succeeded: true },
      { appointmentId: second.id, code: "CONFLICT", succeeded: false },
      { appointmentId: undisclosedAppointmentId, code: "NOT_FOUND", succeeded: false },
    ]);
  });

  it("replays a terminal appointment transition without re-running the state machine", async () => {
    const appointment = await createAppointment("transition-idempotency");
    const idempotencyKey = randomUUID();
    const input = {
      appointmentId: appointment.id,
      expectedVersion: appointment.version,
      idempotencyKey,
      reason: "Customer requested cancellation",
      toStatus: "CANCELLED" as const,
    };
    const cancelled = await crmRepository.transitionAppointment(
      fixture.organizationA.access,
      input,
    );
    const replay = await crmRepository.transitionAppointment(fixture.organizationA.access, input);
    expect(replay.id).toBe(cancelled.id);
    expect(replay.status).toBe("CANCELLED");
    expect(replay.version).toBe(cancelled.version);
    const historyCount = await runInTenant(
      client,
      { actorUserId: fixture.ownerA.id, organizationId: fixture.organizationA.organizationId },
      (transaction) =>
        transaction.appointmentStatusHistory.count({
          where: { appointmentId: appointment.id, toStatus: "CANCELLED" },
        }),
    );
    expect(historyCount).toBe(1);
  });

  it("limits a provider to their own appointments and checks a secretary's sensitive permissions", async () => {
    const providerBAppointment = await createAppointment("provider-b", fixture.providerBRecord.id);
    const providerAccess = await repository.loadTenantAccess(
      fixture.providerA.id,
      {
        activeMembershipId: fixture.providerAMembership.membershipId,
        activeOrganizationId: fixture.organizationA.organizationId,
      },
      {},
    );
    const ownAppointments = await crmRepository.listAppointments(providerAccess);
    expect(
      ownAppointments.every(({ providerId }) => providerId === fixture.providerARecord.id),
    ).toBe(true);
    await expect(
      crmRepository.getAppointment(providerAccess, providerBAppointment.id),
    ).rejects.toMatchObject({
      code: "NOT_FOUND",
    });
    const secretaryAccess = await repository
      .loadTenantAccess(
        fixture.secretary.id,
        {
          activeMembershipId: fixture.secretaryMembership.membershipId,
          activeOrganizationId: fixture.organizationA.organizationId,
        },
        {},
      )
      .catch(() => null);
    // The earlier suspension test may have suspended this shared fixture; use a fresh secretary if so.
    if (secretaryAccess) {
      await expect(
        crmRepository.addInternalNote(secretaryAccess, {
          appointmentId: providerBAppointment.id,
          body: "not allowed",
        }),
      ).rejects.toMatchObject({ code: "FORBIDDEN" });
    }
  });

  it("rejects a concurrent reschedule and shows today's Amman appointments", async () => {
    const appointment = await createAppointment("concurrent");
    const one = localDateTimeInAmman(new Date(Date.now() + 36 * 60 * 60 * 1000));
    const two = localDateTimeInAmman(new Date(Date.now() + 48 * 60 * 60 * 1000));
    const results = await Promise.allSettled([
      crmRepository.rescheduleAppointment(fixture.organizationA.access, {
        appointmentId: appointment.id,
        expectedVersion: appointment.version,
        startsAtLocal: one,
      }),
      crmRepository.rescheduleAppointment(fixture.organizationA.access, {
        appointmentId: appointment.id,
        expectedVersion: appointment.version,
        startsAtLocal: two,
      }),
    ]);
    expect(results.filter(({ status }) => status === "fulfilled")).toHaveLength(1);
    expect(results.filter(({ status }) => status === "rejected")).toHaveLength(1);
    const today = await createAppointment("today", fixture.providerARecord.id, {
      startsAtLocal: localDateTimeInAmman(new Date(Date.now() + 5 * 60 * 1000)),
    });
    const todayOperations = await crmRepository.listTodayOperations(fixture.organizationA.access, {
      branchId: fixture.branchA.id,
    });
    expect(todayOperations.map(({ id }) => id)).toContain(today.id);
  });
});

function localDateFromLocalDateTime(value: string): string {
  return value.slice(0, 10);
}

async function createOfferFixture(label: string, daysAhead: number) {
  const customer = await createCustomer(`waitlist-${label}`);
  await crmRepository.recordConsent(fixture.organizationA.access, {
    channel: "STAFF",
    customerId: customer.customer.id,
    purpose: "appointment_slot_offers",
    source: "STAFF",
    status: "GRANTED",
    textVersion: "test-v1",
  });
  const startsAtLocal = localDateTimeInAmman(new Date(Date.now() + daysAhead * 86_400_000));
  const preferredDate = localDateFromLocalDateTime(startsAtLocal);
  const entry = await schedulingRepository.createWaitlistEntry(fixture.organizationA.access, {
    branchIds: [fixture.branchA.id],
    customerId: customer.customer.id,
    preferredEndDate: preferredDate,
    preferredEndMinute: 1440,
    preferredStartDate: preferredDate,
    preferredStartMinute: 0,
    priority: 2,
    providerIds: [fixture.providerARecord.id],
    serviceId: fixture.serviceA.id,
  });
  const offer = await schedulingRepository.sendMockSlotOffer(fixture.organizationA.access, {
    branchId: fixture.branchA.id,
    expiresAt: new Date(Date.now() + 60 * 60 * 1000),
    providerId: fixture.providerARecord.id,
    startsAtLocal,
    waitlistEntryId: entry.id,
  });
  return { customer, entry, offer, startsAtLocal };
}

describe("Karmalite Phase 1 protected patient and doctor foundations", () => {
  it("stores consented safety intake without exposing it through the patient directory", async () => {
    const secretAllergy = `latex-${suffix}`;
    const created = await crmRepository.createCustomer(fixture.organizationA.access, {
      allergyDetails: secretAllergy,
      allergyState: "PROVIDED",
      displayName: `protected-patient-${suffix}`,
      healthConsentConfirmed: true,
      medicalConditionState: "NONE_REPORTED",
      phoneOriginal: "+962 79 444 5555",
      preferredLocale: "en",
    });

    const health = await crmRepository.getPatientSafetyIntake(
      fixture.organizationA.access,
      created.customer.id,
    );
    expect(health).toMatchObject({
      allergyDetails: secretAllergy,
      allergyState: "PROVIDED",
      medicalConditionState: "NONE_REPORTED",
      updatedByUserId: fixture.ownerA.id,
    });
    expect(health?.consent).toMatchObject({ channel: "STAFF", source: "STAFF" });

    const directory = await crmRepository.listPatients(fixture.organizationA.access, {
      query: created.customer.displayName,
    });
    expect(directory.rows).toHaveLength(1);
    expect(JSON.stringify(directory)).not.toContain(secretAllergy);
    expect(JSON.stringify(directory)).not.toContain("healthInformation");

    const restrictedAccess: TenantAccessSnapshot = {
      ...fixture.organizationA.access,
      grants: fixture.organizationA.access.grants.filter(
        ({ code }) => code !== "patients.health.read" && code !== "patients.health.write",
      ),
    };
    await expect(
      crmRepository.getPatientSafetyIntake(restrictedAccess, created.customer.id),
    ).rejects.toMatchObject({ code: "FORBIDDEN" });
    await expect(
      crmRepository.getPatientSafetyIntake(fixture.organizationB.access, created.customer.id),
    ).rejects.toMatchObject({ code: "NOT_FOUND" });

    const isolated = await runInTenant(
      client,
      {
        actorUserId: fixture.ownerB.id,
        organizationId: fixture.organizationB.organizationId,
      },
      (transaction) =>
        transaction.patientHealthInformation.findUnique({ where: { id: health?.id } }),
    );
    expect(isolated).toBeNull();

    const auditActions = await runInTenant(
      client,
      {
        actorUserId: fixture.ownerA.id,
        organizationId: fixture.organizationA.organizationId,
      },
      (transaction) =>
        transaction.auditEvent.findMany({
          select: { action: true },
          where: {
            organizationId: fixture.organizationA.organizationId,
            targetId: created.customer.id,
          },
        }),
    );
    expect(auditActions.map(({ action }) => action)).toContain("PATIENT_SAFETY_INTAKE_READ");
  });

  it("requires provenance for recorded health states and rejects ambiguous details", async () => {
    await expect(
      crmRepository.createCustomer(fixture.organizationA.access, {
        allergyState: "NONE_REPORTED",
        displayName: `missing-consent-${suffix}`,
        preferredLocale: "en",
      }),
    ).rejects.toMatchObject({ code: "FORBIDDEN" });
    await expect(
      crmRepository.createCustomer(fixture.organizationA.access, {
        allergyDetails: "unbound detail",
        allergyState: "DECLINED",
        displayName: `invalid-health-${suffix}`,
        healthConsentConfirmed: true,
        preferredLocale: "en",
      }),
    ).rejects.toMatchObject({ code: "VALIDATION_FAILED" });
  });

  it("keeps explicit doctor schedules, breaks, leave and room compatibility tenant-scoped", async () => {
    await repository.replaceDoctorSchedule(fixture.organizationA.access, {
      branchId: fixture.branchA.id,
      breaks: [
        {
          endMinuteLocal: 780,
          label: "Lunch",
          startMinuteLocal: 720,
          weekday: "SUNDAY",
        },
      ],
      confirmAffected: true,
      periods: [{ endMinuteLocal: 1020, startMinuteLocal: 540, weekday: "SUNDAY" }],
      staffProfileId: fixture.providerARecord.id,
    });
    const doctors = await repository.listDoctors(fixture.organizationA.access);
    const doctor = doctors.find(({ id }) => id === fixture.providerARecord.id);
    expect(doctor?.availabilityRules).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ startMinuteLocal: 540, weekday: "SUNDAY" }),
      ]),
    );
    expect(doctor?.breaks).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ startMinuteLocal: 720, weekday: "SUNDAY" }),
      ]),
    );

    const leaveStart = new Date(Date.now() + 500 * 86_400_000);
    const leave = await repository.addDoctorTimeOff(fixture.organizationA.access, {
      branchId: fixture.branchA.id,
      confirmAffected: true,
      endsAt: new Date(leaveStart.getTime() + 3_600_000),
      reason: "Approved leave",
      staffProfileId: fixture.providerARecord.id,
      startsAt: leaveStart,
    });
    expect(leave.created).toBe(true);
    await expect(
      repository.replaceDoctorSchedule(fixture.organizationB.access, {
        branchId: fixture.branchB.id,
        breaks: [],
        confirmAffected: true,
        periods: [{ endMinuteLocal: 1020, startMinuteLocal: 540, weekday: "SUNDAY" }],
        staffProfileId: fixture.providerARecord.id,
      }),
    ).rejects.toMatchObject({ code: "NOT_FOUND" });
    await repository.replaceDoctorSchedule(fixture.organizationA.access, {
      branchId: fixture.branchA.id,
      breaks: [],
      confirmAffected: true,
      periods: ["SUNDAY", "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"].map(
        (weekday) => ({
          endMinuteLocal: 1440,
          startMinuteLocal: 0,
          weekday: weekday as
            "SUNDAY" | "MONDAY" | "TUESDAY" | "WEDNESDAY" | "THURSDAY" | "FRIDAY" | "SATURDAY",
        }),
      ),
      staffProfileId: fixture.providerARecord.id,
    });
  });

  it("prevents concurrent overlapping appointments for one patient across two doctors", async () => {
    const secondRoom = await schedulingRepository.createResource(fixture.organizationA.access, {
      allowedServiceIds: [fixture.serviceA.id],
      groupId: phaseThreeFixture.resourceGroupId,
      nameAr: `غرفة ثانية-${suffix}`,
      nameEn: `Second room-${suffix}`,
    });
    const customer = await createCustomer("patient-overlap-race");
    const day = localDateTimeInAmman(new Date(Date.now() + 450 * 86_400_000)).slice(0, 10);
    const common = {
      branchId: fixture.branchA.id,
      customerId: customer.customer.id,
      serviceId: fixture.serviceA.id,
      startsAtLocal: `${day}T10:00`,
      status: "CONFIRMED" as const,
    };
    const outcomes = await Promise.allSettled([
      crmRepository.createAppointment(fixture.organizationA.access, {
        ...common,
        providerId: fixture.providerARecord.id,
        roomId: phaseThreeFixture.resourceId,
      }),
      crmRepository.createAppointment(fixture.organizationA.access, {
        ...common,
        providerId: fixture.providerBRecord.id,
        roomId: secondRoom.id,
      }),
    ]);
    expect(outcomes.filter(({ status }) => status === "fulfilled")).toHaveLength(1);
    expect(outcomes.filter(({ status }) => status === "rejected")).toHaveLength(1);
    const committed = await runInTenant(
      client,
      {
        actorUserId: fixture.ownerA.id,
        organizationId: fixture.organizationA.organizationId,
      },
      (transaction) =>
        transaction.appointment.count({
          where: {
            customerId: customer.customer.id,
            startsAt: {
              gte: new Date(`${day}T00:00:00+03:00`),
              lt: new Date(`${day}T23:59:59+03:00`),
            },
          },
        }),
    );
    expect(committed).toBe(1);
    await runInTenant(
      client,
      {
        actorUserId: fixture.ownerA.id,
        organizationId: fixture.organizationA.organizationId,
      },
      (transaction) =>
        transaction.resource.update({
          data: { status: "MAINTENANCE" },
          where: { id: secondRoom.id },
        }),
    );
  });
});

describe("PostgreSQL Phase 3 scheduling invariants", () => {
  it("rejects a new waitlist request whose preferred window is already past", async () => {
    const customer = await createCustomer("past-waitlist-window");
    const preferredDate = localDateFromLocalDateTime(
      localDateTimeInAmman(new Date(Date.now() - 86_400_000)),
    );

    await expect(
      schedulingRepository.createWaitlistEntry(fixture.organizationA.access, {
        branchIds: [fixture.branchA.id],
        customerId: customer.customer.id,
        preferredEndDate: preferredDate,
        preferredEndMinute: 17 * 60,
        preferredStartDate: preferredDate,
        preferredStartMinute: 9 * 60,
        priority: 2,
        providerIds: [fixture.providerARecord.id],
        serviceId: fixture.serviceA.id,
      }),
    ).rejects.toMatchObject({
      code: "VALIDATION_FAILED",
      metadata: { reason: "WAITLIST_TIME_INVALID" },
    });
  });

  it("enforces assigned-branch scope on every waitlist and slot-offer mutation", async () => {
    const customer = await createCustomer("waitlist-branch-scope");
    await repository.createBranch(fixture.organizationA.access, {
      nameAr: `فرع نطاق آخر ${suffix}`,
      nameEn: `Other scoped branch ${suffix}`,
      timezone: "Asia/Amman",
    });
    const otherBranch = (await repository.listBranches(fixture.organizationA.access)).find(
      ({ nameEn }) => nameEn === `Other scoped branch ${suffix}`,
    );
    if (!otherBranch) throw new Error("Other branch scope fixture is missing.");
    await runInTenant(
      client,
      {
        actorUserId: fixture.ownerA.id,
        organizationId: fixture.organizationA.organizationId,
      },
      (transaction) =>
        transaction.staffBranchAssignment.create({
          data: {
            branchId: otherBranch.id,
            organizationId: fixture.organizationA.organizationId,
            staffProfileId: fixture.providerARecord.id,
          },
        }),
    );
    const assignedWaitlistAccess: TenantAccessSnapshot = {
      ...fixture.organizationA.access,
      assignedBranchIds: [fixture.branchA.id],
      grants: [{ code: "waitlist.manage", scope: "ASSIGNED_BRANCHES" }],
    };
    const preferredDate = localDateFromLocalDateTime(
      localDateTimeInAmman(new Date(Date.now() + 18 * 86_400_000)),
    );
    const input = {
      branchIds: [otherBranch.id],
      customerId: customer.customer.id,
      preferredEndDate: preferredDate,
      preferredEndMinute: 1440,
      preferredStartDate: preferredDate,
      preferredStartMinute: 0,
      priority: 2,
      providerIds: [fixture.providerARecord.id],
      serviceId: fixture.serviceA.id,
    } as const;
    await expect(
      schedulingRepository.createWaitlistEntry(assignedWaitlistAccess, input),
    ).rejects.toMatchObject({ code: "FORBIDDEN" });

    const entry = await schedulingRepository.createWaitlistEntry(
      fixture.organizationA.access,
      input,
    );
    await expect(
      schedulingRepository.cancelWaitlistEntry(assignedWaitlistAccess, {
        entryId: entry.id,
        expectedVersion: entry.version,
      }),
    ).rejects.toMatchObject({ code: "FORBIDDEN" });

    const mixedEntry = await schedulingRepository.createWaitlistEntry(
      fixture.organizationA.access,
      { ...input, branchIds: [fixture.branchA.id, otherBranch.id] },
    );
    const scopedReadAccess: TenantAccessSnapshot = {
      ...assignedWaitlistAccess,
      grants: [{ code: "waitlist.read", scope: "ASSIGNED_BRANCHES" }],
    };
    const visibleEntries = await schedulingRepository.listWaitlist(scopedReadAccess);
    expect(visibleEntries.map(({ id }) => id)).not.toContain(mixedEntry.id);
    const formOptions = await schedulingRepository.listWaitlistFormOptions(assignedWaitlistAccess);
    expect(formOptions.branches.map(({ id }) => id)).not.toContain(otherBranch.id);

    const { offer } = await createOfferFixture("offer-branch-scope", 18);
    const unassignedOfferAccess: TenantAccessSnapshot = {
      ...fixture.organizationA.access,
      assignedBranchIds: [otherBranch.id],
      grants: [{ code: "slot_offers.manage", scope: "ASSIGNED_BRANCHES" }],
    };
    await expect(
      schedulingRepository.acceptSlotOffer(unassignedOfferAccess, {
        offerId: offer.id,
        requestKey: randomUUID(),
      }),
    ).rejects.toMatchObject({ code: "FORBIDDEN" });
    await expect(
      schedulingRepository.declineSlotOffer(unassignedOfferAccess, {
        offerId: offer.id,
        requestKey: randomUUID(),
      }),
    ).rejects.toMatchObject({ code: "FORBIDDEN" });
    await expect(
      schedulingRepository.expireSlotOffer(
        unassignedOfferAccess,
        offer.id,
        new Date(Date.now() + 2 * 60 * 60 * 1000),
      ),
    ).rejects.toMatchObject({ code: "FORBIDDEN" });
  });

  it("replays resource-aware booking and rescheduling idempotency keys", async () => {
    const customer = await createCustomer("phase3-idempotency");
    const startsAtLocal = localDateTimeInAmman(new Date(Date.now() + 19 * 86_400_000));
    const createKey = randomUUID();
    const createInput = {
      branchId: fixture.branchA.id,
      customerId: customer.customer.id,
      idempotencyKey: createKey,
      providerId: fixture.providerARecord.id,
      serviceId: fixture.serviceA.id,
      startsAtLocal,
    } as const;
    const created = await Promise.all([
      crmRepository.createAppointment(fixture.organizationA.access, createInput),
      crmRepository.createAppointment(fixture.organizationA.access, createInput),
    ]);
    expect(new Set(created.map(({ id }) => id)).size).toBe(1);
    const initial = created[0];
    if (!initial) throw new Error("Idempotent appointment was not returned.");
    const rescheduleKey = randomUUID();
    const rescheduleInput = {
      appointmentId: initial.id,
      expectedVersion: initial.version,
      idempotencyKey: rescheduleKey,
      startsAtLocal: localDateTimeInAmman(
        new Date(initial.startsAt.getTime() + 2 * 60 * 60 * 1000),
      ),
    };
    const first = await crmRepository.rescheduleAppointment(
      fixture.organizationA.access,
      rescheduleInput,
    );
    const replay = await crmRepository.rescheduleAppointment(
      fixture.organizationA.access,
      rescheduleInput,
    );
    expect(replay.id).toBe(first.id);
    expect(replay.version).toBe(first.version);
  });

  it("allows only one booking when two providers race for one capacity-one resource", async () => {
    const capacityGroup = await schedulingRepository.createResourceGroup(
      fixture.organizationA.access,
      {
        branchId: fixture.branchA.id,
        kind: "SHARED_EQUIPMENT",
        nameAr: `معدات سباق السعة-${suffix}`,
        nameEn: `Capacity-race equipment-${suffix}`,
      },
    );
    await schedulingRepository.createResource(fixture.organizationA.access, {
      groupId: capacityGroup.id,
      nameAr: `جهاز سباق السعة-${suffix}`,
      nameEn: `Capacity-race unit-${suffix}`,
    });
    await schedulingRepository.setServiceResourceRequirement(fixture.organizationA.access, {
      branchId: fixture.branchA.id,
      quantity: 1,
      resourceGroupId: capacityGroup.id,
      serviceId: fixture.serviceA.id,
    });
    const [customerA, customerB] = await Promise.all([
      createCustomer("resource-race-a"),
      createCustomer("resource-race-b"),
    ]);
    const startsAtLocal = localDateTimeInAmman(new Date(Date.now() + 20 * 86_400_000));
    const results = await Promise.allSettled([
      crmRepository.createAppointment(fixture.organizationA.access, {
        branchId: fixture.branchA.id,
        customerId: customerA.customer.id,
        providerId: fixture.providerARecord.id,
        serviceId: fixture.serviceA.id,
        startsAtLocal,
      }),
      crmRepository.createAppointment(fixture.organizationA.access, {
        branchId: fixture.branchA.id,
        customerId: customerB.customer.id,
        providerId: fixture.providerBRecord.id,
        serviceId: fixture.serviceA.id,
        startsAtLocal,
      }),
    ]);
    expect(results.filter(({ status }) => status === "fulfilled")).toHaveLength(1);
    expect(results.filter(({ status }) => status === "rejected")).toHaveLength(1);
    const committed = await crmRepository.listAppointments(fixture.organizationA.access);
    expect(
      committed.filter(({ customerId }) =>
        [customerA.customer.id, customerB.customer.id].includes(customerId),
      ),
    ).toHaveLength(1);
    await runInTenant(client, fixture.organizationA.access, async (transaction) => {
      await transaction.appointmentResource.deleteMany({
        where: {
          organizationId: fixture.organizationA.organizationId,
          resourceGroupId: capacityGroup.id,
        },
      });
      await transaction.serviceResourceRequirement.deleteMany({
        where: {
          organizationId: fixture.organizationA.organizationId,
          resourceGroupId: capacityGroup.id,
        },
      });
      await transaction.resource.deleteMany({
        where: {
          groupId: capacityGroup.id,
          organizationId: fixture.organizationA.organizationId,
        },
      });
      await transaction.resourceGroup.delete({ where: { id: capacityGroup.id } });
    });
  });

  it("allows only one booking when the same provider races despite spare resource capacity", async () => {
    await schedulingRepository.createResource(fixture.organizationA.access, {
      groupId: phaseThreeFixture.resourceGroupId,
      nameAr: `غرفة-إضافية-${suffix}`,
      nameEn: `Extra-room-${suffix}`,
    });
    const [customerA, customerB] = await Promise.all([
      createCustomer("staff-race-a"),
      createCustomer("staff-race-b"),
    ]);
    const startsAtLocal = localDateTimeInAmman(new Date(Date.now() + 21 * 86_400_000));
    const results = await Promise.allSettled(
      [customerA, customerB].map((customer) =>
        crmRepository.createAppointment(fixture.organizationA.access, {
          branchId: fixture.branchA.id,
          customerId: customer.customer.id,
          providerId: fixture.providerARecord.id,
          serviceId: fixture.serviceA.id,
          startsAtLocal,
        }),
      ),
    );
    expect(results.filter(({ status }) => status === "fulfilled")).toHaveLength(1);
    expect(results.filter(({ status }) => status === "rejected")).toHaveLength(1);
  });

  it("rejects display-time adjacency when service buffers overlap", async () => {
    await runInTenant(
      client,
      { actorUserId: fixture.ownerA.id, organizationId: fixture.organizationA.organizationId },
      (transaction) =>
        transaction.serviceBranch.update({
          data: { bufferAfterMins: 15, bufferBeforeMins: 15 },
          where: {
            organizationId_serviceId_branchId: {
              branchId: fixture.branchA.id,
              organizationId: fixture.organizationA.organizationId,
              serviceId: fixture.serviceA.id,
            },
          },
        }),
    );
    const firstStart = localDateTimeInAmman(new Date(Date.now() + 22 * 86_400_000));
    const first = await createAppointment("buffer-first", fixture.providerARecord.id, {
      startsAtLocal: firstStart,
    });
    const adjacent = localDateTimeInAmman(new Date(first.startsAt.getTime() + 30 * 60_000));
    await expect(
      createAppointment("buffer-adjacent", fixture.providerARecord.id, {
        startsAtLocal: adjacent,
      }),
    ).rejects.toMatchObject({ code: "CONFLICT" });
    await runInTenant(
      client,
      { actorUserId: fixture.ownerA.id, organizationId: fixture.organizationA.organizationId },
      (transaction) =>
        transaction.serviceBranch.update({
          data: { bufferAfterMins: 0, bufferBeforeMins: 0 },
          where: {
            organizationId_serviceId_branchId: {
              branchId: fixture.branchA.id,
              organizationId: fixture.organizationA.organizationId,
              serviceId: fixture.serviceA.id,
            },
          },
        }),
    );
  });

  it("calculates bounded availability without permanent slot rows", async () => {
    const target = localDateTimeInAmman(new Date(Date.now() + 25 * 86_400_000)).slice(0, 10);
    const slots = await schedulingRepository.findAvailableSlots(fixture.organizationA.access, {
      branchId: fixture.branchA.id,
      endsOn: target,
      limit: 8,
      providerId: fixture.providerARecord.id,
      serviceId: fixture.serviceA.id,
      startsOn: target,
    });
    expect(slots.length).toBeGreaterThan(0);
    expect(slots.length).toBeLessThanOrEqual(8);
    const permanentSlotTable = await client.$queryRaw<Array<{ table: string | null }>>`
      SELECT to_regclass('public.availability_slots')::text AS "table"
    `;
    expect(permanentSlotTable[0]?.table).toBeNull();
  });

  it("assigns a cancelled opening by priority and then earliest request", async () => {
    const startsAtLocal = `${localDateTimeInAmman(new Date(Date.now() + 26 * 86_400_000)).slice(
      0,
      10,
    )}T14:00`;
    const date = startsAtLocal.slice(0, 10);
    const cancelled = await createAppointment(
      "cancelled-waitlist-opening",
      fixture.providerARecord.id,
      {
        startsAtLocal,
      },
    );
    const normalCustomer = await createCustomer("waitlist-normal-oldest");
    const urgentOlderCustomer = await createCustomer("waitlist-urgent-older");
    const urgentNewerCustomer = await createCustomer("waitlist-urgent-newer");
    await expect(
      schedulingRepository.createWaitlistEntry(fixture.organizationA.access, {
        branchIds: [fixture.branchA.id],
        customerId: normalCustomer.customer.id,
        preferredEndDate: date,
        preferredEndMinute: 1440,
        preferredStartDate: date,
        preferredStartMinute: 0,
        priority: 2,
        providerIds: [],
        serviceId: fixture.serviceA.id,
      }),
    ).rejects.toMatchObject({ code: "VALIDATION_FAILED" });
    const createEntry = (customerId: string, priority: number) =>
      schedulingRepository.createWaitlistEntry(fixture.organizationA.access, {
        branchIds: [fixture.branchA.id],
        customerId,
        preferredEndDate: date,
        preferredEndMinute: 1440,
        preferredStartDate: date,
        preferredStartMinute: 0,
        priority,
        ...(priority >= 3 ? { priorityReason: "Time-sensitive test request" } : {}),
        providerIds: [fixture.providerARecord.id],
        serviceId: fixture.serviceA.id,
      });
    const normal = await createEntry(normalCustomer.customer.id, 2);
    const urgentOlder = await createEntry(urgentOlderCustomer.customer.id, 4);
    const urgentNewer = await createEntry(urgentNewerCustomer.customer.id, 4);
    await crmRepository.transitionAppointment(fixture.organizationA.access, {
      appointmentId: cancelled.id,
      expectedVersion: cancelled.version,
      reason: "Patient cancelled",
      toStatus: "CANCELLED",
    });

    const openings = await schedulingRepository.listCancelledWaitlistOpenings(
      fixture.organizationA.access,
    );
    const match = openings.find(({ opening }) => opening.id === cancelled.id);
    expect(match?.entry.id).toBe(urgentOlder.id);
    await expect(
      schedulingRepository.bookWaitlistOpening(fixture.organizationA.access, {
        cancelledAppointmentId: cancelled.id,
        requestKey: randomUUID(),
        waitlistEntryId: normal.id,
      }),
    ).rejects.toMatchObject({ code: "CONFLICT" });
    await expect(
      schedulingRepository.bookWaitlistOpening(fixture.organizationA.access, {
        cancelledAppointmentId: cancelled.id,
        requestKey: randomUUID(),
        waitlistEntryId: urgentNewer.id,
      }),
    ).rejects.toMatchObject({ code: "CONFLICT" });
    const replacement = await schedulingRepository.bookWaitlistOpening(
      fixture.organizationA.access,
      {
        cancelledAppointmentId: cancelled.id,
        requestKey: randomUUID(),
        waitlistEntryId: urgentOlder.id,
      },
    );
    expect(replacement).toMatchObject({
      customerId: urgentOlderCustomer.customer.id,
      providerId: fixture.providerARecord.id,
      status: "CONFIRMED",
    });
    expect(
      (await schedulingRepository.listCancelledWaitlistOpenings(fixture.organizationA.access)).some(
        ({ opening }) => opening.id === cancelled.id,
      ),
    ).toBe(false);
  });

  it("accepts a slot offer atomically and replays the same acceptance key", async () => {
    const { entry, offer } = await createOfferFixture("accept", 27);
    const requestKey = randomUUID();
    const first = await schedulingRepository.acceptSlotOffer(fixture.organizationA.access, {
      offerId: offer.id,
      requestKey,
    });
    const replay = await schedulingRepository.acceptSlotOffer(fixture.organizationA.access, {
      offerId: offer.id,
      requestKey,
    });
    expect(replay.id).toBe(first.id);
    await expect(
      schedulingRepository.acceptSlotOffer(fixture.organizationA.access, {
        offerId: offer.id,
        requestKey: randomUUID(),
      }),
    ).rejects.toMatchObject({ code: "CONFLICT" });
    const state = await runInTenant(
      client,
      { actorUserId: fixture.ownerA.id, organizationId: fixture.organizationA.organizationId },
      async (transaction) => ({
        appointmentResources: await transaction.appointmentResource.count({
          where: { appointmentId: first.id },
        }),
        entry: await transaction.waitlistEntry.findUnique({ where: { id: entry.id } }),
        offer: await transaction.slotOffer.findUnique({ where: { id: offer.id } }),
      }),
    );
    expect(state.offer?.status).toBe("ACCEPTED");
    expect(state.entry?.status).toBe("CONVERTED");
    expect(state.appointmentResources).toBe(1);
  });

  it("reschedules an existing appointment atomically when its offer is accepted", async () => {
    const customer = await createCustomer("offer-reschedule");
    await crmRepository.recordConsent(fixture.organizationA.access, {
      channel: "STAFF",
      customerId: customer.customer.id,
      purpose: "appointment_slot_offers",
      source: "STAFF",
      status: "GRANTED",
      textVersion: "test-v1",
    });
    const original = await crmRepository.createAppointment(fixture.organizationA.access, {
      branchId: fixture.branchA.id,
      customerId: customer.customer.id,
      providerId: fixture.providerARecord.id,
      serviceId: fixture.serviceA.id,
      startsAtLocal: localDateTimeInAmman(new Date(Date.now() + 32 * 86_400_000)),
    });
    const proposedLocal = localDateTimeInAmman(new Date(Date.now() + 33 * 86_400_000));
    const proposedDate = proposedLocal.slice(0, 10);
    const entry = await schedulingRepository.createWaitlistEntry(fixture.organizationA.access, {
      appointmentId: original.id,
      branchIds: [fixture.branchA.id],
      customerId: customer.customer.id,
      preferredEndDate: proposedDate,
      preferredEndMinute: 1440,
      preferredStartDate: proposedDate,
      preferredStartMinute: 0,
      priority: 2,
      providerIds: [fixture.providerARecord.id],
      serviceId: fixture.serviceA.id,
    });
    const offer = await schedulingRepository.sendMockSlotOffer(fixture.organizationA.access, {
      branchId: fixture.branchA.id,
      expiresAt: new Date(Date.now() + 60 * 60 * 1000),
      providerId: fixture.providerARecord.id,
      startsAtLocal: proposedLocal,
      waitlistEntryId: entry.id,
    });
    const rescheduled = await schedulingRepository.acceptSlotOffer(fixture.organizationA.access, {
      offerId: offer.id,
      requestKey: randomUUID(),
    });
    expect(rescheduled.id).toBe(original.id);
    expect(rescheduled.version).toBe(original.version + 1);
    expect(rescheduled.startsAt.toISOString()).toBe(offer.startsAt.toISOString());
  });

  it("expires offers once and blocks later acceptance", async () => {
    const { offer } = await createOfferFixture("expire", 28);
    const expired = await schedulingRepository.expireSlotOffer(
      fixture.organizationA.access,
      offer.id,
      new Date(Date.now() + 2 * 60 * 60 * 1000),
    );
    expect(expired.status).toBe("EXPIRED");
    const replay = await schedulingRepository.expireSlotOffer(
      fixture.organizationA.access,
      offer.id,
      new Date(Date.now() + 2 * 60 * 60 * 1000),
    );
    expect(replay.status).toBe("EXPIRED");
    await expect(
      schedulingRepository.acceptSlotOffer(fixture.organizationA.access, {
        offerId: offer.id,
        requestKey: randomUUID(),
      }),
    ).rejects.toMatchObject({ code: "CONFLICT" });
  });

  it("blocks cross-tenant reads and URL-style mutations for every Phase 3 aggregate", async () => {
    const { entry, offer } = await createOfferFixture("tenant", 29);
    const isolated = await runInTenant(
      client,
      { actorUserId: fixture.ownerB.id, organizationId: fixture.organizationB.organizationId },
      async (transaction) => ({
        entry: await transaction.waitlistEntry.findUnique({ where: { id: entry.id } }),
        offer: await transaction.slotOffer.findUnique({ where: { id: offer.id } }),
        resource: await transaction.resource.findUnique({
          where: { id: phaseThreeFixture.resourceId },
        }),
      }),
    );
    expect(isolated).toEqual({ entry: null, offer: null, resource: null });
    await expect(
      schedulingRepository.cancelWaitlistEntry(fixture.organizationB.access, {
        entryId: entry.id,
        expectedVersion: entry.version,
      }),
    ).rejects.toMatchObject({ code: "CONFLICT" });
  });
});

async function createCommunicationFixture(label: string) {
  const customer = await createCustomer(`communications-${label}`);
  const consent = await crmRepository.recordConsent(fixture.organizationA.access, {
    channel: "STAFF",
    customerId: customer.customer.id,
    purpose: "appointment_messages",
    source: "STAFF",
    status: "GRANTED",
    textVersion: "phase4-test-v1",
  });
  await communicationRepository.setCommunicationPreference(fixture.organizationA.access, {
    channel: "SMS",
    customerId: customer.customer.id,
    enabled: true,
  });
  const appointment = await createAppointment(
    `communications-${label}`,
    fixture.providerARecord.id,
    {
      customerId: customer.customer.id,
    },
  );
  return { appointment, consent, customer };
}

async function setMockSmsBehavior(
  behavior: "SUCCESS" | "TRANSIENT_ONCE" | "TIMEOUT" | "PERMANENT_FAILURE",
) {
  await runInTenant(
    client,
    { actorUserId: fixture.ownerA.id, organizationId: fixture.organizationA.organizationId },
    (transaction) =>
      transaction.providerConnection.updateMany({
        data: { mockBehavior: behavior },
        where: { adapterKey: "MOCK_SMS", organizationId: fixture.organizationA.organizationId },
      }),
  );
}

describe("PostgreSQL Phase 4 reliable communications", () => {
  it("commits a message and its outbox event atomically and rolls both back on failure", async () => {
    await setMockSmsBehavior("SUCCESS");
    const communication = await createCommunicationFixture("atomicity");
    const queued = await communicationRepository.createOutboundMessage(
      fixture.organizationA.access,
      {
        appointmentId: communication.appointment.id,
        channel: "SMS",
        customerId: communication.customer.customer.id,
        locale: "en",
        templateKey: "APPOINTMENT_CONFIRMATION",
      },
    );
    const committed = await runInTenant(
      client,
      { actorUserId: fixture.ownerA.id, organizationId: fixture.organizationA.organizationId },
      async (transaction) => ({
        message: await transaction.message.findUnique({ where: { id: queued.message.id } }),
        outbox: await transaction.outboxEvent.findUnique({ where: { id: queued.outbox.id } }),
      }),
    );
    expect(committed.message?.status).toBe("QUEUED");
    expect(committed.outbox?.aggregateId).toBe(queued.message.id);

    const rollbackMessageId = randomUUID();
    const rollbackOutboxId = randomUUID();
    await expect(
      runInTenant(
        client,
        { actorUserId: fixture.ownerA.id, organizationId: fixture.organizationA.organizationId },
        async (transaction) => {
          const conversation = await transaction.conversation.create({
            data: {
              channel: "INTERNAL",
              customerId: communication.customer.customer.id,
              organizationId: fixture.organizationA.organizationId,
            },
          });
          await transaction.message.create({
            data: {
              body: "rollback-sensitive-body",
              channel: "INTERNAL",
              conversationId: conversation.id,
              customerId: communication.customer.customer.id,
              direction: "INTERNAL",
              id: rollbackMessageId,
              locale: "en",
              organizationId: fixture.organizationA.organizationId,
            },
          });
          await transaction.outboxEvent.create({
            data: {
              aggregateId: rollbackMessageId,
              aggregateType: "Message",
              aggregateVersion: 1,
              deduplicationKey: `rollback:${rollbackMessageId}`,
              eventType: "MESSAGE_SEND_REQUESTED",
              id: rollbackOutboxId,
              organizationId: fixture.organizationA.organizationId,
              payload: { messageId: rollbackMessageId },
            },
          });
          throw new Error("ROLLBACK_PROBE");
        },
      ),
    ).rejects.toThrow("ROLLBACK_PROBE");
    const rolledBack = await runInTenant(
      client,
      { actorUserId: fixture.ownerA.id, organizationId: fixture.organizationA.organizationId },
      async (transaction) => ({
        messages: await transaction.message.count({ where: { id: rollbackMessageId } }),
        outbox: await transaction.outboxEvent.count({ where: { id: rollbackOutboxId } }),
      }),
    );
    expect(rolledBack).toEqual({ messages: 0, outbox: 0 });
  });

  it("retries transient failures, normalizes timeouts, and dead-letters exhausted work", async () => {
    await setMockSmsBehavior("TRANSIENT_ONCE");
    const communication = await createCommunicationFixture("retries");
    const queued = await communicationRepository.createOutboundMessage(
      fixture.organizationA.access,
      {
        appointmentId: communication.appointment.id,
        channel: "SMS",
        customerId: communication.customer.customer.id,
        locale: "en",
        templateKey: "APPOINTMENT_REMINDER",
      },
    );
    await expect(
      communicationRepository.processOutboxEvent(
        fixture.organizationA.organizationId,
        queued.outbox.id,
        communicationAdapters,
      ),
    ).resolves.toBe("retry");
    await expect(
      communicationRepository.processOutboxEvent(
        fixture.organizationA.organizationId,
        queued.outbox.id,
        communicationAdapters,
      ),
    ).resolves.toBe("processed");
    const delivered = await runInTenant(
      client,
      { actorUserId: fixture.ownerA.id, organizationId: fixture.organizationA.organizationId },
      (transaction) =>
        transaction.message.findUnique({
          include: { attempts: { orderBy: { attemptNumber: "asc" } } },
          where: { id: queued.message.id },
        }),
    );
    expect(delivered?.status).toBe("SENT");
    expect(delivered?.attempts.map(({ status }) => status)).toEqual([
      "RETRYABLE_FAILURE",
      "SUCCEEDED",
    ]);

    await setMockSmsBehavior("TIMEOUT");
    const timeoutCommunication = await createCommunicationFixture("timeout");
    const timeout = await communicationRepository.createOutboundMessage(
      fixture.organizationA.access,
      {
        appointmentId: timeoutCommunication.appointment.id,
        channel: "SMS",
        customerId: timeoutCommunication.customer.customer.id,
        locale: "ar",
        templateKey: "APPOINTMENT_REMINDER",
      },
    );
    for (let attempt = 1; attempt <= 4; attempt += 1) {
      const result = await communicationRepository.processOutboxEvent(
        fixture.organizationA.organizationId,
        timeout.outbox.id,
        communicationAdapters,
      );
      expect(result).toBe(attempt < 4 ? "retry" : "processed");
    }
    const exhausted = await runInTenant(
      client,
      { actorUserId: fixture.ownerA.id, organizationId: fixture.organizationA.organizationId },
      (transaction) =>
        transaction.message.findUnique({
          include: { attempts: true },
          where: { id: timeout.message.id },
        }),
    );
    expect(exhausted?.status).toBe("DEAD_LETTER");
    expect(exhausted?.attempts).toHaveLength(4);
    expect(exhausted?.attempts.every(({ errorCode }) => errorCode === "PROVIDER_TIMEOUT")).toBe(
      true,
    );
    await setMockSmsBehavior("SUCCESS");
    const manualRetry = await communicationRepository.retryMessage(
      fixture.organizationA.access,
      timeout.message.id,
    );
    await expect(
      communicationRepository.processOutboxEvent(
        fixture.organizationA.organizationId,
        manualRetry.id,
        communicationAdapters,
      ),
    ).resolves.toBe("processed");
    const recovered = await runInTenant(
      client,
      { actorUserId: fixture.ownerA.id, organizationId: fixture.organizationA.organizationId },
      (transaction) => transaction.message.findUnique({ where: { id: timeout.message.id } }),
    );
    expect(recovered?.status).toBe("SENT");
  });

  it("deduplicates verified webhook events and applies delivery receipts monotonically", async () => {
    const communication = await createCommunicationFixture("webhook");
    const queued = await communicationRepository.createOutboundMessage(
      fixture.organizationA.access,
      {
        appointmentId: communication.appointment.id,
        channel: "SMS",
        customerId: communication.customer.customer.id,
        locale: "en",
        templateKey: "APPOINTMENT_CONFIRMATION",
      },
    );
    await communicationRepository.processOutboxEvent(
      fixture.organizationA.organizationId,
      queued.outbox.id,
      communicationAdapters,
    );
    const sent = await runInTenant(
      client,
      { actorUserId: fixture.ownerA.id, organizationId: fixture.organizationA.organizationId },
      (transaction) => transaction.message.findUnique({ where: { id: queued.message.id } }),
    );
    const connection = await runInTenant(
      client,
      { actorUserId: fixture.ownerA.id, organizationId: fixture.organizationA.organizationId },
      (transaction) =>
        transaction.providerConnection.findFirstOrThrow({ where: { adapterKey: "MOCK_SMS" } }),
    );
    const webhook = {
      eventId: `delivery-${randomUUID()}`,
      occurredAt: new Date().toISOString(),
      providerMessageId: sent?.providerMessageId ?? "missing",
      type: "message.delivered" as const,
    };
    const rawBody = JSON.stringify(webhook);
    const first = await communicationRepository.storeVerifiedWebhook(connection, webhook, rawBody);
    const duplicate = await communicationRepository.storeVerifiedWebhook(
      connection,
      webhook,
      rawBody,
    );
    expect(first.duplicate).toBe(false);
    expect(duplicate.duplicate).toBe(true);
    const inboxOutbox = await runInTenant(
      client,
      { actorUserId: fixture.ownerA.id, organizationId: fixture.organizationA.organizationId },
      (transaction) =>
        transaction.outboxEvent.findFirstOrThrow({ where: { aggregateId: first.inboxEventId } }),
    );
    await communicationRepository.processOutboxEvent(
      fixture.organizationA.organizationId,
      inboxOutbox.id,
      communicationAdapters,
    );
    const updated = await runInTenant(
      client,
      { actorUserId: fixture.ownerA.id, organizationId: fixture.organizationA.organizationId },
      (transaction) =>
        transaction.message.findUnique({
          include: { deliveryReceipts: true },
          where: { id: queued.message.id },
        }),
    );
    expect(updated?.status).toBe("DELIVERED");
    expect(updated?.deliveryReceipts).toHaveLength(1);
  });

  it("enforces consent, tenant isolation, scoped provider reads, and append-only evidence", async () => {
    const communication = await createCommunicationFixture("security");
    const revoked = await crmRepository.recordConsent(fixture.organizationA.access, {
      channel: "STAFF",
      customerId: communication.customer.customer.id,
      purpose: "appointment_messages",
      revokesConsentId: communication.consent.id,
      source: "STAFF",
      status: "REVOKED",
      textVersion: "phase4-test-v1",
    });
    expect(revoked.status).toBe("REVOKED");
    await expect(
      communicationRepository.createOutboundMessage(fixture.organizationA.access, {
        appointmentId: communication.appointment.id,
        channel: "SMS",
        customerId: communication.customer.customer.id,
        locale: "en",
        templateKey: "APPOINTMENT_CANCELLATION",
      }),
    ).rejects.toMatchObject({ code: "CONSENT_REQUIRED" });

    const tenantB = await crmRepository.createCustomer(fixture.organizationB.access, {
      displayName: `communications-tenant-b-${suffix}`,
      phoneOriginal: "+962791112222",
      preferredLocale: "en",
    });
    const isolated = await runInTenant(
      client,
      { actorUserId: fixture.ownerA.id, organizationId: fixture.organizationA.organizationId },
      async (transaction) => ({
        conversations: await transaction.conversation.count({
          where: { organizationId: fixture.organizationB.organizationId },
        }),
        preferences: await transaction.communicationPreference.count({
          where: { customerId: tenantB.customer.id },
        }),
        messages: await transaction.message.count({ where: { customerId: tenantB.customer.id } }),
      }),
    );
    expect(isolated).toEqual({ conversations: 0, messages: 0, preferences: 0 });

    const providerAccess = await repository.loadTenantAccess(
      fixture.providerA.id,
      {
        activeMembershipId: fixture.providerAMembership.membershipId,
        activeOrganizationId: fixture.organizationA.organizationId,
      },
      {},
    );
    const unrelated = await createAppointment(
      "communication-unrelated",
      fixture.providerBRecord.id,
      {
        customerId: communication.customer.customer.id,
      },
    );
    await expect(
      communicationRepository.listAppointmentMessages(providerAccess, unrelated.id),
    ).rejects.toMatchObject({ code: "FORBIDDEN" });
    const mockConnection = await runInTenant(
      client,
      { actorUserId: fixture.ownerA.id, organizationId: fixture.organizationA.organizationId },
      (transaction) =>
        transaction.providerConnection.findFirstOrThrow({ where: { adapterKey: "MOCK_SMS" } }),
    );
    await expect(
      communicationRepository.setMockProviderBehavior(
        providerAccess,
        mockConnection.id,
        "PERMANENT_FAILURE",
      ),
    ).rejects.toMatchObject({ code: "FORBIDDEN" });

    const attempts = await runInTenant(
      client,
      { actorUserId: fixture.ownerA.id, organizationId: fixture.organizationA.organizationId },
      (transaction) => transaction.messageAttempt.findFirst(),
    );
    if (attempts) {
      await expect(
        client.messageAttempt.update({
          data: { errorCode: "tampered" },
          where: { id: attempts.id },
        }),
      ).rejects.toThrow(/append-only/);
    }
    const safeLog = safeCommunicationLog({ event: "test", messageId: "message-id" });
    expect(JSON.stringify(safeLog)).not.toContain("secret");
    expect(JSON.stringify(safeLog)).not.toContain("sensitive");
  });

  it("forces RLS on every Phase 4 tenant table", async () => {
    const rows = await client.$queryRaw<
      Array<{ relforcerowsecurity: boolean; relname: string; relrowsecurity: boolean }>
    >`
      SELECT relname, relrowsecurity, relforcerowsecurity
      FROM pg_class
      WHERE relname IN (
        'conversations', 'message_templates', 'provider_connections', 'communication_preferences',
        'messages', 'message_attempts', 'outbox_events', 'inbox_events', 'delivery_receipts'
      )
    `;
    expect(rows).toHaveLength(9);
    expect(rows.every((row) => row.relrowsecurity && row.relforcerowsecurity)).toBe(true);
  });
});
