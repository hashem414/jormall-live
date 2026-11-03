import { describe, expect, it } from "vitest";

import { defaultRolePermissions } from "./identity";

describe("default role permissions", () => {
  it("allows organization managers to manage tenant roles", () => {
    expect(defaultRolePermissions.ORGANIZATION_MANAGER).toContainEqual({
      code: "roles.manage",
      scope: "ORGANIZATION",
    });
  });

  it("does not allow secretaries or service providers to manage roles", () => {
    expect(defaultRolePermissions.SECRETARY).not.toContainEqual(
      expect.objectContaining({ code: "roles.manage" }),
    );
    expect(defaultRolePermissions.PROVIDER).not.toContainEqual(
      expect.objectContaining({ code: "roles.manage" }),
    );
  });

  it.each(["ORGANIZATION_MANAGER", "SECRETARY"] as const)(
    "allows %s to view assigned-branch inventory and submit requests",
    (role) => {
      expect(defaultRolePermissions[role]).toEqual(
        expect.arrayContaining([
          { code: "inventory.items.read", scope: "ASSIGNED_BRANCHES" },
          { code: "inventory.itemProposal.create", scope: "ASSIGNED_BRANCHES" },
          { code: "inventory.orderRequest.create", scope: "ASSIGNED_BRANCHES" },
        ]),
      );
    },
  );

  it.each(["ORGANIZATION_MANAGER", "SECRETARY"] as const)(
    "does not let %s approve or change stock by default",
    (role) => {
      const restrictedPermissions = new Set([
        "inventory.itemProposal.approve",
        "inventory.orderRequest.approve",
        "inventory.order.markOrdered",
        "inventory.order.receive",
        "inventory.stock.adjust",
        "inventory.stock.transfer",
        "inventory.cost.read",
      ]);
      expect(defaultRolePermissions[role].some(({ code }) => restrictedPermissions.has(code))).toBe(
        false,
      );
    },
  );
});
