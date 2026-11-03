import { canAccessResource } from "@jormall/auth/tenant-policy";
import { z } from "zod";

import { crmAppointmentRepository, identityRepository } from "../../../../server/identity";
import {
  requireApiTenantAccess,
  workspaceError,
  workspaceJson,
} from "../../../../server/workspace-http";

const querySchema = z.object({
  locale: z.enum(["en", "ar"]).catch("en"),
  q: z.string().trim().min(2).max(100),
});

type SearchResult = Readonly<{
  href: string;
  id: string;
  label: string;
  secondary: string;
  type: "appointment" | "branch" | "customer" | "service" | "service_provider";
}>;

export async function GET(request: Request): Promise<Response> {
  try {
    const url = new URL(request.url);
    const parsed = querySchema.safeParse({
      locale: url.searchParams.get("locale") ?? "en",
      q: url.searchParams.get("q"),
    });
    if (!parsed.success) return workspaceJson({ error: { code: "VALIDATION_FAILED" } }, 400);
    const access = await requireApiTenantAccess();
    const { locale, q } = parsed.data;
    const needle = q.toLocaleLowerCase(locale);
    const [customers, appointments, services, staff, branches] = await Promise.all([
      canAccessResource(access, "customers.read")
        ? crmAppointmentRepository.listCustomers(access, q)
        : Promise.resolve([]),
      canAccessResource(access, "appointments.read")
        ? crmAppointmentRepository.listAppointments(access)
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
    const results: SearchResult[] = [];
    for (const customer of customers.slice(0, 8)) {
      results.push({
        href: `/${locale}/customers/${customer.id}`,
        id: customer.id,
        label: customer.displayName,
        secondary: customer.referenceCode,
        type: "customer",
      });
    }
    for (const appointment of appointments) {
      const text = [
        appointment.referenceCode,
        appointment.customer.displayName,
        appointment.service.nameEn,
        appointment.service.nameAr,
        appointment.provider.displayNameEn,
        appointment.provider.displayNameAr,
      ]
        .join(" ")
        .toLocaleLowerCase(locale);
      if (text.includes(needle)) {
        results.push({
          href: `/${locale}/schedule/appointments?appointment=${appointment.id}`,
          id: appointment.id,
          label: `${appointment.referenceCode} · ${appointment.customer.displayName}`,
          secondary: locale === "ar" ? appointment.service.nameAr : appointment.service.nameEn,
          type: "appointment",
        });
      }
    }
    for (const service of services) {
      if (
        access.activeBranchId &&
        !service.branches.some(({ branchId }) => branchId === access.activeBranchId)
      )
        continue;
      if (`${service.nameEn} ${service.nameAr}`.toLocaleLowerCase(locale).includes(needle)) {
        results.push({
          href: `/${locale}/business/services`,
          id: service.id,
          label: locale === "ar" ? service.nameAr : service.nameEn,
          secondary: service.category ?? "",
          type: "service",
        });
      }
    }
    for (const membership of staff) {
      if (!membership.roles.some(({ role }) => role.systemKey === "PROVIDER")) continue;
      const profile = membership.staffProfile;
      if (!profile) continue;
      if (
        access.activeBranchId &&
        !profile.branchAssignments.some(({ branchId }) => branchId === access.activeBranchId)
      )
        continue;
      if (
        `${profile.displayNameEn} ${profile.displayNameAr}`
          .toLocaleLowerCase(locale)
          .includes(needle)
      ) {
        results.push({
          href: `/${locale}/business/team?tab=team`,
          id: profile.id,
          label: locale === "ar" ? profile.displayNameAr : profile.displayNameEn,
          secondary: locale === "ar" ? "مقدم خدمة" : "Service Provider",
          type: "service_provider",
        });
      }
    }
    for (const branch of branches) {
      if (access.activeBranchId && branch.id !== access.activeBranchId) continue;
      if (`${branch.nameEn} ${branch.nameAr}`.toLocaleLowerCase(locale).includes(needle)) {
        results.push({
          href: `/${locale}/business/branches`,
          id: branch.id,
          label: locale === "ar" ? branch.nameAr : branch.nameEn,
          secondary: branch.timezone,
          type: "branch",
        });
      }
    }
    return workspaceJson({ results: results.slice(0, 20) });
  } catch (error) {
    return workspaceError(error);
  }
}
