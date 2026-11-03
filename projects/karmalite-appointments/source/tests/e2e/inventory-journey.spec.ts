import { expect, test } from "@playwright/test";

test("complete inventory operational journey: proposal, approval, order, ETA, partial & full receipt, movements", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const password = process.env.DEV_SEED_PASSWORD ?? process.env.KARMALITE_LOCAL_TEST_PASSWORD;
  test.skip(!password, "DEV_SEED_PASSWORD or KARMALITE_LOCAL_TEST_PASSWORD is required.");

  const email = process.env.KARMALITE_LOCAL_TEST_EMAIL ?? "owner@example.invalid";
  const uniqueId = Date.now().toString().slice(-6);
  const proposedName = `Hydrating Skincare Pack ${uniqueId}`;

  // 1. Sign in
  await page.goto("/en/login");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/en\/dashboard/u, { timeout: 20_000 });

  // 2. Navigate to Inventory main destination
  await page.goto("/en/business/inventory");
  await expect(page.getByRole("heading", { level: 1, name: "Inventory" })).toBeVisible();

  // 3. Verify all 6 tabs are present
  const tabsNav = page.locator("nav.workspace-tabs");
  await expect(tabsNav.getByRole("link", { name: "Overview" })).toBeVisible();
  await expect(tabsNav.getByRole("link", { name: "Items" })).toBeVisible();
  await expect(tabsNav.getByRole("link", { name: "Requests" })).toBeVisible();
  await expect(tabsNav.getByRole("link", { name: "Orders" })).toBeVisible();
  await expect(tabsNav.getByRole("link", { name: "Receiving" })).toBeVisible();
  await expect(tabsNav.getByRole("link", { name: "Movements" })).toBeVisible();

  // 4. Check Overview tab KPIs
  await expect(page.getByText("Low Stock", { exact: true })).toBeVisible();
  await expect(page.getByText("Projected Shortage", { exact: true })).toBeVisible();

  // 5. Propose a new item
  await page.getByRole("button", { name: "Request New Item" }).click();
  const proposalDialog = page.locator("dialog.operation-dialog[open]");
  await expect(proposalDialog).toBeVisible();
  await proposalDialog.locator('input[name="proposedName"]').fill(proposedName);
  await proposalDialog.locator('select[name="category"]').selectOption("CONSUMABLE");
  await proposalDialog.locator('input[name="unitOfMeasure"]').fill("box");
  await proposalDialog.locator('input[name="suggestedQuantity"]').fill("10");
  await proposalDialog.locator('input[name="reasonNeeded"]').fill("Upcoming esthetic services");
  await proposalDialog.getByRole("button", { name: "Request New Item" }).click();

  // Redirects to Requests tab with success notice
  await expect(page).toHaveURL(/tab=requests/u);
  await expect(page.locator(".record-card").filter({ hasText: proposedName })).toBeVisible();

  // 6. Approve the proposed item
  const proposalCard = page.locator(".record-card").filter({ hasText: proposedName });
  await proposalCard.getByRole("button", { name: "Approve" }).click();
  const approveDialog = page.locator("dialog.operation-dialog[open]");
  await expect(approveDialog).toBeVisible();
  await approveDialog.locator('input[name="minimumStock"]').fill("2");
  await approveDialog.locator('input[name="reorderQuantity"]').fill("10");
  await approveDialog.locator('input[name="sku"]').fill(`SKU-${uniqueId}`);
  await expect(approveDialog.getByText("SKU (internal item code)")).toBeVisible();
  await expect(approveDialog.getByText("Unit price (JOD)")).toBeVisible();
  await approveDialog.locator('input[name="unitPrice"]').fill("12.50");
  await expect(approveDialog.getByText("Batch tracking", { exact: true })).toBeVisible();
  await expect(approveDialog.getByText("Expiry tracking", { exact: true })).toBeVisible();
  await approveDialog.getByRole("button", { name: "Approve" }).click();

  // Redirects to Items tab
  await expect(page).toHaveURL(/tab=items/u);
  const itemRow = page.locator("tr").filter({ hasText: proposedName });
  await expect(itemRow).toBeVisible();
  await expect(itemRow).toContainText("0 box");
  await expect(itemRow).toContainText("12.50 JOD");

  // 7. Place an Order for this item
  await itemRow.getByRole("button", { name: "Place Order" }).click();
  const orderDialog = page.locator("dialog.operation-dialog[open]");
  await expect(orderDialog).toBeVisible();
  await orderDialog.locator('input[name="quantity"]').fill("10");
  await orderDialog.locator('input[name="reason"]').fill("Initial stock order");
  await orderDialog.locator('select[name="urgency"]').selectOption("NORMAL");
  await orderDialog.getByRole("button", { name: "Place Order" }).click();

  // Redirects to Orders tab
  await expect(page).toHaveURL(/tab=orders/u);
  const orderCard = page.locator(".record-card").filter({ hasText: proposedName }).first();
  await expect(orderCard).toBeVisible();
  await expect(orderCard).toContainText("PENDING_APPROVAL");

  // 8. Approver approves the order
  await orderCard.getByRole("button", { name: "Approve" }).click();
  await expect(page).toHaveURL(/tab=orders/u);
  await expect(orderCard).toContainText("APPROVED");

  // 9. Mark Ordered with ETA
  await page.goto("/en/business/inventory?tab=receiving");
  const receivingCard = page.locator(".record-card").filter({ hasText: proposedName }).first();
  await expect(receivingCard).toBeVisible();
  await receivingCard.getByRole("button", { name: "Mark Ordered" }).click();
  const markOrderedDialog = page.locator("dialog.operation-dialog[open]");
  await expect(markOrderedDialog).toBeVisible();
  await markOrderedDialog.locator('input[name="supplierName"]').fill("Karmalite Beauty Supplies");
  await markOrderedDialog.locator('input[name="expectedDeliveryValue"]').fill("3");
  await markOrderedDialog.locator('select[name="expectedDeliveryUnit"]').selectOption("DAYS");
  await markOrderedDialog.getByRole("button", { name: "Mark Ordered" }).click();

  // Shows a readable in-transit status with ETA
  await expect(page).toHaveURL(/tab=receiving/u);
  await expect(receivingCard).toContainText("In Transit");
  await expect(receivingCard).toContainText("Expected Arrival");

  // 10. Partial Receipt (6 units)
  await receivingCard.getByRole("button", { name: "Receive" }).click();
  const receiveDialog = page.locator("dialog.operation-dialog[open]");
  await expect(receiveDialog).toBeVisible();
  await receiveDialog.locator('input[name="quantity"]').fill("6");
  await receiveDialog.locator('input[name="batchNumber"]').fill(`BATCH-${uniqueId}`);
  await receiveDialog.getByRole("button", { name: "Receive" }).click();

  // Shows a readable partial-receipt status with Remaining: 4
  await expect(page).toHaveURL(/tab=receiving/u);
  await expect(receivingCard).toContainText("Partially Received");
  await expect(receivingCard).toContainText("Remaining: 4");

  // 11. Receive remaining 4 units
  await receivingCard.getByRole("button", { name: "Receive" }).click();
  const receiveDialogRemaining = page.locator("dialog.operation-dialog[open]");
  await expect(receiveDialogRemaining).toBeVisible();
  await receiveDialogRemaining.locator('input[name="quantity"]').fill("4");
  await receiveDialogRemaining.getByRole("button", { name: "Receive" }).click();
  await expect(receivingCard).toBeHidden();

  // 12. Verify Stock updated in Items tab
  await page.goto("/en/business/inventory?tab=items");
  const updatedItemRow = page.locator("tr").filter({ hasText: proposedName });
  await expect(updatedItemRow).toContainText("10 box");

  // 13. Verify Movements tab records the receipts
  await page.goto("/en/business/inventory?tab=movements");
  const movementRows = page.locator("tr").filter({ hasText: proposedName });
  await expect(movementRows).toHaveCount(2);
  await expect(movementRows.first()).toContainText("Received");
});
