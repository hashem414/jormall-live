import { expect, test } from "@playwright/test";

test("applies the active organization theme and keeps the appearance editor tenant-scoped", async ({
  page,
}) => {
  const seedPassword = process.env.DEV_SEED_PASSWORD;
  test.skip(!seedPassword, "DEV_SEED_PASSWORD is required for the authenticated browser test.");

  await page.goto("/en/login");
  await page.getByLabel("Email address").fill("owner@example.invalid");
  await page.getByLabel("Password").fill(seedPassword ?? "");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/en\/dashboard$/u, { timeout: 15_000 });

  await expect(page.locator(".header-organization-brand strong")).toHaveText("Rose Beauty Center");
  await expect(page.locator(".header-organization-brand .organization-logo")).toHaveText("RB");
  await expect(page.locator(".app-header .jormall-lockup")).toHaveCount(0);
  await expect(page.locator(".app-shell")).toHaveCSS("--brand", "#9f4f88");
  await expect(page.locator(".app-shell")).toHaveCSS("--accent", "#f08aaa");
  await expect(page.getByRole("button", { name: "Back" })).toHaveCount(0);
  await expect(page.locator(".locale-switch")).toHaveText(/EN\s*\|\s*AR/u);

  await page.goto("/en/settings/branding");
  await expect(page.locator(".locale-switch")).toHaveAttribute("href", "/ar/settings/branding");
  await expect(
    page.getByRole("heading", { level: 1, name: "Organization appearance" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Extract colors" })).toBeVisible();
  await expect(page.getByLabel("Logo file for color extraction")).toBeVisible();
  await expect(page.getByLabel("Theme color palette")).toBeVisible();
  await expect(page.getByLabel("Primary color")).toHaveValue("#9f4f88");
  await expect(page.getByLabel("Accent color")).toHaveValue("#f08aaa");
  await expect(page.getByText(/Text contrast on primary.*WCAG AA pass/u)).toBeVisible();
  await expect(page.getByText("EN · Calendar · Customers · Services")).toBeVisible();
  await expect(page.getByText("AR · التقويم · العملاء · الخدمات")).toBeVisible();
  const logoDataUrl = await page.evaluate(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 96;
    canvas.height = 48;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("E2E_CANVAS_UNAVAILABLE");
    context.fillStyle = "#189070";
    context.fillRect(0, 0, 64, 48);
    context.fillStyle = "#f5a524";
    context.fillRect(64, 0, 32, 48);
    return canvas.toDataURL("image/png");
  });
  const dataUrlPrefix = "data:image/png;base64,";
  expect(logoDataUrl.startsWith(dataUrlPrefix)).toBe(true);
  await page.getByLabel("Logo file for color extraction").setInputFiles({
    buffer: Buffer.from(logoDataUrl.slice(dataUrlPrefix.length), "base64"),
    mimeType: "image/png",
    name: "organization-logo.png",
  });
  await expect(page.getByText("Palette extracted. Review the colors before saving.")).toBeVisible();
  await expect(page.getByLabel("Primary color")).toHaveValue("#189070");
  await expect(page.getByLabel("Accent color")).toHaveValue("#f5a524");
  await page.getByRole("button", { name: "Reset default colors" }).click();
  await expect(page.getByLabel("Primary color")).toHaveValue("#9f4f88");
  await expect(page.getByLabel("Accent color")).toHaveValue("#f08aaa");
  await expect(page.locator('input[name="organizationId"]')).toHaveCount(0);

  const logoBox = await page.locator(".header-organization-brand").boundingBox();
  const localeBox = await page.locator(".locale-switch").boundingBox();
  const userMenuBox = await page.getByLabel("User menu").boundingBox();
  expect(logoBox).not.toBeNull();
  expect(localeBox).not.toBeNull();
  expect(userMenuBox).not.toBeNull();
  expect(logoBox?.x).toBeLessThan(100);
  expect(localeBox?.x).toBeGreaterThan(logoBox?.x ?? 0);
  expect(userMenuBox?.x).toBeGreaterThan(localeBox?.x ?? 0);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/ar/dashboard");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.locator(".header-organization-brand .organization-logo")).toBeVisible();
  await expect(page.locator(".header-utility-group .locale-switch")).toBeVisible();
  await expect(page.locator(".header-utility-group .user-menu")).toBeVisible();
  await expect(page.locator(".app-header .jormall-lockup")).toHaveCount(0);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
  ).toBe(true);
});

test("keeps the redesigned login usable on a narrow Arabic screen", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/ar/login");

  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.locator(".jormall-lockup").first()).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
  ).toBe(true);
});
