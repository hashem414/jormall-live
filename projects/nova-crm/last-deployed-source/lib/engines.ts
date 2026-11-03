import { z } from "zod";
import type { Person } from "./domain";

export const PlanTaskSchema = z.object({
  title: z.string().min(3),
  description: z.string().min(8),
  required_position: z.string().min(2),
  required_skills: z.array(z.string()).min(1),
  estimated_hours: z.number().positive().max(80),
  priority: z.enum(["Low", "Medium", "High", "Critical"]),
  dependencies: z.array(z.string()),
  acceptance_criteria: z.array(z.string()).min(2),
  expected_output: z.string().min(3),
});
export const ProjectPlanSchema = z.object({
  project_summary: z.string().min(10),
  recommended_architecture: z.string().min(10),
  risks: z.array(
    z.object({
      title: z.string(),
      severity: z.enum(["Low", "Medium", "High", "Critical"]),
      mitigation: z.string(),
    }),
  ),
  phases: z
    .array(
      z.object({
        name: z.string(),
        description: z.string(),
        milestones: z.array(z.string()),
        tasks: z.array(PlanTaskSchema),
      }),
    )
    .min(1),
});
export type ProjectPlan = z.infer<typeof ProjectPlanSchema>;

export function expandPlanToDailyTasks(
  rawPlan: ProjectPlan,
  maxDailyHours = 8,
): ProjectPlan {
  const plan = ProjectPlanSchema.parse(rawPlan);
  const limit = Math.min(8, Math.max(1, maxDailyHours));
  const finalTitle = new Map<string, string>();
  const expandedPhases = plan.phases.map((phase) => ({
    ...phase,
    tasks: phase.tasks.flatMap((task) => {
      const count = Math.ceil(task.estimated_hours / limit);
      if (count === 1) {
        finalTitle.set(task.title, task.title);
        return [task];
      }
      let remaining = task.estimated_hours;
      const chunks = Array.from({ length: count }, (_, index) => {
        const hours = Math.min(limit, remaining);
        remaining -= hours;
        const title = `${task.title} — Day ${index + 1}/${count}`;
        const previousTitle =
          index > 0 ? `${task.title} — Day ${index}/${count}` : null;
        return {
          ...task,
          title,
          description: `${task.description} Daily work package ${index + 1} of ${count}; estimate reflects focused human engineering time after normal AI assistance, including implementation, review, debugging, testing and documentation.`,
          estimated_hours: hours,
          dependencies: previousTitle ? [previousTitle] : task.dependencies,
          acceptance_criteria: [
            ...task.acceptance_criteria,
            `Daily package ${index + 1}/${count} is reviewed and leaves reproducible evidence.`,
          ],
          expected_output:
            index === count - 1
              ? task.expected_output
              : `${task.expected_output} — verified progress package ${index + 1}/${count}`,
        };
      });
      finalTitle.set(task.title, chunks[chunks.length - 1].title);
      return chunks;
    }),
  }));
  for (const phase of expandedPhases)
    for (const task of phase.tasks)
      task.dependencies = task.dependencies.map(
        (dependency) => finalTitle.get(dependency) ?? dependency,
      );
  return ProjectPlanSchema.parse({ ...plan, phases: expandedPhases });
}

export const PLAN_JSON_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["project_summary", "recommended_architecture", "risks", "phases"],
  properties: {
    project_summary: { type: "string" },
    recommended_architecture: { type: "string" },
    risks: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["title", "severity", "mitigation"],
        properties: {
          title: { type: "string" },
          severity: {
            type: "string",
            enum: ["Low", "Medium", "High", "Critical"],
          },
          mitigation: { type: "string" },
        },
      },
    },
    phases: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["name", "description", "milestones", "tasks"],
        properties: {
          name: { type: "string" },
          description: { type: "string" },
          milestones: { type: "array", items: { type: "string" } },
          tasks: {
            type: "array",
            items: {
              type: "object",
              additionalProperties: false,
              required: [
                "title",
                "description",
                "required_position",
                "required_skills",
                "estimated_hours",
                "priority",
                "dependencies",
                "acceptance_criteria",
                "expected_output",
              ],
              properties: {
                title: { type: "string" },
                description: { type: "string" },
                required_position: { type: "string" },
                required_skills: { type: "array", items: { type: "string" } },
                estimated_hours: { type: "number" },
                priority: {
                  type: "string",
                  enum: ["Low", "Medium", "High", "Critical"],
                },
                dependencies: { type: "array", items: { type: "string" } },
                acceptance_criteria: {
                  type: "array",
                  items: { type: "string" },
                },
                expected_output: { type: "string" },
              },
            },
          },
        },
      },
    },
  },
} as const;

