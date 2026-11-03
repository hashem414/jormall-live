/* eslint-disable @typescript-eslint/no-explicit-any */
import { env } from "cloudflare:workers";
import { headers } from "next/headers";
import {
  activity,
  people,
  projects,
  tasks,
  type Project,
  type Task,
} from "./domain";
import {
  assignTasks,
  expandPlanToDailyTasks,
  ProjectPlanSchema,
  scheduleAssignedTasks,
  scoreCandidate,
  type ProjectPlan,
} from "./engines";
import {
  createSessionToken,
  hashPassword,
  hashSessionToken,
  verifyPassword,
} from "./auth";

const SESSION_COOKIE = "nova_session";
const SESSION_DAYS = 7;
const managerSettings = () => {
  const runtime = env as unknown as {
    NOVA_MANAGER_EMAIL?: string;
    NOVA_MANAGER_NAME?: string;
    NOVA_MANAGER_PASSWORD?: string;
  };
  return {
    email:
      runtime.NOVA_MANAGER_EMAIL?.trim().toLowerCase() || "manager@nova.local",
    name: runtime.NOVA_MANAGER_NAME?.trim() || "Mohammad — AI Manager",
    password: runtime.NOVA_MANAGER_PASSWORD?.trim() || "Nova-Local-Manager!26",
  };
};

const statements = [
  `CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)`,
  `CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, full_name TEXT NOT NULL, role TEXT NOT NULL, position TEXT NOT NULL, department TEXT NOT NULL, skills_json TEXT NOT NULL DEFAULT '[]', daily_capacity REAL NOT NULL DEFAULT 8, scheduled_hours REAL NOT NULL DEFAULT 0, completed_hours REAL NOT NULL DEFAULT 0, accent TEXT NOT NULL DEFAULT '#7566ff', active INTEGER NOT NULL DEFAULT 1, password_hash TEXT, password_salt TEXT, must_change_password INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)`,
  `CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE, expires_at TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)`,
  `CREATE TABLE IF NOT EXISTS login_attempts (email TEXT PRIMARY KEY, failures INTEGER NOT NULL DEFAULT 0, locked_until TEXT, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)`,
  `CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL, client TEXT NOT NULL, description TEXT NOT NULL, priority TEXT NOT NULL DEFAULT 'Medium', status TEXT NOT NULL DEFAULT 'Planning', progress INTEGER NOT NULL DEFAULT 0, health TEXT NOT NULL DEFAULT 'Healthy', deadline TEXT NOT NULL, predicted TEXT NOT NULL, phase TEXT NOT NULL, team_json TEXT NOT NULL DEFAULT '[]', accent TEXT NOT NULL DEFAULT '#7566ff', created_by TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, archived_at TEXT)`,
  `CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL, assignee_id TEXT NOT NULL, status TEXT NOT NULL, priority TEXT NOT NULL, estimate REAL NOT NULL, actual REAL NOT NULL DEFAULT 0, due TEXT NOT NULL, start_time TEXT NOT NULL, required_skills_json TEXT NOT NULL DEFAULT '[]', dependencies_json TEXT NOT NULL DEFAULT '[]', acceptance_json TEXT NOT NULL DEFAULT '[]', result TEXT, ai_generated INTEGER NOT NULL DEFAULT 0, completed_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)`,
  `CREATE TABLE IF NOT EXISTS ai_generated_plans (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft', plan_json TEXT NOT NULL, model TEXT NOT NULL, input_tokens INTEGER NOT NULL DEFAULT 0, output_tokens INTEGER NOT NULL DEFAULT 0, estimated_cost REAL NOT NULL DEFAULT 0, created_by TEXT, approved_by TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, approved_at TEXT)`,
  `CREATE TABLE IF NOT EXISTS activity_logs (id TEXT PRIMARY KEY, actor_id TEXT, action TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)`,
  `CREATE TABLE IF NOT EXISTS notifications (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL, kind TEXT NOT NULL, read_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)`,
  `CREATE TABLE IF NOT EXISTS task_comments (id TEXT PRIMARY KEY, task_id TEXT NOT NULL, user_id TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)`,
  `CREATE TABLE IF NOT EXISTS task_time_logs (id TEXT PRIMARY KEY, task_id TEXT NOT NULL, user_id TEXT NOT NULL, started_at TEXT NOT NULL, paused_at TEXT, ended_at TEXT, minutes INTEGER NOT NULL DEFAULT 0)`,
  `CREATE TABLE IF NOT EXISTS daily_schedules (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, task_id TEXT NOT NULL, work_date TEXT NOT NULL, start_time TEXT NOT NULL, planned_hours REAL NOT NULL, status TEXT NOT NULL DEFAULT 'planned')`,
  `CREATE INDEX IF NOT EXISTS idx_tasks_project_status ON tasks(project_id, status)`,
  `CREATE INDEX IF NOT EXISTS idx_tasks_assignee_status ON tasks(assignee_id, status)`,
  `CREATE INDEX IF NOT EXISTS idx_activity_entity ON activity_logs(entity_type, entity_id)`,
  `CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id, expires_at)`,
];

function db() {
  if (!env.DB) throw new Error("D1 binding DB is unavailable");
  return env.DB;
}
const uid = () => crypto.randomUUID();

const WORKSPACE_SEED = "jormall-realistic-v1";
const memberEmails: Record<string, string> = {
  u2: "christine@jormall.com",
  u3: "ahmad@jormall.com",
  u4: "mohammad.ai@jormall.com",
};

