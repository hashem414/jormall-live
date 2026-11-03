import { randomUUID } from "node:crypto";

import { createPrismaClient } from "@jormall/db/client";
import { CrmAppointmentRepository } from "@jormall/db/crm-appointment-repository";
import { IdentityRepository } from "@jormall/db/identity-repository";
import { OperationalWorkflowsRepository } from "@jormall/db/operational-workflows-repository";
import { SchedulingRepository } from "@jormall/db/scheduling-repository";
import { expect, test } from "@playwright/test";

test("service completion records actual inventory consumption once", async ({ page }) => {
  test.setTimeout(90_000);
  const databaseUrl = process.env.DATABASE_URL;
  const password = process.env.DEV_SEED_PASSWORD;
  test.skip(!databaseUrl || !password, "Local database and seeded test password are required.");

  const client = createPrismaClient(databaseUrl ?? "");
  const identity = new IdentityRepository(client);
  const crm = new CrmAppointmentRepository(client);
  const inventory = new OperationalWorkflowsRepository(client);
  const scheduling = new SchedulingRepository(client);

  try {
    const owner = await client.user.findUniqueOrThrow({
      where: { email: "owner@example.invalid" },
    });
    const membership = await client.organizationMembership.findFirstOrThrow({
      where: { userId: owner.id },
    });
    const access = await identity.loadTenantAccess(
      owner.id,
      {
        activeMembershipId: membership.id,
        activeOrganizationId: membership.organizationId,
      },
      {},
    );
    const template = await client.appointment.findFirstOrThrow({
      orderBy: { createdAt: "asc" },
      where: { organizationId: access.organizationId, status: "PENDING" },
    });
    const serviceName = `Inventory E2E Service ${randomUUID().slice(0, 8)}`;
    await identity.createService(access, {
      currency: "JOD",
      defaultDurationMins: 30,
      nameAr: `خدمة اختبار المخزون ${randomUUID().slice(0, 5)}`,
      nameEn: serviceName,
    });
    const service = (await identity.listServices(access)).find(
      ({ nameEn }) => nameEn === serviceName,
    );
    if (!service) throw new Error("The E2E service was not created.");
    await identity.configureServiceBranch(access, {
      branchId: template.branchId,
      isEnabled: true,
      serviceId: service.id,
    });
    const item = await inventory.createItemDirect(access, {
      branchId: template.branchId,
      category: "CONSUMABLE",
      currentStock: 5,
      minimumStock: 1,
      name: `E2E Service Material ${randomUUID().slice(0, 8)}`,
      unitOfMeasure: "unit",
    });
    await inventory.addServiceRequirement(access, {
      expectedQuantity: 1,
      isRequired: true,
      itemId: item.id,
      reservationMode: "RESERVE_ON_CONFIRMATION",
      serviceId: service.id,
      unitOfMeasure: "unit",
    });
    const group = await scheduling.createResourceGroup(access, {
      branchId: template.branchId,
      kind: "ROOM",
      nameAr: `غرف اختبار المخزون ${randomUUID().slice(0, 5)}`,
      nameEn: `Inventory E2E Rooms ${randomUUID().slice(0, 5)}`,
    });
    const room = await scheduling.createResource(access, {
      allowedServiceIds: [service.id],
      groupId: group.id,
      nameAr: `غرفة اختبار المخزون ${randomUUID().slice(0, 5)}`,
      nameEn: `Inventory E2E Room ${randomUUID().slice(0, 5)}`,
    });
    const weekdays = [
      "SUNDAY",
      "MONDAY",
      "TUESDAY",
      "WEDNESDAY",
      "THURSDAY",
      "FRIDAY",
      "SATURDAY",
    ] as const;
    const doctor = await client.staffProfile.findUniqueOrThrow({
      where: { id: template.providerId },
    });
    await identity.configureDoctor(access, {
      branchIds: [template.branchId],
      displayNameAr: doctor.displayNameAr,
      displayNameEn: doctor.displayNameEn,
      isActive: true,
      serviceIds: [service.id],
      staffProfileId: doctor.id,
    });
    await scheduling.replaceBranchHours(
      access,
      template.branchId,
      weekdays.map((weekday) => ({ endMinuteLocal: 1140, startMinuteLocal: 540, weekday })),
    );
    await identity.replaceDoctorSchedule(access, {
      branchId: template.branchId,
      breaks: [],
      confirmAffected: true,
      periods: weekdays.map((weekday) => ({
        endMinuteLocal: 1140,
        startMinuteLocal: 540,
        weekday,
      })),
      staffProfileId: template.providerId,
    });
    const start = new Date();
    start.setUTCDate(start.getUTCDate() + 1);
    const end = new Date(start);
    end.setUTCDate(end.getUTCDate() + 30);
    const slots = await scheduling.findAvailableSlots(access, {
      branchId: template.branchId,
      customerId: template.customerId,
      endsOn: end.toISOString().slice(0, 10),
      limit: 1,
      providerId: template.providerId,
      serviceId: service.id,
      startsOn: start.toISOString().slice(0, 10),
    });
    const slot = slots[0];
    if (!slot) throw new Error("No future slot is available for the E2E appointment.");
    const pending = await crm.createAppointment(access, {
      branchId: template.branchId,
      customerId: template.customerId,
      providerId: template.providerId,
      serviceId: service.id,
      startsAtLocal: slot.startsAtLocal,
      status: "PENDING",
    });
    const confirmed = await crm.transitionAppointment(access, {
      appointmentId: pending.id,
      expectedVersion: pending.version,
      toStatus: "CONFIRMED",
    });
    const inProgress = await crm.startAppointmentService(access, {
      appointmentId: confirmed.id,
      expectedVersion: confirmed.version,
      includeCheckIn: true,
      roomId: room.id,
    });

    await page.goto("/en/login");
    await page.getByLabel("Email address").fill(owner.email);
    await page.getByLabel("Password").fill(password ?? "");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/en\/dashboard/u, { timeout: 15_000 });
    await page.goto(`/en/schedule/appointments/${inProgress.id}`);
    await expect(page.getByRole("heading", { name: "Items Used (Inventory)" })).toBeVisible();
    await page.locator('input[name="recordSummary"]').fill("Inventory E2E completion");
    await page.getByRole("button", { name: "Service Done", exact: true }).click();
    await expect(page.getByText("Consumed Inventory Items", { exact: true })).toBeVisible();

    const [updatedItem, consumptionCount, movementCount] = await Promise.all([
      client.inventoryItem.findUniqueOrThrow({ where: { id: item.id } }),
      client.appointmentInventoryConsumption.count({
        where: { appointmentId: inProgress.id, itemId: item.id },
      }),
      client.inventoryStockMovement.count({
        where: {
          appointmentId: inProgress.id,
          itemId: item.id,
          type: "APPOINTMENT_CONSUMPTION",
        },
      }),
    ]);
    expect(Number(updatedItem.currentStock)).toBe(4);
    expect(consumptionCount).toBe(1);
    expect(movementCount).toBe(1);

    await page.reload();
    await expect(page.getByText("Consumed Inventory Items", { exact: true })).toBeVisible();
    expect(
      await client.inventoryStockMovement.count({
        where: {
          appointmentId: inProgress.id,
          itemId: item.id,
          type: "APPOINTMENT_CONSUMPTION",
        },
      }),
    ).toBe(1);
  } finally {
    await client.$disconnect();
  }
});
