import { AIFoundationRepository } from "@jormall/db/ai-foundation-repository";
import { AIChannelRepository } from "@jormall/db/ai-channel-repository";
import { prisma } from "@jormall/db/client";
import { CommunicationRepository } from "@jormall/db/communication-repository";
import { CrmAppointmentRepository } from "@jormall/db/crm-appointment-repository";
import { OrganizationStatus, PlatformRole } from "@jormall/db/generated/enums";
import { IdentityRepository } from "@jormall/db/identity-repository";
import { SchedulingRepository } from "@jormall/db/scheduling-repository";
import { runInTenant } from "@jormall/db/tenant-context";
import { hashPassword } from "better-auth/crypto";

import { auth } from "../src/server/auth-config";

if (process.env.NODE_ENV === "production") {
  throw new Error("Development seed is disabled in production.");
}

const seedPassword = process.env.DEV_SEED_PASSWORD;
if (!seedPassword || seedPassword.length < 12) {
  throw new Error("DEV_SEED_PASSWORD with at least 12 characters is required.");
}

const identity = new IdentityRepository(prisma);
const crm = new CrmAppointmentRepository(prisma);
const communications = new CommunicationRepository(prisma);
const scheduling = new SchedulingRepository(prisma);
const aiFoundation = new AIFoundationRepository(prisma);
const aiChannels = new AIChannelRepository(prisma);
const weekdays = [
  "SUNDAY",
  "MONDAY",
  "TUESDAY",
  "WEDNESDAY",
  "THURSDAY",
  "FRIDAY",
  "SATURDAY",
] as const;

async function ensureUser(email: string, name: string) {
  const existing = await prisma.user.findUnique({
    include: { accounts: { select: { id: true, providerId: true } } },
    where: { email },
  });
  if (existing?.accounts.length) {
    if (!email.endsWith("@example.invalid")) {
      throw new Error("The development seed only updates reserved example.invalid identities.");
    }
    const credential = existing.accounts.find(({ providerId }) => providerId === "credential");
    if (!credential) throw new Error(`Seed identity ${email} has no credential account.`);
    await prisma.$transaction([
      prisma.account.update({
        data: { password: await hashPassword(seedPassword) },
        where: { id: credential.id },
      }),
      prisma.session.deleteMany({ where: { userId: existing.id } }),
    ]);
    return existing;
  }
  if (existing) await prisma.user.delete({ where: { id: existing.id } });
  return (await auth.api.signUpEmail({ body: { email, name, password: seedPassword } })).user;
}

async function ensureOrganization(
  superAdminId: string,
  owner: Readonly<{ email: string; id: string }>,
  input: Readonly<{ nameAr: string; nameEn: string; slug: string }>,
) {
  const existing = await prisma.organization.findUnique({ where: { slug: input.slug } });
  if (existing) {
    await prisma.organizationSettings.update({
      data: { businessSector: "BEAUTY_CENTER" },
      where: { organizationId: existing.id },
    });
    return existing;
  }
  const created = await identity.createOrganization(superAdminId, {
    ...input,
    ownerEmail: owner.email,
  });
  await identity.acceptInvitation(owner.id, owner.email, created.invitationToken);
  await identity.setOrganizationStatus(
    superAdminId,
    created.organizationId,
    OrganizationStatus.ACTIVE,
  );
  const organization = await prisma.organization.findUnique({
    where: { id: created.organizationId },
  });
  if (!organization) throw new Error("Seed beauty center was not created.");
  return organization;
}

