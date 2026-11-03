import { expect, test } from "@playwright/test";

test("renders the English login page", async ({ page }) => {
  await page.goto("/en");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Sign in");
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
});

test("renders the Arabic login page right-to-left", async ({ page }) => {
  await page.goto("/ar");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("تسجيل الدخول");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.locator("html")).toHaveAttribute("lang", "ar");
});

test("blocks the public credential sign-up endpoint", async ({ request }) => {
  const response = await request.post("/api/auth/sign-up/email", {
    data: {
      email: "uninvited@example.invalid",
      name: "Uninvited User",
      password: "not-a-real-password",
    },
  });
  expect(response.status()).toBe(404);
  await expect(response.json()).resolves.toMatchObject({ code: "INVITATION_REQUIRED" });
});

test("an owner enters only their organization without a tenant switcher", async ({ page }) => {
  const seedPassword = process.env.DEV_SEED_PASSWORD;
  test.skip(!seedPassword, "DEV_SEED_PASSWORD is required for the authenticated browser test.");
  await page.goto("/en/login");
  await page.getByLabel("Email address").fill("owner@example.invalid");
  await page.getByLabel("Password").fill(seedPassword ?? "");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/en\/dashboard$/u, { timeout: 15_000 });
  await expect(page.getByRole("heading", { level: 1, name: "Rose Beauty Center" })).toBeVisible();
  await expect(page.getByText("Owner overview", { exact: true })).toBeVisible();
  await expect(page.locator(".header-organization-brand strong")).toHaveText("Rose Beauty Center");
  await expect(page.getByLabel("Switch organization")).toHaveCount(0);
  await expect(page.locator(".global-search")).toHaveCount(0);
  const sidebar = page.locator(".workspace-sidebar");
  await page.getByRole("button", { name: "Close sidebar" }).click();
  await expect(sidebar).toHaveClass(/is-collapsed/u);
  await page.getByRole("button", { name: "Open sidebar" }).click();
  await expect(sidebar).not.toHaveClass(/is-collapsed/u);
  const alertsButton = page.getByRole("button", { name: "Alerts" });
  await alertsButton.click();
  await expect(page.getByRole("dialog", { name: "Alerts" })).toBeVisible();
  await page.locator(".header-organization-brand").click();
  await expect(page.getByRole("dialog", { name: "Alerts" })).toHaveCount(0);
  const userMenu = page.getByLabel("User menu");
  await expect(userMenu.locator("span")).toHaveCount(1);
  await expect(userMenu).toHaveText(/^[A-Z]$/u);
  await userMenu.click();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Sign in" })).toBeVisible();
});

