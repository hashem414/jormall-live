import { randomUUID } from "node:crypto";

import { createPrismaClient } from "@jormall/db/client";
import { IdentityRepository } from "@jormall/db/identity-repository";
import { OperationalWorkflowsRepository } from "@jormall/db/operational-workflows-repository";
import { OrganizationStatus, PlatformRole } from "@jormall/db/generated/enums";
import { runInTenant } from "@jormall/db/tenant-context";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

const databaseUrl = process.env.TEST_DATABASE_URL ?? process.env.DATABASE_URL;
if (!databaseUrl) throw new Error("TEST_DATABASE_URL or DATABASE_URL is required.");
const client = createPrismaClient(databaseUrl);
const identity = new IdentityRepository(client);
const workflows = new OperationalWorkflowsRepository(client);
const suffix = randomUUID().slice(0, 8);

async function tenant(label: string) {
  const admin = await client.user.create({
    data: {
      email: `remaining-admin-${label}-${suffix}@example.invalid`,
      name: "Test Admin",
      platformRole: PlatformRole.JORMALL_SUPER_ADMIN,
    },
  });
  const owner = await client.user.create({
    data: { email: `remaining-owner-${label}-${suffix}@example.invalid`, name: "Test Owner" },
  });
  const created = await identity.createOrganization(admin.id, {
    nameAr: `اختبار ${label}`,
    nameEn: `Test ${label}`,
    ownerEmail: owner.email,
    slug: `remaining-${label}-${suffix}`,
  });
  const accepted = await identity.acceptInvitation(owner.id, owner.email, created.invitationToken);
  await identity.setOrganizationStatus(admin.id, created.organizationId, OrganizationStatus.ACTIVE);
  const access = await identity.loadTenantAccess(
    owner.id,
    { activeMembershipId: accepted.membershipId, activeOrganizationId: accepted.organizationId },
    {},
  );
  await identity.createBranch(access, {
    nameAr: "الفرع",
    nameEn: "Branch",
    timezone: "Asia/Amman",
  });
  const [branch] = await identity.listBranches(access);
  if (!branch) throw new Error("Branch fixture missing.");
  return { access, branch, owner };
}

