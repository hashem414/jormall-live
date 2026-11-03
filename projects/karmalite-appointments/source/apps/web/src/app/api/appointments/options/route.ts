import { canAccessResource } from "@jormall/auth/tenant-policy";

import { crmAppointmentRepository, identityRepository } from "../../../../server/identity";
import {
  requireApiTenantAccess,
  workspaceError,
  workspaceJson,
} from "../../../../server/workspace-http";

export async function GET(): Promise<Response> {
  try {
    const access = await requireApiTenantAccess();
    const [customers, services, memberships, branches] = await Promise.all([
      canAccessResource(access, "customers.read")
        ? crmAppointmentRepository.listCustomers(access)
        : Promise.resolve([]),
      canAccessResource(access, "services.read")
        ? identityRepository.listServices(access)
        : Promise.resolve([]),
      canAccessResource(access, "staff.read")
        ? identityRepository.listStaff(access)
        : Promise.resolve([]),
      canAccessResource(access, "branches.read")
        ? identityRepository.listBranches(access)
        : Promise.resolve([]),
    ]);
    return workspaceJson({
      branches: branches.filter(({ isActive }) => isActive),
      customers: customers.map(({ displayName, id, referenceCode }) => ({
        displayName,
        id,
        referenceCode,
      })),
      serviceProviders: memberships.flatMap(({ roles, staffProfile }) =>
        staffProfile && roles.some(({ role }) => role.systemKey === "PROVIDER")
          ? [staffProfile]
          : [],
      ),
      services: services.filter(({ isActive }) => isActive),
    });
  } catch (error) {
    return workspaceError(error);
  }
}