test("owner can use the patient directory and appointment wizard", async ({ page }) => {
  const seedPassword = process.env.DEV_SEED_PASSWORD;
  test.skip(!seedPassword, "DEV_SEED_PASSWORD is required for the authenticated browser test.");
  await page.goto("/en/login");
  await page.getByLabel("Email address").fill("owner@example.invalid");
  await page.getByLabel("Password").fill(seedPassword ?? "");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/en\/dashboard$/u, { timeout: 15_000 });
  await page.goto("/en/customers");
  await expect(page.getByRole("heading", { level: 1, name: "Patients" })).toBeVisible();
  await page.goto("/en/schedule/calendar");
  await expect(page.getByRole("heading", { level: 1, name: "Calendar" })).toBeVisible();
  for (const view of ["Day", "Week", "Doctor", "Resource", "Branch"]) {
    await expect(page.getByRole("link", { name: view, exact: true })).toBeVisible();
  }
  await page.locator("summary").filter({ hasText: "Create appointment" }).click();
  await page.getByRole("button", { name: "Add new patient" }).click();
  await page.getByLabel("Patient name").fill(`E2E Patient ${Date.now()}`);
  await page.getByLabel("Phone number").fill("+962 79 000 0123");
  await expect(page.getByRole("button", { name: "Add patient", exact: true })).toBeVisible();
  await page.goto("/en/schedule/today");
  await expect(page.getByRole("heading", { level: 1, name: "Appointments" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Pending", exact: true })).toBeVisible();
  for (const view of ["Table", "Kanban", "List"]) {
    await expect(page.getByRole("link", { name: view, exact: true })).toBeVisible();
  }
  const sectionOrder = await page.evaluate(() => {
    const summary = document.querySelector(".operations-summary");
    const filters = document.querySelector(".filter-toolbar");
    const views = document.querySelector(".appointment-display-tabs");
    if (!summary || !filters || !views) return false;
    return Boolean(
      summary.compareDocumentPosition(filters) & Node.DOCUMENT_POSITION_FOLLOWING &&
      filters.compareDocumentPosition(views) & Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });
  expect(sectionOrder).toBe(true);
  await page.getByRole("link", { name: "Kanban", exact: true }).click();
  await expect(page).toHaveURL(/view=kanban/u);
  await expect(page.getByRole("link", { name: "Kanban", exact: true })).toHaveAttribute(
    "aria-current",
    "page",
  );
  await expect(page.getByRole("heading", { level: 2, name: "Called", exact: true })).toHaveCount(0);
  await expect(
    page.getByRole("heading", { level: 2, name: "In service", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "List", exact: true }).click();
  await expect(page).toHaveURL(/view=list/u);
  await page.getByRole("link", { name: "Table", exact: true }).click();
  await expect(page).toHaveURL(/view=table/u);
});

test("every primary beauty-center workspace is permission-aware and mobile-safe", async ({
  page,
}) => {
  test.setTimeout(60_000);
  const seedPassword = process.env.DEV_SEED_PASSWORD;
  test.skip(!seedPassword, "DEV_SEED_PASSWORD is required for the authenticated browser test.");
  await page.goto("/en/login");
  await page.getByLabel("Email address").fill("owner@example.invalid");
  await page.getByLabel("Password").fill(seedPassword ?? "");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/en\/dashboard$/u, { timeout: 15_000 });

  const workspaces = [
    ["/en/schedule/today", "Appointments"],
    ["/en/schedule/calendar", "Calendar"],
    ["/en/schedule/appointments", "Appointments"],
    ["/en/schedule/waitlist", "Waitlist"],
    ["/en/customers", "Patients"],
    ["/en/inbox?tab=conversations", "AI conversations"],
    ["/en/business/services", "Services"],
    ["/en/business/team", "Service Providers"],
    ["/en/business/roles-access", "Roles & Access"],
    ["/en/business/resources", "Resources"],
    ["/en/business/branches", "Branches"],
    ["/en/insights/reports", "Reports"],
    ["/en/settings/organization", "Organization"],
  ] as const;

  await page.setViewportSize({ height: 844, width: 390 });
  for (const [path, heading] of workspaces) {
    await page.goto(path);
    await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
    await expect(page.getByRole("heading", { level: 1 })).toContainText(heading);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
    ).toBe(true);
  }

  await page.goto("/en/schedule/waitlist");
  await expect(page.getByRole("link", { name: "Today", exact: true })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "All Appointments", exact: true })).toHaveCount(0);

  await page.goto("/ar/settings/organization");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.locator('select[name="businessSector"]')).toHaveCount(0);
  await expect(page.locator(".header-organization-brand")).toBeVisible();
  await expect(page.locator(".app-header .jormall-lockup")).toHaveCount(0);
});

test("home uses a branded permission-aware command center in English and Arabic", async ({
  page,
}) => {
  test.setTimeout(60_000);
  const password = process.env.DEV_SEED_PASSWORD;
  test.skip(!password, "DEV_SEED_PASSWORD is required for the authenticated browser test.");
  await page.goto("/en/login");
  await page.getByLabel("Email address").fill("owner@example.invalid");
  await page.getByLabel("Password").fill(password ?? "");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/en\/dashboard$/u, { timeout: 15_000 });

  await expect(page.locator(".home-brand-hero")).toBeVisible();
  await expect(page.locator(".home-hero-logo .organization-logo")).toBeVisible();
  await expect(
    page.locator(".home-kpi-card, .home-primary-grid, .home-secondary-grid"),
  ).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Quick access" })).toBeVisible();
  await expect(page.locator(".home-quick-action-card")).toHaveCount(13);
  await expect(page.locator(".home-quick-action-card", { hasText: "Waiting List" })).toBeVisible();
  expect(
    await page
      .locator(".product-home")
      .evaluate((element) => getComputedStyle(element).backgroundColor),
  ).not.toBe("rgb(14, 24, 41)");

  await page.setViewportSize({ height: 844, width: 390 });
  await page.goto("/ar/dashboard");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.getByRole("heading", { name: "الوصول السريع" })).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
  ).toBe(true);

  await page.context().clearCookies();
  await page.setViewportSize({ height: 900, width: 1280 });
  await page.goto("/en/login");
  await page.getByLabel("Email address").fill("provider@example.invalid");
  await page.getByLabel("Password").fill(password ?? "");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/en\/dashboard$/u, { timeout: 15_000 });
  const sidebarLabels = (
    await page.locator(".workspace-sidebar .nav-links a span").allTextContents()
  )
    .map((label) => label.trim())
    .toSorted();
  const homeLabels = (await page.locator(".home-quick-action-card strong").allTextContents())
    .map((label) => label.trim())
    .toSorted();
  expect(homeLabels).toEqual(sidebarLabels);
});

