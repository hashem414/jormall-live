import "server-only";

import { requirePermission, type ResourceScope } from "@jormall/auth/tenant-policy";
import { prisma } from "@jormall/db/client";
import { AIFoundationRepository } from "@jormall/db/ai-foundation-repository";
import { CopilotRepository } from "@jormall/db/copilot-repository";
import { AIChannelRepository } from "@jormall/db/ai-channel-repository";
import { CrmAppointmentRepository } from "@jormall/db/crm-appointment-repository";
import { CommunicationRepository } from "@jormall/db/communication-repository";
import { IdentityRepository, type SessionTenantSelection } from "@jormall/db/identity-repository";
import { OperationsIntelligenceRepository } from "@jormall/db/operations-intelligence-repository";
import { OperationalWorkflowsRepository } from "@jormall/db/operational-workflows-repository";
import { SchedulingRepository } from "@jormall/db/scheduling-repository";
import type { PermissionCode, TenantAccessSnapshot } from "@jormall/domain/identity";
import { DomainError } from "@jormall/domain/errors";
import { redirect } from "next/navigation";

import { requestAuditDetails } from "./request-context";
import { requireSession } from "./session";

export const identityRepository = new IdentityRepository(prisma);
export const crmAppointmentRepository = new CrmAppointmentRepository(prisma);
export const communicationRepository = new CommunicationRepository(prisma);
export const schedulingRepository = new SchedulingRepository(prisma);
export const aiFoundationRepository = new AIFoundationRepository(prisma);
export const aiChannelRepository = new AIChannelRepository(prisma);
export const copilotRepository = new CopilotRepository(prisma);
export const operationsIntelligenceRepository = new OperationsIntelligenceRepository(prisma);
export const operationalWorkflowsRepository = new OperationalWorkflowsRepository(prisma);

export async function requireTenantAccess(locale: string): Promise<TenantAccessSnapshot> {
  const session = await requireSession(locale);
  const selection: SessionTenantSelection = {
    ...(session.session.activeMembershipId
      ? { activeMembershipId: session.session.activeMembershipId }
      : {}),
    ...(session.session.activeOrganizationId
      ? { activeOrganizationId: session.session.activeOrganizationId }
      : {}),
    ...(session.session.activeSupportAccessId
      ? { activeSupportAccessId: session.session.activeSupportAccessId }
      : {}),
  };
  const access = await identityRepository.loadTenantAccess(
    session.user.id,
    selection,
    await requestAuditDetails(),
  );
  if (!access.grants.some(({ code }) => code === "branches.read")) return access;

  const permittedBranches = await identityRepository.listBranches(access);
  const requestedBranch = session.session.activeBranchId;
  const activeBranchId = permittedBranches.some(({ id }) => id === requestedBranch)
    ? requestedBranch
    : permittedBranches[0]?.id;

  if (activeBranchId && activeBranchId !== requestedBranch) {
    await prisma.session.updateMany({
      data: { activeBranchId },
      where: { id: session.session.id, userId: session.user.id },
    });
  }

  return activeBranchId ? { ...access, activeBranchId } : access;
}

export async function requireTenantPermission(
  locale: string,
  permission: PermissionCode,
  resource: ResourceScope = {},
): Promise<TenantAccessSnapshot> {
  const access = await requireTenantAccess(locale);
  requirePermission(access, permission, resource);
  return access;
}

export async function requirePagePermission(
  locale: string,
  permission: PermissionCode,
  resource: ResourceScope = {},
): Promise<TenantAccessSnapshot> {
  let code = "INTERNAL_ERROR";
  try {
    return await requireTenantPermission(locale, permission, resource);
  } catch (error) {
    if (error instanceof DomainError) {
      code = error.code;
    }
  }
  redirect(`/${locale}/dashboard?error=${encodeURIComponent(code)}`);
}

export async function requirePageCollectionPermission(
  locale: string,
  permission: PermissionCode,
): Promise<TenantAccessSnapshot> {
  let code = "INTERNAL_ERROR";
  try {
    const access = await requireTenantAccess(locale);
    if (!access.grants.some((grant) => grant.code === permission)) {
      throw new DomainError({ code: "FORBIDDEN", message: "Permission is required." });
    }
    return access;
  } catch (error) {
    if (error instanceof DomainError) {
      code = error.code;
    }
  }
  redirect(`/${locale}/dashboard?error=${encodeURIComponent(code)}`);
}
