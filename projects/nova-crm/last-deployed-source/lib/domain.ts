export type Role = "manager" | "employee" | "viewer" | "executive" | "admin";
export type TaskStatus =
  | "Backlog"
  | "Ready"
  | "In Progress"
  | "In Review"
  | "Testing"
  | "Blocked"
  | "Completed";

export type Person = {
  id: string;
  name: string;
  initials: string;
  position: string;
  department: string;
  email?: string;
  role?: Role;
  active?: boolean;
  skills: string[];
  capacity: number;
  scheduled: number;
  completed: number;
  accent: string;
};

export type Project = {
  id: string;
  code: string;
  name: string;
  client: string;
  description: string;
  progress: number;
  health: "Healthy" | "Watch" | "At Risk" | "Critical";
  deadline: string;
  predicted: string;
  phase: string;
  team: string[];
  accent: string;
};

export type Task = {
  id: string;
  projectId: string;
  title: string;
  description: string;
  assigneeId: string;
  status: TaskStatus;
  priority: "Low" | "Medium" | "High" | "Critical";
  estimate: number;
  actual: number;
  due: string;
  start: string;
  requiredSkills: string[];
  dependencies: string[];
  acceptance: string[];
  result?: string;
  aiGenerated?: boolean;
};

export const people: Person[] = [
  {
    id: "u1",
    name: "Mohammad — AI Manager",
    initials: "MM",
    email: "manager@nova.local",
    role: "manager",
    active: true,
    position: "AI Division Manager",
    department: "AI & Innovation",
    skills: ["AI Strategy", "OpenAI API", "Architecture", "Product Delivery"],
    capacity: 8,
    scheduled: 6,
    completed: 3,
    accent: "#7c6cff",
  },
  {
    id: "u2",
    name: "Christine",
    initials: "CH",
    email: "christine@jormall.com",
    role: "employee",
    active: true,
    position: "Technical Sales & AI Solutions",
    department: "Technical Sales",
    skills: [
      "Client Discovery",
      "Solution Design",
      "AI Demos",
      "Prompt Engineering",
    ],
    capacity: 8,
    scheduled: 7,
    completed: 4,
    accent: "#21c7a8",
  },
  {
    id: "u3",
    name: "Ahmad",
    initials: "AH",
    email: "ahmad@jormall.com",
    role: "employee",
    active: true,
    position: "AI Full-Stack Engineer",
    department: "AI Engineering",
    skills: [
      "OpenAI API",
      "React",
      "Next.js",
      "TypeScript",
      "Python",
      "Testing",
    ],
    capacity: 8,
    scheduled: 8,
    completed: 5,
    accent: "#56a8ff",
  },
  {
    id: "u4",
    name: "Mohammad — AI Engineer",
    initials: "MA",
    email: "mohammad.ai@jormall.com",
    role: "employee",
    active: true,
    position: "AI & Backend Engineer",
    department: "AI Engineering",
    skills: [
      "Python",
      "FastAPI",
      "PostgreSQL",
      "Docker",
      "Nginx",
      "OpenAI API",
    ],
    capacity: 8,
    scheduled: 8,
    completed: 4,
    accent: "#f7a84a",
  },
];