test("appointments use a compact responsive filter and results workspace", async ({ page }) => {
  test.setTimeout(60_000);
  const password = process.env.DEV_SEED_PASSWORD;
  test.skip(!password, "DEV_SEED_PASSWORD is required for the authenticated browser test.");
  await page.goto("/en/login");
  await page.getByLabel("Email address").fill("owner@example.invalid");
  await page.getByLabel("Password").fill(password ?? "");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/en\/dashboard$/u, { timeout: 15_000 });

  await page.goto("/en/schedule/appointments?tab=all");
  await expect(page.locator(".appointments-kpi-grid .appointment-metric-card")).toHaveCount(7);
  await expect(page.locator(".appointment-category-tabs")).toBeVisible();
  await expect(page.locator(".appointment-status-filters")).toBeVisible();
  await expect(page.getByRole("link", { name: "Remove all filters" })).toBeVisible();
  await expect(page.locator(".appointment-advanced-filters")).not.toHaveAttribute("open", "");
  await page.locator(".appointment-advanced-filters summary").click();
  await expect(page.locator(".appointment-advanced-filter-grid")).toBeVisible();
  await expect(page.locator(".appointment-table-card")).toBeVisible();

  await page.setViewportSize({ height: 844, width: 390 });
  await page.goto("/ar/schedule/appointments?tab=all");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.getByRole("link", { name: "إزالة جميع عوامل التصفية" })).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
  ).toBe(true);
});

test("schedule tabs retain date and search after a status notice in English and Arabic", async ({
  page,
}) => {
  test.setTimeout(60_000);
  const password = process.env.DEV_SEED_PASSWORD;
  test.skip(!password, "DEV_SEED_PASSWORD is required for the authenticated browser test.");
  await page.goto("/en/login");
  await page.getByLabel("Email address").fill("owner@example.invalid");
  await page.getByLabel("Password").fill(password ?? "");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/en\/dashboard$/u);
  for (const locale of ["en", "ar"]) {
    await page.goto(`/${locale}/schedule/today?day=2026-09-06&q=retained-search&status=CONFIRMED`);
    await page.locator('.workspace-tabs a[href*="/schedule/calendar"]').click();
    expect(new URL(page.url()).searchParams.get("day")).toBe("2026-09-06");
    expect(new URL(page.url()).searchParams.get("q")).toBe("retained-search");
    await page.locator('.workspace-tabs a[href*="/schedule/appointments"]').click();
    await expect(
      page.locator('section[aria-labelledby="appointments-title"] input[name="q"]'),
    ).toHaveValue("retained-search");
    await page.goto(`${page.url()}&notice=APPOINTMENT_UPDATED`);
    await expect(
      page.locator('section[aria-labelledby="appointments-title"] input[name="q"]'),
    ).toHaveValue("retained-search");
    await expect(
      page.locator('section[aria-labelledby="appointments-title"] input[name="day"]'),
    ).toHaveValue("2026-09-06");
    await expect(page.locator("html")).toHaveAttribute("dir", locale === "ar" ? "rtl" : "ltr");
  }
});

test("retired gym and trainee routes return not found", async ({ page }) => {
  for (const path of [
    "/en/dashboard/gym/trainees",
    "/en/dashboard/gym/memberships",
    "/en/trainee",
  ]) {
    const response = await page.goto(path);
    expect(response?.status()).toBe(404);
  }
});

