import { createHash } from "node:crypto";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { prisma } from "@jormall/db/client";
import {
  BusinessSector,
  ConfigurationApprovalStatus,
  InvitationStatus,
  KnowledgeVersionStatus,
  MembershipStatus,
  PlatformRole,
  TenantRoleKey,
} from "@jormall/db/generated/enums";
import { z } from "zod";

import { karmaliteTemplate } from "../src/server/karmalite-template";

const environment = z
  .object({
    KARMALITE_OWNER_EMAIL: z.email().trim().toLowerCase(),
    NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  })
  .parse(process.env);

async function verify(): Promise<void> {
  const organizations = await prisma.organization.findMany({
    where: { slug: karmaliteTemplate.organization.slug },
  });
  assert.equal(organizations.length, 1, "Expected one Karmalite organization.");
  const organization = organizations[0];
  assert.ok(organization);
  assert.equal(organization.nameEn, karmaliteTemplate.organization.nameEn);
  assert.equal(organization.nameAr, karmaliteTemplate.organization.nameAr);
  assert.equal(organization.profileStatus, ConfigurationApprovalStatus.DRAFT);

  const [settings, branches, services, roles, configuredDoctorCount, ownerInvitations, ownerUser] =
    await Promise.all([
      prisma.organizationSettings.findUnique({ where: { organizationId: organization.id } }),
      prisma.branch.findMany({
        include: { hoursRules: true },
        where: { organizationId: organization.id },
      }),
      prisma.service.findMany({
        include: { branches: true },
        where: { organizationId: organization.id },
      }),
      prisma.role.findMany({ where: { organizationId: organization.id } }),
      prisma.staffProfile.count({
        where: { isDoctor: true, organizationId: organization.id },
      }),
      prisma.organizationInvitation.findMany({
        where: {
          email: environment.KARMALITE_OWNER_EMAIL,
          organizationId: organization.id,
        },
      }),
      prisma.user.findUnique({ where: { email: environment.KARMALITE_OWNER_EMAIL } }),
    ]);
  const pendingOwnerInvitations = ownerInvitations.filter(
    ({ status }) => status === InvitationStatus.PENDING,
  );

  assert.ok(settings);
  assert.equal(settings.businessSector, BusinessSector.BEAUTY_CENTER);
  assert.equal(settings.bookingPolicyStatus, ConfigurationApprovalStatus.DRAFT);
  assert.equal(settings.bookingWindowDays, null);
  assert.equal(settings.confirmationEnabled, false);
  assert.equal(settings.brandLogoUrl, karmaliteTemplate.branding.logoUrl);
  assert.equal(settings.brandPrimaryColor.toUpperCase(), karmaliteTemplate.branding.primaryColor);
  assert.equal(settings.brandAccentColor.toUpperCase(), karmaliteTemplate.branding.accentColor);

  assert.equal(branches.length, 1, "Expected exactly one Karmalite branch.");
  const branch = branches[0];
  assert.ok(branch);
  assert.equal(branch.nameEn, karmaliteTemplate.branch.nameEn);
  assert.equal(branch.nameAr, karmaliteTemplate.branch.nameAr);
  assert.equal(branch.email, "info@karmalite.com");
  assert.equal(branch.phone, "+962 6 586 8024");
  assert.equal(branch.mobilePhone, "+962 77 586 8024");
  assert.equal(branch.locationStatus, ConfigurationApprovalStatus.DRAFT);
  assert.deepEqual(branch.hoursRules.map(({ weekday }) => weekday).toSorted(), [
    "MONDAY",
    "SATURDAY",
    "SUNDAY",
    "THURSDAY",
    "TUESDAY",
    "WEDNESDAY",
  ]);
  assert.ok(branch.hoursRules.every(({ startMinuteLocal }) => startMinuteLocal === 540));
  assert.ok(branch.hoursRules.every(({ endMinuteLocal }) => endMinuteLocal === 1140));

  assert.deepEqual(
    services.map(({ nameEn }) => nameEn).toSorted(),
    karmaliteTemplate.services.map(({ nameEn }) => nameEn).toSorted(),
  );
  assert.ok(
    services.every(
      (service) =>
        service.configurationStatus === ConfigurationApprovalStatus.DRAFT &&
        service.defaultPriceMinor === null &&
        service.isOnlineBookable === false &&
        service.minimumNoticeMins === null &&
        service.branches.length === 1 &&
        service.branches[0]?.priceMinor === null,
    ),
    "All five services must remain Draft, request-only, and price-unpublished.",
  );

  assert.deepEqual(roles.map(({ nameEn }) => nameEn).toSorted(), [
    "Manager",
    "Owner",
    "Secretary",
    "Service Provider",
  ]);
  assert.equal(configuredDoctorCount, 0, "No unapproved doctors may be configured.");
  if (ownerUser) {
    assert.equal(ownerUser.platformRole, PlatformRole.USER);
    const ownerMemberships = await prisma.organizationMembership.findMany({
      include: { roles: { include: { role: true } } },
      where: { userId: ownerUser.id },
    });
    const karmaliteOwnerMembership = ownerMemberships.find(
      (membership) =>
        membership.organizationId === organization.id &&
        membership.status === MembershipStatus.ACTIVE &&
        membership.roles.some(({ role }) => role.systemKey === TenantRoleKey.ORGANIZATION_OWNER),
    );
    assert.ok(karmaliteOwnerMembership, "The activated account must be an active Karmalite Owner.");
    if (environment.NODE_ENV === "production") {
      assert.equal(ownerUser.emailVerified, true, "The production Owner email must be verified.");
    }
    assert.equal(
      pendingOwnerInvitations.length,
      0,
      "An activated Owner must not retain a pending invitation.",
    );
    assert.ok(
      ownerInvitations.some(
        ({ acceptedByUserId, status }) =>
          status === InvitationStatus.ACCEPTED && acceptedByUserId === ownerUser.id,
      ),
      "The activated Owner must originate from the secure invitation workflow.",
    );
  } else {
    assert.equal(pendingOwnerInvitations.length, 1, "Expected one pending Owner invitation.");
  }

  const [knowledgeSources, activeKnowledgeCount, prompt, productionProviders, auditActions] =
    await Promise.all([
      prisma.knowledgeSource.findMany({
        include: { versions: { orderBy: { versionNumber: "desc" } } },
        where: { organizationId: organization.id },
      }),
      prisma.knowledgeSource.count({
        where: { activeVersionId: { not: null }, organizationId: organization.id },
      }),
      prisma.promptConfiguration.findFirstOrThrow({
        where: { isActive: true, organizationId: organization.id },
      }),
      prisma.providerConnection.count({
        where: { integrationMode: "PRODUCTION", organizationId: organization.id },
      }),
      prisma.auditEvent.findMany({
        select: { action: true },
        where: { organizationId: organization.id },
      }),
    ]);
  const cleanSource = knowledgeSources.find(
    ({ name }) => name === karmaliteTemplate.knowledge.name,
  );
  assert.ok(cleanSource, "The clean Karmalite knowledge source is missing.");
  assert.equal(cleanSource.activeVersionId, null);
  const knowledgePath = resolve(
    dirname(fileURLToPath(import.meta.url)),
    "../../../docs/tenants/karmalite/karmalite-beauty-center-knowledge.md",
  );
  const expectedKnowledgeChecksum = createHash("sha256")
    .update((await readFile(knowledgePath, "utf8")).replace(/\r\n?/g, "\n").trim())
    .digest("hex");
  assert.ok(cleanSource.versions.length >= 1, "The Draft knowledge version is missing.");
  assert.equal(
    cleanSource.versions[0]?.checksum,
    expectedKnowledgeChecksum,
    "The latest Draft knowledge version must match the reviewed tenant source.",
  );
  assert.ok(
    cleanSource.versions.every(({ status }) => status === KnowledgeVersionStatus.DRAFT),
    "Every Karmalite knowledge version must remain Draft until explicit approval.",
  );
  assert.equal(
    activeKnowledgeCount,
    0,
    "No Draft Karmalite knowledge may be customer-retrievable.",
  );
  assert.equal(productionProviders, 0, "No untested production provider may be claimed.");
  assert.ok(!prompt.allowedActionNames.includes("create_booking"));
  assert.ok(!prompt.allowedActionNames.includes("reschedule_booking"));
  assert.ok(!prompt.allowedActionNames.includes("cancel_booking"));

  const requiredAuditActions = [
    "BRANCH_CREATED",
    "KNOWLEDGE_VERSION_INGESTED",
    "ORGANIZATION_CREATED",
    "ORGANIZATION_PROFILE_UPDATED",
    "ORGANIZATION_SETTINGS_UPDATED",
    "OWNER_INVITATION_ISSUED",
    "SERVICE_CREATED",
  ];
  if (ownerUser) {
    requiredAuditActions.push("INVITATION_ACCEPTED", "MEMBERSHIP_ROLE_ASSIGNED");
  }
  const recordedActions = new Set(auditActions.map(({ action }) => action));
  for (const requiredAction of requiredAuditActions) {
    assert.ok(recordedActions.has(requiredAction), `Missing audit action: ${requiredAction}`);
  }

  process.stdout.write(
    "Karmalite verification passed: 1 BEAUTY_CENTER, 1 branch, 5 Draft services, 0 prices, 0 unapproved doctors, 0 active knowledge versions, and 0 production providers.\n",
  );
}

try {
  await verify();
} finally {
  await prisma.$disconnect();
}