export function fallbackPlan(name: string, description: string): ProjectPlan {
  return ProjectPlanSchema.parse({
    project_summary:
      `${name} will turn the approved business workflow into a secure, measurable AI product with human oversight. ${description}`.slice(
        0,
        700,
      ),
    recommended_architecture:
      "A typed web application with an API service, PostgreSQL system of record, asynchronous AI jobs, evaluation telemetry, role-based access control and approval-gated model outputs.",
    risks: [
      {
        title: "Integration data quality",
        severity: "High",
        mitigation:
          "Profile source data early and require contract tests before integration tasks become Ready.",
      },
      {
        title: "AI output reliability",
        severity: "High",
        mitigation:
          "Use strict schemas, evaluation datasets, refusal handling and human approval for consequential actions.",
      },
      {
        title: "Delivery capacity",
        severity: "Medium",
        mitigation:
          "Schedule by dependency and daily focus capacity; reforecast after every blocker.",
      },
    ],
    phases: [
      {
        name: "Discovery & architecture",
        description:
          "Turn the brief into approved product and technical boundaries.",
        milestones: ["Architecture approved", "Evaluation plan approved"],
        tasks: [
          {
            title: "Map business workflow and success metrics",
            description:
              "Document users, decisions, integrations, KPIs and operational failure modes.",
            required_position: "AI Division Manager",
            required_skills: ["Prompt Engineering"],
            estimated_hours: 12,
            priority: "Critical",
            dependencies: [],
            acceptance_criteria: [
              "Primary workflow is approved",
              "KPIs have owners and target values",
              "Failure modes are documented",
            ],
            expected_output: "Approved product and measurement brief",
          },
          {
            title: "Design system architecture and security model",
            description:
              "Define services, data boundaries, authorization, observability and model guardrails.",
            required_position: "Senior AI Engineer",
            required_skills: ["OpenAI API", "Security", "Python"],
            estimated_hours: 18,
            priority: "Critical",
            dependencies: ["Map business workflow and success metrics"],
            acceptance_criteria: [
              "Architecture decision record approved",
              "Authorization boundaries documented",
              "AI guardrails mapped to backend checks",
            ],
            expected_output: "Architecture and security design",
          },
        ],
      },
      {
        name: "Core build",
        description:
          "Implement data, AI and product workflows behind feature flags.",
        milestones: ["Core workflow end-to-end", "Evaluation baseline passed"],
        tasks: [
          {
            title: "Implement domain API and persistence",
            description:
              "Build validated project APIs, audit events and authorized data access.",
            required_position: "Backend Engineer",
            required_skills: ["FastAPI", "PostgreSQL", "Testing"],
            estimated_hours: 36,
            priority: "High",
            dependencies: ["Design system architecture and security model"],
            acceptance_criteria: [
              "API contract tests pass",
              "Project isolation tests pass",
              "Audit events cover material writes",
            ],
            expected_output: "Tested domain API",
          },
          {
            title: "Implement AI workflow with structured outputs",
            description:
              "Connect the model through schema validation, retry controls and approval states.",
            required_position: "AI Engineer",
            required_skills: ["OpenAI API", "Python", "Prompt Engineering"],
            estimated_hours: 28,
            priority: "High",
            dependencies: ["Design system architecture and security model"],
            acceptance_criteria: [
              "Malformed responses never persist",
              "Usage and cost are recorded",
              "Manager approval is required",
            ],
            expected_output: "Approval-gated AI workflow",
          },
          {
            title: "Build operational user experience",
            description:
              "Create manager and employee workflows with accessible states and responsive layouts.",
            required_position: "Frontend Engineer",
            required_skills: ["React", "Next.js", "TypeScript"],
            estimated_hours: 34,
            priority: "High",
            dependencies: ["Implement domain API and persistence"],
            acceptance_criteria: [
              "Core workflows work on desktop and mobile",
              "Loading, empty and error states exist",
              "Permission boundaries are reflected in UI",
            ],
            expected_output: "Connected product interface",
          },
        ],
      },
      {
        name: "Quality & launch",
        description: "Prove the system, prepare operations and release safely.",
        milestones: ["Release candidate approved", "Production launch"],
        tasks: [
          {
            title: "Run integration, authorization and AI failure tests",
            description:
              "Validate security, dependency, capacity and model failure scenarios.",
            required_position: "QA Engineer",
            required_skills: ["Testing", "Security"],
            estimated_hours: 24,
            priority: "Critical",
            dependencies: [
              "Implement AI workflow with structured outputs",
              "Build operational user experience",
            ],
            acceptance_criteria: [
              "Critical E2E path passes",
              "Cross-project access is denied",
              "AI timeout and malformed-output tests pass",
            ],
            expected_output: "Signed release test report",
          },
          {
            title: "Deploy canary and operating runbook",
            description:
              "Release with health checks, rollback and support documentation.",
            required_position: "DevOps Engineer",
            required_skills: ["Docker", "CI/CD", "Security"],
            estimated_hours: 18,
            priority: "High",
            dependencies: [
              "Run integration, authorization and AI failure tests",
            ],
            acceptance_criteria: [
              "Health checks pass",
              "Rollback is rehearsed",
              "Runbook has named owners",
            ],
            expected_output: "Production canary and runbook",
          },
        ],
      },
    ],
  });
}