test("owner can use Phase 3 resource and waitlist screens in English and Arabic RTL", async ({
  page,
}) => {
  const seedPassword = process.env.DEV_SEED_PASSWORD;
  test.skip(!seedPassword, "DEV_SEED_PASSWORD is required for the authenticated browser test.");
  await page.goto("/en/login");
  await page.getByLabel("Email address").fill("owner@example.invalid");
  await page.getByLabel("Password").fill(seedPassword ?? "");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/en\/dashboard$/u, { timeout: 15_000 });

  await page.goto("/en/business/resources");
  await expect(page.getByRole("heading", { level: 1, name: "Resources" })).toBeVisible();
  await page.goto("/en/schedule/waitlist");
  await expect(page.getByRole("heading", { level: 1, name: "Waitlist" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "Add to waitlist" })).toBeVisible();
  await expect(page.getByLabel("Requested Doctor")).toHaveAttribute("required", "");
  await expect(page.getByRole("combobox", { name: "Patient" })).toBeVisible();
  await expect(page.locator('select[name="customerId"]')).toHaveCount(0);
  await expect(page.getByLabel("Preferred start time")).toHaveAttribute("type", "time");
  await expect(page.getByLabel("Preferred start time")).not.toHaveValue("");
  await expect(page.getByLabel("Preferred end time")).not.toHaveValue("");
  const minimumDate = await page.getByLabel("From date").getAttribute("min");
  expect(minimumDate).toBeTruthy();
  const priorDate = new Date(`${minimumDate ?? "2026-09-13"}T00:00:00.000Z`);
  priorDate.setUTCDate(priorDate.getUTCDate() - 1);
  const pastDate = priorDate.toISOString().slice(0, 10);
  await page.getByLabel("From date").fill(pastDate);
  await page.getByLabel("To date").fill(pastDate);
  await expect(page.getByText("A waitlist request cannot use a past date or time.")).toBeVisible();
  await expect(page.getByText("Window start minute")).toHaveCount(0);
  const priority = page.locator('select[name="priority"]');
  await expect(priority).toHaveValue("2");
  await expect(priority.locator("option")).toHaveText(["Low", "Normal", "High", "Urgent"]);
  await page.getByRole("link", { name: "Cancelled Openings", exact: true }).click();
  await expect(
    page.getByRole("heading", { level: 2, name: "Available Cancelled Appointments" }),
  ).toBeVisible();

  await page.goto("/ar/business/resources");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.getByRole("heading", { level: 1, name: "الموارد" })).toBeVisible();
  await page.goto("/ar/schedule/waitlist");
  await expect(page.getByRole("heading", { level: 1, name: "قائمة الانتظار" })).toBeVisible();
  await expect(page.getByLabel("وقت بداية الفترة المفضل")).toHaveAttribute("type", "time");
  await expect(page.getByLabel("وقت نهاية الفترة المفضل")).not.toHaveValue("");
  await expect(page.locator('select[name="priority"]').locator("option")).toHaveText([
    "منخفضة",
    "عادية",
    "عالية",
    "عاجلة",
  ]);
});

test("waitlist is separate from appointment tabs and requires a Doctor", async ({ page }) => {
  const seedPassword = process.env.DEV_SEED_PASSWORD;
  test.skip(!seedPassword, "DEV_SEED_PASSWORD is required for the authenticated browser test.");
  await page.goto("/en/login");
  await page.getByLabel("Email address").fill("owner@example.invalid");
  await page.getByLabel("Password").fill(seedPassword ?? "");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/en\/dashboard$/u, { timeout: 15_000 });
  await page.goto("/en/schedule/waitlist");

  const primaryNavigation = page.getByRole("navigation", { name: "Primary navigation" });
  const primaryLabels = await primaryNavigation.getByRole("link").allTextContents();
  expect(primaryLabels.slice(0, 3).map((label) => label.trim())).toEqual([
    "Home",
    "Appointments",
    "Waiting List",
  ]);
  await expect(page.getByLabel("Requested Doctor")).toHaveAttribute("required", "");
  await page.getByRole("link", { name: "Cancelled Openings", exact: true }).click();
  await expect(
    page.getByRole("heading", { level: 2, name: "Available Cancelled Appointments" }),
  ).toBeVisible();
});

