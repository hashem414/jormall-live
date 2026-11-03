import { randomUUID } from "node:crypto";

import { createPrismaClient } from "@jormall/db/client";
import { CrmAppointmentRepository } from "@jormall/db/crm-appointment-repository";
import { IdentityRepository } from "@jormall/db/identity-repository";
import { OperationalWorkflowsRepository } from "@jormall/db/operational-workflows-repository";
import { SchedulingRepository } from "@jormall/db/scheduling-repository";
import { OrganizationStatus, PlatformRole } from "@jormall/db/generated/enums";
import { runInTenant } from "@jormall/db/tenant-context";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

const databaseUrl = process.env.TEST_DATABASE_URL ?? process.env.DATABASE_URL;
if (!databaseUrl) throw new Error("TEST_DATABASE_URL or DATABASE_URL is required.");
const client = createPrismaClient(databaseUrl);
const identity = new IdentityRepository(client);
const workflows = new OperationalWorkflowsRepository(client);
const crm = new CrmAppointmentRepository(client);
const scheduling = new SchedulingRepository(client);
const suffix = randomUUID().slice(0, 8);

async function createTenantFixture(label: string) {
  const admin = await client.user.create({
    data: {
      email: `inv-admin-${label}-${suffix}@example.invalid`,
      name: "Inventory Test Admin",
      platformRole: PlatformRole.JORMALL_SUPER_ADMIN,
    },
  });
  const owner = await client.user.create({
    data: { email: `inv-owner-${label}-${suffix}@example.invalid`, name: `Owner ${label}` },
  });
  const created = await identity.createOrganization(admin.id, {
    nameAr: `مركز تجريبي ${label}`,
    nameEn: `Center ${label}`,
    ownerEmail: owner.email,
    slug: `inv-center-${label}-${suffix}`,
  });
  const accepted = await identity.acceptInvitation(owner.id, owner.email, created.invitationToken);
  await identity.setOrganizationStatus(admin.id, created.organizationId, OrganizationStatus.ACTIVE);
  const access = await identity.loadTenantAccess(
    owner.id,
    { activeMembershipId: accepted.membershipId, activeOrganizationId: accepted.organizationId },
    {},
  );
  await identity.createBranch(access, {
    nameAr: "الفرع الرئيسي",
    nameEn: "Main Branch",
    timezone: "Asia/Amman",
  });
  const [branch] = await identity.listBranches(access);
  if (!branch) throw new Error("Branch fixture missing.");

  // Create a doctor / provider
  const doctorUser = await client.user.create({
    data: { email: `inv-doctor-${label}-${suffix}@example.invalid`, name: `Doctor ${label}` },
  });
  const providerRole = (await identity.listRoles(access)).find(
    ({ systemKey }) => systemKey === "PROVIDER",
  );
  if (!providerRole) throw new Error("Provider role fixture missing.");
  const invitationToken = await identity.createInvitation(
    access,
    doctorUser.email,
    providerRole.id,
  );
  const doctorMembership = await identity.acceptInvitation(
    doctorUser.id,
    doctorUser.email,
    invitationToken,
  );
  const doctorStaff = await runInTenant(client, access, (transaction) =>
    transaction.staffProfile.findFirstOrThrow({
      include: { branchAssignments: true },
      where: {
        membershipId: doctorMembership.membershipId,
        organizationId: access.organizationId,
      },
    }),
  );
  expect(doctorStaff.branchAssignments.map(({ branchId }) => branchId)).toEqual([branch.id]);
  await identity.configureDoctor(access, {
    branchIds: [branch.id],
    displayNameAr: `د. طبيب ${label}`,
    displayNameEn: `Dr. Physician ${label}`,
    email: doctorUser.email,
    isActive: true,
    serviceIds: [],
    staffProfileId: doctorStaff.id,
  });
  await identity.replaceDoctorSchedule(access, {
    branchId: branch.id,
    breaks: [],
    confirmAffected: true,
    periods: [{ endMinuteLocal: 1440, startMinuteLocal: 0, weekday: "THURSDAY" }],
    staffProfileId: doctorStaff.id,
  });
  const doctorAccess = await identity.loadTenantAccess(
    doctorUser.id,
    {
      activeMembershipId: doctorMembership.membershipId,
      activeOrganizationId: accepted.organizationId,
    },
    {},
  );

  // Create a service
  await identity.createService(access, {
    currency: "JOD",
    defaultDurationMins: 30,
    defaultPriceMinor: 5000,
    nameAr: "جلسة ليزر",
    nameEn: "Laser Treatment",
  });
  const service = (await identity.listServices(access)).find(
    ({ nameEn }) => nameEn === "Laser Treatment",
  );
  if (!service) throw new Error("Service fixture missing.");
  await identity.configureServiceBranch(access, {
    branchId: branch.id,
    durationMins: 30,
    isEnabled: true,
    serviceId: service.id,
  });
  await identity.configureDoctor(access, {
    branchIds: [branch.id],
    displayNameAr: `د. طبيب ${label}`,
    displayNameEn: `Dr. Physician ${label}`,
    email: doctorUser.email,
    isActive: true,
    serviceIds: [service.id],
    staffProfileId: doctorStaff.id,
  });
  const roomGroup = await scheduling.createResourceGroup(access, {
    branchId: branch.id,
    kind: "ROOM",
    nameAr: `غرف المخزون ${label}`,
    nameEn: `Inventory Rooms ${label}`,
  });
  const room = await scheduling.createResource(access, {
    allowedServiceIds: [service.id],
    groupId: roomGroup.id,
    nameAr: `غرفة المخزون ${label}`,
    nameEn: `Inventory Room ${label}`,
  });

  // Customer
  const customer = await crm.createCustomer(access, {
    displayName: `Patient ${label}`,
    phoneOriginal: "079 000 1111",
    preferredLocale: "en",
  });

  return { access, branch, customer, doctorAccess, doctorStaff, owner, room, service };
}