export function scoreCandidate(
  requiredSkills: string[],
  requiredPosition: string,
  person: Person,
) {
  const skill = requiredSkills.length
    ? requiredSkills.filter((s) => person.skills.includes(s)).length /
      requiredSkills.length
    : 0.5;
  const position = person.position
    .toLowerCase()
    .includes(requiredPosition.toLowerCase().replace("senior ", ""))
    ? 1
    : person.position
          .toLowerCase()
          .split(" ")
          .some(
            (w) => requiredPosition.toLowerCase().includes(w) && w.length > 2,
          )
      ? 0.7
      : 0.35;
  const availability =
    Math.max(0, person.capacity - person.scheduled) / person.capacity;
  const workloadPenalty = Math.max(
    0,
    person.scheduled / person.capacity - 0.85,
  );
  return (
    Math.round(
      (skill * 0.55 +
        position * 0.25 +
        availability * 0.2 -
        workloadPenalty * 0.25) *
        1000,
    ) / 10
  );
}

export function assignTasks(plan: ProjectPlan, people: Person[]) {
  const projectedHours = new Map(
    people.map((person) => [person.id, Math.max(0, person.scheduled)]),
  );
  return plan.phases.flatMap((phase) =>
    phase.tasks.map((task) => {
      const ranked = people
        .map((person) => ({
          person,
          score:
            scoreCandidate(
              task.required_skills,
              task.required_position,
              person,
            ) -
            ((projectedHours.get(person.id) ?? 0) /
              Math.max(1, person.capacity)) *
              2.4,
        }))
        .sort((a, b) => b.score - a.score);
      const selected = ranked[0]?.person;
      if (selected)
        projectedHours.set(
          selected.id,
          (projectedHours.get(selected.id) ?? 0) + task.estimated_hours,
        );
      return {
        phase: phase.name,
        task,
        assigneeId: selected?.id ?? null,
        score: Math.round((ranked[0]?.score ?? 0) * 10) / 10,
        alternatives: ranked
          .slice(1, 3)
          .map((x) => ({ id: x.person.id, score: x.score })),
      };
    }),
  );
}