test("owner can open remaining-work modules in English, Arabic RTL, and mobile", async ({
  page,
}) => {
  const seedPassword = process.env.DEV_SEED_PASSWORD;
  test.skip(!seedPassword, "DEV_SEED_PASSWORD is required for the authenticated browser test.");
  await page.goto("/en/login");
  await page.getByLabel("Email address").fill("owner@example.invalid");
  await page.getByLabel("Password").fill(seedPassword ?? "");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/en\/dashboard$/u, { timeout: 15_000 });

  for (const [path, heading] of [
    ["/en/notifications", "Notifications"],
    ["/en/inbox/escalations", "Chatbot Escalations"],
    ["/en/business/inventory", "Inventory"],
  ] as const) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
  }

  await page.setViewportSize({ height: 844, width: 390 });
  await page.goto("/ar/business/inventory");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.getByRole("heading", { level: 1, name: "المخزون" })).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
  ).toBe(true);
});

test("owner can use the Phase 4 inbox and queue a consented mock message", async ({ page }) => {
  const seedPassword = process.env.DEV_SEED_PASSWORD;
  test.skip(!seedPassword, "DEV_SEED_PASSWORD is required for the authenticated browser test.");
  await page.goto("/en/login");
  await page.getByLabel("Email address").fill("owner@example.invalid");
  await page.getByLabel("Password").fill(seedPassword ?? "");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/en\/dashboard$/u);

  await page.goto("/en/inbox?tab=messages");
  await expect(page.getByRole("heading", { level: 1, name: "Communications" })).toBeVisible();
  await expect(
    page.getByText("Test mode is active. No live customer messages will be sent."),
  ).toBeVisible();
  await page.locator("summary").filter({ hasText: "Send a message" }).click();
  const patientPicker = page.locator(".patient-combobox");
  await patientPicker.getByRole("combobox", { name: "Patient" }).fill("Leila Beauty");
  await patientPicker.getByRole("option", { name: /Leila Beauty/u }).click();
  await expect(page.locator('select[name="customerId"]')).toHaveCount(0);
  await page.locator('select[name="appointmentId"]').selectOption("");
  await page.getByRole("button", { name: "Send template" }).click();
  await expect(page.getByText("Message queued for mock delivery.")).toBeVisible();

  await page.goto("/ar/inbox?tab=messages");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.getByRole("heading", { level: 1, name: "الاتصالات" })).toBeVisible();
  await expect(
    page.getByRole("heading", { level: 2, name: "صندوق اتصالات الموظفين" }),
  ).toBeVisible();
});