describe("Comprehensive Inventory Workflow Integration", () => {
  let tenantA: Awaited<ReturnType<typeof createTenantFixture>>;
  let tenantB: Awaited<ReturnType<typeof createTenantFixture>>;

  beforeAll(async () => {
    [tenantA, tenantB] = await Promise.all([
      createTenantFixture("alpha"),
      createTenantFixture("beta"),
    ]);
  });

  afterAll(async () => {
    await client.$disconnect();
  });

  it("enforces tenant isolation and permission denial for inventory items and operations", async () => {
    // Tenant A creates an item direct
    const itemA = await workflows.createItemDirect(tenantA.access, {
      branchId: tenantA.branch.id,
      category: "CONSUMABLE",
      minimumStock: 5,
      name: `Disposable Tips ${suffix}`,
      unitOfMeasure: "box",
    });

    // Tenant B cannot view Tenant A item
    const tenantBInventory = await workflows.listInventory(tenantB.access);
    expect(tenantBInventory.items.some((i) => i.id === itemA.id)).toBe(false);

    // Tenant B cannot update or adjust Tenant A item
    await expect(
      workflows.updateItem(tenantB.access, {
        expectedVersion: itemA.version,
        id: itemA.id,
        name: "Hacked Item",
      }),
    ).rejects.toMatchObject({ code: "CONFLICT" });

    // Doctor in Tenant A lacks inventory.items.manage, so cannot create items direct
    await expect(
      workflows.createItemDirect(tenantA.doctorAccess, {
        branchId: tenantA.branch.id,
        category: "CONSUMABLE",
        minimumStock: 1,
        name: "Unauthorized Item",
        unitOfMeasure: "pcs",
      }),
    ).rejects.toMatchObject({ code: "FORBIDDEN" });
  });

  it("handles Item Proposal workflow: doctor requests, approver approves, supplier/cost visibility rules", async () => {
    // Doctor creates proposal
    const proposal = await workflows.createItemProposal(tenantA.doctorAccess, {
      branchId: tenantA.branch.id,
      category: "SKINCARE_PRODUCT",
      note: "Urgent restocking needed for skin treatments",
      proposedName: `Hydrating Serum ${suffix}`,
      reasonNeeded: "Low esthetic-service supply",
      suggestedQuantity: 15,
      unitOfMeasure: "bottle",
      urgent: true,
    });
    expect(proposal.status).toBe("PENDING_APPROVAL");
    expect(proposal.urgent).toBe(true);

    // Approver approves proposal with SKU, supplier and unit price
    const approvedItem = await workflows.approveItemProposal(tenantA.access, {
      batchTrackingEnabled: true,
      expectedVersion: proposal.version,
      expiryTrackingEnabled: true,
      id: proposal.id,
      minimumStock: 3,
      name: proposal.proposedName,
      reorderQuantity: 10,
      sku: `SKU-${suffix}`,
      supplierName: "Karmalite Beauty Supplies",
      supplierPhone: "+962791112233",
      unitPrice: 25.5,
    });
    expect(approvedItem.id).toBeTruthy();
    expect(approvedItem.batchTrackingEnabled).toBe(true);
    expect(approvedItem.expiryTrackingEnabled).toBe(true);

    // Check doctor visibility: Doctor does NOT have inventory.supplier.read or inventory.cost.read
    const doctorInventory = await workflows.listInventory(tenantA.doctorAccess);
    const doctorViewItem = doctorInventory.items.find((i) => i.id === approvedItem.id);
    expect(doctorViewItem).toBeDefined();
    expect(doctorViewItem?.supplierName).toBeNull();
    expect(doctorViewItem?.supplierPhone).toBeNull();
    expect(doctorViewItem?.unitPrice).toBeNull();

    // Owner has full visibility
    const ownerInventory = await workflows.listInventory(tenantA.access);
    const ownerViewItem = ownerInventory.items.find((i) => i.id === approvedItem.id);
    expect(ownerViewItem?.supplierName).toBe("Karmalite Beauty Supplies");
    expect(ownerViewItem?.supplierPhone).toBe("+962791112233");
    expect(Number(ownerViewItem?.unitPrice)).toBe(25.5);
  });

  it("executes complete Order workflow: place order, approve, mark ordered with ETA, partial receipt and full receipt with batch/cost", async () => {
    const item = await workflows.createItemDirect(tenantA.access, {
      batchTrackingEnabled: true,
      branchId: tenantA.branch.id,
      category: "CONSUMABLE",
      expiryTrackingEnabled: true,
      minimumStock: 5,
      name: `Laser Gel Cartridge ${suffix}`,
      reorderQuantity: 20,
      unitOfMeasure: "cartridge",
    });

    // 1. Doctor requests order
    const orderRequest = await workflows.createOrderRequest(tenantA.doctorAccess, {
      branchId: tenantA.branch.id,
      itemId: item.id,
      quantity: 20,
      reason: "Anticipated high weekend volume",
      urgency: "URGENT",
    });
    expect(orderRequest.status).toBe("PENDING_APPROVAL");

    // 2. Approver approves order
    const approvedOrder = await workflows.approveOrder(tenantA.access, {
      expectedVersion: orderRequest.version,
      id: orderRequest.id,
      note: "Approved immediately due to urgency",
    });
    expect(approvedOrder.status).toBe("APPROVED");

    // 3. Mark Ordered with ETA
    const orderDate = new Date();
    const placedOrder = await workflows.markOrderPlaced(tenantA.access, {
      expectedDeliveryUnit: "DAYS",
      expectedDeliveryValue: 3,
      expectedVersion: approvedOrder.version,
      id: approvedOrder.id,
      orderedAt: orderDate,
      orderedQuantity: 20,
      supplierName: "Beauty Supply Jordan",
      supplierReference: `PO-${suffix}`,
    });
    expect(placedOrder.status).toBe("ORDERED");
    expect(placedOrder.expectedArrivalAt).toBeInstanceOf(Date);
    const expectedArrivalAt = placedOrder.expectedArrivalAt;
    if (!expectedArrivalAt) throw new Error("Expected arrival was not calculated.");
    const expectedHoursDiff = (expectedArrivalAt.getTime() - orderDate.getTime()) / (1000 * 3600);
    expect(Math.round(expectedHoursDiff)).toBe(72); // 3 days = 72 hours

    // 4. Partial Receipt (12 units)
    const loc = await workflows.createLocation(tenantA.access, {
      branchId: tenantA.branch.id,
      isDefault: true,
      name: `Central Storage ${suffix}`,
    });

    const expiryDate = new Date(Date.now() + 180 * 24 * 3600 * 1000); // 180 days in future
    const receiptKey1 = randomUUID();
    const receivedAt = new Date();
    const partialReceipt = await workflows.receiveOrder(tenantA.access, {
      batchNumber: `BATCH-01-${suffix}`,
      expiryDate,
      id: placedOrder.id,
      locationId: loc.id,
      purchaseCost: 120,
      quantity: 12,
      receivedAt,
      requestKey: receiptKey1,
    });
    expect(partialReceipt).toBeDefined();

    // Verify order is PARTIALLY_RECEIVED
    const orderAfterPartial = await client.inventoryOrderRequest.findUniqueOrThrow({
      where: { id: placedOrder.id },
    });
    expect(orderAfterPartial.status).toBe("PARTIALLY_RECEIVED");
    expect(Number(orderAfterPartial.receivedQuantity)).toBe(12);

    // Verify batch was created with correct quantity and cost
    const batch = await client.inventoryBatch.findFirstOrThrow({
      where: { batchNumber: `BATCH-01-${suffix}`, itemId: item.id },
    });
    expect(Number(batch.quantity)).toBe(12);
    expect(Number(batch.purchaseCost)).toBe(120);

    // Verify immutable movement ledger entry created
    const movement = await client.inventoryStockMovement.findFirstOrThrow({
      where: { batchId: batch.id, itemId: item.id, type: "PURCHASE_RECEIPT" },
    });
    expect(Number(movement.quantity)).toBe(12);
    expect(Number(movement.balanceAfter)).toBe(12);

    // 5. Idempotent re-receipt with same requestKey
    const replay = await workflows.receiveOrder(tenantA.access, {
      batchNumber: `BATCH-01-${suffix}`,
      expiryDate,
      id: placedOrder.id,
      locationId: loc.id,
      purchaseCost: 120,
      quantity: 12,
      receivedAt,
      requestKey: receiptKey1,
    });
    expect(replay.id).toBe(partialReceipt.id);

    // 6. Attempt over-receipt (remaining is 8, try receiving 9) -> must fail
    await expect(
      workflows.receiveOrder(tenantA.access, {
        id: placedOrder.id,
        quantity: 9,
        receivedAt: new Date(),
        requestKey: randomUUID(),
      }),
    ).rejects.toMatchObject({ code: "VALIDATION_FAILED" });

    // 7. Receive remaining 8 units -> order becomes RECEIVED
    await workflows.receiveOrder(tenantA.access, {
      batchNumber: `BATCH-02-${suffix}`,
      expiryDate,
      id: placedOrder.id,
      locationId: loc.id,
      purchaseCost: 80,
      quantity: 8,
      receivedAt: new Date(),
      requestKey: randomUUID(),
    });

    const orderFinal = await client.inventoryOrderRequest.findUniqueOrThrow({
      where: { id: placedOrder.id },
    });
    expect(orderFinal.status).toBe("RECEIVED");
    expect(Number(orderFinal.receivedQuantity)).toBe(20);

    // Stock should now be 20
    const updatedItem = await client.inventoryItem.findUniqueOrThrow({
      where: { id: item.id },
    });
    expect(Number(updatedItem.currentStock)).toBe(20);

    // A partial batch transfer splits the batch between locations instead of moving it wholesale.
    const treatmentRoomStock = await workflows.createLocation(tenantA.access, {
      branchId: tenantA.branch.id,
      name: `Treatment Room Stock ${suffix}`,
    });
    await workflows.transferStock(tenantA.access, {
      batchId: batch.id,
      branchId: tenantA.branch.id,
      fromLocationId: loc.id,
      itemId: item.id,
      quantity: 5,
      reason: "Supply the treatment room",
      toLocationId: treatmentRoomStock.id,
    });
    const [sourceBatch, destinationBatch] = await Promise.all([
      client.inventoryBatch.findUniqueOrThrow({ where: { id: batch.id } }),
      client.inventoryBatch.findFirstOrThrow({
        where: {
          batchNumber: batch.batchNumber,
          itemId: item.id,
          locationId: treatmentRoomStock.id,
        },
      }),
    ]);
    expect(Number(sourceBatch.quantity)).toBe(7);
    expect(Number(destinationBatch.quantity)).toBe(5);

    // Distinct concurrent receipt commands serialize on the order and cannot over-receive.
    const concurrentRequest = await workflows.createOrderRequest(tenantA.access, {
      branchId: tenantA.branch.id,
      itemId: item.id,
      quantity: 10,
      reason: "Concurrency verification",
      urgency: "NORMAL",
    });
    const concurrentApproved = await workflows.approveOrder(tenantA.access, {
      expectedVersion: concurrentRequest.version,
      id: concurrentRequest.id,
    });
    const concurrentOrder = await workflows.markOrderPlaced(tenantA.access, {
      expectedDeliveryUnit: "HOURS",
      expectedDeliveryValue: 1,
      expectedVersion: concurrentApproved.version,
      id: concurrentApproved.id,
      orderedAt: new Date(),
      orderedQuantity: 10,
      supplierName: "Concurrency Supplier",
    });
    const concurrentReceipts = await Promise.allSettled([
      workflows.receiveOrder(tenantA.access, {
        id: concurrentOrder.id,
        locationId: loc.id,
        quantity: 6,
        receivedAt: new Date(),
        requestKey: randomUUID(),
      }),
      workflows.receiveOrder(tenantA.access, {
        id: concurrentOrder.id,
        locationId: loc.id,
        quantity: 6,
        receivedAt: new Date(),
        requestKey: randomUUID(),
      }),
    ]);
    expect(concurrentReceipts.filter(({ status }) => status === "fulfilled")).toHaveLength(1);
    expect(concurrentReceipts.filter(({ status }) => status === "rejected")).toHaveLength(1);
    const concurrentFinal = await client.inventoryOrderRequest.findUniqueOrThrow({
      where: { id: concurrentOrder.id },
    });
    expect(Number(concurrentFinal.receivedQuantity)).toBe(6);
  });

  it("handles atomic stock transfers between locations and adjustments with ledger entries", async () => {
    const locRoom = await workflows.createLocation(tenantA.access, {
      branchId: tenantA.branch.id,
      name: `Laser Suite 1 ${suffix}`,
    });

    const item = await workflows.createItemDirect(tenantA.access, {
      branchId: tenantA.branch.id,
      category: "MATERIAL",
      currentStock: 50,
      minimumStock: 10,
      name: `Alcohol Wipes Box ${suffix}`,
      unitOfMeasure: "box",
    });

    // Ensure default location has the stock, then transfer 15 units to locRoom
    const defaultLoc = await client.inventoryLocation.findFirstOrThrow({
      where: {
        branchId: tenantA.branch.id,
        isDefault: true,
        organizationId: tenantA.access.organizationId,
      },
    });

    await workflows.transferStock(tenantA.access, {
      branchId: tenantA.branch.id,
      fromLocationId: defaultLoc.id,
      itemId: item.id,
      quantity: 15,
      reason: "Refill Laser Suite",
      toLocationId: locRoom.id,
    });

    // Check movements: TRANSFER_OUT and TRANSFER_IN
    const transferOut = await client.inventoryStockMovement.findFirst({
      where: { itemId: item.id, locationId: defaultLoc.id, type: "TRANSFER_OUT" },
    });
    const transferIn = await client.inventoryStockMovement.findFirst({
      where: { itemId: item.id, locationId: locRoom.id, type: "TRANSFER_IN" },
    });
    expect(transferOut).toBeDefined();
    expect(transferIn).toBeDefined();
    expect(Number(transferOut?.quantity)).toBe(-15);
    expect(Number(transferIn?.quantity)).toBe(15);

    // Stock adjustment: 2 boxes expired in locRoom
    await workflows.adjustStock(tenantA.access, {
      branchId: tenantA.branch.id,
      itemId: item.id,
      locationId: locRoom.id,
      movementType: "EXPIRED",
      quantityChange: 2, // signed automatically as -2
      reason: "Found past expiration date during audit",
    });

    const expiredMovement = await client.inventoryStockMovement.findFirst({
      where: { itemId: item.id, locationId: locRoom.id, type: "EXPIRED" },
    });
    expect(expiredMovement).toBeDefined();
    expect(Number(expiredMovement?.quantity)).toBe(-2);
  });

  it("integrates service inventory requirements, appointment reservation on CONFIRM, and actual consumption on Service Done", async () => {
    // 1. Create consumable item and stock it
    const gelItem = await workflows.createItemDirect(tenantA.access, {
      batchTrackingEnabled: true,
      branchId: tenantA.branch.id,
      category: "CONSUMABLE",
      currentStock: 10,
      minimumStock: 2,
      name: `Cooling Gel Tube ${suffix}`,
      unitOfMeasure: "tube",
    });

    // 2. Add service inventory requirement with RESERVE_ON_CONFIRMATION
    const req = await workflows.addServiceRequirement(tenantA.access, {
      expectedQuantity: 2,
      isRequired: true,
      itemId: gelItem.id,
      reservationMode: "RESERVE_ON_CONFIRMATION",
      serviceId: tenantA.service.id,
      unitOfMeasure: "tube",
    });
    expect(req.id).toBeDefined();

    // 3. Book appointment in PENDING
    const appointment = await crm.createAppointment(tenantA.access, {
      branchId: tenantA.branch.id,
      customerId: tenantA.customer.customer.id,
      providerId: tenantA.doctorStaff.id,
      serviceId: tenantA.service.id,
      startsAtLocal: "2026-10-15T14:00",
      status: "PENDING",
    });

    // Check inventory demand forecast: upcoming demand is 2, available is 10, reserved is 0
    const invPreConfirm = await workflows.listInventory(tenantA.access);
    const itemPreConfirm = invPreConfirm.items.find((i) => i.id === gelItem.id);
    expect(itemPreConfirm?.availableStock).toBe(10);
    expect(Number(itemPreConfirm?.reservedQuantity)).toBe(0);

    // 4. Confirm appointment -> should reserve 2 units
    const confirmedAppt = await crm.transitionAppointment(tenantA.access, {
      appointmentId: appointment.id,
      expectedVersion: appointment.version,
      toStatus: "CONFIRMED",
    });

    const itemPostConfirm = (await workflows.listInventory(tenantA.access)).items.find(
      (i) => i.id === gelItem.id,
    );
    expect(Number(itemPostConfirm?.reservedQuantity)).toBe(2);
    expect(itemPostConfirm?.availableStock).toBe(8);

    // 5. Progress to CHECKED_IN and IN_PROGRESS
    const checkedInAppt = await crm.transitionAppointment(tenantA.access, {
      appointmentId: confirmedAppt.id,
      expectedVersion: confirmedAppt.version,
      toStatus: "CHECKED_IN",
    });
    const inProgressAppt = await crm.startAppointmentService(tenantA.access, {
      appointmentId: checkedInAppt.id,
      expectedVersion: checkedInAppt.version,
      roomId: tenantA.room.id,
    });

    // 6. Completion records a shortage for reconciliation without rolling back the appointment.
    const completedAppt = await crm.transitionAppointment(tenantA.access, {
      appointmentId: inProgressAppt.id,
      consumptions: [
        {
          actualQuantity: 12,
          expectedQuantity: 2,
          itemId: gelItem.id,
          reconciliationNote: "Extra tube used due to large treatment area",
          unitOfMeasure: "tube",
        },
      ],
      expectedVersion: inProgressAppt.version,
      recordSummary: "Treatment completed safely",
      toStatus: "COMPLETED",
    });
    expect(completedAppt.status).toBe("COMPLETED");

    // Only the 10 recorded units are deducted; stock never becomes negative.
    const itemFinal = await client.inventoryItem.findUniqueOrThrow({
      where: { id: gelItem.id },
    });
    expect(Number(itemFinal.currentStock)).toBe(0);
    expect(Number(itemFinal.reservedQuantity)).toBe(0);

    // Check appointment consumption record
    const consumptionRecord = await client.appointmentInventoryConsumption.findFirstOrThrow({
      where: { appointmentId: appointment.id, itemId: gelItem.id },
    });
    expect(Number(consumptionRecord.expectedQuantity)).toBe(2);
    expect(Number(consumptionRecord.actualQuantity)).toBe(12);
    expect(consumptionRecord.isReconciliationRequired).toBe(true);
    expect(consumptionRecord.reconciliationNote).toContain("Extra tube used");

    // Check stock movement ledger has APPOINTMENT_CONSUMPTION
    const apptMovement = await client.inventoryStockMovement.findFirstOrThrow({
      where: {
        appointmentId: appointment.id,
        itemId: gelItem.id,
        type: "APPOINTMENT_CONSUMPTION",
      },
    });
    expect(Number(apptMovement.quantity)).toBe(-10);

    // Creating directly as CONFIRMED reserves once, and cancellation releases that reservation.
    const directlyConfirmed = await crm.createAppointment(tenantA.access, {
      branchId: tenantA.branch.id,
      customerId: tenantA.customer.customer.id,
      providerId: tenantA.doctorStaff.id,
      serviceId: tenantA.service.id,
      startsAtLocal: "2026-10-15T15:00",
      status: "CONFIRMED",
    });
    const reservedAfterCreate = await client.inventoryItem.findUniqueOrThrow({
      where: { id: gelItem.id },
    });
    expect(Number(reservedAfterCreate.reservedQuantity)).toBe(2);
    await crm.transitionAppointment(tenantA.access, {
      appointmentId: directlyConfirmed.id,
      expectedVersion: directlyConfirmed.version,
      reason: "Reservation release verification",
      toStatus: "CANCELLED",
    });
    const releasedAfterCancel = await client.inventoryItem.findUniqueOrThrow({
      where: { id: gelItem.id },
    });
    expect(Number(releasedAfterCancel.reservedQuantity)).toBe(0);
    expect(
      await client.appointmentInventoryConsumption.count({
        where: { appointmentId: appointment.id, itemId: gelItem.id },
      }),
    ).toBe(1);
  });

  it("lets the assigned doctor change an in-progress service and safely replaces inventory demand", async () => {
    const originalItem = await workflows.createItemDirect(tenantA.access, {
      branchId: tenantA.branch.id,
      category: "CONSUMABLE",
      currentStock: 10,
      minimumStock: 1,
      name: `Original treatment supply ${suffix}`,
      unitOfMeasure: "piece",
    });
    const replacementItem = await workflows.createItemDirect(tenantA.access, {
      branchId: tenantA.branch.id,
      category: "CONSUMABLE",
      currentStock: 10,
      minimumStock: 1,
      name: `Replacement treatment supply ${suffix}`,
      unitOfMeasure: "piece",
    });
    await workflows.addServiceRequirement(tenantA.access, {
      expectedQuantity: 1,
      isRequired: true,
      itemId: originalItem.id,
      reservationMode: "RESERVE_ON_CONFIRMATION",
      serviceId: tenantA.service.id,
      unitOfMeasure: "piece",
    });
    await identity.createService(tenantA.access, {
      currency: "JOD",
      defaultDurationMins: 30,
      nameAr: `خدمة بديلة ${suffix}`,
      nameEn: `Alternative service ${suffix}`,
    });
    const alternativeService = (await identity.listServices(tenantA.access)).find(
      ({ nameEn }) => nameEn === `Alternative service ${suffix}`,
    );
    if (!alternativeService) throw new Error("Alternative service fixture missing.");
    await identity.configureServiceBranch(tenantA.access, {
      branchId: tenantA.branch.id,
      durationMins: 30,
      isEnabled: true,
      serviceId: alternativeService.id,
    });
    await identity.configureDoctor(tenantA.access, {
      branchIds: [tenantA.branch.id],
      displayNameAr: tenantA.doctorStaff.displayNameAr,
      displayNameEn: tenantA.doctorStaff.displayNameEn,
      email: tenantA.doctorStaff.email ?? undefined,
      isActive: true,
      serviceIds: [tenantA.service.id, alternativeService.id],
      staffProfileId: tenantA.doctorStaff.id,
    });
    await scheduling.updateRoom(tenantA.access, {
      allowedServiceIds: [tenantA.service.id, alternativeService.id],
      capacity: tenantA.room.capacity,
      confirmAffected: true,
      nameAr: tenantA.room.nameAr,
      nameEn: tenantA.room.nameEn,
      resourceId: tenantA.room.id,
    });
    await workflows.addServiceRequirement(tenantA.access, {
      expectedQuantity: 2,
      isRequired: true,
      itemId: replacementItem.id,
      reservationMode: "RESERVE_ON_CONFIRMATION",
      serviceId: alternativeService.id,
      unitOfMeasure: "piece",
    });

    const appointment = await crm.createAppointment(tenantA.access, {
      branchId: tenantA.branch.id,
      customerId: tenantA.customer.customer.id,
      providerId: tenantA.doctorStaff.id,
      serviceId: tenantA.service.id,
      startsAtLocal: "2026-10-15T16:00",
      status: "CONFIRMED",
    });
    const checkedIn = await crm.transitionAppointment(tenantA.access, {
      appointmentId: appointment.id,
      expectedVersion: appointment.version,
      toStatus: "CHECKED_IN",
    });
    const started = await crm.startAppointmentService(tenantA.doctorAccess, {
      appointmentId: checkedIn.id,
      expectedVersion: checkedIn.version,
      roomId: tenantA.room.id,
    });
    const changed = await crm.changeAppointmentService(tenantA.doctorAccess, {
      appointmentId: started.id,
      expectedVersion: started.version,
      reason: "Treatment adjusted after the in-person assessment.",
      serviceId: alternativeService.id,
    });
    expect(changed).toMatchObject({ serviceId: alternativeService.id, status: "IN_PROGRESS" });

    const [originalAfterChange, replacementAfterChange, history] = await Promise.all([
      client.inventoryItem.findUniqueOrThrow({ where: { id: originalItem.id } }),
      client.inventoryItem.findUniqueOrThrow({ where: { id: replacementItem.id } }),
      client.appointmentStatusHistory.findFirst({
        where: { appointmentId: appointment.id, eventType: "SERVICE_CHANGED" },
      }),
    ]);
    expect(Number(originalAfterChange.reservedQuantity)).toBe(0);
    expect(Number(replacementAfterChange.reservedQuantity)).toBe(2);
    expect(history?.serviceSnapshotId).toBe(alternativeService.id);

    await expect(
      crm.changeAppointmentService(tenantB.doctorAccess, {
        appointmentId: changed.id,
        expectedVersion: changed.version,
        serviceId: tenantB.service.id,
      }),
    ).rejects.toMatchObject({ code: "NOT_FOUND" });
  });
});