function isoWorkDate(day: number, startDate = new Date()) {
  const date = new Date(startDate);
  date.setHours(12, 0, 0, 0);
  while (date.getDay() === 0 || date.getDay() === 6)
    date.setDate(date.getDate() + 1);
  let added = 1;
  while (added < day) {
    date.setDate(date.getDate() + 1);
    if (date.getDay() !== 0 && date.getDay() !== 6) added++;
  }
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export function buildDeliveryPreview(
  plan: ProjectPlan,
  people: Person[],
  deadline: string,
  startDate = new Date(),
) {
  const assignments = assignTasks(plan, people);
  const items = assignments.map((assignment, index) => ({
    id: `preview-${index + 1}`,
    title: assignment.task.title,
    estimatedHours: assignment.task.estimated_hours,
    dependencies: assignment.task.dependencies,
    assigneeId: assignment.assigneeId ?? people[0]?.id ?? "unassigned",
    assignment,
  }));
  const capacities = Object.fromEntries(
    people.map((person) => [person.id, Math.min(8, person.capacity)]),
  );
  const rows = scheduleAssignedTasks(items, capacities);
  const used = new Map<string, number>();
  const slots = rows.map((row) => {
    const key = `${row.assigneeId}:${row.day}`;
    const prior = used.get(key) ?? 0;
    used.set(key, prior + row.hours);
    const minutes = 9 * 60 + Math.round(prior * 60);
    return {
      ...row,
      date: isoWorkDate(row.day, startDate),
      startTime: `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`,
    };
  });
  const tasks = items.map((item) => {
    const assignment = item.assignment;
    const person = people.find(
      (candidate) => candidate.id === assignment.assigneeId,
    );
    const taskSlots = slots.filter((slot) => slot.taskId === item.id);
    return {
      id: item.id,
      phase: assignment.phase,
      title: assignment.task.title,
      description: assignment.task.description,
      priority: assignment.task.priority,
      estimatedHours: assignment.task.estimated_hours,
      requiredPosition: assignment.task.required_position,
      requiredSkills: assignment.task.required_skills,
      dependencies: assignment.task.dependencies,
      acceptanceCriteria: assignment.task.acceptance_criteria,
      expectedOutput: assignment.task.expected_output,
      assignee: person
        ? {
            id: person.id,
            name: person.name,
            position: person.position,
            accent: person.accent,
            initials: person.initials,
            score: assignment.score,
          }
        : null,
      schedule: taskSlots.map(({ day, date, startTime, hours }) => ({
        day,
        date,
        startTime,
        hours,
      })),
      startDate: taskSlots[0]?.date ?? null,
      finishDate: taskSlots.at(-1)?.date ?? null,
    };
  });
  const forecastDate = slots.length
    ? isoWorkDate(Math.max(...slots.map((row) => row.day)), startDate)
    : isoWorkDate(1, startDate);
  const distribution = people
    .map((person) => {
      const plannedHours = tasks
        .filter((task) => task.assignee?.id === person.id)
        .reduce((total, task) => total + task.estimatedHours, 0);
      return {
        id: person.id,
        name: person.name,
        position: person.position,
        accent: person.accent,
        initials: person.initials,
        plannedHours,
        workDays: Math.ceil(plannedHours / Math.min(8, person.capacity)),
        taskCount: tasks.filter((task) => task.assignee?.id === person.id)
          .length,
      };
    })
    .filter((person) => person.plannedHours > 0);
  const normalizedDeadline = /^\d{4}-\d{2}-\d{2}$/.test(deadline)
    ? deadline
    : null;
  return {
    tasks,
    distribution,
    startDate: isoWorkDate(1, startDate),
    forecastDate,
    deadline: normalizedDeadline,
    onTime: normalizedDeadline ? forecastDate <= normalizedDeadline : null,
    totalHours: tasks.reduce((total, task) => total + task.estimatedHours, 0),
  };
}

export function buildDailySchedule(
  items: { id: string; estimatedHours: number; dependencies: string[] }[],
  capacity: number,
) {
  const result: { day: number; taskId: string; hours: number }[] = [];
  const remaining = new Map(items.map((i) => [i.id, i.estimatedHours]));
  let day = 1;
  while (remaining.size && day < 366) {
    let available = capacity,
      scheduled = false;
    for (const item of items) {
      const left = remaining.get(item.id);
      if (!left) continue;
      const dependenciesDone = item.dependencies.every(
        (dep) => !remaining.has(dep),
      );
      if (!dependenciesDone) continue;
      const hours = Math.min(left, available);
      if (hours <= 0) break;
      result.push({ day, taskId: item.id, hours });
      scheduled = true;
      available -= hours;
      if (hours >= left) remaining.delete(item.id);
      else remaining.set(item.id, left - hours);
      if (available <= 0) break;
    }
    if (!scheduled && remaining.size) throw new Error("CYCLIC_DEPENDENCY");
    day++;
  }
  return result;
}

export type AssignedScheduleInput = {
  id: string;
  title: string;
  estimatedHours: number;
  dependencies: string[];
  assigneeId: string;
};
export function scheduleAssignedTasks(
  items: AssignedScheduleInput[],
  capacities: Record<string, number>,
) {
  const byTitle = new Map(items.map((item) => [item.title, item]));
  const finishedDay = new Map<string, number>();
  const used = new Map<string, number>();
  const rows: {
    day: number;
    taskId: string;
    assigneeId: string;
    hours: number;
  }[] = [];
  const pending = new Map(items.map((item) => [item.id, item]));
  while (pending.size) {
    let progressed = false;
    for (const item of items) {
      if (!pending.has(item.id)) continue;
      const deps = item.dependencies
        .map((name) => byTitle.get(name))
        .filter(Boolean) as AssignedScheduleInput[];
      if (deps.some((dep) => !finishedDay.has(dep.id))) continue;
      let day = Math.max(
        1,
        ...deps.map((dep) => (finishedDay.get(dep.id) ?? 0) + 1),
      );
      let remaining = item.estimatedHours;
      const capacity = Math.max(0.5, capacities[item.assigneeId] ?? 8);
      while (remaining > 0) {
        const key = `${item.assigneeId}:${day}`;
        const available = Math.max(0, capacity - (used.get(key) ?? 0));
        if (available <= 0) {
          day++;
          continue;
        }
        const hours = Math.min(remaining, available);
        rows.push({ day, taskId: item.id, assigneeId: item.assigneeId, hours });
        used.set(key, (used.get(key) ?? 0) + hours);
        remaining -= hours;
        if (remaining > 0) day++;
      }
      finishedDay.set(item.id, day);
      pending.delete(item.id);
      progressed = true;
    }
    if (!progressed) throw new Error("CYCLIC_DEPENDENCY");
  }
  return rows;
}