test("owner retains verified customer channels while AI Studio and Handoffs are retired", async ({
  page,
}) => {
  // This journey visits every retired route in both languages, then exercises the widget.
  test.setTimeout(90_000);
  const seedPassword = process.env.DEV_SEED_PASSWORD;
  test.skip(!seedPassword, "DEV_SEED_PASSWORD is required for the authenticated browser test.");
  await page.goto("/en/login");
  await page.getByLabel("Email address").fill("owner@example.invalid");
  await page.getByLabel("Password").fill(seedPassword ?? "");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/en\/dashboard$/u);

  await expect(page.locator('a[href*="/ai-studio/"]')).toHaveCount(0);
  await expect(page.locator('a[href*="tab=handoffs"]')).toHaveCount(0);
  for (const locale of ["en", "ar"]) {
    for (const route of [
      "ai-studio/knowledge",
      "ai-studio/behavior",
      "ai-studio/actions",
      "ai-studio/usage",
      "ai-studio/test",
      "inbox?tab=handoffs",
      "dashboard/ai-handoffs",
    ]) {
      await page.goto(`/${locale}/${route}`);
      await expect(page.getByRole("heading", { name: "404", exact: true })).toBeVisible();
    }
  }
  await page.goto("/en/inbox?tab=conversations");
  await expect(page.getByRole("heading", { level: 1, name: "AI conversations" })).toBeVisible();
  await page.goto("/en/settings/channels");
  await expect(page.getByRole("heading", { level: 1, name: "AI customer channels" })).toBeVisible();
  const widgetName = `E2E widget ${Date.now()}`;
  await page.getByLabel("Installation name").fill(widgetName);
  await page.getByLabel("English display name").fill("E2E assistant");
  await page.getByLabel("Arabic display name").fill("مساعد الاختبار");
  await page.getByRole("button", { name: "Create widget installation" }).click();
  await expect(page.getByRole("heading", { level: 2, name: "Website installation" })).toBeVisible();
  const widgetCard = page.getByRole("heading", { level: 3, name: widgetName }).locator("..");
  const snippet = await widgetCard
    .getByRole("textbox", { name: "Website installation" })
    .inputValue();
  const configurationToken = /data-jormall-config="([^"]+)"/u.exec(snippet)?.[1];
  expect(configurationToken).toBeTruthy();
  const sessionResponsePromise = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/ai/widget/session") && response.request().method() === "POST",
  );
  await page.evaluate((token) => {
    const script = document.createElement("script");
    script.src = "/ai-widget.js";
    script.dataset.jormallConfig = token;
    script.dataset.locale = "en";
    document.body.append(script);
  }, configurationToken ?? "");
  const sessionResponse = await sessionResponsePromise;
  if (!sessionResponse.ok()) {
    throw new Error(`Widget session failed with HTTP ${sessionResponse.status()}.`);
  }
  const sessionBody: unknown = await sessionResponse.json();
  if (
    typeof sessionBody !== "object" ||
    sessionBody === null ||
    !("sessionToken" in sessionBody) ||
    typeof sessionBody.sessionToken !== "string"
  ) {
    throw new Error("Widget session response is missing its capability.");
  }
  const encodedSession = sessionBody.sessionToken.split(".")[0] ?? "";
  const sessionCapability: unknown = JSON.parse(
    Buffer.from(encodedSession, "base64url").toString("utf8"),
  );
  expect(sessionCapability).not.toHaveProperty("organizationId");
  expect(sessionCapability).not.toHaveProperty("sessionId");
  await page.getByRole("button", { name: "Chat with JorMall" }).click();
  await page
    .getByRole("textbox", { name: "Type your message" })
    .fill("Which services do you offer?");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByRole("log")).toContainText("Skin care treatment");

  await page.goto("/ar/settings/channels");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(
    page.getByRole("heading", { level: 1, name: "قنوات العملاء بالذكاء الاصطناعي" }),
  ).toBeVisible();
});

test("owner can use Copilot while patient safety data stays in its protected profile tab", async ({
  page,
}) => {
  const seedPassword = process.env.DEV_SEED_PASSWORD;
  test.skip(!seedPassword, "DEV_SEED_PASSWORD is required for the authenticated browser test.");
  await page.goto("/en/login");
  await page.getByLabel("Email address").fill("owner@example.invalid");
  await page.getByLabel("Password").fill(seedPassword ?? "");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/en\/dashboard$/u, { timeout: 15_000 });

  await page.goto("/en/insights/recommendations?view=copilot");
  await expect(page.getByRole("heading", { level: 1, name: "Staff Copilot" })).toBeVisible();
  await page
    .locator('form:has(input[name="insightType"][value="DAILY_BRIEFING"])')
    .getByRole("button", { name: "Generate from authorized records" })
    .click();
  await expect(
    page.getByRole("heading", { level: 3, name: /Daily briefing ·/u }).first(),
  ).toBeVisible();
  await expect(page.getByText("Computed metric", { exact: true }).first()).toBeVisible();
  await page.getByText("Model and policy trace", { exact: true }).first().click();
  await expect(page.getByText("jormall-copilot-deterministic-mock-v1").first()).toBeVisible();

  await page.goto("/en/customers");
  const patientHref = await page.getByRole("link", { name: "Leila Beauty" }).getAttribute("href");
  if (!patientHref) throw new Error("Seeded patient profile link is missing.");
  await page.goto(patientHref);
  await expect(page.getByRole("heading", { level: 1, name: "Leila Beauty" })).toBeVisible();
  await page.getByRole("link", { name: "Health & allergies" }).click();
  await expect(page.getByRole("heading", { name: "Patient safety intake" })).toBeVisible();
  await expect(page.getByText("This is not a medical record.")).toBeVisible();

  await page.goto("/ar/insights/recommendations?view=copilot");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.getByRole("heading", { level: 1, name: "مساعد الموظفين" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "مساعد التحليلات" })).toBeVisible();
});

