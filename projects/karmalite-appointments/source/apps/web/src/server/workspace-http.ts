import "server-only";

import type { SessionTenantSelection } from "@jormall/db/identity-repository";
import { DomainError } from "@jormall/domain/errors";

import { identityRepository } from "./identity";
import { requestAuditDetails } from "./request-context";
import { getSession } from "./session";

export async function requireApiTenantAccess() {
  const session = await getSession();
  if (!session) {
    throw new DomainError({ code: "UNAUTHENTICATED", message: "Authentication is required." });
  }
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
  const branches = await identityRepository.listBranches(access);
  const activeBranchId = branches.some(({ id }) => id === session.session.activeBranchId)
    ? session.session.activeBranchId
    : branches[0]?.id;
  return activeBranchId ? { ...access, activeBranchId } : access;
}

export function workspaceJson(value: unknown, status = 200): Response {
  return Response.json(value, {
    headers: { "Cache-Control": "private, no-store" },
    status,
  });
}

export function workspaceError(error: unknown): Response {
  const code = error instanceof DomainError ? error.code : "INTERNAL_ERROR";
  const status =
    code === "UNAUTHENTICATED"
      ? 401
      : code === "FORBIDDEN" || code === "TENANT_SCOPE_VIOLATION"
        ? 403
        : code === "NOT_FOUND"
          ? 404
          : code === "VALIDATION_FAILED"
            ? 400
            : code === "CONFLICT" || code === "IDEMPOTENCY_CONFLICT"
              ? 409
              : 500;
  return workspaceJson({ error: { code } }, status);
}