async function main(): Promise<void> {
  const [superAdmin, owner, beautyOwner, secondBeautyOwner, secretary, provider] =
    await Promise.all([
      ensureUser("superadmin@example.invalid", "Development Super Admin"),
      ensureUser("owner@example.invalid", "Rose Beauty Owner"),
      ensureUser("beauty-owner@example.invalid", "Luna Beauty Owner"),
      ensureUser("second-beauty-owner@example.invalid", "Silk Beauty Owner"),
      ensureUser("secretary@example.invalid", "Development Secretary"),
      ensureUser("provider@example.invalid", "Development Service Provider"),
    ]);
  await prisma.user.update({
    data: { platformRole: PlatformRole.JORMALL_SUPER_ADMIN },
    where: { id: superAdmin.id },
  });

  const primary = await ensureOrganization(superAdmin.id, owner, {
    nameAr: "مركز روز للتجميل",
    nameEn: "Rose Beauty Center",
    slug: "rose-beauty-center",
  });
  const secondary = await ensureOrganization(superAdmin.id, beautyOwner, {
    nameAr: "مركز لونا للتجميل",
    nameEn: "Luna Beauty Center",
    slug: "luna-beauty-center",
  });
  const third = await ensureOrganization(superAdmin.id, secondBeautyOwner, {
    nameAr: "مركز سيلك للتجميل",
    nameEn: "Silk Beauty Center",
    slug: "silk-beauty-center",
  });

  for (const [organization, organizationOwner, colors] of [
    [primary, owner, { accent: "#f08aaa", primary: "#9f4f88" }],
    [secondary, beautyOwner, { accent: "#d88aa8", primary: "#7f456f" }],
    [third, secondBeautyOwner, { accent: "#db9a72", primary: "#80534f" }],
  ] as const) {
    const membership = await prisma.organizationMembership.findUnique({
      where: {
        organizationId_userId: {
          organizationId: organization.id,
          userId: organizationOwner.id,
        },
      },
    });
    if (!membership) throw new Error("Seed owner membership is missing.");
    const access = await identity.loadTenantAccess(
      organizationOwner.id,
      { activeMembershipId: membership.id, activeOrganizationId: organization.id },
      {},
    );
    const settings = await identity.getSettings(access);
    if (!settings) throw new Error("Seed organization settings are missing.");
    await identity.updateSettings(access, {
      bookingWindowDays: settings.bookingWindowDays,
      brandAccentColor: colors.accent,
      brandLogoUrl: null,
      brandPrimaryColor: colors.primary,
      cancellationWindowMins: settings.cancellationWindowMins,
      confirmationEnabled: settings.confirmationEnabled,
      currency: settings.currency,
      defaultAppointmentStatus:
        settings.defaultAppointmentStatus === "CONFIRMED" ? "CONFIRMED" : "PENDING",
      defaultLocale: settings.defaultLocale,
      noShowPolicyAr: settings.noShowPolicyAr,
      noShowPolicyEn: settings.noShowPolicyEn,
      reminderLeadMins: settings.reminderLeadMins,
      secondaryReminderLeadMins: settings.secondaryReminderLeadMins,
      rescheduleWindowMins: settings.rescheduleWindowMins,
      timezone: settings.timezone,
    });
  }

  const ownerMembership = await prisma.organizationMembership.findUnique({
    where: { organizationId_userId: { organizationId: primary.id, userId: owner.id } },
  });
  if (!ownerMembership) throw new Error("Primary owner membership is missing.");
  const access = await identity.loadTenantAccess(
    owner.id,
    { activeMembershipId: ownerMembership.id, activeOrganizationId: primary.id },
    {},
  );
  const roles = await identity.listRoles(access);
  for (const invitee of [
    { roleKey: "SECRETARY", user: secretary },
    { roleKey: "PROVIDER", user: provider },
  ] as const) {
    const existing = await prisma.organizationMembership.findUnique({
      where: {
        organizationId_userId: { organizationId: primary.id, userId: invitee.user.id },
      },
    });
    if (!existing) {
      const role = roles.find(({ systemKey }) => systemKey === invitee.roleKey);
      if (!role) throw new Error(`Seed role ${invitee.roleKey} is missing.`);
      const token = await identity.createInvitation(access, invitee.user.email, role.id);
      await identity.acceptInvitation(invitee.user.id, invitee.user.email, token);
    }
  }

  if ((await identity.listBranches(access)).length === 0) {
    await identity.createBranch(access, {
      addressAr: "عمان، الأردن",
      addressEn: "Amman, Jordan",
      email: "amman@rose-beauty.example.invalid",
      mapUrl: "https://maps.example.invalid/rose-beauty-amman",
      nameAr: "فرع عمان",
      nameEn: "Amman Branch",
      phone: "+962 6 000 0000",
      timezone: "Asia/Amman",
    });
  }
  if ((await identity.listServices(access)).length === 0) {
    await identity.createService(access, {
      category: "Skin Care",
      currency: "JOD",
      defaultDurationMins: 60,
      defaultPriceMinor: 3500,
      isOnlineBookable: true,
      minimumNoticeMins: 120,
      nameAr: "علاج العناية بالبشرة",
      nameEn: "Skin care treatment",
      postTreatmentInstructionsAr: "استخدمي واقي الشمس وتجنبي الحرارة العالية بعد العلاج.",
      postTreatmentInstructionsEn: "Use sunscreen and avoid high heat after treatment.",
      preTreatmentInstructionsAr: "تجنبي المقشرات القوية قبل العلاج.",
      preTreatmentInstructionsEn: "Avoid strong exfoliants before treatment.",
    });
  }
  const [branch] = await identity.listBranches(access);
  const [service] = await identity.listServices(access);
  const providerMembership = await prisma.organizationMembership.findUnique({
    where: { organizationId_userId: { organizationId: primary.id, userId: provider.id } },
  });
  if (!branch || !service || !providerMembership)
    throw new Error("Seed prerequisites are missing.");

  const providerProfile = await runInTenant(
    prisma,
    { actorUserId: owner.id, organizationId: primary.id },
    async (transaction) => {
      const profile = await transaction.staffProfile.findFirst({
        where: { membershipId: providerMembership.id, organizationId: primary.id },
      });
      if (!profile) throw new Error("Seed service-provider profile is missing.");
      await transaction.staffProfile.update({
        data: { isBookable: true, isDoctor: true },
        where: { id: profile.id },
      });
      await transaction.staffBranchAssignment.upsert({
        create: { branchId: branch.id, organizationId: primary.id, staffProfileId: profile.id },
        update: {},
        where: {
          organizationId_staffProfileId_branchId: {
            branchId: branch.id,
            organizationId: primary.id,
            staffProfileId: profile.id,
          },
        },
      });
      await transaction.staffService.upsert({
        create: {
          isEnabled: true,
          organizationId: primary.id,
          serviceId: service.id,
          staffProfileId: profile.id,
        },
        update: { isEnabled: true },
        where: {
          organizationId_staffProfileId_serviceId: {
            organizationId: primary.id,
            serviceId: service.id,
            staffProfileId: profile.id,
          },
        },
      });
      const existingRules = await transaction.availabilityRule.findMany({
        select: { weekday: true },
        where: { branchId: branch.id, organizationId: primary.id, staffProfileId: profile.id },
      });
      const existingDays = new Set(existingRules.map(({ weekday }) => weekday));
      await transaction.availabilityRule.createMany({
        data: weekdays
          .filter((day) => !existingDays.has(day))
          .map((weekday) => ({
            branchId: branch.id,
            endMinuteLocal: 1440,
            organizationId: primary.id,
            staffProfileId: profile.id,
            startMinuteLocal: 0,
            weekday,
          })),
      });
      return profile;
    },
  );
  await identity.configureServiceBranch(access, {
    branchId: branch.id,
    durationMins: 60,
    isEnabled: true,
    priceMinor: 3500,
    serviceId: service.id,
  });

  const customers = await crm.listCustomers(access, "Leila Beauty");
  const customer =
    customers.find(({ displayName }) => displayName === "Leila Beauty") ??
    (
      await crm.createCustomer(access, {
        displayName: "Leila Beauty",
        phoneOriginal: "079 123 4567",
        preferredLocale: "en",
      })
    ).customer;
  const detail = await crm.getCustomer(access, customer.id);
  for (const purpose of ["appointment_slot_offers", "appointment_messages"] as const) {
    if (
      !detail.consents.some(
        (consent) => consent.purpose === purpose && consent.status === "GRANTED",
      )
    ) {
      await crm.recordConsent(access, {
        channel: "STAFF",
        customerId: customer.id,
        purpose,
        source: "STAFF",
        status: "GRANTED",
        textVersion: "development-v1",
      });
    }
  }
  for (const channel of ["SMS", "WHATSAPP"] as const) {
    await communications.setCommunicationPreference(access, {
      channel,
      customerId: customer.id,
      enabled: true,
      reason: "Development-only mock lifecycle fixture",
    });
  }

  let roomGroup = (await scheduling.listResourceConfiguration(access)).groups.find(
    (group) => group.branchId === branch.id && group.kind === "ROOM",
  );
  if (!roomGroup) {
    roomGroup = await scheduling.createResourceGroup(access, {
      branchId: branch.id,
      kind: "ROOM",
      nameAr: "غرف العلاج",
      nameEn: "Treatment rooms",
    });
  }
  const group = (await scheduling.listResourceConfiguration(access)).groups.find(
    ({ id }) => id === roomGroup.id,
  );
  if (!group?.resources.length) {
    await scheduling.createResource(access, {
      allowedServiceIds: [service.id],
      groupId: roomGroup.id,
      nameAr: "غرفة علاج 1",
      nameEn: "Treatment Room 1",
    });
  }
  await scheduling.setServiceResourceRequirement(access, {
    branchId: branch.id,
    quantity: 1,
    resourceGroupId: roomGroup.id,
    serviceId: service.id,
  });
  if (!(await crm.listAppointments(access, { branchId: branch.id })).length) {
    await crm.createAppointment(access, {
      branchId: branch.id,
      customerId: customer.id,
      providerId: providerProfile.id,
      serviceId: service.id,
      startsAtLocal: localDateTimeInAmman(new Date(Date.now() + 2 * 60 * 60 * 1000)),
    });
  }

  if (!(await aiFoundation.listKnowledgeSources(access)).length) {
    const knowledge = await aiFoundation.ingestKnowledge(access, {
      content:
        "Rose Beauty Center is open Sunday through Thursday from 09:00 to 17:00.\n\nمركز روز للتجميل مفتوح من الأحد إلى الخميس من التاسعة صباحاً حتى الخامسة مساءً.",
      name: "Beauty center information",
      title: "Hours and treatment information",
    });
    await aiFoundation.activateKnowledgeVersion(access, knowledge.sourceId, knowledge.versionId);
  }
  if (!(await aiChannels.listChannelOverview(access)).widgets.length) {
    await aiChannels.createWidgetConfiguration(access, {
      accentColor: "#f08aaa",
      allowedOrigins: ["http://localhost:3000"],
      defaultLocale: "en",
      displayNameAr: "مساعد مركز روز",
      displayNameEn: "Rose Beauty Assistant",
      name: "Local development widget",
      primaryColor: "#9f4f88",
    });
  }
}

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

await main();
await prisma.$disconnect();
process.stdout.write("Development identities and three isolated beauty centers are ready.\n");
