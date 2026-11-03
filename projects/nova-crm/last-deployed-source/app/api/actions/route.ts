import { z } from "zod";
import {
  activateProjectPlan,
  addTaskComment,
  archiveProject,
  createEmployee,
  createManualTask,
  deactivateEmployee,
  getActor,
  rebalanceWorkspace,
  requireRole,
  saveProject,
  setTaskStatus,
  updateProject,
} from "../../../lib/server-store";
import { ProjectPlanSchema } from "../../../lib/engines";

const status = z.enum([
  "Backlog",
  "Ready",
  "In Progress",
  "In Review",
  "Testing",
  "Blocked",
  "Completed",
]);
const projectSchema = z.object({
  id: z.string().min(1),
  code: z.string().trim().min(2).max(24),
  name: z.string().trim().min(2).max(120),
  client: z.string().trim().min(2).max(120),
  description: z.string().trim().min(4).max(2000),
  progress: z.number().int().min(0).max(100),
  health: z.enum(["Healthy", "Watch", "At Risk", "Critical"]),
  deadline: z.string().trim().min(1).max(80),
  predicted: z.string().trim().min(1).max(80),
  phase: z.string().trim().min(1).max(120),
  team: z.array(z.string().min(1)).max(100),
  accent: z.string().regex(/^#[0-9a-f]{6}$/i),
});
const payload = z.discriminatedUnion("action", [
  z.object({
    action: z.literal("task_status"),
    taskId: z.string().min(1),
    status,
  }),
  z.object({
    action: z.literal("create_project"),
    activate: z.boolean().optional().default(false),
    plan: z.unknown().optional(),
    project: projectSchema,
  }),
  z.object({
    action: z.literal("update_project"),
    project: projectSchema,
  }),
  z.object({
    action: z.literal("archive_project"),
    projectId: z.string().min(1),
  }),
  z.object({
    action: z.literal("create_task"),
    task: z.object({
      projectId: z.string().min(1),
      title: z.string().trim().min(3).max(180),
      description: z.string().trim().min(8).max(2000),
      assigneeId: z.string().min(1),
      priority: z.enum(["Low", "Medium", "High", "Critical"]),
      estimate: z.number().min(0.5).max(8),
      due: z.string().min(4).max(80),
      requiredSkills: z.array(z.string().trim().min(1)).max(20),
      acceptance: z.array(z.string().trim().min(2)).min(1).max(20),
    }),
  }),
  z.object({
    action: z.literal("rebalance_work"),
  }),
  z.object({
    action: z.literal("add_task_comment"),
    taskId: z.string().min(1),
    body: z.string().trim().min(2).max(4000),
  }),
  z.object({
    action: z.literal("create_employee"),
    employee: z.object({
      fullName: z.string().trim().min(2).max(120),
      email: z.string().email().max(180),
      position: z.string().trim().min(2).max(100),
      department: z.string().trim().min(2).max(100),
      role: z.enum(["employee", "viewer"]),
      dailyCapacity: z.number().min(2).max(12),
      skills: z.array(z.string().trim().min(1)).max(30),
      temporaryPassword: z.string().min(10).max(128),
    }),
  }),
  z.object({
    action: z.literal("deactivate_employee"),
    userId: z.string().min(1),
    releaseTasks: z.boolean().default(false),
  }),
]);

export async function POST(request: Request) {
  try {
    const actor = await getActor();
    const body = payload.parse(await request.json());
    if (body.action === "create_project") {
      requireRole(actor, ["manager", "admin"]);
      if (body.activate && body.plan) {
        await activateProjectPlan(
          body.project,
          ProjectPlanSchema.parse(body.plan),
          actor.id,
        );
        const result = await rebalanceWorkspace(actor);
        return Response.json({ ok: true, ...result });
      } else await saveProject(body.project, actor.id);
    } else if (body.action === "update_project")
      await updateProject(body.project, actor);
    else if (body.action === "archive_project")
      await archiveProject(body.projectId, actor);
    else if (body.action === "create_task") {
      const taskId = await createManualTask(body.task, actor);
      return Response.json({ ok: true, taskId });
    } else if (body.action === "rebalance_work") {
      const result = await rebalanceWorkspace(actor);
      return Response.json({ ok: true, ...result });
    } else if (body.action === "add_task_comment")
      await addTaskComment(body.taskId, body.body, actor);
    else if (body.action === "create_employee")
      await createEmployee(body.employee, actor);
    else if (body.action === "deactivate_employee") {
      const releasedTasks = await deactivateEmployee(
        body.userId,
        body.releaseTasks,
        actor,
      );
      return Response.json({ ok: true, releasedTasks });
    } else {
      requireRole(actor, ["manager", "admin", "employee"]);
      await setTaskStatus(body.taskId, body.status, actor);
    }
    return Response.json({ ok: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Invalid request";
    const forbidden = message === "FORBIDDEN";
    const unauthenticated = message === "UNAUTHENTICATED";
    const notFound = [
      "PROJECT_NOT_FOUND",
      "USER_NOT_FOUND",
      "TASK_NOT_FOUND",
    ].includes(message);
    const conflict =
      message.startsWith("ACTIVE_TASKS:") ||
      [
        "EMAIL_EXISTS",
        "INACTIVE_EMAIL_EXISTS",
        "CANNOT_DEACTIVATE_SELF",
      ].includes(message);
    const friendly = message.startsWith("ACTIVE_TASKS:")
      ? `This employee still owns ${message.split(":")[1]} active tasks.`
      : message === "EMAIL_EXISTS"
        ? "An active employee already uses this email."
        : message === "INACTIVE_EMAIL_EXISTS"
          ? "This email belongs to an inactive employee. Reactivate that profile instead."
          : message === "CANNOT_DEACTIVATE_SELF"
            ? "You cannot deactivate your own profile."
            : message === "PROJECT_NOT_FOUND"
              ? "This project no longer exists or has already been archived."
              : message === "USER_NOT_FOUND"
                ? "This employee profile no longer exists."
                : message === "TASK_NOT_FOUND"
                  ? "This task no longer exists."
                  : unauthenticated
                    ? "Please sign in to continue."
                    : forbidden
                      ? "You do not have permission for this action."
                      : "The requested change could not be saved.";
    return Response.json(
      {
        error: {
          code: unauthenticated
            ? "UNAUTHENTICATED"
            : forbidden
              ? "FORBIDDEN"
              : conflict
                ? message.split(":")[0]
                : notFound
                  ? "NOT_FOUND"
                  : "ACTION_FAILED",
          message: friendly,
        },
      },
      {
        status: unauthenticated
          ? 401
          : forbidden
            ? 403
            : notFound
              ? 404
              : conflict
                ? 409
                : 400,
      },
    );
  }
}
