import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { AIFoundationRepository } from "@jormall/db/ai-foundation-repository";
import { AIChannelRepository } from "@jormall/db/ai-channel-repository";
import { prisma } from "@jormall/db/client";
import {
  ConfigurationApprovalStatus,
  OrganizationStatus,
  PlatformRole,
} from "@jormall/db/generated/enums";
import { IdentityRepository } from "@jormall/db/identity-repository";
import { SchedulingRepository } from "@jormall/db/scheduling-repository";
import { z } from "zod";

import { auth } from "../src/server/auth-config";
import { karmaliteTemplate } from "../src/server/karmalite-template";

const environment = z
  .object({
    DEV_SEED_PASSWORD: z.string().min(12).optional(),
    KARMALITE_OWNER_EMAIL: z.email().trim().toLowerCase(),
    KARMALITE_PROVISIONING_ADMIN_EMAIL: z.email().trim().toLowerCase(),
    NEXT_PUBLIC_APP_URL: z.url(),
    NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  })
  .parse(process.env);

const appUrl = new URL(environment.NEXT_PUBLIC_APP_URL);
const localAppUrl =
  appUrl.protocol === "http:" &&
  (appUrl.hostname === "localhost" || appUrl.hostname === "127.0.0.1");
if (appUrl.protocol !== "https:" && !localAppUrl) {
  throw new Error("NEXT_PUBLIC_APP_URL must use HTTPS, except for local development.");
}

const identity = new IdentityRepository(prisma);
const scheduling = new SchedulingRepository(prisma);
const aiFoundation = new AIFoundationRepository(prisma);
const aiChannels = new AIChannelRepository(prisma);
const auditDetails = { userAgent: "karmalite-provisioning-script" } as const;
const commandArguments = process.argv.slice(2);
if (
  commandArguments.some(
    (argument) => argument !== "--force" && argument !== "--rotate-owner-invitation",
  )
) {
  throw new Error("Supported options are --force and --rotate-owner-invitation.");
}
const forceUpdate = commandArguments.includes("--force");
const rotateOwnerInvitation = commandArguments.includes("--rotate-owner-invitation");

async function provisioningAdmin() {
  const existing = await prisma.user.findUnique({
    where: { email: environment.KARMALITE_PROVISIONING_ADMIN_EMAIL },
  });
  if (existing) {
    if (existing.platformRole !== PlatformRole.JORMALL_SUPER_ADMIN) {
      throw new Error(
        "The configured provisioning administrator exists without the required platform role.",
      );
    }
    return existing;
  }
  if (
    environment.NODE_ENV === "production" ||
    !environment.KARMALITE_PROVISIONING_ADMIN_EMAIL.endsWith("@example.invalid")
  ) {
    throw new Error(
      "Production provisioning requires an existing verified platform administrator.",
    );
  }
  if (!environment.DEV_SEED_PASSWORD) {
    throw new Error(
      "DEV_SEED_PASSWORD is required to create the reserved local provisioning administrator.",
    );
  }
  const registration = await auth.api.signUpEmail({
    body: {
      email: environment.KARMALITE_PROVISIONING_ADMIN_EMAIL,
      name: "Karmalite Local Provisioning Administrator",
      password: environment.DEV_SEED_PASSWORD,
    },
  });
  return prisma.user.update({
    data: { platformRole: PlatformRole.JORMALL_SUPER_ADMIN },
    where: { id: registration.user.id },
  });
}

async function ensureOrganization(actorUserId: string) {
  const existing = await prisma.organization.findUnique({
    where: { slug: karmaliteTemplate.organization.slug },
  });
  if (!existing) {
    const created = await identity.createOrganization(actorUserId, {
      ...karmaliteTemplate.organization,
      ownerEmail: environment.KARMALITE_OWNER_EMAIL,
    });
    await identity.setOrganizationStatus(
      actorUserId,
      created.organizationId,
      OrganizationStatus.ACTIVE,
    );
    const organization = await prisma.organization.findUnique({
      where: { id: created.organizationId },
    });
    if (!organization) throw new Error("Karmalite organization creation did not complete.");
    return { created: true, invitationToken: created.invitationToken, organization };
  }
  if (existing.status === OrganizationStatus.SUSPENDED) {
    throw new Error("Karmalite is suspended; provisioning will not bypass lifecycle controls.");
  }
  if (existing.status === OrganizationStatus.PENDING) {
    await identity.setOrganizationStatus(actorUserId, existing.id, OrganizationStatus.ACTIVE);
  }
  const invitationToken = await identity.ensureOwnerInvitation(
    actorUserId,
    existing.id,
    environment.KARMALITE_OWNER_EMAIL,
    "Secure Karmalite Owner activation requested by tenant provisioning.",
    rotateOwnerInvitation,
  );
  return { created: false, invitationToken, organization: existing };
}