async function seedRealisticWorkspace(
  d1: ReturnType<typeof db>,
  manager: ReturnType<typeof managerSettings>,
) {
  const existingManager = await d1
    .prepare("SELECT password_hash,password_salt FROM users WHERE id='u1'")
    .first<{ password_hash: string | null; password_salt: string | null }>();
  const writes = [
    d1.prepare("DELETE FROM daily_schedules"),
    d1.prepare("DELETE FROM task_time_logs"),
    d1.prepare("DELETE FROM task_comments"),
    d1.prepare("DELETE FROM notifications"),
    d1.prepare("DELETE FROM ai_generated_plans"),
    d1.prepare("DELETE FROM activity_logs"),
    d1.prepare("DELETE FROM tasks"),
    d1.prepare("DELETE FROM projects"),
    d1.prepare("DELETE FROM sessions"),
    d1.prepare("DELETE FROM login_attempts"),
    d1.prepare("DELETE FROM users"),
  ];
  for (const person of people)
    writes.push(
      d1
        .prepare(
          "INSERT INTO users (id,email,full_name,role,position,department,skills_json,daily_capacity,scheduled_hours,completed_hours,accent,password_hash,password_salt,must_change_password) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        )
        .bind(
          person.id,
          person.id === "u1"
            ? manager.email
            : (memberEmails[person.id] ?? `${person.id}@jormall.com`),
          person.id === "u1" ? manager.name : person.name,
          person.id === "u1" ? "manager" : "employee",
          person.position,
          person.department,
          JSON.stringify(person.skills),
          person.capacity,
          person.scheduled,
          person.completed,
          person.accent,
          person.id === "u1" ? (existingManager?.password_hash ?? null) : null,
          person.id === "u1" ? (existingManager?.password_salt ?? null) : null,
          person.id === "u1" && existingManager?.password_hash ? 0 : 1,
        ),
    );
  for (const project of projects)
    writes.push(
      d1
        .prepare(
          "INSERT INTO projects (id,code,name,client,description,progress,health,deadline,predicted,phase,team_json,accent,status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        )
        .bind(
          project.id,
          project.code,
          project.name,
          project.client,
          project.description,
          project.progress,
          project.health,
          project.deadline,
          project.predicted,
          project.phase,
          JSON.stringify(project.team),
          project.accent,
          "Active",
        ),
    );
  for (const task of tasks)
    writes.push(
      d1
        .prepare(
          "INSERT INTO tasks (id,project_id,title,description,assignee_id,status,priority,estimate,actual,due,start_time,required_skills_json,dependencies_json,acceptance_json,result,ai_generated,completed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        )
        .bind(
          task.id,
          task.projectId,
          task.title,
          task.description,
          task.assigneeId,
          task.status,
          task.priority,
          task.estimate,
          task.actual,
          task.due,
          task.start,
          JSON.stringify(task.requiredSkills),
          JSON.stringify(task.dependencies),
          JSON.stringify(task.acceptance),
          task.result ?? null,
          task.aiGenerated ? 1 : 0,
          task.status === "Completed" ? new Date().toISOString() : null,
        ),
    );
  for (const entry of activity)
    writes.push(
      d1
        .prepare(
          "INSERT INTO activity_logs (id,actor_id,action,entity_type,entity_id,metadata_json) VALUES (?,?,?,?,?,?)",
        )
        .bind(
          uid(),
          null,
          entry.text,
          "project",
          entry.project,
          JSON.stringify(entry),
        ),
    );
  writes.push(
    d1
      .prepare(
        "INSERT INTO app_meta (key,value,updated_at) VALUES ('workspace_seed',?,CURRENT_TIMESTAMP) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP",
      )
      .bind(WORKSPACE_SEED),
  );
  await d1.batch(writes);
  await d1.prepare("PRAGMA optimize").run();
}

export async function ensureSeeded() {
  const d1 = db();
  const manager = managerSettings();
  await d1.batch(statements.map((s) => d1.prepare(s)));
  const columns = await d1
    .prepare("PRAGMA table_info(users)")
    .all<{ name: string }>();
  const names = new Set(columns.results.map((column) => column.name));
  const migrations = [];
  if (!names.has("password_hash"))
    migrations.push(
      d1.prepare("ALTER TABLE users ADD COLUMN password_hash TEXT"),
    );
  if (!names.has("password_salt"))
    migrations.push(
      d1.prepare("ALTER TABLE users ADD COLUMN password_salt TEXT"),
    );
  if (!names.has("must_change_password"))
    migrations.push(
      d1.prepare(
        "ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 1",
      ),
    );
  if (migrations.length) await d1.batch(migrations);
  const seed = await d1
    .prepare("SELECT value FROM app_meta WHERE key='workspace_seed'")
    .first<{ value: string }>();
  if (seed?.value !== WORKSPACE_SEED) await seedRealisticWorkspace(d1, manager);
  const user = await d1
    .prepare("SELECT password_hash FROM users WHERE id='u1'")
    .first<{ password_hash: string | null }>();
  if (user && !user.password_hash) {
    const credential = await hashPassword(manager.password);
    await d1
      .prepare(
        "UPDATE users SET email=?,full_name=?,position='AI Division Manager',password_hash=?,password_salt=?,must_change_password=0 WHERE id='u1'",
      )
      .bind(manager.email, manager.name, credential.hash, credential.salt)
      .run();
  }
}

export type Actor = {
  id: string;
  email: string;
  role: string;
  fullName: string;
  position: string;
};

function cookieValue(cookieHeader: string | null, name: string) {
  return cookieHeader
    ?.split(";")
    .map((part) => part.trim().split("="))
    .find(([key]) => key === name)?.[1];
}

export async function getOptionalActor(): Promise<Actor | null> {
  await ensureSeeded();
  const h = await headers();
  const token = cookieValue(h.get("cookie"), SESSION_COOKIE);
  if (!token) return null;
  const tokenHash = await hashSessionToken(decodeURIComponent(token));
  const found = await db()
    .prepare(
      `SELECT u.id,u.email,u.role,u.full_name,u.position
       FROM sessions s JOIN users u ON u.id=s.user_id
       WHERE s.token_hash=? AND s.expires_at>CURRENT_TIMESTAMP AND u.active=1`,
    )
    .bind(tokenHash)
    .first<any>();
  if (!found) return null;
  await db()
    .prepare(
      "UPDATE sessions SET last_seen_at=CURRENT_TIMESTAMP WHERE token_hash=?",
    )
    .bind(tokenHash)
    .run();
  return {
    id: found.id,
    email: found.email,
    role: found.role,
    fullName: found.full_name,
    position: found.position,
  };
}

export async function getActor() {
  const actor = await getOptionalActor();
  if (!actor) throw new Error("UNAUTHENTICATED");
  return actor;
}

export async function login(emailInput: string, password: string) {
  await ensureSeeded();
  const email = emailInput.trim().toLowerCase();
  const attempt = await db()
    .prepare("SELECT failures,locked_until FROM login_attempts WHERE email=?")
    .bind(email)
    .first<{ failures: number; locked_until: string | null }>();
  if (attempt?.locked_until && new Date(attempt.locked_until) > new Date())
    throw new Error("LOGIN_LOCKED");
  const user = await db()
    .prepare(
      "SELECT id,email,role,full_name,position,password_hash,password_salt FROM users WHERE lower(email)=? AND active=1",
    )
    .bind(email)
    .first<any>();
  const valid = Boolean(
    user?.password_hash &&
    user?.password_salt &&
    (await verifyPassword(password, user.password_salt, user.password_hash)),
  );
  if (!valid) {
    const failures = Number(attempt?.failures ?? 0) + 1;
    const lockedUntil =
      failures >= 5
        ? new Date(Date.now() + 15 * 60 * 1000).toISOString()
        : null;
    await db()
      .prepare(
        `INSERT INTO login_attempts (email,failures,locked_until,updated_at)
         VALUES (?,?,?,CURRENT_TIMESTAMP)
         ON CONFLICT(email) DO UPDATE SET failures=excluded.failures,locked_until=excluded.locked_until,updated_at=CURRENT_TIMESTAMP`,
      )
      .bind(email, failures, lockedUntil)
      .run();
    throw new Error("INVALID_LOGIN");
  }
  await db()
    .prepare("DELETE FROM login_attempts WHERE email=?")
    .bind(email)
    .run();
  const token = createSessionToken();
  const expiresAt = new Date(Date.now() + SESSION_DAYS * 86400_000);
  await db()
    .prepare(
      "INSERT INTO sessions (id,user_id,token_hash,expires_at) VALUES (?,?,?,?)",
    )
    .bind(
      uid(),
      user.id,
      await hashSessionToken(token),
      expiresAt.toISOString(),
    )
    .run();
  return {
    token,
    expiresAt,
    actor: {
      id: user.id,
      email: user.email,
      role: user.role,
      fullName: user.full_name,
      position: user.position,
    } as Actor,
  };
}

export async function logout(token: string | undefined) {
  if (!token) return;
  await ensureSeeded();
  await db()
    .prepare("DELETE FROM sessions WHERE token_hash=?")
    .bind(await hashSessionToken(token))
    .run();
}

export function sessionCookie(token: string, expiresAt: Date, secure: boolean) {
  return `${SESSION_COOKIE}=${encodeURIComponent(token)}; Path=/; HttpOnly; SameSite=Lax; Expires=${expiresAt.toUTCString()}${secure ? "; Secure" : ""}`;
}

export function clearSessionCookie(secure: boolean) {
  return `${SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0${secure ? "; Secure" : ""}`;
}

export function requireRole(actor: { role: string }, allowed: string[]) {
  if (!allowed.includes(actor.role)) throw new Error("FORBIDDEN");
}

const parse = (value: unknown, fallback: any = []) => {
  try {
    return JSON.parse(String(value ?? ""));
  } catch {
    return fallback;
  }
};
export async function getBootstrap(actor: Actor) {
  await ensureSeeded();
  const d1 = db();
  const [u, p, t, a, s] = await Promise.all([
    d1.prepare("SELECT * FROM users WHERE active=1 ORDER BY full_name").all(),
    d1
      .prepare(
        "SELECT * FROM projects WHERE archived_at IS NULL ORDER BY created_at DESC",
      )
      .all(),
    d1
      .prepare(
        `SELECT t.* FROM tasks t
         JOIN projects p ON p.id=t.project_id
         WHERE p.archived_at IS NULL
         ORDER BY t.created_at`,
      )
      .all(),
    d1
      .prepare(
        "SELECT metadata_json FROM activity_logs ORDER BY created_at DESC LIMIT 12",
      )
      .all(),
    d1
      .prepare(
        `SELECT s.id,s.user_id,s.task_id,s.work_date,s.start_time,s.planned_hours,s.status,t.assignee_id
         FROM daily_schedules s
         JOIN tasks t ON t.id=s.task_id
         JOIN projects p ON p.id=t.project_id
         WHERE p.archived_at IS NULL AND t.status!='Completed'
         ORDER BY s.work_date,s.start_time`,
      )
      .all(),
  ]);
  const allPeople = u.results.map((x: any) => ({
    id: x.id,
    name: x.full_name,
    initials: x.full_name
      .split(" ")
      .map((w: string) => w[0])
      .join("")
      .slice(0, 2),
    email: x.email,
    role: x.role,
    active: Boolean(x.active),
    position: x.position,
    department: x.department,
    skills: parse(x.skills_json),
    capacity: x.daily_capacity,
    scheduled: x.scheduled_hours,
    completed: x.completed_hours,
    accent: x.accent,
  }));
  const allProjects = p.results.map((x: any) => ({
    id: x.id,
    code: x.code,
    name: x.name,
    client: x.client,
    description: x.description,
    progress: x.progress,
    health: x.health,
    deadline: x.deadline,
    predicted: x.predicted,
    phase: x.phase,
    team: parse(x.team_json),
    accent: x.accent,
  }));
  const allTasks = t.results.map((x: any) => ({
    id: x.id,
    projectId: x.project_id,
    title: x.title,
    description: x.description,
    assigneeId: x.assignee_id,
    status: x.status,
    priority: x.priority,
    estimate: x.estimate,
    actual: x.actual,
    due: x.due,
    start: x.start_time,
    requiredSkills: parse(x.required_skills_json),
    dependencies: parse(x.dependencies_json),
    acceptance: parse(x.acceptance_json),
    result: x.result,
    aiGenerated: Boolean(x.ai_generated),
  }));
  const unrestricted = ["manager", "admin", "viewer", "executive"].includes(
    actor.role,
  );
  const visibleTasks = unrestricted
    ? allTasks
    : allTasks.filter((task: any) => task.assigneeId === actor.id);
  const visibleProjectIds = new Set(
    allProjects
      .filter(
        (project: any) =>
          unrestricted ||
          project.team.includes(actor.id) ||
          visibleTasks.some((task: any) => task.projectId === project.id),
      )
      .map((project: any) => project.id),
  );
  const visibleProjects = allProjects.filter((project: any) =>
    visibleProjectIds.has(project.id),
  );
  const teammateIds = new Set(
    visibleProjects.flatMap((project: any) => project.team as string[]),
  );
  return {
    currentUser: {
      id: actor.id,
      name: actor.fullName,
      email: actor.email,
      role: actor.role,
      position: actor.position,
    },
    people: unrestricted
      ? allPeople
      : allPeople.filter(
          (person: any) => person.id === actor.id || teammateIds.has(person.id),
        ),
    projects: visibleProjects,
    tasks: visibleTasks,
    schedules: s.results
      .filter(
        (row: any) =>
          unrestricted ||
          (row.user_id === actor.id && row.assignee_id === actor.id),
      )
      .map((row: any) => ({
        id: row.id,
        userId: row.user_id,
        taskId: row.task_id,
        workDate: row.work_date,
        startTime: row.start_time,
        plannedHours: row.planned_hours,
        status: row.status,
      })),
    activity: a.results.map((x: any) => parse(x.metadata_json, {})),
  };
}

export async function saveProject(project: Project, actorId: string) {
  const projectCode = await nextAvailableProjectCode(project.code);
  await db()
    .prepare(
      "INSERT INTO projects (id,code,name,client,description,progress,health,deadline,predicted,phase,team_json,accent,created_by,status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
    )
    .bind(
      project.id,
      projectCode,
      project.name,
      project.client,
      project.description,
      project.progress,
      project.health,
      project.deadline,
      project.predicted,
      project.phase,
      JSON.stringify(project.team),
      project.accent,
      actorId,
      "Planning",
    )
    .run();
  await audit(actorId, "project.created", "project", project.id, {
    name: project.name,
    code: projectCode,
  });
}

async function nextAvailableProjectCode(requestedCode: string) {
  const base = requestedCode.trim().slice(0, 24);
  const numbered = base.match(/^(.*?)-(\d+)$/);
  for (let attempt = 0; attempt < 1000; attempt++) {
    const suffix = numbered
      ? `-${String(Number(numbered[2]) + attempt).padStart(numbered[2].length, "0")}`
      : attempt === 0
        ? ""
        : `-${String(attempt + 1).padStart(2, "0")}`;
    const prefix = numbered ? numbered[1] : base;
    const candidate = `${prefix.slice(0, Math.max(1, 24 - suffix.length))}${suffix}`;
    const existing = await db()
      .prepare("SELECT id FROM projects WHERE code=? LIMIT 1")
      .bind(candidate)
      .first<{ id: string }>();
    if (!existing) return candidate;
  }
  throw new Error("PROJECT_CODE_EXHAUSTED");
}

export async function updateProject(project: Project, actor: Actor) {
  requireRole(actor, ["manager", "admin"]);
  const current = await db()
    .prepare("SELECT id FROM projects WHERE id=? AND archived_at IS NULL")
    .bind(project.id)
    .first<{ id: string }>();
  if (!current) throw new Error("PROJECT_NOT_FOUND");
  await db()
    .prepare(
      `UPDATE projects
       SET code=?,name=?,client=?,description=?,progress=?,health=?,deadline=?,predicted=?,phase=?,team_json=?,accent=?
       WHERE id=? AND archived_at IS NULL`,
    )
    .bind(
      project.code,
      project.name,
      project.client,
      project.description,
      project.progress,
      project.health,
      project.deadline,
      project.predicted,
      project.phase,
      JSON.stringify(project.team),
      project.accent,
      project.id,
    )
    .run();
  await audit(actor.id, "project.updated", "project", project.id, {
    name: project.name,
    health: project.health,
    progress: project.progress,
    team: project.team,
  });
}

export async function archiveProject(projectId: string, actor: Actor) {
  requireRole(actor, ["manager", "admin"]);
  const project = await db()
    .prepare("SELECT id,name FROM projects WHERE id=? AND archived_at IS NULL")
    .bind(projectId)
    .first<{ id: string; name: string }>();
  if (!project) throw new Error("PROJECT_NOT_FOUND");
  const d1 = db();
  await d1.batch([
    d1
      .prepare(
        "DELETE FROM daily_schedules WHERE task_id IN (SELECT id FROM tasks WHERE project_id=?)",
      )
      .bind(projectId),
    d1
      .prepare(
        "UPDATE projects SET status='Archived',archived_at=CURRENT_TIMESTAMP WHERE id=?",
      )
      .bind(projectId),
  ]);
  await audit(actor.id, "project.archived", "project", projectId, {
    name: project.name,
  });
}

function inferredPosition(skills: string[]) {
  const has = (...values: string[]) =>
    values.some((value) => skills.includes(value));
  if (has("AI Strategy", "Product Delivery", "Architecture"))
    return "AI Division Manager";
  if (has("Client Discovery", "Solution Design", "AI Demos"))
    return "Technical Sales & AI Solutions";
  if (has("Docker", "Nginx", "FastAPI", "PostgreSQL", "CI/CD"))
    return "AI & Backend Engineer";
  if (has("React", "Next.js", "TypeScript")) return "AI Full-Stack Engineer";
  return "AI Engineer";
}

export async function rebalanceWorkspace(actor: Actor) {
  requireRole(actor, ["manager", "admin"]);
  const d1 = db();
  const [userRows, taskRows] = await Promise.all([
    d1
      .prepare(
        "SELECT * FROM users WHERE active=1 AND role IN ('manager','employee') ORDER BY created_at",
      )
      .all<any>(),
    d1
      .prepare(
        `SELECT t.* FROM tasks t JOIN projects p ON p.id=t.project_id
         WHERE p.archived_at IS NULL AND t.status!='Completed'
         ORDER BY t.created_at`,
      )
      .all<any>(),
  ]);
  const activePeople = userRows.results.map((row: any) => ({
    id: row.id,
    name: row.full_name,
    initials: row.full_name
      .split(" ")
      .map((word: string) => word[0])
      .join("")
      .slice(0, 2),
    email: row.email,
    role: row.role,
    active: true,
    position: row.position,
    department: row.department,
    skills: parse(row.skills_json),
    capacity: Math.min(8, Number(row.daily_capacity)),
    scheduled: 0,
    completed: Number(row.completed_hours),
    accent: row.accent,
  }));
  const statusOrder: Record<string, number> = {
    "In Progress": 0,
    Testing: 1,
    "In Review": 2,
    Ready: 3,
    Blocked: 4,
    Backlog: 5,
  };
  const priorityOrder: Record<string, number> = {
    Critical: 0,
    High: 1,
    Medium: 2,
    Low: 3,
  };
  const orderedTasks = [...taskRows.results].sort(
    (left: any, right: any) =>
      (statusOrder[left.status] ?? 9) - (statusOrder[right.status] ?? 9) ||
      (priorityOrder[left.priority] ?? 9) -
        (priorityOrder[right.priority] ?? 9) ||
      String(left.created_at).localeCompare(String(right.created_at)),
  );
  const projected = new Map(activePeople.map((person) => [person.id, 0]));
  for (const task of orderedTasks) {
    const movable =
      Boolean(task.ai_generated) && ["Backlog", "Ready"].includes(task.status);
    if (!movable && projected.has(task.assignee_id))
      projected.set(
        task.assignee_id,
        (projected.get(task.assignee_id) ?? 0) + Number(task.estimate),
      );
  }
  const assignments = new Map<string, string>();
  for (const task of orderedTasks) {
    const skills = parse(task.required_skills_json) as string[];
    const movable =
      Boolean(task.ai_generated) && ["Backlog", "Ready"].includes(task.status);
    let assigneeId = task.assignee_id;
    if (movable) {
      const ranked = activePeople
        .map((person) => ({
          id: person.id,
          score:
            scoreCandidate(skills, inferredPosition(skills), person) -
            ((projected.get(person.id) ?? 0) / Math.max(1, person.capacity)) *
              2.4,
        }))
        .sort((a, b) => b.score - a.score);
      assigneeId = ranked[0]?.id ?? assigneeId;
    }
    if (!activePeople.some((person) => person.id === assigneeId))
      assigneeId = activePeople[0]?.id ?? "";
    assignments.set(task.id, assigneeId);
    if (movable)
      projected.set(
        assigneeId,
        (projected.get(assigneeId) ?? 0) + Number(task.estimate),
      );
  }
  const scheduledItems = orderedTasks.map((task: any) => ({
    id: task.id,
    title: task.id,
    estimatedHours: Number(task.estimate),
    dependencies: (parse(task.dependencies_json) as string[]).filter((id) =>
      taskRows.results.some((candidate: any) => candidate.id === id),
    ),
    assigneeId: assignments.get(task.id)!,
  }));
  const capacities = Object.fromEntries(
    activePeople.map((person) => [person.id, person.capacity]),
  );
  const schedule = scheduleAssignedTasks(scheduledItems, capacities);
  const used = new Map<string, number>();
  const scheduleWithTimes = schedule.map((row) => {
    const key = `${row.assigneeId}:${row.day}`;
    const prior = used.get(key) ?? 0;
    used.set(key, prior + row.hours);
    const minutes = 9 * 60 + Math.round(prior * 60);
    return {
      ...row,
      date: workDate(row.day),
      startTime: `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`,
    };
  });
  const finishDate = new Map<string, string>();
  const firstStart = new Map<string, string>();
  for (const row of scheduleWithTimes) {
    finishDate.set(row.taskId, row.date);
    if (!firstStart.has(row.taskId)) firstStart.set(row.taskId, row.startTime);
  }
  await d1
    .prepare(
      `DELETE FROM daily_schedules WHERE task_id IN (
         SELECT t.id FROM tasks t JOIN projects p ON p.id=t.project_id
         WHERE p.archived_at IS NULL
       )`,
    )
    .run();
  const writes = [];
  for (const task of orderedTasks)
    writes.push(
      d1
        .prepare("UPDATE tasks SET assignee_id=?,due=?,start_time=? WHERE id=?")
        .bind(
          assignments.get(task.id),
          finishDate.get(task.id) ?? task.due,
          firstStart.get(task.id) ?? "09:00",
          task.id,
        ),
    );
  for (const row of scheduleWithTimes)
    writes.push(
      d1
        .prepare(
          "INSERT INTO daily_schedules (id,user_id,task_id,work_date,start_time,planned_hours,status) VALUES (?,?,?,?,?,?,?)",
        )
        .bind(
          uid(),
          row.assigneeId,
          row.taskId,
          row.date,
          row.startTime,
          row.hours,
          "planned",
        ),
    );
  for (const person of activePeople)
    writes.push(
      d1.prepare("UPDATE users SET scheduled_hours=? WHERE id=?").bind(
        scheduleWithTimes
          .filter((row) => row.assigneeId === person.id && row.day === 1)
          .reduce((total, row) => total + row.hours, 0),
        person.id,
      ),
    );
  for (let index = 0; index < writes.length; index += 70)
    await d1.batch(writes.slice(index, index + 70));
  const projectIds = [
    ...new Set(orderedTasks.map((task: any) => task.project_id as string)),
  ];
  for (const projectId of projectIds) {
    const taskIds = orderedTasks
      .filter((task: any) => task.project_id === projectId)
      .map((task: any) => task.id);
    const predicted = taskIds
      .map((id) => finishDate.get(id))
      .filter(Boolean)
      .sort()
      .at(-1);
    const team = [
      ...new Set(taskIds.map((id) => assignments.get(id)).filter(Boolean)),
    ];
    if (predicted)
      await d1
        .prepare("UPDATE projects SET predicted=?,team_json=? WHERE id=?")
        .bind(predicted, JSON.stringify(team), projectId)
        .run();
  }
  await audit(actor.id, "workspace.rebalanced", "workspace", "active", {
    taskCount: orderedTasks.length,
    scheduleRows: scheduleWithTimes.length,
    forecastDate: scheduleWithTimes
      .map((row) => row.date)
      .sort()
      .at(-1),
  });
  return {
    taskCount: orderedTasks.length,
    scheduleRows: scheduleWithTimes.length,
    forecastDate: scheduleWithTimes
      .map((row) => row.date)
      .sort()
      .at(-1),
    distribution: activePeople.map((person) => ({
      id: person.id,
      name: person.name,
      hours: orderedTasks
        .filter((task: any) => assignments.get(task.id) === person.id)
        .reduce((total: number, task: any) => total + Number(task.estimate), 0),
      tasks: orderedTasks.filter(
        (task: any) => assignments.get(task.id) === person.id,
      ).length,
    })),
  };
}

export type NewManualTask = {
  projectId: string;
  title: string;
  description: string;
  assigneeId: string;
  priority: Task["priority"];
  estimate: number;
  due: string;
  requiredSkills: string[];
  acceptance: string[];
};

export async function createManualTask(input: NewManualTask, actor: Actor) {
  requireRole(actor, ["manager", "admin"]);
  const [project, assignee] = await Promise.all([
    db()
      .prepare("SELECT id FROM projects WHERE id=? AND archived_at IS NULL")
      .bind(input.projectId)
      .first<{ id: string }>(),
    db()
      .prepare("SELECT id FROM users WHERE id=? AND active=1")
      .bind(input.assigneeId)
      .first<{ id: string }>(),
  ]);
  if (!project) throw new Error("PROJECT_NOT_FOUND");
  if (!assignee) throw new Error("USER_NOT_FOUND");
  const id = uid();
  await db()
    .prepare(
      "INSERT INTO tasks (id,project_id,title,description,assignee_id,status,priority,estimate,actual,due,start_time,required_skills_json,dependencies_json,acceptance_json,result,ai_generated) VALUES (?,?,?,?,?,'Ready',?,?,0,?,'09:00',?,'[]',?,NULL,0)",
    )
    .bind(
      id,
      input.projectId,
      input.title,
      input.description,
      input.assigneeId,
      input.priority,
      input.estimate,
      input.due,
      JSON.stringify(input.requiredSkills),
      JSON.stringify(input.acceptance),
    )
    .run();
  await audit(actor.id, "task.created", "task", id, {
    title: input.title,
    projectId: input.projectId,
    assigneeId: input.assigneeId,
    estimate: input.estimate,
    due: input.due,
  });
  return id;
}

export type NewEmployee = {
  fullName: string;
  email: string;
  position: string;
  department: string;
  role: "employee" | "viewer";
  dailyCapacity: number;
  skills: string[];
  temporaryPassword: string;
};
export async function createEmployee(
  input: NewEmployee,
  actor: { id: string; role: string },
) {
  requireRole(actor, ["manager", "admin"]);
  if (actor.role !== "admin" && !["employee", "viewer"].includes(input.role))
    throw new Error("FORBIDDEN");
  const existing = await db()
    .prepare("SELECT id,active FROM users WHERE lower(email)=lower(?)")
    .bind(input.email)
    .first<{ id: string; active: number }>();
  if (existing)
    throw new Error(existing.active ? "EMAIL_EXISTS" : "INACTIVE_EMAIL_EXISTS");
  const accents = [
    "#7c6cff",
    "#21c7a8",
    "#56a8ff",
    "#f7a84a",
    "#e46c9b",
    "#33b6c5",
  ];
  const id = uid();
  const accent = accents[Math.floor(Math.random() * accents.length)];
  const credential = await hashPassword(input.temporaryPassword);
  await db()
    .prepare(
      "INSERT INTO users (id,email,full_name,role,position,department,skills_json,daily_capacity,scheduled_hours,completed_hours,accent,active,password_hash,password_salt,must_change_password) VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?,?,1)",
    )
    .bind(
      id,
      input.email.toLowerCase(),
      input.fullName,
      input.role,
      input.position,
      input.department,
      JSON.stringify(input.skills),
      input.dailyCapacity,
      0,
      0,
      accent,
      credential.hash,
      credential.salt,
    )
    .run();
  await audit(actor.id, "user.created", "user", id, {
    email: input.email,
    position: input.position,
    role: input.role,
    dailyCapacity: input.dailyCapacity,
  });
  return id;
}

export async function deactivateEmployee(
  userId: string,
  releaseTasks: boolean,
  actor: { id: string; role: string },
) {
  requireRole(actor, ["manager", "admin"]);
  if (userId === actor.id) throw new Error("CANNOT_DEACTIVATE_SELF");
  const target = await db()
    .prepare("SELECT id,role,active FROM users WHERE id=?")
    .bind(userId)
    .first<{ id: string; role: string; active: number }>();
  if (!target) throw new Error("USER_NOT_FOUND");
  if (target.role === "admin" && actor.role !== "admin")
    throw new Error("FORBIDDEN");
  const activeTasks = await db()
    .prepare(
      "SELECT COUNT(*) AS count FROM tasks WHERE assignee_id=? AND status NOT IN ('Completed','Cancelled')",
    )
    .bind(userId)
    .first<{ count: number }>();
  const count = Number(activeTasks?.count ?? 0);
  if (count > 0 && !releaseTasks) throw new Error(`ACTIVE_TASKS:${count}`);
  const d1 = db();
  const writes = [
    d1.prepare("UPDATE users SET active=0 WHERE id=?").bind(userId),
  ];
  if (count > 0)
    writes.push(
      d1
        .prepare(
          "UPDATE tasks SET assignee_id='', status='Backlog' WHERE assignee_id=? AND status NOT IN ('Completed','Cancelled')",
        )
        .bind(userId),
    );
  await d1.batch(writes);
  await audit(actor.id, "user.deactivated", "user", userId, {
    releasedTasks: count,
  });
  return count;
}

function workDate(day: number) {
  const date = new Date();
  date.setHours(12, 0, 0, 0);
  while (date.getDay() === 0 || date.getDay() === 6)
    date.setDate(date.getDate() + 1);
  let added = 1;
  while (added < day) {
    date.setDate(date.getDate() + 1);
    if (date.getDay() !== 0 && date.getDay() !== 6) added++;
  }
  return date.toISOString().slice(0, 10);
}
export async function activateProjectPlan(
  project: Project,
  rawPlan: unknown,
  actorId: string,
) {
  const projectCode = await nextAvailableProjectCode(project.code);
  const plan: ProjectPlan = expandPlanToDailyTasks(
    ProjectPlanSchema.parse(rawPlan),
  );
  const rows = await db()
    .prepare(
      "SELECT * FROM users WHERE active=1 AND role IN ('manager','employee')",
    )
    .all<any>();
  const activePeople = rows.results.map((x: any) => ({
    id: x.id,
    name: x.full_name,
    initials: x.full_name
      .split(" ")
      .map((word: string) => word[0])
      .join("")
      .slice(0, 2),
    email: x.email,
    role: x.role,
    active: true,
    position: x.position,
    department: x.department,
    skills: parse(x.skills_json),
    capacity: Math.min(8, Number(x.daily_capacity)),
    scheduled: Number(x.scheduled_hours),
    completed: Number(x.completed_hours),
    accent: x.accent,
  }));
  const assignments = assignTasks(plan, activePeople);
  const titleToId = new Map(
    assignments.map((item) => [item.task.title, uid()]),
  );
  const assigned = assignments.map((item) => ({
    id: titleToId.get(item.task.title)!,
    title: item.task.title,
    estimatedHours: item.task.estimated_hours,
    dependencies: item.task.dependencies,
    assigneeId: item.assigneeId ?? activePeople[0].id,
    phase: item.phase,
    task: item.task,
    score: item.score,
  }));
  const capacities = Object.fromEntries(
    activePeople.map((person) => [person.id, Math.min(8, person.capacity)]),
  );
  const schedule = scheduleAssignedTasks(assigned, capacities);
  const scheduledHours = new Map<string, number>();
  const scheduleWithTimes = schedule.map((row) => {
    const key = `${row.assigneeId}:${row.day}`;
    const used = scheduledHours.get(key) ?? 0;
    scheduledHours.set(key, used + row.hours);
    const minutes = 9 * 60 + Math.round(used * 60);
    return {
      ...row,
      startTime: `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`,
    };
  });
  const taskFinishDates = new Map<string, string>();
  for (const row of scheduleWithTimes)
    taskFinishDates.set(row.taskId, workDate(row.day));
  const forecastDate = workDate(
    Math.max(1, ...scheduleWithTimes.map((row) => row.day)),
  );
  const team = [...new Set(assigned.map((item) => item.assigneeId))];
  const d1 = db();
  const writes = [
    d1
      .prepare(
        "INSERT INTO projects (id,code,name,client,description,progress,health,deadline,predicted,phase,team_json,accent,created_by,status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
      )
      .bind(
        project.id,
        projectCode,
        project.name,
        project.client,
        project.description,
        0,
        "Healthy",
        project.deadline,
        forecastDate,
        plan.phases[0].name,
        JSON.stringify(team),
        project.accent,
        actorId,
        "Active",
      ),
    d1
      .prepare(
        "INSERT INTO ai_generated_plans (id,project_id,status,plan_json,model,created_by,approved_by,approved_at) VALUES (?,?,?,?,?,?,?,?)",
      )
      .bind(
        uid(),
        project.id,
        "approved",
        JSON.stringify(plan),
        "validated-plan",
        actorId,
        actorId,
        new Date().toISOString(),
      ),
  ];
  for (const item of assigned)
    writes.push(
      d1
        .prepare(
          "INSERT INTO tasks (id,project_id,title,description,assignee_id,status,priority,estimate,actual,due,start_time,required_skills_json,dependencies_json,acceptance_json,result,ai_generated) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        )
        .bind(
          item.id,
          project.id,
          item.title,
          item.task.description,
          item.assigneeId,
          item.dependencies.length ? "Backlog" : "Ready",
          item.task.priority,
          item.estimatedHours,
          0,
          taskFinishDates.get(item.id) ?? project.deadline,
          scheduleWithTimes.find((row) => row.taskId === item.id)?.startTime ??
            "09:00",
          JSON.stringify(item.task.required_skills),
          JSON.stringify(
            item.dependencies
              .map((name) => titleToId.get(name))
              .filter(Boolean),
          ),
          JSON.stringify(item.task.acceptance_criteria),
          null,
          1,
        ),
    );
  for (const row of scheduleWithTimes)
    writes.push(
      d1
        .prepare(
          "INSERT INTO daily_schedules (id,user_id,task_id,work_date,start_time,planned_hours,status) VALUES (?,?,?,?,?,?,?)",
        )
        .bind(
          uid(),
          row.assigneeId,
          row.taskId,
          workDate(row.day),
          row.startTime,
          row.hours,
          "planned",
        ),
    );
  await d1.batch(writes);
  await audit(actorId, "ai.plan_approved", "project", project.id, {
    code: projectCode,
    tasks: assigned.length,
    totalHours: assigned.reduce((sum, item) => sum + item.estimatedHours, 0),
    team,
    assignmentScores: Object.fromEntries(
      assigned.map((item) => [item.id, item.score]),
    ),
  });
}

export async function setTaskStatus(
  taskId: string,
  status: Task["status"],
  actor: Actor,
) {
  const task = await db()
    .prepare("SELECT project_id,assignee_id FROM tasks WHERE id=?")
    .bind(taskId)
    .first<{ project_id: string; assignee_id: string }>();
  if (!task) throw new Error("TASK_NOT_FOUND");
  if (actor.role === "employee" && task.assignee_id !== actor.id)
    throw new Error("FORBIDDEN");
  await db()
    .prepare("UPDATE tasks SET status=?, completed_at=? WHERE id=?")
    .bind(
      status,
      status === "Completed" ? new Date().toISOString() : null,
      taskId,
    )
    .run();
  if (status === "Completed")
    await db()
      .prepare("DELETE FROM daily_schedules WHERE task_id=?")
      .bind(taskId)
      .run();
  const progress = await db()
    .prepare(
      "SELECT ROUND(100.0 * SUM(CASE WHEN status='Completed' THEN estimate ELSE 0 END) / MAX(SUM(estimate),1)) AS progress FROM tasks WHERE project_id=?",
    )
    .bind(task.project_id)
    .first<{ progress: number }>();
  await db()
    .prepare("UPDATE projects SET progress=? WHERE id=?")
    .bind(Number(progress?.progress ?? 0), task.project_id)
    .run();
  await audit(actor.id, "task.status_changed", "task", taskId, { status });
}

export async function addTaskComment(
  taskId: string,
  body: string,
  actor: Actor,
) {
  const task = await db()
    .prepare("SELECT assignee_id FROM tasks WHERE id=?")
    .bind(taskId)
    .first<{ assignee_id: string }>();
  if (!task) throw new Error("TASK_NOT_FOUND");
  if (actor.role === "employee" && task.assignee_id !== actor.id)
    throw new Error("FORBIDDEN");
  await db()
    .prepare(
      "INSERT INTO task_comments (id,task_id,user_id,body) VALUES (?,?,?,?)",
    )
    .bind(uid(), taskId, actor.id, body)
    .run();
  await audit(actor.id, "task.comment_added", "task", taskId, {
    length: body.length,
  });
}

export async function audit(
  actorId: string,
  action: string,
  entityType: string,
  entityId: string,
  metadata: unknown,
) {
  await db()
    .prepare(
      "INSERT INTO activity_logs (id,actor_id,action,entity_type,entity_id,metadata_json) VALUES (?,?,?,?,?,?)",
    )
    .bind(
      uid(),
      actorId,
      action,
      entityType,
      entityId,
      JSON.stringify(metadata),
    )
    .run();
}

export { db };
