import { sql } from "drizzle-orm";
import {
  integer,
  real,
  sqliteTable,
  text,
  uniqueIndex,
} from "drizzle-orm/sqlite-core";

export const appMeta = sqliteTable("app_meta", {
  key: text("key").primaryKey(),
  value: text("value").notNull(),
  updatedAt: text("updated_at")
    .notNull()
    .default(sql`CURRENT_TIMESTAMP`),
});

export const users = sqliteTable(
  "users",
  {
    id: text("id").primaryKey(),
    email: text("email").notNull(),
    fullName: text("full_name").notNull(),
    role: text("role").notNull(),
    position: text("position").notNull(),
    department: text("department").notNull(),
    skillsJson: text("skills_json").notNull().default("[]"),
    dailyCapacity: real("daily_capacity").notNull().default(8),
    scheduledHours: real("scheduled_hours").notNull().default(0),
    completedHours: real("completed_hours").notNull().default(0),
    accent: text("accent").notNull().default("#7566ff"),
    active: integer("active", { mode: "boolean" }).notNull().default(true),
    passwordHash: text("password_hash"),
    passwordSalt: text("password_salt"),
    mustChangePassword: integer("must_change_password", { mode: "boolean" })
      .notNull()
      .default(true),
    createdAt: text("created_at")
      .notNull()
      .default(sql`CURRENT_TIMESTAMP`),
  },
  (table) => ({ emailUnique: uniqueIndex("idx_users_email").on(table.email) }),
);

export const sessions = sqliteTable(
  "sessions",
  {
    id: text("id").primaryKey(),
    userId: text("user_id").notNull(),
    tokenHash: text("token_hash").notNull(),
    expiresAt: text("expires_at").notNull(),
    createdAt: text("created_at")
      .notNull()
      .default(sql`CURRENT_TIMESTAMP`),
    lastSeenAt: text("last_seen_at")
      .notNull()
      .default(sql`CURRENT_TIMESTAMP`),
  },
  (table) => ({
    tokenUnique: uniqueIndex("idx_sessions_token").on(table.tokenHash),
  }),
);

export const loginAttempts = sqliteTable("login_attempts", {
  email: text("email").primaryKey(),
  failures: integer("failures").notNull().default(0),
  lockedUntil: text("locked_until"),
  updatedAt: text("updated_at")
    .notNull()
    .default(sql`CURRENT_TIMESTAMP`),
});

export const projects = sqliteTable(
  "projects",
  {
    id: text("id").primaryKey(),
    code: text("code").notNull(),
    name: text("name").notNull(),
    client: text("client").notNull(),
    description: text("description").notNull(),
    priority: text("priority").notNull().default("Medium"),
    status: text("status").notNull().default("Planning"),
    progress: integer("progress").notNull().default(0),
    health: text("health").notNull().default("Healthy"),
    deadline: text("deadline").notNull(),
    predicted: text("predicted").notNull(),
    phase: text("phase").notNull(),
    teamJson: text("team_json").notNull().default("[]"),
    accent: text("accent").notNull().default("#7566ff"),
    createdBy: text("created_by"),
    createdAt: text("created_at")
      .notNull()
      .default(sql`CURRENT_TIMESTAMP`),
    archivedAt: text("archived_at"),
  },
  (table) => ({ codeUnique: uniqueIndex("idx_projects_code").on(table.code) }),
);

export const tasks = sqliteTable("tasks", {
  id: text("id").primaryKey(),
  projectId: text("project_id").notNull(),
  title: text("title").notNull(),
  description: text("description").notNull(),
  assigneeId: text("assignee_id").notNull(),
  status: text("status").notNull(),
  priority: text("priority").notNull(),
  estimate: real("estimate").notNull(),
  actual: real("actual").notNull().default(0),
  due: text("due").notNull(),
  start: text("start_time").notNull(),
  requiredSkillsJson: text("required_skills_json").notNull().default("[]"),
  dependenciesJson: text("dependencies_json").notNull().default("[]"),
  acceptanceJson: text("acceptance_json").notNull().default("[]"),
  result: text("result"),
  aiGenerated: integer("ai_generated", { mode: "boolean" })
    .notNull()
    .default(false),
  completedAt: text("completed_at"),
  createdAt: text("created_at")
    .notNull()
    .default(sql`CURRENT_TIMESTAMP`),
});

export const aiPlans = sqliteTable("ai_generated_plans", {
  id: text("id").primaryKey(),
  projectId: text("project_id").notNull(),
  status: text("status").notNull().default("draft"),
  planJson: text("plan_json").notNull(),
  model: text("model").notNull(),
  inputTokens: integer("input_tokens").notNull().default(0),
  outputTokens: integer("output_tokens").notNull().default(0),
  estimatedCost: real("estimated_cost").notNull().default(0),
  createdBy: text("created_by"),
  approvedBy: text("approved_by"),
  createdAt: text("created_at")
    .notNull()
    .default(sql`CURRENT_TIMESTAMP`),
  approvedAt: text("approved_at"),
});

export const activityLogs = sqliteTable("activity_logs", {
  id: text("id").primaryKey(),
  actorId: text("actor_id"),
  action: text("action").notNull(),
  entityType: text("entity_type").notNull(),
  entityId: text("entity_id").notNull(),
  metadataJson: text("metadata_json").notNull().default("{}"),
  createdAt: text("created_at")
    .notNull()
    .default(sql`CURRENT_TIMESTAMP`),
});

export const notifications = sqliteTable("notifications", {
  id: text("id").primaryKey(),
  userId: text("user_id").notNull(),
  title: text("title").notNull(),
  body: text("body").notNull(),
  kind: text("kind").notNull(),
  readAt: text("read_at"),
  createdAt: text("created_at")
    .notNull()
    .default(sql`CURRENT_TIMESTAMP`),
});

export const comments = sqliteTable("task_comments", {
  id: text("id").primaryKey(),
  taskId: text("task_id").notNull(),
  userId: text("user_id").notNull(),
  body: text("body").notNull(),
  createdAt: text("created_at")
    .notNull()
    .default(sql`CURRENT_TIMESTAMP`),
});

export const timeLogs = sqliteTable("task_time_logs", {
  id: text("id").primaryKey(),
  taskId: text("task_id").notNull(),
  userId: text("user_id").notNull(),
  startedAt: text("started_at").notNull(),
  pausedAt: text("paused_at"),
  endedAt: text("ended_at"),
  minutes: integer("minutes").notNull().default(0),
});

export const dailySchedules = sqliteTable("daily_schedules", {
  id: text("id").primaryKey(),
  userId: text("user_id").notNull(),
  taskId: text("task_id").notNull(),
  workDate: text("work_date").notNull(),
  startTime: text("start_time").notNull(),
  plannedHours: real("planned_hours").notNull(),
  status: text("status").notNull().default("planned"),
});