async function configureTenant(
  actorUserId: string,
  organizationId: string,
  organizationCreated: boolean,
): Promise<void> {
  const supportAccessId = await identity.startSupportAccess(
    actorUserId,
    organizationId,
    "Initial audited configuration of the Karmalite beauty-center tenant.",
    auditDetails,
  );
  try {
    const access = await identity.loadTenantAccess(
      actorUserId,
      { activeOrganizationId: organizationId, activeSupportAccessId: supportAccessId },
      auditDetails,
    );
    const currentSettings = await identity.getSettings(access);
    if (!currentSettings) throw new Error("Karmalite organization settings are missing.");
    const applyTemplateValues = organizationCreated || forceUpdate;
    if (applyTemplateValues) {
      await identity.updateOrganizationProfile(access, {
        descriptionAr: karmaliteTemplate.organization.descriptionAr,
        descriptionEn: karmaliteTemplate.organization.descriptionEn,
        nameAr: karmaliteTemplate.organization.nameAr,
        nameEn: karmaliteTemplate.organization.nameEn,
        profileStatus: ConfigurationApprovalStatus.DRAFT,
        subtitleAr: karmaliteTemplate.organization.subtitleAr,
      });
      await identity.updateSettings(access, {
        bookingPolicyStatus: ConfigurationApprovalStatus.DRAFT,
        bookingWindowDays: karmaliteTemplate.settings.bookingWindowDays,
        brandAccentColor: karmaliteTemplate.branding.accentColor,
        brandLogoUrl: karmaliteTemplate.branding.logoUrl,
        brandPrimaryColor: karmaliteTemplate.branding.primaryColor,
        cancellationWindowMins: karmaliteTemplate.settings.cancellationWindowMins,
        confirmationEnabled: karmaliteTemplate.settings.confirmationEnabled,
        currency: karmaliteTemplate.settings.currency,
        defaultAppointmentStatus: karmaliteTemplate.settings.defaultAppointmentStatus,
        defaultLocale: karmaliteTemplate.settings.defaultLocale,
        noShowPolicyAr: karmaliteTemplate.settings.noShowPolicyAr,
        noShowPolicyEn: karmaliteTemplate.settings.noShowPolicyEn,
        reminderLeadMins: karmaliteTemplate.settings.reminderLeadMins,
        rescheduleWindowMins: karmaliteTemplate.settings.rescheduleWindowMins,
        secondaryReminderLeadMins: karmaliteTemplate.settings.secondaryReminderLeadMins,
        timezone: karmaliteTemplate.settings.timezone,
      });
    }

    let branches = await identity.listBranches(access);
    const unrelatedBranches = branches.filter(
      ({ nameEn }) => nameEn !== karmaliteTemplate.branch.nameEn,
    );
    if (unrelatedBranches.length > 0) {
      throw new Error(
        "Karmalite already contains unrelated branches. Provisioning stopped without deleting them.",
      );
    }
    if (branches.length === 0) {
      await identity.createBranch(access, {
        ...karmaliteTemplate.branch,
        locationStatus: ConfigurationApprovalStatus.DRAFT,
      });
      branches = await identity.listBranches(access);
    }
    const branch = branches.find(({ nameEn }) => nameEn === karmaliteTemplate.branch.nameEn);
    if (!branch) throw new Error("The Karmalite branch could not be configured.");
    if (forceUpdate && !organizationCreated) {
      await identity.updateBranch(access, branch.id, {
        ...karmaliteTemplate.branch,
        locationStatus: ConfigurationApprovalStatus.DRAFT,
      });
    }
    if (organizationCreated || forceUpdate) {
      await scheduling.replaceBranchHours(access, branch.id, karmaliteTemplate.hours, auditDetails);
    }

    let services = await identity.listServices(access);
    const approvedNames = new Set(karmaliteTemplate.services.map(({ nameEn }) => nameEn));
    const unrelatedServices = services.filter(({ nameEn }) => !approvedNames.has(nameEn));
    if (unrelatedServices.length > 0) {
      throw new Error(
        "Karmalite already contains services outside the approved five. Provisioning stopped without deleting them.",
      );
    }
    for (const service of karmaliteTemplate.services) {
      if (!services.some(({ nameEn }) => nameEn === service.nameEn)) {
        await identity.createService(access, {
          ...service,
          currency: karmaliteTemplate.settings.currency,
        });
      }
    }
    services = await identity.listServices(access);
    for (const serviceTemplate of karmaliteTemplate.services) {
      const service = services.find(({ nameEn }) => nameEn === serviceTemplate.nameEn);
      if (!service) throw new Error(`Missing Karmalite service: ${serviceTemplate.nameEn}`);
      if (service.defaultPriceMinor !== null) {
        throw new Error(
          `Karmalite service ${service.nameEn} has a numeric price. Provisioning will not overwrite it.`,
        );
      }
      if (forceUpdate && !organizationCreated) {
        await identity.updateService(access, service.id, serviceTemplate);
      }
      const branchConfiguration = service.branches.find(({ branchId }) => branchId === branch.id);
      if (!branchConfiguration || forceUpdate) {
        await identity.configureServiceBranch(access, {
          branchId: branch.id,
          bufferAfterMins: 0,
          bufferBeforeMins: 0,
          durationMins: serviceTemplate.defaultDurationMins,
          isEnabled: true,
          serviceId: service.id,
        });
      }
    }

    const knowledgePath = resolve(
      dirname(fileURLToPath(import.meta.url)),
      "../../../docs/tenants/karmalite/karmalite-beauty-center-knowledge.md",
    );
    const knowledgeContent = await readFile(knowledgePath, "utf8");
    const knowledgeChecksum = createHash("sha256")
      .update(knowledgeContent.replace(/\r\n?/g, "\n").trim())
      .digest("hex");
    const knowledgeSources = await aiFoundation.listKnowledgeSources(access);
    const sourcesThatMustRemainDraft = knowledgeSources.filter(({ name }) =>
      [karmaliteTemplate.knowledge.name, "Karmalite approved beauty-center knowledge"].includes(
        name,
      ),
    );
    for (const source of sourcesThatMustRemainDraft) {
      if (source.activeVersion) {
        await aiFoundation.deactivateKnowledgeSource(access, source.id);
      }
    }
    const existingSource = knowledgeSources.find(
      ({ name }) => name === karmaliteTemplate.knowledge.name,
    );
    if (
      !existingSource ||
      (forceUpdate && existingSource.versions[0]?.checksum !== knowledgeChecksum)
    ) {
      await aiFoundation.ingestKnowledge(access, {
        content: knowledgeContent,
        name: karmaliteTemplate.knowledge.name,
        originalFilename: karmaliteTemplate.knowledge.originalFilename,
        ...(existingSource ? { sourceId: existingSource.id } : {}),
        title: karmaliteTemplate.knowledge.title,
      });
    }

    const prompt = await aiFoundation.getPromptConfiguration(access);
    if (
      applyTemplateValues &&
      !prompt.systemPrompt.endsWith(karmaliteTemplate.aiBusinessGuidance)
    ) {
      await aiFoundation.updatePromptConfiguration(access, {
        allowedActionNames: prompt.allowedActionNames.filter(
          (actionName) =>
            actionName !== "create_booking" &&
            actionName !== "reschedule_booking" &&
            actionName !== "cancel_booking",
        ),
        businessGuidance: karmaliteTemplate.aiBusinessGuidance,
        expectedVersion: prompt.version,
        minimumConfidence: prompt.minimumConfidence,
        monthlyActionLimit: prompt.monthlyActionLimit,
        monthlyCostLimitMicros: prompt.monthlyCostLimitMicros,
        monthlyTokenLimit: prompt.monthlyTokenLimit,
      });
    }

    const channelOverview = await aiChannels.listChannelOverview(access);
    if (channelOverview.widgets.length === 0) {
      await aiChannels.createWidgetConfiguration(access, {
        accentColor: currentSettings.brandAccentColor,
        allowedOrigins: [appUrl.origin],
        defaultLocale: karmaliteTemplate.settings.defaultLocale,
        displayNameAr: karmaliteTemplate.widget.displayNameAr,
        displayNameEn: karmaliteTemplate.widget.displayNameEn,
        name: karmaliteTemplate.widget.name,
        primaryColor: currentSettings.brandPrimaryColor,
      });
    }
  } finally {
    await identity.revokeSupportAccess(actorUserId, supportAccessId, auditDetails);
  }
}