export const projects: Project[] = [
  {
    id: "p1",
    code: "MAIN-01",
    name: "Main Site",
    client: "JorMall",
    description:
      "الموقع الرئيسي لقسم الذكاء الاصطناعي والابتكار لعرض المشاريع والخدمات وحالات الاستخدام.",
    progress: 78,
    health: "Healthy",
    deadline: "Aug 20",
    predicted: "Aug 18",
    phase: "Content & launch readiness",
    team: ["u1", "u2", "u3"],
    accent: "#8b73ff",
  },
  {
    id: "p2",
    code: "JMA-02",
    name: "JorMall Assistant",
    client: "JorMall Internal",
    description:
      "مساعد داخلي لتوليد التقارير والخطط التسويقية والحملات وتحليل الشركات مع قوالب ومراجعة بشرية.",
    progress: 72,
    health: "Watch",
    deadline: "Aug 28",
    predicted: "Sep 01",
    phase: "Evaluation & report templates",
    team: ["u1", "u3", "u4"],
    accent: "#21c7a8",
  },
  {
    id: "p3",
    code: "PLA-03",
    name: "Platform Assistant",
    client: "JorMall SMS",
    description:
      "مساعد لمستخدمي منصة JorMall SMS يشرح التعليمات والأنظمة وطريقة الاستخدام ويصعّد الحالات المعقدة.",
    progress: 64,
    health: "Healthy",
    deadline: "Sep 04",
    predicted: "Sep 03",
    phase: "Knowledge grounding",
    team: ["u1", "u3", "u4"],
    accent: "#56a8ff",
  },
  {
    id: "p4",
    code: "AID-04",
    name: "AI Dashboard",
    client: "JorMall Leadership",
    description:
      "لوحة مرئية لعرض مؤشرات الأداء والبيانات والنتائج التشغيلية والتنفيذية.",
    progress: 81,
    health: "Healthy",
    deadline: "Aug 16",
    predicted: "Aug 15",
    phase: "Executive reporting",
    team: ["u1", "u3"],
    accent: "#f7a84a",
  },
  {
    id: "p5",
    code: "SMA-05",
    name: "SMA Extension",
    client: "Sales Management",
    description:
      "أدوات مساعدة لإدارة وتحليل المبيعات وتجهيز التقارير واكتشاف فرص المتابعة.",
    progress: 69,
    health: "Watch",
    deadline: "Aug 25",
    predicted: "Aug 27",
    phase: "Report accuracy",
    team: ["u2", "u3", "u4"],
    accent: "#e46c9b",
  },
  {
    id: "p6",
    code: "SPN-06",
    name: "Spin",
    client: "Campaign Operations",
    description:
      "Backend لإدارة الحملات والتفاعل؛ حالياً API فقط بدون واجهة مستخدم.",
    progress: 55,
    health: "Watch",
    deadline: "Sep 10",
    predicted: "Sep 12",
    phase: "API hardening",
    team: ["u3", "u4"],
    accent: "#9d75ff",
  },
  {
    id: "p7",
    code: "API-07",
    name: "API Staging",
    client: "JorMall Platform",
    description:
      "نسخة تجريبية من JorMall API لاختبار التعديلات والتوافق قبل النقل إلى الإنتاج.",
    progress: 74,
    health: "Healthy",
    deadline: "Aug 18",
    predicted: "Aug 18",
    phase: "Regression & parity",
    team: ["u3", "u4"],
    accent: "#33b6c5",
  },
  {
    id: "p8",
    code: "CEC-08",
    name: "Central Ecommerce Chatbot",
    client: "Central Ecommerce",
    description:
      "Chatbot مخصص لخدمات Central Ecommerce مرتبط بقاعدة PostgreSQL وسجل محادثات قابل للتحليل.",
    progress: 88,
    health: "Healthy",
    deadline: "Aug 14",
    predicted: "Aug 14",
    phase: "Production validation",
    team: ["u3", "u4"],
    accent: "#4fa77b",
  },
  {
    id: "p9",
    code: "TOY-09",
    name: "Markazia Toyota Chatbot",
    client: "Markazia Toyota Jordan",
    description:
      "Chatbot لخدمات مركزية تويوتا الأردن مرتبط بقاعدة PostgreSQL ومعرفة الخدمات والصيانة.",
    progress: 83,
    health: "Healthy",
    deadline: "Aug 15",
    predicted: "Aug 15",
    phase: "Arabic evaluation",
    team: ["u3", "u4"],
    accent: "#e0565b",
  },
  {
    id: "p10",
    code: "SMS-10",
    name: "SMS Service Chatbot",
    client: "SMS Operations",
    description:
      "Chatbot متخصص بخدمات الرسائل القصيرة وحالات الأخطاء والتسليم، مرتبط بقاعدة PostgreSQL.",
    progress: 76,
    health: "Watch",
    deadline: "Aug 19",
    predicted: "Aug 21",
    phase: "Troubleshooting coverage",
    team: ["u3", "u4"],
    accent: "#377fd6",
  },
  {
    id: "p11",
    code: "DEP-11",
    name: "Deployer API",
    client: "JorMall Engineering",
    description:
      "النظام الإداري لرفع التطبيقات والنشر والتحديث والـrollback وإدارة Docker وNginx.",
    progress: 61,
    health: "At Risk",
    deadline: "Aug 24",
    predicted: "Aug 28",
    phase: "Safe rollout controls",
    team: ["u1", "u3", "u4"],
    accent: "#d27b35",
  },
];