test("owner can dry-run Phase 7 imports and view reports, exports, audit and Arabic RTL", async ({
  page,
}) => {
  const seedPassword = process.env.DEV_SEED_PASSWORD;
  test.skip(!seedPassword, "DEV_SEED_PASSWORD is required for the authenticated browser test.");
  await page.goto("/en/login");
  await page.getByLabel("Email address").fill("owner@example.invalid");
  await page.getByLabel("Password").fill(seedPassword ?? "");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/en\/dashboard$/u);

  await page.goto("/en/settings/imports");
  await expect(page.getByRole("heading", { level: 1, name: "Safe imports" })).toBeVisible();
  await page.getByLabel("CSV").setInputFiles({
    buffer: Buffer.from(
      `external_key,display_name,phone,preferred_locale\ne2e-${Date.now()},Phase Seven Browser,0798112233,en\n`,
    ),
    mimeType: "text/csv",
    name: "phase-seven-customers.csv",
  });
  await page.getByRole("button", { name: "Upload and dry run" }).click();
  await expect(
    page.getByText("Import dry run completed without changing operational records."),
  ).toBeVisible();
  await expect(page.getByText("DRY_RUN_READY").first()).toBeVisible();

  await page.goto("/en/insights/reports");
  await expect(
    page.getByRole("heading", { level: 1, name: "Reports and attribution" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Run report" }).click();
  await expect(
    page.getByText("A report with a traceable data watermark was created."),
  ).toBeVisible();
  await page.getByRole("button", { name: "Data exports" }).click();
  await expect(page.getByText("Export job is ready to download for one hour.")).toBeVisible();

  await page.goto("/en/settings/audit");
  await expect(page.getByRole("heading", { level: 1, name: "Audit log" })).toBeVisible();
  await page.goto("/ar/settings/imports");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.getByRole("heading", { level: 1, name: "الاستيراد الآمن" })).toBeVisible();
});

test("owner can inspect and queue the advisory Phase 8 predictive layer in English and Arabic RTL", async ({
  page,
}) => {
  const seedPassword = process.env.DEV_SEED_PASSWORD;
  test.skip(!seedPassword, "DEV_SEED_PASSWORD is required for the authenticated browser test.");
  await page.goto("/en/login");
  await page.getByLabel("Email address").fill("owner@example.invalid");
  await page.getByLabel("Password").fill(seedPassword ?? "");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/en\/dashboard$/u);

  await page.goto("/en/insights/recommendations?view=predictions");
  await expect(
    page.getByRole("heading", { level: 1, name: "Predictive intelligence" }),
  ).toBeVisible();
  const readinessRegion = page.getByLabel("Historical data readiness");
  await expect(
    readinessRegion.getByRole("heading", { level: 3, name: "No-show prediction" }),
  ).toBeVisible();
  await expect(
    readinessRegion.getByRole("heading", { level: 3, name: "Demand forecasting" }),
  ).toBeVisible();
  await expect(
    readinessRegion.getByRole("heading", { level: 3, name: "Staffing suggestions" }),
  ).toBeVisible();
  await expect(
    readinessRegion.getByRole("heading", { level: 3, name: "Advanced schedule reflow" }),
  ).toBeVisible();
  await expect(
    readinessRegion.getByRole("heading", {
      level: 3,
      name: "Service, provider and slot recommendations",
    }),
  ).toBeVisible();
  await expect(page.getByText(/operational assistance only.*never deny service/u)).toBeVisible();

  await page.getByLabel("Capability").selectOption("NO_SHOW");
  await page.getByLabel("Job type").selectOption("DATA_AUDIT");
  await page.getByRole("button", { name: "Queue predictive job" }).click();
  await expect(page.getByText("Predictive job queued for safe processing.")).toBeVisible();
  await expect(page.getByRole("cell", { name: "Data audit" }).first()).toBeVisible();

  await page.goto("/ar/insights/recommendations?view=predictions");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.getByRole("heading", { level: 1, name: "الذكاء التنبؤي" })).toBeVisible();
  await expect(
    page
      .getByLabel("جاهزية البيانات التاريخية")
      .getByRole("heading", { level: 3, name: "توقع عدم الحضور" }),
  ).toBeVisible();
});