describe("remaining Karmalite operational workflows", () => {
  let first: Awaited<ReturnType<typeof tenant>>;
  let second: Awaited<ReturnType<typeof tenant>>;
  beforeAll(async () => {
    [first, second] = await Promise.all([tenant("a"), tenant("b")]);
  });
  afterAll(async () => {
    await client.$disconnect();
  });

  it("keeps notification state recipient-scoped and independent", async () => {
    const escalation = await workflows.createEscalation(first.access, {
      branchId: first.branch.id,
      emergencySummary: "Patient reported an urgent concern",
      patientName: "Reported patient",
      relevantMessage: "Please ask a staff member to contact me",
      severity: "CRITICAL",
      sourceActionId: randomUUID(),
      sourceChannel: "INTERNAL",
    });
    const [notification] = await workflows.listNotifications(first.access, "UNREAD");
    expect(notification?.relatedEntityId).toBe(escalation.id);
    if (!notification) throw new Error("Notification fixture missing.");
    const unreadBefore = await workflows.countUnreadNotifications(first.access);
    await workflows.setNotificationState(first.access, { id: notification.id, state: "READ" });
    await expect(workflows.countUnreadNotifications(first.access)).resolves.toBe(unreadBefore - 1);
    await expect(
      workflows.setNotificationState(second.access, { id: notification.id, state: "DONE" }),
    ).rejects.toMatchObject({ code: "NOT_FOUND" });
    const unchanged = await workflows.listEscalations(first.access);
    expect(unchanged.find(({ id }) => id === escalation.id)?.status).toBe("NEW");

    const high = await workflows.createEscalation(first.access, {
      branchId: first.branch.id,
      emergencySummary: "A second reported concern",
      patientName: "Second patient",
      relevantMessage: "Please contact me",
      severity: "HIGH",
      sourceActionId: randomUUID(),
      sourceChannel: "INTERNAL",
    });
    const ordered = await workflows.listEscalations(first.access);
    expect(ordered.findIndex(({ id }) => id === escalation.id)).toBeLessThan(
      ordered.findIndex(({ id }) => id === high.id),
    );
    if (!first.access.membershipId) throw new Error("Membership fixture missing.");
    const acknowledged = await workflows.updateEscalation(first.access, {
      assignedMembershipId: first.access.membershipId,
      expectedVersion: escalation.version,
      id: escalation.id,
      status: "ACKNOWLEDGED",
    });
    expect(acknowledged.assignedUserId).toBe(first.owner.id);
    const resolved = await workflows.updateEscalation(first.access, {
      expectedVersion: acknowledged.version,
      id: escalation.id,
      reason: "Patient contacted; operational follow-up complete.",
      status: "RESOLVED",
    });
    expect(resolved.resolvedAt).not.toBeNull();
  });

  it("supports proposal review and order rejection without exposing costs to a restricted reader", async () => {
    const moreInfo = await workflows.createItemProposal(first.access, {
      branchId: first.branch.id,
      category: "MATERIAL",
      proposedName: `Review material ${suffix}`,
      reasonNeeded: "Needs specification",
      suggestedQuantity: 2,
      unitOfMeasure: "box",
      urgent: false,
    });
    const reviewed = await workflows.reviewItemProposal(first.access, {
      expectedVersion: moreInfo.version,
      id: moreInfo.id,
      reason: "Please provide the exact size.",
      status: "MORE_INFO_REQUIRED",
    });
    expect(reviewed.status).toBe("MORE_INFO_REQUIRED");

    const optionalReasonProposal = await workflows.createItemProposal(first.access, {
      branchId: first.branch.id,
      category: "MATERIAL",
      proposedName: `Optional reason item ${suffix}`,
      suggestedQuantity: 4,
      unitOfMeasure: "pack",
      urgent: false,
    });
    expect(optionalReasonProposal.reasonNeeded).toBe("");
    const reviewedWithoutReason = await workflows.reviewItemProposal(first.access, {
      expectedVersion: optionalReasonProposal.version,
      id: optionalReasonProposal.id,
      status: "REJECTED",
    });
    expect(reviewedWithoutReason).toMatchObject({ reviewNote: null, status: "REJECTED" });

    const proposal = await workflows.createItemProposal(first.access, {
      branchId: first.branch.id,
      category: "CONSUMABLE",
      proposedName: `Private cost item ${suffix}`,
      reasonNeeded: "Routine stock",
      suggestedQuantity: 3,
      unitOfMeasure: "piece",
      urgent: false,
    });
    const item = await workflows.approveItemProposal(first.access, {
      expectedVersion: proposal.version,
      id: proposal.id,
      minimumStock: 1,
      name: proposal.proposedName,
      supplierName: "Restricted supplier",
      supplierPhone: "+962700000000",
      unitPrice: 12,
    });
    const order = await workflows.createOrderRequest(first.access, {
      branchId: first.branch.id,
      itemId: item.id,
      quantity: 3,
      reason: "Routine stock",
      urgency: "NORMAL",
    });
    const rejected = await workflows.rejectOrder(first.access, {
      expectedVersion: order.version,
      id: order.id,
      reason: "Not needed this week.",
    });
    expect(rejected.status).toBe("REJECTED");

    const restricted = await workflows.listInventory({
      ...first.access,
      grants: [{ code: "inventory.items.read", scope: "ORGANIZATION" }],
    });
    const safeItem = restricted.items.find(({ id }) => id === item.id);
    expect(safeItem).toMatchObject({ supplierName: null, supplierPhone: null, unitPrice: null });
  });

  it("receives stock atomically, rejects over-receipt, and replays idempotently", async () => {
    const proposal = await workflows.createItemProposal(first.access, {
      branchId: first.branch.id,
      category: "CONSUMABLE",
      proposedName: `Disposable ${suffix}`,
      reasonNeeded: "Operational test",
      suggestedQuantity: 10,
      unitOfMeasure: "piece",
      urgent: false,
    });
    const item = await workflows.approveItemProposal(first.access, {
      expectedVersion: proposal.version,
      id: proposal.id,
      minimumStock: 2,
      name: proposal.proposedName,
    });
    const order = await workflows.createOrderRequest(first.access, {
      branchId: first.branch.id,
      itemId: item.id,
      quantity: 10,
      reason: "Replenishment",
      urgency: "NORMAL",
    });
    const approved = await workflows.approveOrder(first.access, {
      expectedVersion: order.version,
      id: order.id,
    });
    const placed = await workflows.markOrderPlaced(first.access, {
      expectedDeliveryUnit: "HOURS",
      expectedDeliveryValue: 4,
      expectedVersion: approved.version,
      id: approved.id,
      orderedAt: new Date(),
      orderedQuantity: 10,
      supplierName: "Test-only supplier",
    });
    const receivedAt = new Date();
    const key = randomUUID();
    const receipt = await workflows.receiveOrder(first.access, {
      id: placed.id,
      quantity: 6,
      receivedAt,
      requestKey: key,
    });
    const replay = await workflows.receiveOrder(first.access, {
      id: placed.id,
      quantity: 6,
      receivedAt,
      requestKey: key,
    });
    expect(replay.id).toBe(receipt.id);
    const settled = await Promise.allSettled([
      workflows.receiveOrder(first.access, {
        id: placed.id,
        quantity: 4,
        receivedAt: new Date(),
        requestKey: randomUUID(),
      }),
      workflows.receiveOrder(first.access, {
        id: placed.id,
        quantity: 5,
        receivedAt: new Date(),
        requestKey: randomUUID(),
      }),
    ]);
    expect(settled.filter(({ status }) => status === "fulfilled")).toHaveLength(1);
    const state = await runInTenant(client, first.access, async (transaction) => ({
      item: await transaction.inventoryItem.findFirstOrThrow({
        where: { id: item.id, organizationId: first.access.organizationId },
      }),
      order: await transaction.inventoryOrderRequest.findFirstOrThrow({
        where: { id: order.id, organizationId: first.access.organizationId },
      }),
      transactionCount: await transaction.stockTransaction.count({
        where: { itemId: item.id, organizationId: first.access.organizationId },
      }),
    }));
    expect(Number(state.item.currentStock)).toBe(10);
    expect(state.order.status).toBe("RECEIVED");
    expect(state.transactionCount).toBe(2);
  });
});
