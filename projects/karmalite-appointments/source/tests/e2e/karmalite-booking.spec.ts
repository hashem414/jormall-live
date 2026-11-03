import { expect, test } from "@playwright/test";

test("Karmalite booking uses only explicit doctors and valid working-hour slots", async ({
  page,
}) => {
  test.setTimeout(60_000);
  const email = process.env.KARMALITE_PROVISIONING_ADMIN_EMAIL;
  const password = process.env.DEV_SEED_PASSWORD;
  test.skip(!email || !password, "Karmalite test administration credentials are required.");

  await page.goto("/en/login");
  await page.getByLabel("Email address").fill(email ?? "");
  await page.getByLabel("Password").fill(password ?? "");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/login/u, { timeout: 15_000 });

  await page.goto("/en/platform/organizations");
  const karmalite = page.locator("article").filter({ hasText: "Karmalite Medical Esthetic" });
  await karmalite
    .getByLabel("Support reason (required, at least 10 characters)")
    .fill("Verify the Karmalite staff booking experience.");
  await karmalite.getByRole("button", { name: "Start audited support access" }).click();
  await expect(page).toHaveURL(/\/en\/dashboard(?:\?|$)/u, { timeout: 15_000 });

  await page.goto("/en/schedule/calendar");
  await page.locator("summary").filter({ hasText: "Create appointment" }).click();
  const wizard = page.locator(".appointment-wizard");
  await expect(wizard.getByRole("combobox", { name: "Patient", exact: true })).toBeVisible();
  await wizard.getByRole("button", { name: "Add new patient" }).click();
  await wizard.getByLabel("Patient name").fill("Booking preview patient");
  await wizard.getByLabel("Phone number").fill("+962 79 000 0000");
  await expect(wizard.getByRole("button", { name: "Add patient", exact: true })).toBeEnabled();
  await wizard.getByLabel("Service").selectOption({ label: "Laser Hair Removal" });
  await expect(wizard.getByRole("button", { name: "Next", exact: true })).toHaveCount(0);
  for (const section of [
    "Patient",
    "Service & Branch",
    "Doctor",
    "Date & Time",
    "Room",
    "Review",
  ]) {
    await expect(wizard.getByRole("heading", { name: section })).toBeVisible();
  }
  await expect(
    page.getByText("Add the patient first, then choose an available time to complete the booking."),
  ).toBeVisible();
  await wizard.getByRole("button", { name: "Existing patient" }).click();
  const patient = wizard.getByRole("combobox", { name: "Patient", exact: true });
  await patient.fill("Christine");
  await wizard.getByRole("option").first().click();
  const doctor = wizard.getByRole("combobox", { name: "Doctor", exact: true });
  if ((await doctor.locator('option:not([value=""])').count()) === 0) {
    await expect(
      page.getByText("No doctor is configured for this branch and service."),
    ).toBeVisible();
    await page.getByRole("button", { name: "End support access" }).click();
    await expect(page).toHaveURL(/\/en\/platform\/organizations/u);
    return;
  }
  await expect(doctor).toHaveValue(/.+/u);

  const closedDate = nextUtcWeekday(5);
  const openDate = nextUtcWeekday(6);
  const date = wizard.getByLabel("Date");
  const minimumDate = await date.getAttribute("min");
  expect(minimumDate).toMatch(/^\d{4}-\d{2}-\d{2}$/u);
  const pastDate = new Date(`${minimumDate ?? ""}T12:00:00Z`);
  pastDate.setUTCDate(pastDate.getUTCDate() - 1);
  await date.fill(pastDate.toISOString().slice(0, 10));
  await expect(
    page.getByText("Past dates and times cannot be booked. Choose today or a future date."),
  ).toBeVisible();
  await expect(wizard.getByRole("button", { name: "Find available times" })).toBeDisabled();

  await date.fill(closedDate);
  await expect(
    page.getByText("The branch is closed on this day. Choose another day."),
  ).toBeVisible();
  await expect(wizard.getByRole("button", { name: "Find available times" })).toBeDisabled();

  await date.fill(openDate);
  await expect(page.getByText(/Branch working hours: 09:00–19:00/u)).toBeVisible();
  await wizard.getByRole("button", { name: "Find available times" }).click();
  await expect(wizard.getByLabel("Available time")).toBeVisible();
  const availableValues = await wizard
    .getByLabel("Available time")
    .locator("option")
    .evaluateAll((options) =>
      options
        .map((option) => (option as HTMLOptionElement).value)
        .filter((value) => value.length > 0),
    );
  expect(availableValues.length).toBeGreaterThan(0);
  expect(new Set(availableValues).size).toBe(availableValues.length);
  expect(availableValues).toEqual(availableValues.toSorted());
  const invalidValues = availableValues.filter((value) => {
    const startsAtLocal = value.split("|")[1] ?? value;
    const time = startsAtLocal.slice(11);
    const hour = Number(time.slice(0, 2));
    const minute = Number(time.slice(3, 5));
    const startMinute = hour * 60 + minute;
    return !(
      startsAtLocal.startsWith(`${openDate}T`) &&
      startMinute >= 9 * 60 &&
      startMinute <= 18 * 60 &&
      minute % 15 === 0
    );
  });
  expect(invalidValues).toEqual([]);
  await wizard.getByLabel("Available time").selectOption(availableValues[0] ?? "");
  await expect(wizard.getByRole("button", { name: "Create as Pending" })).toBeEnabled();
  await expect(wizard.getByRole("button", { name: "Create & Confirm" })).toBeEnabled();

  await page.getByRole("button", { name: "End support access" }).click();
  await expect(page).toHaveURL(/\/en\/platform\/organizations/u);
});

function nextUtcWeekday(weekday: number): string {
  const candidate = new Date();
  candidate.setUTCHours(12, 0, 0, 0);
  candidate.setUTCDate(candidate.getUTCDate() + 1);
  while (candidate.getUTCDay() !== weekday) candidate.setUTCDate(candidate.getUTCDate() + 1);
  return candidate.toISOString().slice(0, 10);
}