type SeedTask = Omit<
  Task,
  "id" | "dependencies" | "acceptance" | "due" | "start"
> & { dependsOn?: number; output: string };
const seedTasks: SeedTask[] = [
  {
    projectId: "p1",
    title: "Finalize AI services and project content",
    description:
      "Turn the approved service catalogue and live portfolio into launch-ready Arabic and English content.",
    assigneeId: "u2",
    status: "In Review",
    priority: "High",
    estimate: 4,
    actual: 3.5,
    requiredSkills: ["Client Discovery", "Solution Design"],
    output: "Approved bilingual service and portfolio copy",
  },
  {
    projectId: "p1",
    title: "Production SEO, analytics and launch checks",
    description:
      "Validate metadata, analytics events, responsive behavior and production links before release.",
    assigneeId: "u3",
    status: "Ready",
    priority: "High",
    estimate: 4,
    actual: 0,
    requiredSkills: ["Next.js", "Testing"],
    dependsOn: 1,
    output: "Signed launch checklist",
  },
  {
    projectId: "p2",
    title: "Implement report and marketing plan templates",
    description:
      "Generate structured company reports, campaign briefs and marketing plans with reviewable sources.",
    assigneeId: "u3",
    status: "In Progress",
    priority: "Critical",
    estimate: 5,
    actual: 2.5,
    requiredSkills: ["OpenAI API", "TypeScript"],
    output: "Validated generation templates",
  },
  {
    projectId: "p2",
    title: "Approve company analysis evaluation set",
    description:
      "Review business usefulness, factuality and presentation quality across representative companies.",
    assigneeId: "u1",
    status: "Ready",
    priority: "High",
    estimate: 3,
    actual: 0,
    requiredSkills: ["AI Strategy", "Product Delivery"],
    dependsOn: 3,
    output: "Approved evaluation report",
  },
  {
    projectId: "p3",
    title: "Complete SMS platform knowledge grounding",
    description:
      "Map product instructions, account rules and operational procedures into versioned grounded answers.",
    assigneeId: "u4",
    status: "In Progress",
    priority: "High",
    estimate: 4,
    actual: 2,
    requiredSkills: ["Python", "PostgreSQL"],
    output: "Versioned knowledge index",
  },
  {
    projectId: "p3",
    title: "Test escalation and unsupported questions",
    description:
      "Verify refusals, escalation paths and source citations for ambiguous or unsupported customer questions.",
    assigneeId: "u3",
    status: "Ready",
    priority: "High",
    estimate: 4,
    actual: 0,
    requiredSkills: ["Testing", "OpenAI API"],
    dependsOn: 5,
    output: "Grounding and escalation test report",
  },
  {
    projectId: "p4",
    title: "Lock KPI definitions and data contracts",
    description:
      "Confirm source queries, refresh timing, ownership and formulas for every executive indicator.",
    assigneeId: "u3",
    status: "In Review",
    priority: "Critical",
    estimate: 4,
    actual: 4,
    requiredSkills: ["TypeScript", "Testing"],
    output: "Approved KPI contract",
  },
  {
    projectId: "p4",
    title: "Finish executive filters and export",
    description:
      "Deliver date, project and team filters plus a clean management export for weekly reviews.",
    assigneeId: "u3",
    status: "Ready",
    priority: "High",
    estimate: 4,
    actual: 0,
    requiredSkills: ["React", "Next.js"],
    dependsOn: 7,
    output: "Executive dashboard release candidate",
  },
  {
    projectId: "p5",
    title: "Harden sales workbook ingestion",
    description:
      "Normalize sales uploads, field mappings and invalid-row handling before report generation.",
    assigneeId: "u4",
    status: "In Progress",
    priority: "High",
    estimate: 5,
    actual: 2,
    requiredSkills: ["Python", "PostgreSQL"],
    output: "Validated sales ingestion pipeline",
  },
  {
    projectId: "p5",
    title: "Validate sales report usefulness",
    description:
      "Review summary, pipeline risks and follow-up recommendations with technical sales scenarios.",
    assigneeId: "u2",
    status: "Ready",
    priority: "High",
    estimate: 3,
    actual: 0,
    requiredSkills: ["Solution Design", "AI Demos"],
    dependsOn: 9,
    output: "Signed sales report acceptance",
  },
  {
    projectId: "p6",
    title: "Complete campaign lifecycle API",
    description:
      "Finish create, activate, pause and close transitions with idempotent state changes and audit events.",
    assigneeId: "u4",
    status: "In Progress",
    priority: "Critical",
    estimate: 6,
    actual: 3,
    requiredSkills: ["FastAPI", "PostgreSQL"],
    output: "Tested campaign lifecycle endpoints",
  },
  {
    projectId: "p6",
    title: "Publish authentication and API contract",
    description:
      "Document authorization, request schemas, error behavior and examples for consuming teams.",
    assigneeId: "u3",
    status: "Ready",
    priority: "High",
    estimate: 2,
    actual: 0,
    requiredSkills: ["TypeScript", "Testing"],
    dependsOn: 11,
    output: "Versioned OpenAPI and integration guide",
  },
  {
    projectId: "p7",
    title: "Run staging regression and production parity",
    description:
      "Exercise critical API paths and compare configuration, schema and integration behavior with production.",
    assigneeId: "u3",
    status: "Testing",
    priority: "Critical",
    estimate: 5,
    actual: 3.5,
    requiredSkills: ["Testing", "TypeScript"],
    output: "Regression and parity report",
  },
  {
    projectId: "p7",
    title: "Approve production promotion checklist",
    description:
      "Verify database changes, rollback steps, owners and monitoring before production promotion.",
    assigneeId: "u4",
    status: "Ready",
    priority: "High",
    estimate: 3,
    actual: 0,
    requiredSkills: ["Docker", "Nginx"],
    dependsOn: 13,
    output: "Signed promotion checklist",
  },
  {
    projectId: "p8",
    title: "Add PostgreSQL conversation analytics",
    description:
      "Store searchable conversation outcomes, unresolved intents and service categories for improvement.",
    assigneeId: "u4",
    status: "In Review",
    priority: "High",
    estimate: 4,
    actual: 4,
    requiredSkills: ["PostgreSQL", "Python"],
    output: "Conversation analytics dataset",
  },
  {
    projectId: "p8",
    title: "Complete ecommerce answer verification",
    description:
      "Validate policy, service and order-related responses against the approved Central Ecommerce scenarios.",
    assigneeId: "u3",
    status: "Ready",
    priority: "High",
    estimate: 4,
    actual: 0,
    requiredSkills: ["Testing", "OpenAI API"],
    dependsOn: 15,
    output: "Client acceptance test pack",
  },
  {
    projectId: "p9",
    title: "Automate Toyota service knowledge sync",
    description:
      "Version service, maintenance and location knowledge while preserving traceable source updates.",
    assigneeId: "u3",
    status: "In Progress",
    priority: "High",
    estimate: 4,
    actual: 2,
    requiredSkills: ["OpenAI API", "Python"],
    output: "Versioned Toyota knowledge sync",
  },
  {
    projectId: "p9",
    title: "Run Arabic intent and terminology evaluation",
    description:
      "Test Jordanian Arabic questions, Toyota terminology and escalation for uncertain answers.",
    assigneeId: "u4",
    status: "Ready",
    priority: "High",
    estimate: 4,
    actual: 0,
    requiredSkills: ["Python", "OpenAI API"],
    dependsOn: 17,
    output: "Arabic quality evaluation",
  },
  {
    projectId: "p10",
    title: "Complete SMS troubleshooting flows",
    description:
      "Cover delivery status, sender IDs, balances, common errors and escalation with grounded responses.",
    assigneeId: "u4",
    status: "In Progress",
    priority: "Critical",
    estimate: 5,
    actual: 2.5,
    requiredSkills: ["Python", "PostgreSQL"],
    output: "Troubleshooting workflow pack",
  },
  {
    projectId: "p10",
    title: "Map provider errors to customer guidance",
    description:
      "Translate provider codes into safe, actionable explanations and internal diagnostic context.",
    assigneeId: "u3",
    status: "Ready",
    priority: "High",
    estimate: 3,
    actual: 0,
    requiredSkills: ["TypeScript", "Testing"],
    dependsOn: 19,
    output: "Verified provider error catalogue",
  },
  {
    projectId: "p11",
    title: "Approve safe rollout and rollback workflow",
    description:
      "Define approval gates, health criteria, rollback triggers and evidence required for every deployment.",
    assigneeId: "u1",
    status: "In Progress",
    priority: "Critical",
    estimate: 3,
    actual: 1.5,
    requiredSkills: ["Architecture", "Product Delivery"],
    output: "Approved deployment control policy",
  },
  {
    projectId: "p11",
    title: "Audit Docker and Nginx deployment execution",
    description:
      "Verify container isolation, port allocation, proxy configuration, health checks and rollback behavior.",
    assigneeId: "u4",
    status: "Ready",
    priority: "Critical",
    estimate: 5,
    actual: 0,
    requiredSkills: ["Docker", "Nginx"],
    dependsOn: 21,
    output: "Deployment safety audit",
  },
];

