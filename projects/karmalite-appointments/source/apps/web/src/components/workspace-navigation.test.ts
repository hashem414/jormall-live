import type { PermissionGrant } from "@jormall/domain/identity";
import { describe, expect, it } from "vitest";

import { createWorkspaceNavigation } from "./workspace-navigation";

const grants = (codes: readonly PermissionGrant["code"][]): readonly PermissionGrant[] =>
  codes.map((code) => ({ code, scope: "ORGANIZATION" }));

describe("beauty-center workspace navigation", () => {
  it("renders operational workspaces without retired AI screens for owner grants", () => {
    const navigation = createWorkspaceNavigation(
      "en",
      grants([
        "organization.read",
        "organization.settings.manage",
        "appointments.read",
        "waitlist.read",
        "patients.directory.read",
        "conversations.read",
        "conversations.handoff",
        "messages.read",
        "messages.retry",
        "services.read",
        "doctors.directory.read",
        "staff.read",
        "roles.read",
        "resources.read",
        "branches.read",
        "reports.read",
        "predictions.read",
        "knowledge.read",
        "ai.configure",
        "provider_credentials.manage",
        "imports.manage",
        "audit.read",
      ]),
    );

    expect(navigation.map(({ label }) => label)).toEqual([
      "Operations",
      "Business",
      "Customer care",
      "Management",
    ]);
  });

  it("removes destinations that a custom role cannot read", () => {
    const navigation = createWorkspaceNavigation("en", grants(["patients.directory.read"]));

    expect(navigation).toEqual([
      {
        items: [
          {
            href: "/en/customers",
            icon: "customers",
            label: "Patients",
            permissions: ["patients.directory.read"],
          },
        ],
        label: "Operations",
      },
    ]);
  });

  it("uses the fixed Arabic beauty-center labels", () => {
    const navigation = createWorkspaceNavigation(
      "ar",
      grants(["patients.directory.read", "services.read", "staff.read"]),
    );
    const labels = navigation.flatMap(({ items }) => items.map(({ label }) => label));

    expect(labels).toEqual(["المرضى", "الفريق والصلاحيات", "الخدمات"]);
  });

  it("places Waiting List directly after Appointments as a separate destination", () => {
    const navigation = createWorkspaceNavigation(
      "en",
      grants(["organization.read", "appointments.read", "waitlist.read"]),
    );
    expect(navigation[0]?.items.map(({ href, label }) => ({ href, label }))).toEqual([
      { href: "/en/dashboard", label: "Home" },
      { href: "/en/schedule/today", label: "Appointments" },
      { href: "/en/schedule/waitlist", label: "Waiting List" },
    ]);
  });

  it("shows Roles & Access as a separate business destination only to role managers", () => {
    const navigation = createWorkspaceNavigation(
      "en",
      grants(["staff.read", "roles.read", "roles.manage"]),
    );
    expect(navigation[0]?.items.map(({ href, label }) => ({ href, label }))).toEqual([
      { href: "/en/business/team", label: "Team & Access" },
      { href: "/en/business/roles-access", label: "Roles & Access" },
    ]);

    const readOnlyNavigation = createWorkspaceNavigation("en", grants(["roles.read"]));
    expect(readOnlyNavigation.flatMap(({ items }) => items.map(({ href }) => href))).not.toContain(
      "/en/business/roles-access",
    );
  });
});

describe("retired organization navigation", () => {
  it.each(["en", "ar"] as const)(
    "does not restore retired links through grants in %s",
    (locale) => {
      const navigation = createWorkspaceNavigation(
        locale,
        grants(["knowledge.read", "ai.configure", "conversations.handoff", "conversations.read"]),
      );
      expect(navigation.flatMap(({ items }) => items.map(({ href }) => href))).toEqual([
        `/${locale}/inbox?tab=conversations`,
      ]);
    },
  );
});
