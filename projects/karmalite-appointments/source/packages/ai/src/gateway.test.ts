import { randomUUID } from "node:crypto";

import type {
  AIActionRuntimePort,
  AIActionRuntimeRequest,
  AIActionName,
  AITrustedContext,
} from "@jormall/domain/ai-foundation";
import { describe, expect, it, vi } from "vitest";

import { initialActionDefinitions, SafeActionGateway } from "./gateway";
import { DeterministicMockModelAdapter } from "./model";

const context: AITrustedContext = {
  actorId: "00000000-0000-4000-8000-000000000005",
  actorType: "ai_receptionist",
  channel: "evaluation",
  conversationId: randomUUID(),
  modelIdentifier: "jormall-deterministic-mock-v1",
  organizationId: randomUUID(),
};

function envelope(actionName: AIActionName, payload: unknown) {
  return {
    actionName,
    actor: { id: context.actorId, type: context.actorType },
    authorization: {
      decisionId: randomUUID(),
      requiredPermission: initialActionDefinitions[actionName].requiredPermission,
    },
    channel: context.channel,
    idempotencyKey: `fixture-${randomUUID()}`,
    occurredAt: new Date().toISOString(),
    payload,
    requestId: randomUUID(),
    tenant: { organizationId: context.organizationId },
    version: 1,
  };
}

describe("safe Action Gateway and deterministic model", () => {
  it("validates structured input and passes only redacted evidence to the runtime", async () => {
    let captured: AIActionRuntimeRequest | undefined;
    const runtime: AIActionRuntimePort = {
      executeAction: vi.fn(async (request) => {
        captured = request;
        return {
          actionId: randomUUID(),
          auditEventId: randomUUID(),
          outcome: "completed" as const,
          payload: { match: false },
        };
      }),
      rejectAction: vi.fn(async () => ({
        actionId: randomUUID(),
        auditEventId: randomUUID(),
        outcome: "rejected" as const,
        payload: { errorCode: "REJECTED" },
      })),
    };
    const gateway = new SafeActionGateway(runtime);
    const result = await gateway.execute(
      context,
      envelope("find_customer_safely", { phoneOrEmail: "customer@example.invalid" }),
    );
    expect(result.outcome).toBe("completed");
    expect(captured?.rawInputRedacted).toEqual({ phoneOrEmail: "[REDACTED]" });
    expect(captured?.validatedInputRedacted).toEqual({ phoneOrEmail: "[REDACTED]" });
  });

  it("rejects an organization identifier that disagrees with trusted context", async () => {
    const rejectAction = vi.fn(async () => ({
      actionId: randomUUID(),
      auditEventId: randomUUID(),
      outcome: "rejected" as const,
      payload: { errorCode: "UNTRUSTED_CONTEXT" },
    }));
    const runtime: AIActionRuntimePort = {
      executeAction: vi.fn(),
      rejectAction,
    };
    const gateway = new SafeActionGateway(runtime);
    const input = envelope("find_customer_safely", { phoneOrEmail: "0799001122" });
    const result = await gateway.execute(context, {
      ...input,
      tenant: { organizationId: randomUUID() },
    });
    expect(result.outcome).toBe("rejected");
    expect(rejectAction).toHaveBeenCalledWith(
      expect.objectContaining({ errorCode: "UNTRUSTED_CONTEXT", trustedContext: context }),
    );
  });

  it("allowlists verified check-in and rejects sensitive extra input", async () => {
    const executeAction = vi.fn(async () => ({
      actionId: randomUUID(),
      auditEventId: randomUUID(),
      outcome: "completed" as const,
      payload: { status: "CHECKED_IN" },
    }));
    const rejectAction = vi.fn(async () => ({
      actionId: randomUUID(),
      auditEventId: randomUUID(),
      outcome: "rejected" as const,
      payload: { errorCode: "INVALID_TOOL_INPUT" },
    }));
    const gateway = new SafeActionGateway({ executeAction, rejectAction });
    const bookingReference = randomUUID();
    expect(
      (
        await gateway.execute(
          context,
          envelope("check_in_appointment", { bookingReference, expectedVersion: 1 }),
        )
      ).outcome,
    ).toBe("completed");
    expect(
      (
        await gateway.execute(
          context,
          envelope("check_in_appointment", {
            allergyDetails: "must not pass",
            bookingReference,
            expectedVersion: 1,
          }),
        )
      ).outcome,
    ).toBe("rejected");
    expect(initialActionDefinitions.create_emergency_escalation.requiredPermission).toBe(
      "chatbot_escalations.manage",
    );
  });

  it("handles Arabic ambiguity and unknown information deterministically", async () => {
    const model = new DeterministicMockModelAdapter();
    const ambiguous = await model.complete({
      immutableSafetyPolicy: "policy",
      knowledge: [],
      locale: "ar",
      organizationInstructions: "safe",
      userMessage: "بدي أحجز بكرا العصر",
    });
    const unknown = await model.complete({
      immutableSafetyPolicy: "policy",
      knowledge: [],
      locale: "en",
      organizationInstructions: "safe",
      userMessage: "Do you validate helicopter parking?",
    });
    expect(ambiguous.ambiguous).toBe(true);
    expect(ambiguous.toolCall).toBeUndefined();
    expect(unknown.informationAbsent).toBe(true);
    expect(unknown.content).toContain("not present");
  });
});