export const tasks: Task[] = seedTasks.map((task, index) => ({
  ...task,
  id: `t${index + 1}`,
  dependencies: task.dependsOn ? [`t${task.dependsOn}`] : [],
  acceptance: [
    `${task.output} is stored with an owner and review evidence`,
    "Critical paths pass their documented validation checks",
    "Operational notes and next action are recorded",
  ],
  due: index % 2 === 0 ? "Today" : "Tomorrow",
  start: index % 2 === 0 ? "09:00" : "13:00",
}));

export const activity = [
  {
    time: "15:35",
    user: "Ahmad",
    text: "submitted KPI definitions for review",
    project: "AI Dashboard",
    tone: "info",
  },
  {
    time: "14:20",
    user: "Mohammad (AI Engineer)",
    text: "completed PostgreSQL conversation analytics",
    project: "Central Ecommerce Chatbot",
    tone: "success",
  },
  {
    time: "12:40",
    user: "Christine",
    text: "approved the Main Site service catalogue",
    project: "Main Site",
    tone: "success",
  },
  {
    time: "11:15",
    user: "Mohammad (AI Manager)",
    text: "updated rollout approval criteria",
    project: "Deployer API",
    tone: "neutral",
  },
  {
    time: "09:50",
    user: "Ahmad",
    text: "started Arabic intent evaluation preparation",
    project: "Markazia Toyota Chatbot",
    tone: "info",
  },
];

