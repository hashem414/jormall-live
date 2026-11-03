/* eslint-disable @typescript-eslint/no-explicit-any */
import { env } from "cloudflare:workers";
import { z } from "zod";
import {
  buildDeliveryPreview,
  expandPlanToDailyTasks,
  fallbackPlan,
  PLAN_JSON_SCHEMA,
  ProjectPlanSchema,
} from "../../../../lib/engines";
import {
  getActor,
  getBootstrap,
  requireRole,
} from "../../../../lib/server-store";

const requestSchema = z.object({
  name: z.string().min(2).max(140),
  description: z.string().min(8).max(8000),
  deadline: z.string().min(4),
});

export async function POST(request: Request) {
  try {
    const actor = await getActor();
    requireRole(actor, ["manager", "admin"]);
    const input = requestSchema.parse(await request.json());
    const apiKey = (env as unknown as { OPENAI_API_KEY?: string })
      .OPENAI_API_KEY;
    const respond = async (
      plan: ReturnType<typeof expandPlanToDailyTasks>,
      source: string,
      extra: Record<string, unknown> = {},
    ) => {
      const workspace = await getBootstrap(actor);
      const delivery = buildDeliveryPreview(
        plan,
        workspace.people,
        input.deadline,
      );
      return Response.json({
        plan,
        delivery,
        source,
        totalHours: delivery.totalHours,
        ...extra,
      });
    };
    if (!apiKey) {
      const plan = expandPlanToDailyTasks(
        fallbackPlan(input.name, input.description),
      );
      return respond(plan, "deterministic_preview");
    }
    const model =
      (env as unknown as { OPENAI_MODEL?: string }).OPENAI_MODEL ??
      "gpt-5.6-terra";
    const response = await fetch("https://api.openai.com/v1/responses", {
      method: "POST",
      headers: {
        authorization: `Bearer ${apiKey}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({
        model,
        store: false,
        reasoning: { effort: "low" },
        max_output_tokens: 12000,
        safety_identifier: actor.id,
        input: [
          {
            role: "system",
            content:
              "You are the senior delivery planner for JorMall's AI division. Write the complete plan in the same language as the user's brief. Make it specific to the actual product instead of returning generic software tasks. Produce realistic, dependency-aware work through production launch. Every estimate is focused HUMAN engineering time AFTER normal AI assistance. Include discovery, content and data preparation, architecture, implementation, prompt and retrieval work, evaluation, Arabic quality, security, review, debugging, testing, deployment, monitoring, documentation and client handover when relevant. Treat the supplied deadline as a real constraint, create concrete acceptance criteria and expected outputs, prefer daily work packages of 2-8 hours and never exceed 8 hours per task after expansion. Do not assign people or modify any system record; NOVA assigns the validated plan against live skills and capacity.",
          },
          { role: "user", content: JSON.stringify(input) },
        ],
        text: {
          format: {
            type: "json_schema",
            name: "ai_project_plan",
            strict: true,
            schema: PLAN_JSON_SCHEMA,
          },
        },
      }),
    });
    if (!response.ok) throw new Error(`OPENAI_${response.status}`);
    const raw: any = await response.json();
    const outputText =
      raw.output_text ??
      raw.output
        ?.flatMap((x: any) => x.content ?? [])
        .find((x: any) => x.type === "output_text")?.text;
    const plan = expandPlanToDailyTasks(
      ProjectPlanSchema.parse(JSON.parse(outputText)),
    );
    return respond(plan, "openai", {
      model,
      usage: raw.usage ?? null,
    });
  } catch (error) {
    console.error(error);
    return Response.json(
      {
        error: {
          code: "AI_PLANNING_FAILED",
          message:
            "AI planning failed validation. No project records were changed.",
        },
      },
      { status: 422 },
    );
  }
}
