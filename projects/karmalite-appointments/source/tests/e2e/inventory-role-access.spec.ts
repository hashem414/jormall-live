import { expect, test, type Page } from "@playwright/test";

const password = process.env.DEV_SEED_PASSWORD ?? process.env.KARMALITE_LOCAL_TEST_PASSWORD;

async function signIn(page: Page, email: string) {
  await page.goto("/en/login");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password").fill(password ?? "");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/en\/dashboard/u, { timeout: 20_000 });
}

test.describe("Karmalite Inventory role access", () => {
  test.skip(!password, "A local Karmalite test password is required.");

  for (const account of [
    { email: "inventory.manager.qa@localhost.test", role: "Manager" },
    { email: "abualithamchristine@gmail.com", role: "Secretary" },
    { email: "christineabualitham@gmail.com", role: "Service Provider" },
  ]) {
    test(`${account.role} can request items but cannot approve or alter stock`, async ({
      page,
    }) => {
      await signIn(page, account.email);
      await page.goto("/en/business/inventory");

      await expect(page.getByRole("heading", { level: 1, name: "Inventory" })).toBeVisible();
      await expect(page.getByRole("button", { name: "Request New Item" })).toBeVisible();
      await expect(page.getByRole("button", { name: "Create Item" })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Add Location" })).toHaveCount(0);

      await page.goto("/en/business/inventory?tab=requests");
      await expect(page.getByRole("button", { name: "Approve" })).toHaveCount(0);
      await page.goto("/en/business/inventory?tab=receiving");
      await expect(page.getByRole("button", { name: "Receive" })).toHaveCount(0);
    });
  }

  test("Owner sees separate request, approval, and stock-management permissions", async ({
    page,
  }) => {
    await signIn(page, "christin.abuidam@jormall.com");
    await page.goto("/en/business/inventory");

    await expect(page.getByRole("button", { name: "Request New Item" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Create Item" })).toBeVisible();
    await page.goto("/en/business/roles-access");
    await expect(
      page.getByRole("heading", { name: "Inventory & item requests" }).first(),
    ).toBeVisible();
    await expect(
      page
        .getByText(
          "Request new inventory items only allows staff to submit a request. Approval, purchasing, receiving, and stock changes are separate permissions.",
        )
        .first(),
    ).toBeVisible();
    await expect(
      page.locator('input[value="inventory.itemProposal.create"]').first(),
    ).toBeVisible();
    await expect(
      page.locator('input[value="inventory.itemProposal.approve"]').first(),
    ).toBeVisible();
    await expect(page.locator('input[value="inventory.order.receive"]').first()).toBeVisible();

    const createRoleForm = page.locator("form").filter({ hasText: "Add custom role" });
    const selectablePermissions = createRoleForm.locator('input[name="permissionCodes"]');
    await createRoleForm.getByRole("button", { name: "Select all access" }).click();
    expect(await selectablePermissions.count()).toBeGreaterThan(0);
    for (const checkbox of await selectablePermissions.all()) {
      await expect(checkbox).toBeChecked();
    }
    await createRoleForm.getByRole("button", { name: "Clear all access" }).click();
    for (const checkbox of await selectablePermissions.all()) {
      await expect(checkbox).not.toBeChecked();
    }

    const ownerRole = page.locator("article.role-card").filter({ hasText: "Owner" }).first();
    await ownerRole.locator(".role-card-summary").click();
    await expect(ownerRole.getByText("Edit role", { exact: true })).toBeVisible();
    await expect(ownerRole.getByText("Delete role", { exact: true })).toHaveCount(0);
  });

  test("Owner can create, edit, and delete an inventory request-only role", async ({ page }) => {
    test.setTimeout(60_000);
    const suffix = Date.now().toString().slice(-6);
    const initialName = `Stock Requester ${suffix}`;
    const editedName = `Inventory Requester ${suffix}`;
    await signIn(page, "christin.abuidam@jormall.com");
    await page.goto("/en/business/roles-access");

    await page.locator('input[name="nameEn"]').first().fill(initialName);
    await page.locator('input[name="nameAr"]').first().fill(`طالب مخزون ${suffix}`);
    for (const permission of [
      "inventory.items.read",
      "inventory.itemProposal.create",
      "inventory.orderRequest.create",
    ]) {
      await page.locator(`input[value="${permission}"]`).first().check();
    }
    await page.getByRole("button", { name: "Add custom role" }).click();
    const roleCard = page.locator("article.role-card").filter({ hasText: initialName });
    await expect(roleCard).toBeVisible();
    await roleCard.locator(".role-card-summary").click();
    await expect(roleCard.getByText("Minimize", { exact: true })).toBeAttached();

    await roleCard.getByText("Edit role", { exact: true }).click();
    const editForm = roleCard.locator("form").filter({ hasText: "Save changes" });
    await editForm.locator('input[name="nameEn"]').fill(editedName);
    await editForm.getByRole("button", { name: "Save changes" }).click();
    const editedRoleCard = page.locator("article.role-card").filter({ hasText: editedName });
    await expect(editedRoleCard).toBeVisible();

    await editedRoleCard.locator(".role-card-summary").click();
    await editedRoleCard.locator("summary").filter({ hasText: "Delete role" }).click();
    const deleteForm = editedRoleCard.locator("form").filter({ hasText: "delete this role" });
    await deleteForm.locator('input[name="confirmation"]').check();
    await deleteForm.getByRole("button", { name: "Delete role" }).click();
    await expect(page.locator("article.role-card").filter({ hasText: editedName })).toHaveCount(0);
  });

  test("Manager can create and delete only a role within the Manager's own grants", async ({
    page,
  }) => {
    test.setTimeout(60_000);
    const suffix = Date.now().toString().slice(-6);
    const roleName = `Branch Stock Requester ${suffix}`;
    await signIn(page, "inventory.manager.qa@localhost.test");
    await page.goto("/en/business/roles-access");

    await expect(
      page.locator('input[value="inventory.itemProposal.create"]').first(),
    ).toBeVisible();
    await expect(page.locator('input[value="inventory.itemProposal.approve"]')).toHaveCount(0);
    await page.locator('input[name="nameEn"]').first().fill(roleName);
    await page.locator('input[name="nameAr"]').first().fill(`طالب مخزون فرع ${suffix}`);
    for (const permission of [
      "inventory.items.read",
      "inventory.itemProposal.create",
      "inventory.orderRequest.create",
    ]) {
      await page.locator(`input[value="${permission}"]`).first().check();
    }
    await page.getByRole("button", { name: "Add custom role" }).click();
    const roleCard = page.locator("article.role-card").filter({ hasText: roleName });
    await expect(roleCard).toBeVisible();
    await roleCard.locator(".role-card-summary").click();
    await roleCard.locator("summary").filter({ hasText: "Delete role" }).click();
    const deleteForm = roleCard.locator("form").filter({ hasText: "delete this role" });
    await deleteForm.locator('input[name="confirmation"]').check();
    await deleteForm.getByRole("button", { name: "Delete role" }).click();
    await expect(page.locator("article.role-card").filter({ hasText: roleName })).toHaveCount(0);
  });
});
