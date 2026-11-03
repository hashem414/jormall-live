import { expect, test } from "@playwright/test";

test("persistent Karmalite routes load in authenticated English, Arabic, and mobile views", async ({
  page,
}) => {
  test.setTimeout(90_000);
  const email = process.env.KARMALITE_LOCAL_TEST_EMAIL;
  const password = process.env.KARMALITE_LOCAL_TEST_PASSWORD;
  test.skip(!email || !password, "Karmalite local smoke credentials are required.");

  await page.goto("/en/login");
  await page.getByLabel("Email address").fill(email ?? "");
  await page.getByLabel("Password").fill(password ?? "");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/en\/dashboard$/u, { timeout: 15_000 });
  await expect(page.locator(".header-organization-brand strong")).toHaveText(
    "Karmalite Medical Esthetic",
  );
  const activeBranch = page.locator('#activeBranchId[name="branchId"]');
  await expect(activeBranch).toBeVisible();
  await expect(activeBranch.locator("option")).toHaveCount(1);
  await expect(activeBranch.locator('option[value=""]')).toHaveCount(0);

  for (const [path, heading] of [
    ["/en/schedule/today", "Appointments"],
    ["/en/schedule/calendar", "Calendar"],
    ["/en/schedule/appointments", "Appointments"],
    ["/en/customers", "Patients"],
    ["/en/business/doctors", "Doctors"],
    ["/en/business/roles-access", "Roles & Access"],
    ["/en/business/services", "Services"],
    ["/en/business/resources", "Resources"],
    ["/en/schedule/waitlist", "Waitlist"],
    ["/en/notifications", "Notifications"],
    ["/en/inbox/escalations", "Chatbot Escalations"],
    ["/en/business/inventory", "Inventory"],
  ] as const) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
    await expect(page.locator("body")).not.toContainText("Internal Server Error");
  }

  await page.goto("/en/business/roles-access");
  await expect(page.locator('input[name="permissionCodes"]').first()).toBeVisible();
  const roleCard = page.locator("article.role-card").first();
  await expect(roleCard.getByText("Maximize", { exact: true })).toBeAttached();
  await expect(roleCard.locator(".role-card-toggle svg")).toBeVisible();
  await roleCard.locator(".role-card-summary").click();
  await expect(roleCard.getByText("Minimize", { exact: true })).toBeAttached();
  await roleCard.getByText("Add person with this role", { exact: true }).click();
  await expect(roleCard.locator('input[name="roleId"]')).toHaveValue(/.+/u);

  await page.goto("/en/schedule/waitlist");
  await expect(page.getByRole("navigation", { name: "Schedule sections" })).toHaveCount(0);

  await page.goto("/en/schedule/appointments?tab=all");
  await expect(page.locator(".appointments-kpi-grid .appointment-metric-card")).toHaveCount(7);
  await expect(page.locator(".appointment-category-tabs")).toBeVisible();
  await expect(page.locator(".appointment-status-filters")).toBeVisible();
  await expect(page.getByRole("link", { name: "Remove all filters" })).toBeVisible();
  await expect(page.locator(".appointment-advanced-filters")).not.toHaveAttribute("open", "");
  await page.locator(".appointment-advanced-filters summary").click();
  await expect(page.locator(".appointment-advanced-filter-grid")).toBeVisible();
  await expect(page.locator(".appointment-table-card")).toBeVisible();
  const appointmentLink = page.locator('a[href*="appointment="]').first();
  await expect(appointmentLink).toBeVisible();
  await appointmentLink.click();
  await expect(page.getByLabel("Appointment details")).toBeVisible();

  await page.setViewportSize({ height: 844, width: 390 });
  await page.goto("/ar/business/inventory");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.getByRole("heading", { level: 1, name: "المخزون" })).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
  ).toBe(true);
});
