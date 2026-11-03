import assert from "node:assert/strict";
import test from "node:test";
import {
  buildDailySchedule,
  buildDeliveryPreview,
  expandPlanToDailyTasks,
  fallbackPlan,
  scheduleAssignedTasks,
  scoreCandidate,
} from "../lib/engines";
import { hashPassword, verifyPassword } from "../lib/auth";
import { people, projects, tasks } from "../lib/domain";
import { navKey, tr } from "../lib/i18n";

test("scheduler never exceeds daily capacity", () => {
  const rows = buildDailySchedule(
    [
      { id: "A", estimatedHours: 3, dependencies: [] },
      { id: "B", estimatedHours: 2, dependencies: [] },
      { id: "C", estimatedHours: 2, dependencies: [] },
      { id: "D", estimatedHours: 2, dependencies: [] },
    ],
    8,
  );
  const totals = new Map<number, number>();
  for (const row of rows)
    totals.set(row.day, (totals.get(row.day) ?? 0) + row.hours);
  assert.ok([...totals.values()].every((hours) => hours <= 8));
  assert.equal(
    [...totals.values()].reduce((a, b) => a + b, 0),
    9,
  );
  assert.ok(totals.size >= 2);
});

test("dependencies are scheduled after their prerequisite finishes", () => {
  const rows = buildDailySchedule(
    [
      { id: "A", estimatedHours: 8, dependencies: [] },
      { id: "B", estimatedHours: 2, dependencies: ["A"] },
    ],
    8,
  );
  assert.equal(rows.find((r) => r.taskId === "A")?.day, 1);
  assert.equal(rows.find((r) => r.taskId === "B")?.day, 2);
});

test("position and skills influence assignment suitability", () => {
  const frontend = people.find((p) => p.id === "u3")!;
  const sales = people.find((p) => p.id === "u2")!;
  assert.ok(
    scoreCandidate(
      ["React", "TypeScript"],
      "AI Full-Stack Engineer",
      frontend,
    ) >
      scoreCandidate(["React", "TypeScript"], "AI Full-Stack Engineer", sales),
  );
});

test("realistic JorMall workspace includes four people and eleven eight-hour project days", () => {
  assert.equal(people.length, 4);
  assert.equal(projects.length, 11);
  for (const project of projects) {
    const plannedHours = tasks
      .filter((task) => task.projectId === project.id)
      .reduce((total, task) => total + task.estimate, 0);
    assert.equal(plannedHours, 8, `${project.name} should have an 8-hour day`);
  }
});

test("fallback AI plan is schema-safe and includes quality and deployment", () => {
  const plan = fallbackPlan(
    "Claims Assistant",
    "Automate claims intake with a human review workflow.",
  );
  const titles = plan.phases
    .flatMap((p) => p.tasks.map((t) => t.title))
    .join(" ");
  assert.match(titles, /test/i);
  assert.match(titles, /deploy/i);
  assert.ok(
    plan.phases
      .flatMap((p) => p.tasks)
      .every((t) => t.acceptance_criteria.length >= 2),
  );
});

test("cross-person dependencies start after the prerequisite finishes", () => {
  const rows = scheduleAssignedTasks(
    [
      {
        id: "design",
        title: "Design",
        estimatedHours: 8,
        dependencies: [],
        assigneeId: "a",
      },
      {
        id: "build",
        title: "Build",
        estimatedHours: 4,
        dependencies: ["Design"],
        assigneeId: "b",
      },
    ],
    { a: 8, b: 8 },
  );
  assert.equal(rows.find((r) => r.taskId === "design")?.day, 1);
  assert.equal(rows.find((r) => r.taskId === "build")?.day, 2);
  const constrained = scheduleAssignedTasks(
    [
      {
        id: "design",
        title: "Design",
        estimatedHours: 9,
        dependencies: [],
        assigneeId: "a",
      },
      {
        id: "build",
        title: "Build",
        estimatedHours: 4,
        dependencies: ["Design"],
        assigneeId: "b",
      },
    ],
    { a: 8, b: 8 },
  );
  assert.equal(constrained.find((r) => r.taskId === "build")?.day, 3);
});

test("Arabic and English navigation labels are complete", () => {
  for (const key of Object.values(navKey)) {
    assert.ok(tr("en", key).length > 1);
    assert.ok(tr("ar", key).length > 1);
  }
  assert.equal(tr("ar", "addEmployee"), "إضافة موظف");
});

test("AI plans expand into dependency-safe daily packages of at most eight hours", () => {
  const plan = expandPlanToDailyTasks(
    fallbackPlan("Claims Assistant", "Automate claims with human review."),
  );
  const allTasks = plan.phases.flatMap((phase) => phase.tasks);
  assert.ok(allTasks.every((task) => task.estimated_hours <= 8));
  assert.ok(allTasks.some((task) => /Day 2\//.test(task.title)));
  const architectureEnd = allTasks.find((task) =>
    task.title.startsWith(
      "Design system architecture and security model — Day 3/3",
    ),
  );
  const domainStart = allTasks.find((task) =>
    task.title.startsWith("Implement domain API and persistence — Day 1/"),
  );
  assert.ok(architectureEnd);
  assert.ok(domainStart?.dependencies.includes(architectureEnd!.title));
});

test("delivery preview assigns real people, dates every task and respects eight-hour days", () => {
  const plan = expandPlanToDailyTasks(
    fallbackPlan(
      "Kia Picanto Chatbot",
      "Answer vehicle and service questions.",
    ),
  );
  const preview = buildDeliveryPreview(
    plan,
    people,
    "2027-12-31",
    new Date("2026-08-10T12:00:00Z"),
  );
  assert.ok(preview.distribution.length >= 3);
  assert.ok(preview.tasks.every((task) => task.assignee && task.finishDate));
  const totals = new Map<string, number>();
  for (const task of preview.tasks)
    for (const slot of task.schedule) {
      const key = `${task.assignee!.id}:${slot.date}`;
      totals.set(key, (totals.get(key) ?? 0) + slot.hours);
    }
  assert.ok([...totals.values()].every((hours) => hours <= 8));
  assert.equal(preview.onTime, true);
});

test("passwords are salted and verified without storing plaintext", async () => {
  const credential = await hashPassword("Nova-Test!2026");
  assert.notEqual(credential.hash, "Nova-Test!2026");
  assert.equal(
    await verifyPassword("Nova-Test!2026", credential.salt, credential.hash),
    true,
  );
  assert.equal(
    await verifyPassword("wrong-password", credential.salt, credential.hash),
    false,
  );
});