async function main(): Promise<void> {
  const actor = await provisioningAdmin();
  const { created, invitationToken, organization } = await ensureOrganization(actor.id);
  await configureTenant(actor.id, organization.id, created);
  process.stdout.write("Karmalite BEAUTY_CENTER provisioning completed.\n");
  process.stdout.write(
    "Five Draft services were configured with unpublished/null prices and request-only booking.\n",
  );
  process.stdout.write(
    "The clean knowledge source remains Draft and inactive pending Karmalite approval.\n",
  );
  if (invitationToken) {
    const invitationUrl = new URL(`/en/invitations/${invitationToken}`, appUrl).toString();
    const invitationOutputPath = resolve(
      dirname(fileURLToPath(import.meta.url)),
      "../../../.env.karmalite-invitation",
    );
    await writeFile(invitationOutputPath, `KARMALITE_OWNER_INVITATION_URL=${invitationUrl}\n`, {
      encoding: "utf8",
      mode: 0o600,
    });
    process.stdout.write(
      `The private Owner activation URL was written to ${invitationOutputPath}. It expires in seven days.\n`,
    );
  } else {
    process.stdout.write(
      "An active Owner or unexpired pending Owner invitation already exists; no duplicate invitation was issued.\n",
    );
  }
}

try {
  await main();
} finally {
  await prisma.$disconnect();
}
