import { randomUUID } from "node:crypto";

import type { AITrustedContext } from "@jormall/domain/ai-foundation";
import { describe, expect, it, vi } from "vitest";

import type { ActionGateway } from "./gateway";
import type { ProviderNeutralModelAdapter } from "./model";
import { medicalBoundaryResponse, SafeAIOrchestrator } from "./orchestrator";

const context: AITrustedContext = {
  actorId: randomUUID(),
  actorType: "ai_receptionist",
  channel: "website_chat",
  conversationId: randomUUID(),
  modelIdentifier: "test-model",
  organizationId: randomUUID(),
};

describe("SafeAIOrchestrator medical boundary", () => {
  it("returns the exact Karmalite boundary response without retrieving knowledge or calling tools", async () => {
    const complete = vi.fn<ProviderNeutralModelAdapter["complete"]>();
    const execute = vi.fn<ActionGateway["execute"]>();
    const searchPublishedKnowledge = vi.fn();
    const appendAssistantMessage = vi.fn().mockResolvedValue(randomUUID());
    const appendCustomerMessage = vi.fn().mockResolvedValue(randomUUID());
    const recordUsage = vi.fn().mockResolvedValue(undefined);
    const orchestrator = new SafeAIOrchestrator(
      { complete, identifier: "test-model" },
      { execute },
      { searchPublishedKnowledge },
      {
        assertUsageWithinLimits: vi.fn().mockResolvedValue(undefined),
        appendAssistantMessage,
        appendCustomerMessage,
        loadActivePolicy: vi.fn().mockResolvedValue({
          allowedActionNames: ["request_human_handoff"],
          minimumConfidence: 0.8,
          organizationNameAr: "كارمالايت للتجميل الطبي",
          organizationNameEn: "Karmalite Medical Esthetic",
          systemPrompt: "Safe test policy",
        }),
        recordUsage,
      },
    );

    const result = await orchestrator.runTurn(context, "Is this mole cancerous?", "en");

    expect(result.content).toBe(
      "I am an automated assistant for Karmalite Medical Esthetic. For medical concerns or diagnoses, please consult a dermatologist. I can, however, help you book esthetic skin and body treatments with our specialists.",
    );
    expect(result.handoffRequested).toBe(false);
    expect(searchPublishedKnowledge).not.toHaveBeenCalled();
    expect(complete).not.toHaveBeenCalled();
    expect(execute).not.toHaveBeenCalled();
    expect(appendAssistantMessage).toHaveBeenCalledOnce();
    expect(recordUsage).toHaveBeenCalledOnce();
  });

  it("provides the approved Arabic equivalent", () => {
    expect(
      medicalBoundaryResponse("ar", "كارمالايت للتجميل الطبي", "Karmalite Medical Esthetic"),
    ).toBe(
      "أنا مساعد آلي لدى كارمالايت للتجميل الطبي. للاستفسارات أو التشخيصات الطبية، يرجى استشارة طبيب جلدية. يمكنني مساعدتك في حجز خدمات العناية الجمالية بالبشرة والجسم مع مقدمي الخدمات لدينا.",
    );
  });
});