export function assignmentScore(
  task: Pick<Task, "requiredSkills">,
  person: Person,
) {
  const matches = task.requiredSkills.filter((skill) =>
    person.skills.includes(skill),
  ).length;
  const skillMatch = task.requiredSkills.length
    ? matches / task.requiredSkills.length
    : 0.5;
  const availability =
    Math.max(0, person.capacity - person.scheduled) / person.capacity;
  const positionMatch = task.requiredSkills.some((skill) =>
    person.position.toLowerCase().includes(skill.toLowerCase().split(" ")[0]),
  )
    ? 1
    : 0.7;
  return (
    Math.round(
      (skillMatch * 60 + availability * 25 + positionMatch * 15) * 10,
    ) / 10
  );
}

export function scheduleWithinCapacity(items: Task[], member: Person) {
  const ready = items.filter(
    (task) => task.assigneeId === member.id && task.status !== "Completed",
  );
  const days: Task[][] = [[]];
  for (const task of ready) {
    const current = days[days.length - 1];
    const used = current.reduce((sum, item) => sum + item.estimate, 0);
    if (used + task.estimate > member.capacity) days.push([task]);
    else current.push(task);
  }
  return days;
}

export const nav = [
  "Command Center",
  "My Work",
  "Projects",
  "Tasks",
  "Calendar",
  "Team",
  "Workload",
  "Reports",
  "AI Assistant",
] as const;
