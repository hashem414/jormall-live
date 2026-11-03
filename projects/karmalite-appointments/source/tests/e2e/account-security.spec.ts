import { expect, test, type Page } from "@playwright/test";

async function signIn(page: Page, email: string, password: string) {
  await page.goto("/en/login");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/en\/dashboard$/u, { timeout: 15_000 });
}

async function changePassword(
  page: Page,
  currentPassword: string,
  newPassword: string,
  onSubmit?: () => void,
) {
  await page.goto("/en/account/security");
  await expect(page.getByRole("heading", { level: 1, name: "Account Security" })).toBeVisible();
  await page.getByLabel("Current password").fill(currentPassword);
  await page.getByLabel("New password", { exact: true }).fill(newPassword);
  await page.getByLabel("Confirm new password").fill(newPassword);
  onSubmit?.();
  await page.getByRole("button", { name: "Change Password" }).click();
  await expect(page.getByText("Password changed successfully.")).toBeVisible();
}

test("an authenticated local user can securely change and restore their password", async ({
  context,
  page,
}) => {
  test.setTimeout(90_000);
  const email = process.env.KARMALITE_LOCAL_TEST_EMAIL;
  const originalPassword = process.env.KARMALITE_LOCAL_TEST_PASSWORD;
  test.skip(!email || !originalPassword, "Karmalite local smoke credentials are required.");

  const temporaryPassword = `Temporary-${Date.now()}-Aa1!`;
  let passwordWasChanged = false;

  try {
    await signIn(page, email ?? "", originalPassword ?? "");
    await changePassword(page, originalPassword ?? "", temporaryPassword, () => {
      passwordWasChanged = true;
    });

    await context.clearCookies();
    await signIn(page, email ?? "", temporaryPassword);
    await changePassword(page, temporaryPassword, originalPassword ?? "", () => {
      passwordWasChanged = false;
    });

    await context.clearCookies();
    await signIn(page, email ?? "", originalPassword ?? "");
  } finally {
    if (passwordWasChanged) {
      await context.clearCookies();
      await signIn(page, email ?? "", temporaryPassword);
      await changePassword(page, temporaryPassword, originalPassword ?? "");
    }
  }
});
