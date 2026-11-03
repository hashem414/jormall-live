/* eslint-disable @typescript-eslint/no-explicit-any, @typescript-eslint/no-unused-vars, jsx-a11y/no-static-element-interactions, jsx-a11y/click-events-have-key-events, jsx-a11y/no-noninteractive-element-interactions, jsx-a11y/no-autofocus, react-hooks/exhaustive-deps */
"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Bell,
  Bot,
  BriefcaseBusiness,
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleGauge,
  Clock3,
  Command,
  FileBarChart,
  FolderKanban,
  Gauge,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Menu,
  MoreHorizontal,
  Pencil,
  Play,
  Languages,
  Plus,
  Search,
  Settings,
  Sparkles,
  Target,
  Trash2,
  UserPlus,
  UserRoundX,
  Users,
  X,
  Zap,
} from "lucide-react";
import {
  activity as seedActivity,
  nav,
  people as seedPeople,
  projects as seedProjects,
  tasks as seedTasks,
  type Person,
  type Project,
  type Task,
} from "../lib/domain";
import { navKey, tr, type Locale } from "../lib/i18n";

type Data = {
  currentUser: {
    id: string;
    name: string;
    email: string;
    role: string;
    position: string;
  };
  people: Person[];
  projects: Project[];
  tasks: Task[];
  schedules: {
    id: string;
    userId: string;
    taskId: string;
    workDate: string;
    startTime: string;
    plannedHours: number;
    status: string;
  }[];
  activity: typeof seedActivity;
};
type Toast = { text: string; tone?: "success" | "warning" } | null;

const iconMap = [
  LayoutDashboard,
  ListChecks,
  FolderKanban,
  CheckCircle2,
  CalendarDays,
  Users,
  Gauge,
  FileBarChart,
  Bot,
];
const fallback: Data = {
  currentUser: {
    id: "u1",
    name: "Mohammad — AI Manager",
    email: "manager@nova.local",
    role: "manager",
    position: "AI Division Manager",
  },
  people: seedPeople,
  projects: seedProjects,
  tasks: seedTasks,
  schedules: [],
  activity: seedActivity,
};

export default function DashboardClient({
  displayName = "Mohammad — AI Manager",
  userId = "u1",
  accessRole = "manager",
  position = "AI Division Manager",
}: {
  displayName?: string;
  userId?: string;
  accessRole?: string;
  position?: string;
}) {
  const [data, setData] = useState<Data>(fallback);
  const [active, setActive] = useState<(typeof nav)[number]>(
    accessRole === "employee" ? "My Work" : "Command Center",
  );
  const [sidebar, setSidebar] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [projectOpen, setProjectOpen] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [locale, setLocale] = useState<Locale>("en");
  const [employeeOpen, setEmployeeOpen] = useState(false);
  const [taskOpen, setTaskOpen] = useState(false);
  const [rebalancing, setRebalancing] = useState(false);
  const [removePerson, setRemovePerson] = useState<Person | null>(null);
  const [editProject, setEditProject] = useState<Project | null>(null);
  const [archiveTarget, setArchiveTarget] = useState<Project | null>(null);
  const [toast, setToast] = useState<Toast>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/bootstrap")
      .then((r) => {
        if (r.status === 401) {
          window.location.assign("/login");
          return Promise.reject();
        }
        return r.ok ? r.json() : Promise.reject();
      })
      .then((payload) => {
        if (payload.projects?.length) setData(payload);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
    const savedLocale = window.localStorage.getItem("nova-locale");
    const detectedLocale: Locale =
      savedLocale === "ar" || savedLocale === "en"
        ? savedLocale
        : window.navigator.language.toLowerCase().startsWith("ar")
          ? "ar"
          : "en";
    window.setTimeout(() => setLocale(detectedLocale), 0);
  }, []);

  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCommandOpen(true);
      }
      if (event.key === "Escape") {
        setCommandOpen(false);
        setProjectOpen(false);
        setTaskOpen(false);
        setEditProject(null);
        setArchiveTarget(null);
        setTaskId(null);
      }
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, []);

  const notify = (text: string, tone: "success" | "warning" = "success") => {
    setToast({ text, tone });
    window.setTimeout(() => setToast(null), 3200);
  };
  const canManage = ["manager", "admin"].includes(accessRole);
  const visibleNav = nav.filter((item) => {
    if (canManage) return true;
    if (["viewer", "executive"].includes(accessRole))
      return ["Command Center", "Projects", "Reports"].includes(item);
    return [
      "My Work",
      "Projects",
      "Tasks",
      "Calendar",
      "AI Assistant",
    ].includes(item);
  });
  const signOut = async () => {
    await fetch("/api/auth/logout", { method: "POST" }).catch(() => {});
    window.location.assign("/login");
  };

  const updateTask = async (id: string, status: Task["status"]) => {
    const previous = data.tasks;
    setData((d) => ({
      ...d,
      tasks: d.tasks.map((t) => (t.id === id ? { ...t, status } : t)),
    }));
    try {
      const response = await fetch("/api/actions", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "task_status", taskId: id, status }),
      });
      if (!response.ok) throw new Error();
      notify(
        status === "Completed"
          ? "Task completed and project progress recalculated"
          : `Task moved to ${status}`,
      );
    } catch {
      setData((d) => ({ ...d, tasks: previous }));
      notify("The update could not be saved", "warning");
    }
  };

  const refreshData = async () => {
    const latest = await fetch("/api/bootstrap").then((r) => r.json());
    if (latest.projects) setData(latest);
  };
  const addEmployee = async (employee: {
    fullName: string;
    email: string;
    position: string;
    department: string;
    role: "employee" | "viewer";
    dailyCapacity: number;
    skills: string[];
    temporaryPassword: string;
  }) => {
    const response = await fetch("/api/actions", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action: "create_employee", employee }),
    });
    const payload = await response.json();
    if (!response.ok)
      throw new Error(payload.error?.message ?? tr(locale, "employeeError"));
    await refreshData();
    setEmployeeOpen(false);
    notify(tr(locale, "employeeAdded"));
  };
  const removeEmployee = async (person: Person) => {
    const response = await fetch("/api/actions", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        action: "deactivate_employee",
        userId: person.id,
        releaseTasks: true,
      }),
    });
    const payload = await response.json();
    if (!response.ok)
      throw new Error(payload.error?.message ?? tr(locale, "employeeError"));
    await refreshData();
    setRemovePerson(null);
    notify(tr(locale, "employeeRemoved"));
  };
  const saveProjectEdits = async (project: Project) => {
    const response = await fetch("/api/actions", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action: "update_project", project }),
    });
    const payload = await response.json();
    if (!response.ok)
      throw new Error(payload.error?.message ?? "Project update failed");
    await refreshData();
    setEditProject(null);
    notify(
      locale === "ar" ? "تم حفظ تعديلات المشروع" : "Project changes saved",
    );
  };
  const archiveProjectRecord = async (project: Project) => {
    const response = await fetch("/api/actions", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        action: "archive_project",
        projectId: project.id,
      }),
    });
    const payload = await response.json();
    if (!response.ok)
      throw new Error(payload.error?.message ?? "Project archive failed");
    await refreshData();
    setArchiveTarget(null);
    notify(
      locale === "ar"
        ? "تمت أرشفة المشروع مع الاحتفاظ بسجله"
        : "Project archived and history preserved",
    );
  };
  const rebalanceWork = async () => {
    setRebalancing(true);
    try {
      const response = await fetch("/api/actions", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "rebalance_work" }),
      });
      const payload = await response.json();
      if (!response.ok)
        throw new Error(payload.error?.message ?? "Rebalancing failed");
      await refreshData();
      notify(
        locale === "ar"
          ? `تم ترتيب ${payload.taskCount} مهمة حتى ${payload.forecastDate}`
          : `${payload.taskCount} tasks scheduled through ${payload.forecastDate}`,
      );
      return payload;
    } catch (cause) {
      notify(
        cause instanceof Error ? cause.message : "Rebalancing failed",
        "warning",
      );
      throw cause;
    } finally {
      setRebalancing(false);
    }
  };
  const createTask = async (task: {
    projectId: string;
    title: string;
    description: string;
    assigneeId: string;
    priority: Task["priority"];
    estimate: number;
    due: string;
    requiredSkills: string[];
    acceptance: string[];
  }) => {
    const response = await fetch("/api/actions", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action: "create_task", task }),
    });
    const payload = await response.json();
    if (!response.ok)
      throw new Error(payload.error?.message ?? "Task creation failed");
    await rebalanceWork();
    setTaskOpen(false);
    notify(
      locale === "ar"
        ? "تمت إضافة المهمة وجدولتها"
        : "Task created and scheduled",
    );
  };
  const saveTaskNote = async (id: string, body: string) => {
    const response = await fetch("/api/actions", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action: "add_task_comment", taskId: id, body }),
    });
    const payload = await response.json();
    if (!response.ok)
      throw new Error(payload.error?.message ?? "Note could not be saved");
    notify(locale === "ar" ? "تم حفظ الملاحظة" : "Note saved");
  };

  return (
    <div
      className="app-shell"
      dir={locale === "ar" ? "rtl" : "ltr"}
      lang={locale}
    >
      <aside className={`sidebar ${sidebar ? "sidebar-open" : ""}`}>
        <div className="brand">
          <div className="brand-mark">
            <Sparkles size={18} />
          </div>
          <div>
            <strong>NOVA</strong>
            <span>AI Division OS</span>
          </div>
          <button
            className="icon-button mobile-only"
            onClick={() => setSidebar(false)}
            aria-label="Close menu"
          >
            <X size={18} />
          </button>
        </div>
        <div className="workspace">
          <span className="workspace-avatar">N</span>
          <div>
            <b>JorMall</b>
            <span>{tr(locale, "aiDivision")}</span>
          </div>
          <ChevronDown size={15} />
        </div>
        <nav className="primary-nav">
          <span className="nav-label">{tr(locale, "workspace")}</span>
          {visibleNav.map((item) => {
            const Icon = iconMap[nav.indexOf(item)];
            return (
              <button
                key={item}
                className={active === item ? "active" : ""}
                onClick={() => {
                  setActive(item);
                  setSidebar(false);
                }}
              >
                <Icon size={17} />
                <span>{tr(locale, navKey[item])}</span>
                {item === "Tasks" && (
                  <em>
                    {
                      data.tasks.filter((task) => task.status !== "Completed")
                        .length
                    }
                  </em>
                )}
                {item === "AI Assistant" && <i>AI</i>}
              </button>
            );
          })}
        </nav>
        <div className="sidebar-bottom">
          <button
            onClick={() =>
              notify(
                locale === "ar"
                  ? "إعدادات الحساب والصلاحيات مُدارة بأمان من المدير"
                  : "Account and access settings are managed securely by the manager",
              )
            }
          >
            <Settings size={17} />
            {tr(locale, "settings")}
          </button>
          <button
            onClick={() =>
              notify(
                locale === "ar"
                  ? "لا توجد إشعارات غير مقروءة"
                  : "You have no unread notifications",
              )
            }
          >
            <Bell size={17} />
            {tr(locale, "notifications")}
            <span className="dot" />
          </button>
          <div className="profile">
            <span className="avatar avatar-purple">
              {displayName
                .split(" ")
                .map((word) => word[0])
                .join("")
                .slice(0, 2)}
            </span>
            <div>
              <b>{displayName}</b>
              <span>{position}</span>
            </div>
            <button
              className="icon-button"
              onClick={signOut}
              aria-label={locale === "ar" ? "تسجيل الخروج" : "Sign out"}
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-wrap">
        <header className="topbar">
          <button
            className="icon-button mobile-menu"
            onClick={() => setSidebar(true)}
            aria-label="Open menu"
          >
            <Menu size={20} />
          </button>
          <div className="crumbs">
            <span>{tr(locale, "aiDivision")}</span>
            <b>/</b>
            <strong>{tr(locale, navKey[active])}</strong>
          </div>
          <button
            className="command-trigger"
            onClick={() => setCommandOpen(true)}
          >
            <Search size={16} />
            <span>{tr(locale, "search")}</span>
            <kbd>Ctrl K</kbd>
          </button>
          <div className="top-actions">
            <button
              className="language-button"
              onClick={() =>
                setLocale((value) => {
                  const next = value === "en" ? "ar" : "en";
                  window.localStorage.setItem("nova-locale", next);
                  return next;
                })
              }
              aria-label={tr(locale, "language")}
            >
              <Languages size={16} />
              {locale === "en" ? tr(locale, "arabic") : tr(locale, "english")}
            </button>
            <button
              className="icon-button has-badge"
              aria-label={tr(locale, "notifications")}
              onClick={() =>
                notify(
                  locale === "ar"
                    ? "لا توجد إشعارات غير مقروءة"
                    : "You have no unread notifications",
                )
              }
            >
              <Bell size={18} />
              <span />
            </button>
            {canManage && (
              <button
                className="primary-button"
                onClick={() => setProjectOpen(true)}
              >
                <Plus size={17} />
                {tr(locale, "newProject")}
              </button>
            )}
          </div>
        </header>
        <main className="content">
          {loading && <div className="loading-line" />}
          {active === "Command Center" && (
            <CommandCenter
              locale={locale}
              data={data}
              onTask={setTaskId}
              onProject={() => setActive("Projects")}
              navigate={setActive}
            />
          )}
          {active === "Projects" && (
            <ProjectsView
              locale={locale}
              data={data}
              onNew={() => setProjectOpen(true)}
              onTask={setTaskId}
              canManage={canManage}
              onEdit={setEditProject}
              onArchive={setArchiveTarget}
            />
          )}
          {active === "Tasks" && (
            <TasksView
              locale={locale}
              data={data}
              onTask={setTaskId}
              canManage={canManage}
              onNew={() => setTaskOpen(true)}
              onRebalance={rebalanceWork}
              rebalancing={rebalancing}
            />
          )}
          {active === "Team" && (
            <TeamView
              locale={locale}
              data={data}
              onAdd={() => setEmployeeOpen(true)}
              onRemove={setRemovePerson}
            />
          )}
          {active === "Workload" && (
            <WorkloadView locale={locale} data={data} />
          )}
          {active === "My Work" && (
            <MyWorkView
              locale={locale}
              data={data}
              onTask={setTaskId}
              userId={userId}
            />
          )}
          {active === "AI Assistant" && (
            <AssistantView locale={locale} data={data} />
          )}
          {["Calendar", "Reports"].includes(active) && (
            <ComingView
              locale={locale}
              title={active}
              onOpen={() =>
                setActive(active === "Reports" ? "Tasks" : "My Work")
              }
            />
          )}
        </main>
      </div>
      {commandOpen && (
        <CommandPalette
          locale={locale}
          data={data}
          close={() => setCommandOpen(false)}
          navigate={setActive}
          openTask={(id) => {
            setTaskId(id);
            setCommandOpen(false);
          }}
        />
      )}
      {projectOpen && canManage && (
        <ProjectModal
          locale={locale}
          close={() => setProjectOpen(false)}
          onCreated={async (project) => {
            try {
              const latest = await fetch("/api/bootstrap").then((r) =>
                r.json(),
              );
              if (latest.projects) setData(latest);
              else
                setData((d) => ({ ...d, projects: [project, ...d.projects] }));
            } catch {
              setData((d) => ({ ...d, projects: [project, ...d.projects] }));
            }
            setProjectOpen(false);
            notify(
              locale === "ar"
                ? "تم اعتماد خطة الذكاء الاصطناعي وتوزيع المهام"
                : "AI plan approved — tasks assigned and schedules created",
            );
          }}
        />
      )}
      {employeeOpen && canManage && (
        <EmployeeModal
          locale={locale}
          close={() => setEmployeeOpen(false)}
          save={addEmployee}
        />
      )}
      {taskOpen && canManage && (
        <TaskModal
          locale={locale}
          data={data}
          close={() => setTaskOpen(false)}
          save={createTask}
        />
      )}
      {removePerson && (
        <DeactivateEmployeeModal
          locale={locale}
          person={removePerson}
          tasks={data.tasks}
          close={() => setRemovePerson(null)}
          confirm={removeEmployee}
        />
      )}
      {editProject && canManage && (
        <EditProjectModal
          locale={locale}
          project={editProject}
          people={data.people}
          close={() => setEditProject(null)}
          save={saveProjectEdits}
        />
      )}
      {archiveTarget && canManage && (
        <ArchiveProjectModal
          locale={locale}
          project={archiveTarget}
          close={() => setArchiveTarget(null)}
          confirm={archiveProjectRecord}
        />
      )}
      {taskId && (
        <TaskDrawer
          locale={locale}
          task={data.tasks.find((t) => t.id === taskId)!}
          data={data}
          close={() => setTaskId(null)}
          update={updateTask}
          openTask={setTaskId}
          saveNote={saveTaskNote}
        />
      )}
      {toast && (
        <div className={`toast ${toast.tone}`}>
          <CheckCircle2 size={18} />
          {toast.text}
        </div>
      )}
      {sidebar && (
        <div className="mobile-scrim" onClick={() => setSidebar(false)} />
      )}
    </div>
  );
}

function CommandCenter({
  locale,
  data,
  onTask,
  onProject,
  navigate,
}: {
  locale: Locale;
  data: Data;
  onTask: (id: string) => void;
  onProject: () => void;
  navigate: (view: (typeof nav)[number]) => void;
}) {
  const completed = data.tasks.filter((t) => t.status === "Completed").length,
    blocked = data.tasks.filter((t) => t.status === "Blocked").length;
  const atRisk = data.projects.filter((p) =>
    ["At Risk", "Critical"].includes(p.health),
  ).length;
  const healthy = data.projects.filter((p) => p.health === "Healthy").length;
  const riskProject = data.projects.find((p) =>
    ["At Risk", "Critical"].includes(p.health),
  );
  const blockedTask = data.tasks.find((task) => task.status === "Blocked");
  const reviewTask = data.tasks.find((task) => task.status === "In Review");
  const scheduledHours = data.people.reduce(
    (total, person) => total + person.scheduled,
    0,
  );
  const capacityHours = data.people.reduce(
    (total, person) => total + person.capacity,
    0,
  );
  const utilization = capacityHours
    ? Math.round((scheduledHours / capacityHours) * 100)
    : 0;
  const busiest = [...data.people].sort(
    (a, b) => b.scheduled / b.capacity - a.scheduled / a.capacity,
  )[0];
  const deliveredHours = data.tasks
    .filter((task) => task.status === "Completed")
    .reduce((total, task) => total + task.actual, 0);
  const today = new Intl.DateTimeFormat(locale === "ar" ? "ar-JO" : "en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(new Date());
  const firstName = data.currentUser.name.split(/[ —-]/)[0];
  const downloadBrief = () => {
    const lines = [
      ["Project", "Health", "Progress", "Phase", "Deadline", "Forecast"],
      ...data.projects.map((project) => [
        project.name,
        project.health,
        `${project.progress}%`,
        project.phase,
        project.deadline,
        project.predicted,
      ]),
      [],
      ["Team member", "Position", "Scheduled", "Capacity"],
      ...data.people.map((person) => [
        person.name,
        person.position,
        `${person.scheduled}h`,
        `${person.capacity}h`,
      ]),
    ];
    const csv = lines
      .map((line) =>
        line
          .map((value) => `"${String(value ?? "").replaceAll('"', '""')}"`)
          .join(","),
      )
      .join("\n");
    const url = URL.createObjectURL(
      new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `nova-daily-brief-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };
  return (
    <>
      <section className="page-heading">
        <div>
          <span className="eyebrow">{today}</span>
          <h1>
            {locale === "ar"
              ? `صباح الخير، ${firstName}.`
              : `Good morning, ${firstName}.`}
          </h1>
          <p>{tr(locale, "operatingPicture")}</p>
        </div>
        <button className="secondary-button" onClick={downloadBrief}>
          <FileBarChart size={16} />
          {tr(locale, "dailyBrief")}
        </button>
      </section>
      <section className="metrics-grid">
        <Metric
          label={tr(locale, "activeProjects")}
          value={data.projects.length}
          note={
            locale === "ar"
              ? `${healthy} مشاريع بحالة سليمة`
              : `${healthy} projects are healthy`
          }
          icon={BriefcaseBusiness}
          tone="violet"
        />
        <Metric
          label={tr(locale, "projectsAtRisk")}
          value={atRisk}
          note={
            locale === "ar"
              ? riskProject
                ? `${riskProject.name} يحتاج متابعة`
                : "لا توجد مشاريع عالية المخاطر"
              : riskProject
                ? `${riskProject.name} needs attention`
                : "No high-risk projects"
          }
          icon={AlertTriangle}
          tone="amber"
          warning
        />
        <Metric
          label={tr(locale, "tasksCompleted")}
          value={completed}
          note={
            locale === "ar"
              ? `${deliveredHours} ساعة عمل مكتملة`
              : `${deliveredHours} completed work hours`
          }
          icon={CheckCircle2}
          tone="green"
        />
        <Metric
          label={tr(locale, "teamUtilization")}
          value={`${utilization}%`}
          note={
            locale === "ar"
              ? `تمت جدولة ${scheduledHours} من ${capacityHours} ساعة`
              : `${scheduledHours} of ${capacityHours} hours scheduled`
          }
          icon={CircleGauge}
          tone="blue"
        />
      </section>
      <section className="dashboard-grid">
        <div className="panel projects-panel">
          <PanelHeader
            title={tr(locale, "projectPulse")}
            sub={tr(locale, "liveDelivery")}
            action={tr(locale, "viewAll")}
            onAction={onProject}
          />
          <div className="project-list">
            {data.projects.map((p) => (
              <ProjectRow key={p.id} project={p} onOpen={onProject} />
            ))}
          </div>
        </div>
        <div className="panel attention-panel">
          <PanelHeader
            title={tr(locale, "attentionRequired")}
            sub={`${blocked + atRisk + (reviewTask ? 1 : 0)} ${tr(locale, "signalsDecision")}`}
          />
          <Attention
            icon={AlertTriangle}
            tone="red"
            title={
              blockedTask?.title ??
              (locale === "ar" ? "لا توجد مهام متوقفة" : "No blocked tasks")
            }
            text={
              blockedTask
                ? blockedTask.description
                : locale === "ar"
                  ? "كل المهام الحالية قابلة للتنفيذ أو قيد المراجعة."
                  : "All current tasks are actionable or under review."
            }
            tag={
              blockedTask
                ? locale === "ar"
                  ? `${blockedTask.estimate} ساعات مخططة`
                  : `${blockedTask.estimate} planned hours`
                : locale === "ar"
                  ? "الوضع مستقر"
                  : "Delivery is stable"
            }
            onClick={
              blockedTask
                ? () => onTask(blockedTask.id)
                : () => navigate("Tasks")
            }
          />
          <Attention
            icon={Clock3}
            tone="amber"
            title={riskProject?.name ?? tr(locale, "deadlineChanged")}
            text={
              riskProject
                ? locale === "ar"
                  ? `${riskProject.phase} — التسليم المتوقع ${riskProject.predicted}.`
                  : `${riskProject.phase} — predicted delivery ${riskProject.predicted}.`
                : locale === "ar"
                  ? "المواعيد الحالية ضمن التوقعات."
                  : "Current deadlines remain within forecast."
            }
            tag={locale === "ar" ? "مراجعة الخيارات" : "Review options"}
            onClick={onProject}
          />
          <Attention
            icon={Gauge}
            tone="violet"
            title={
              locale === "ar"
                ? `${busiest?.name ?? "الفريق"} عند السعة اليومية`
                : `${busiest?.name ?? "Team"} is at daily capacity`
            }
            text={
              locale === "ar"
                ? `${busiest?.name ?? "الفريق"}: تمت جدولة ${busiest?.scheduled ?? 0} من ${busiest?.capacity ?? 0} ساعات.`
                : `${busiest?.name ?? "Team"}: ${busiest?.scheduled ?? 0} of ${busiest?.capacity ?? 0} hours scheduled.`
            }
            tag={locale === "ar" ? "موازنة الحمل" : "Balance workload"}
            onClick={() => navigate("Workload")}
          />
        </div>
      </section>
      <section className="dashboard-grid lower-grid">
        <div className="panel team-panel">
          <PanelHeader
            title={tr(locale, "teamToday")}
            sub={tr(locale, "capacityDelivery")}
            action={tr(locale, "teamView")}
            onAction={() => navigate("Team")}
          />
          <div className="team-table table-head">
            <span>{locale === "ar" ? "عضو الفريق" : "Team member"}</span>
            <span>{tr(locale, "today")}</span>
            <span>{locale === "ar" ? "الاستغلال" : "Utilization"}</span>
            <span>{locale === "ar" ? "الحالة" : "Status"}</span>
          </div>
          {data.people.slice(0, 6).map((p) => (
            <div className="team-table" key={p.id}>
              <span className="person-cell">
                <i className="avatar" style={{ background: p.accent }}>
                  {p.initials}
                </i>
                <span>
                  <b>{p.name}</b>
                  <small>{p.position}</small>
                </span>
              </span>
              <span>
                <b>{p.scheduled}h</b>
                <small>
                  {p.completed}h {tr(locale, "completed")}
                </small>
              </span>
              <span>
                <b>{Math.round((p.scheduled / p.capacity) * 100)}%</b>
                <i className="mini-bar">
                  <i
                    style={{
                      width: `${Math.min(100, (p.scheduled / p.capacity) * 100)}%`,
                      background:
                        p.scheduled >= p.capacity ? "#f7a84a" : "#7566ff",
                    }}
                  />
                </i>
              </span>
              <span>
                <em
                  className={`status-dot ${p.scheduled >= p.capacity ? "busy" : "focus"}`}
                />
                {p.scheduled >= p.capacity
                  ? tr(locale, "atCapacity")
                  : tr(locale, "focused")}
              </span>
            </div>
          ))}
        </div>
        <div className="panel activity-panel">
          <PanelHeader
            title={tr(locale, "todaysActivity")}
            sub={tr(locale, "latestEvents")}
          />
          {data.activity.map((a, i) => (
            <div className="activity-row" key={i}>
              <span className={`activity-icon ${a.tone}`}>
                <Activity size={14} />
              </span>
              <div>
                <p>
                  <b>{a.user}</b> {a.text}
                </p>
                <span>
                  {a.project} · {a.time}
                </span>
              </div>
            </div>
          ))}
          <button className="text-button" onClick={() => navigate("Reports")}>
            {locale === "ar" ? "فتح كامل النشاط" : "Open full activity"}{" "}
            <ArrowRight size={15} />
          </button>
        </div>
      </section>
    </>
  );
}

function Metric({
  label,
  value,
  note,
  icon: Icon,
  tone,
  warning,
}: {
  label: string;
  value: string | number;
  note: string;
  icon: any;
  tone: string;
  warning?: boolean;
}) {
  return (
    <div className="metric-card">
      <div className={`metric-icon ${tone}`}>
        <Icon size={19} />
      </div>
      <div className="metric-label">
        {label}
        <MoreHorizontal size={16} />
      </div>
      <strong>{value}</strong>
      <span className={warning ? "metric-warning" : ""}>{note}</span>
    </div>
  );
}
function PanelHeader({
  title,
  sub,
  action,
  onAction,
}: {
  title: string;
  sub: string;
  action?: string;
  onAction?: () => void;
}) {
  return (
    <div className="panel-header">
      <div>
        <h2>{title}</h2>
        <p>{sub}</p>
      </div>
      {action && (
        <button onClick={onAction}>
          {action}
          <ArrowRight size={14} />
        </button>
      )}
    </div>
  );
}
function ProjectRow({
  project,
  onOpen,
}: {
  project: Project;
  onOpen: () => void;
}) {
  return (
    <div className="project-row">
      <span
        className="project-glyph"
        style={{ background: `${project.accent}22`, color: project.accent }}
      >
        {project.code.slice(0, 2)}
      </span>
      <div className="project-main">
        <div>
          <b>{project.name}</b>
          <span
            className={`health ${project.health.toLowerCase().replace(" ", "-")}`}
          >
            {project.health}
          </span>
        </div>
        <span>
          {project.code} · {project.phase}
        </span>
      </div>
      <div className="progress-cell">
        <div>
          <span>Progress</span>
          <b>{project.progress}%</b>
        </div>
        <i>
          <i
            style={{
              width: `${project.progress}%`,
              background: project.accent,
            }}
          />
        </i>
      </div>
      <div className="deadline-cell">
        <span>Deadline</span>
        <b>{project.deadline}</b>
      </div>
      <div className="avatar-stack">
        {project.team.slice(0, 3).map((id, i) => (
          <i
            key={id}
            className="avatar"
            style={{
              background: seedPeople.find((p) => p.id === id)?.accent,
              zIndex: 4 - i,
            }}
          >
            {seedPeople.find((p) => p.id === id)?.initials}
          </i>
        ))}
      </div>
      <button
        className="icon-button"
        onClick={onOpen}
        aria-label={`Open ${project.name}`}
      >
        <MoreHorizontal size={17} />
      </button>
    </div>
  );
}
function Attention({
  icon: Icon,
  tone,
  title,
  text,
  tag,
  onClick,
}: {
  icon: any;
  tone: string;
  title: string;
  text: string;
  tag: string;
  onClick?: () => void;
}) {
  return (
    <button className="attention-row" onClick={onClick}>
      <span className={`attention-icon ${tone}`}>
        <Icon size={17} />
      </span>
      <span>
        <b>{title}</b>
        <p>{text}</p>
        <em>
          {tag}
          <ArrowRight size={13} />
        </em>
      </span>
    </button>
  );
}

function ProjectsView({
  locale,
  data,
  onNew,
  onTask,
  canManage,
  onEdit,
  onArchive,
}: {
  locale: Locale;
  data: Data;
  onNew: () => void;
  onTask: (id: string) => void;
  canManage: boolean;
  onEdit: (project: Project) => void;
  onArchive: (project: Project) => void;
}) {
  const [filter, setFilter] = useState<"all" | "risk" | "healthy">("all");
  const [query, setQuery] = useState("");
  const atRisk = data.projects.filter((project) =>
    ["At Risk", "Critical"].includes(project.health),
  ).length;
  const healthy = data.projects.filter(
    (project) => project.health === "Healthy",
  ).length;
  const visibleProjects = data.projects.filter((project) => {
    const matchesStatus =
      filter === "all" ||
      (filter === "risk" && ["At Risk", "Critical"].includes(project.health)) ||
      (filter === "healthy" && project.health === "Healthy");
    const search = query.trim().toLowerCase();
    return (
      matchesStatus &&
      (!search ||
        [project.name, project.code, project.client, project.description].some(
          (value) => value.toLowerCase().includes(search),
        ))
    );
  });
  return (
    <>
      <section className="page-heading">
        <div>
          <span className="eyebrow">{tr(locale, "portfolio")}</span>
          <h1>{tr(locale, "projects")}</h1>
          <p>{tr(locale, "projectsSubtitle")}</p>
        </div>
        {canManage && (
          <button className="primary-button" onClick={onNew}>
            <Plus size={17} />
            {tr(locale, "newProject")}
          </button>
        )}
      </section>
      <div className="filter-row">
        <button
          className={filter === "all" ? "filter-active" : ""}
          onClick={() => setFilter("all")}
        >
          {locale === "ar" ? "نشطة" : "Active"} <b>{data.projects.length}</b>
        </button>
        <button
          className={filter === "risk" ? "filter-active" : ""}
          onClick={() => setFilter("risk")}
        >
          {locale === "ar" ? "تحتاج انتباه" : "At risk"} <b>{atRisk}</b>
        </button>
        <button
          className={filter === "healthy" ? "filter-active" : ""}
          onClick={() => setFilter("healthy")}
        >
          {locale === "ar" ? "سليمة" : "Healthy"} <b>{healthy}</b>
        </button>
        <span />
        <label className="project-search-filter">
          <Search size={15} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={locale === "ar" ? "تصفية المشاريع" : "Filter projects"}
          />
        </label>
      </div>
      <section className="project-card-grid">
        {visibleProjects.map((p) => (
          <article className="project-card" key={p.id}>
            <div className="project-card-top">
              <span
                className="project-glyph large"
                style={{ background: `${p.accent}22`, color: p.accent }}
              >
                {p.code.slice(0, 2)}
              </span>
              <span
                className={`health ${p.health.toLowerCase().replace(" ", "-")}`}
              >
                {p.health}
              </span>
              {canManage ? (
                <div className="project-card-actions">
                  <button
                    className="icon-button"
                    onClick={() => onEdit(p)}
                    aria-label={
                      locale === "ar" ? "تعديل المشروع" : "Edit project"
                    }
                  >
                    <Pencil size={15} />
                  </button>
                  <button
                    className="icon-button danger-icon"
                    onClick={() => onArchive(p)}
                    aria-label={
                      locale === "ar" ? "أرشفة المشروع" : "Archive project"
                    }
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              ) : (
                <span className="icon-button static-control" aria-hidden="true">
                  <MoreHorizontal size={17} />
                </span>
              )}
            </div>
            <h2>{p.name}</h2>
            <p>{p.description}</p>
            <div className="project-meta">
              <span>
                <Target size={14} />
                {p.phase}
              </span>
              <span>
                <CalendarDays size={14} />
                {p.deadline}
              </span>
            </div>
            <div className="card-progress">
              <span>
                <b>{p.progress}%</b> {locale === "ar" ? "مكتمل" : "complete"}
              </span>
              <i>
                <i style={{ width: `${p.progress}%`, background: p.accent }} />
              </i>
            </div>
            <div className="project-card-foot">
              <div className="avatar-stack">
                {p.team.slice(0, 4).map((id) => (
                  <i
                    key={id}
                    className="avatar"
                    style={{
                      background: data.people.find((x) => x.id === id)?.accent,
                    }}
                  >
                    {data.people.find((x) => x.id === id)?.initials}
                  </i>
                ))}
              </div>
              <button
                onClick={() => {
                  const task = data.tasks.find((t) => t.projectId === p.id);
                  if (task) onTask(task.id);
                }}
              >
                {locale === "ar" ? "فتح المشروع" : "Open project"}{" "}
                <ArrowRight size={14} />
              </button>
            </div>
          </article>
        ))}
      </section>
    </>
  );
}

function TasksView({
  locale,
  data,
  onTask,
  canManage,
  onNew,
  onRebalance,
  rebalancing,
}: {
  locale: Locale;
  data: Data;
  onTask: (id: string) => void;
  canManage: boolean;
  onNew: () => void;
  onRebalance: () => Promise<unknown>;
  rebalancing: boolean;
}) {
  const groups = [
    "Blocked",
    "In Progress",
    "In Review",
    "Ready",
    "Completed",
  ] as const;
  return (
    <>
      <section className="page-heading">
        <div>
          <span className="eyebrow">{tr(locale, "delivery")}</span>
          <h1>{tr(locale, "tasks")}</h1>
          <p>{tr(locale, "tasksSubtitle")}</p>
        </div>
        {canManage && (
          <div className="heading-actions">
            <button
              className="secondary-button"
              onClick={() => void onRebalance()}
              disabled={rebalancing}
            >
              <CircleGauge size={16} />
              {rebalancing
                ? locale === "ar"
                  ? "جارٍ الترتيب…"
                  : "Scheduling…"
                : locale === "ar"
                  ? "ترتيب وتوزيع العمل"
                  : "Rebalance work"}
            </button>
            <button className="primary-button" onClick={onNew}>
              <Plus size={16} />
              {locale === "ar" ? "إضافة مهمة" : "Add task"}
            </button>
          </div>
        )}
      </section>
      <div className="task-board">
        {groups.map((status) => (
          <section className="task-column" key={status}>
            <header>
              <span
                className={`status-dot ${status.toLowerCase().replace(" ", "-")}`}
              />
              <b>{status}</b>
              <em>{data.tasks.filter((t) => t.status === status).length}</em>
              <MoreHorizontal size={16} />
            </header>
            {data.tasks
              .filter((t) => t.status === status)
              .map((t) => (
                <button
                  className="task-card"
                  key={t.id}
                  onClick={() => onTask(t.id)}
                >
                  <span className={`priority ${t.priority.toLowerCase()}`}>
                    {t.priority}
                  </span>
                  <b>{t.title}</b>
                  <p>{data.projects.find((p) => p.id === t.projectId)?.name}</p>
                  <div>
                    <span>
                      <Clock3 size={13} />
                      {t.estimate}h
                    </span>
                    <i
                      className="avatar"
                      style={{
                        background: data.people.find(
                          (p) => p.id === t.assigneeId,
                        )?.accent,
                      }}
                    >
                      {data.people.find((p) => p.id === t.assigneeId)?.initials}
                    </i>
                  </div>
                </button>
              ))}
          </section>
        ))}
      </div>
    </>
  );
}

function TeamView({
  locale,
  data,
  onAdd,
  onRemove,
}: {
  locale: Locale;
  data: Data;
  onAdd: () => void;
  onRemove: (person: Person) => void;
}) {
  return (
    <>
      <section className="page-heading">
        <div>
          <span className="eyebrow">{tr(locale, "peopleLabel")}</span>
          <h1>{tr(locale, "teamTitle")}</h1>
          <p>{tr(locale, "teamSubtitle")}</p>
        </div>
        <button className="primary-button" onClick={onAdd}>
          <UserPlus size={17} />
          {tr(locale, "addEmployee")}
        </button>
      </section>
      <section className="people-grid">
        {data.people.map((p) => (
          <article className="person-card" key={p.id}>
            <div>
              <i className="avatar xl" style={{ background: p.accent }}>
                {p.initials}
              </i>
              <span
                className={`availability ${p.scheduled >= p.capacity ? "busy" : ""}`}
              />
            </div>
            <h2>{p.name}</h2>
            <p>{p.position}</p>
            <span>
              {p.department} ·{" "}
              {p.role === "viewer"
                ? tr(locale, "viewer")
                : tr(locale, "employee")}
            </span>
            <div className="skills">
              {p.skills.slice(0, 3).map((s) => (
                <em key={s}>{s}</em>
              ))}
              {p.skills.length > 3 && <em>+{p.skills.length - 3}</em>}
            </div>
            <div className="capacity">
              <span>
                <b>
                  {p.scheduled} / {p.capacity}h
                </b>{" "}
                {tr(locale, "today")}
              </span>
              <strong>{Math.round((p.scheduled / p.capacity) * 100)}%</strong>
              <i>
                <i
                  style={{
                    width: `${Math.min(100, (p.scheduled / p.capacity) * 100)}%`,
                    background: p.accent,
                  }}
                />
              </i>
            </div>
            <div className="person-actions">
              <button
                className="danger-text-button"
                onClick={() => onRemove(p)}
              >
                <UserRoundX size={14} />
                {tr(locale, "removeEmployee")}
              </button>
            </div>
          </article>
        ))}
      </section>
    </>
  );
}

function WorkloadView({ locale, data }: { locale: Locale; data: Data }) {
  const [fallbackDates] = useState(() => {
    const dates: string[] = [];
    const cursor = new Date();
    cursor.setHours(12, 0, 0, 0);
    while (dates.length < 7) {
      if (cursor.getDay() !== 0 && cursor.getDay() !== 6)
        dates.push(cursor.toISOString().slice(0, 10));
      cursor.setDate(cursor.getDate() + 1);
    }
    return dates;
  });
  const scheduledDates = [
    ...new Set(data.schedules.map((row) => row.workDate)),
  ].sort();
  const dates = (scheduledDates.length ? scheduledDates : fallbackDates).slice(
    0,
    7,
  );
  const formatDate = (value: string) =>
    new Date(`${value}T12:00:00`).toLocaleDateString(
      locale === "ar" ? "ar-JO" : "en-GB",
      { weekday: "short", day: "numeric", month: "short" },
    );
  return (
    <>
      <section className="page-heading">
        <div>
          <span className="eyebrow">{tr(locale, "capacity")}</span>
          <h1>{tr(locale, "workloadTitle")}</h1>
          <p>{tr(locale, "workloadSubtitle")}</p>
        </div>
        <span className="secondary-button static-control">
          <CalendarDays size={16} />
          {dates[0] ? formatDate(dates[0]) : "—"}
          {" — "}
          {dates.at(-1) ? formatDate(dates.at(-1)!) : "—"}
        </span>
      </section>
      <section className="panel workload-panel">
        <div className="workload-legend">
          <b>{locale === "ar" ? "سعة الفريق" : "Team capacity"}</b>
          <span>
            <i className="legend under" />
            {locale === "ar" ? "متاح" : "Available"}
          </span>
          <span>
            <i className="legend balanced" />
            {locale === "ar" ? "متوازن" : "Balanced"}
          </span>
          <span>
            <i className="legend over" />
            {tr(locale, "atCapacity")}
          </span>
        </div>
        <div className="workload-head">
          <span>{locale === "ar" ? "عضو الفريق" : "Team member"}</span>
          {dates.map((date) => (
            <span key={date}>{formatDate(date)}</span>
          ))}
        </div>
        {data.people.map((p) => (
          <div className="workload-row" key={p.id}>
            <span className="person-cell">
              <i className="avatar" style={{ background: p.accent }}>
                {p.initials}
              </i>
              <span>
                <b>{p.name}</b>
                <small>{p.position}</small>
              </span>
            </span>
            {dates.map((date) => {
              const hours = data.schedules
                .filter((row) => row.userId === p.id && row.workDate === date)
                .reduce((total, row) => total + row.plannedHours, 0);
              const val = Math.round((hours / Math.max(1, p.capacity)) * 100);
              return (
                <span
                  key={date}
                  className={`load-cell ${val >= 100 ? "over" : val < 65 ? "under" : "balanced"}`}
                >
                  <b>{val}%</b>
                  <small>{hours.toFixed(1)}h</small>
                </span>
              );
            })}
          </div>
        ))}
      </section>
    </>
  );
}

function MyWorkView({
  locale,
  data,
  onTask,
  userId,
}: {
  locale: Locale;
  data: Data;
  onTask: (id: string) => void;
  userId: string;
}) {
  const mine = data.tasks.filter(
    (t) => t.assigneeId === userId && t.status !== "Completed",
  );
  const userSchedules = data.schedules.filter((row) => row.userId === userId);
  const scheduleDate = [
    ...new Set(userSchedules.map((row) => row.workDate)),
  ].sort()[0];
  const todayRows = scheduleDate
    ? userSchedules.filter((row) => row.workDate === scheduleDate)
    : mine.map((task) => ({
        id: `fallback-${task.id}`,
        userId,
        taskId: task.id,
        workDate: new Date().toISOString().slice(0, 10),
        startTime: task.start,
        plannedHours: Math.min(task.estimate, 8),
        status: "planned",
      }));
  const plannedHours = todayRows.reduce(
    (sum, row) => sum + row.plannedHours,
    0,
  );
  const plannedTasks = todayRows
    .map((row) => ({
      row,
      task: data.tasks.find((task) => task.id === row.taskId),
    }))
    .filter((item) => item.task);
  const projectCount = new Set(plannedTasks.map((item) => item.task!.projectId))
    .size;
  const currentTask = plannedTasks[0]?.task ?? mine[0];
  const scheduleLabel = new Date(
    `${scheduleDate ?? new Date().toISOString().slice(0, 10)}T12:00:00`,
  ).toLocaleDateString(locale === "ar" ? "ar-JO" : "en-US", {
    weekday: "long",
    month: "short",
    day: "numeric",
  });
  return (
    <>
      <section className="page-heading">
        <div>
          <span className="eyebrow">{tr(locale, "yourDay")}</span>
          <h1>{tr(locale, "todayPlan")}</h1>
          <p>
            {plannedTasks.length} {locale === "ar" ? "مهام" : "tasks"} ·{" "}
            {plannedHours.toFixed(1)} / 8{" "}
            {locale === "ar" ? "ساعات مجدولة" : "scheduled hours"} ·{" "}
            {projectCount} {locale === "ar" ? "مشاريع" : "projects"}
          </p>
        </div>
        <button
          className="primary-button"
          onClick={() => currentTask && onTask(currentTask.id)}
          disabled={!currentTask}
        >
          <Play size={16} />
          {locale === "ar" ? "بدء المهمة الحالية" : "Start current task"}
        </button>
      </section>
      <div className="day-grid">
        <section className="panel schedule-panel">
          <PanelHeader
            title={`${locale === "ar" ? "جدول" : "Schedule"} ${scheduleLabel}`}
            sub={
              locale === "ar"
                ? `حماية ${plannedHours.toFixed(1)} من 8 ساعات عمل هندسي مركّز بعد استخدام AI`
                : `${plannedHours.toFixed(1)} of 8 focused engineering hours protected after AI assistance`
            }
          />
          {plannedTasks.map(({ row, task: t }) => (
            <button
              key={row.id}
              className="schedule-row"
              onClick={() => onTask(t!.id)}
            >
              <span>{row.startTime}</span>
              <i
                style={{
                  background: data.projects.find((p) => p.id === t!.projectId)
                    ?.accent,
                }}
              />
              <div>
                <b>{t!.title}</b>
                <small>
                  {data.projects.find((p) => p.id === t!.projectId)?.name}
                </small>
              </div>
              <em>{row.plannedHours}h</em>
              <ArrowRight size={15} />
            </button>
          ))}
        </section>
        <section className="panel focus-panel">
          <span className="focus-badge">
            <Zap size={14} />
            {locale === "ar" ? "التركيز الحالي" : "Current focus"}
          </span>
          <h2>{currentTask?.title}</h2>
          <p>{currentTask?.description}</p>
          <div className="focus-stats">
            <span>
              <small>{locale === "ar" ? "المقدّر" : "Estimated"}</small>
              <b>{currentTask?.estimate}h</b>
            </span>
            <span>
              <small>{locale === "ar" ? "المنقضي" : "Elapsed"}</small>
              <b>{currentTask?.actual}h</b>
            </span>
            <span>
              <small>{locale === "ar" ? "الاستحقاق" : "Due"}</small>
              <b>{tr(locale, "today")}</b>
            </span>
          </div>
          <button
            className="primary-button"
            onClick={() => currentTask && onTask(currentTask.id)}
          >
            <Play size={16} />
            {locale === "ar" ? "متابعة العمل" : "Resume work"}
          </button>
        </section>
      </div>
    </>
  );
}

function AssistantView({ locale, data }: { locale: Locale; data: Data }) {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      text:
        locale === "ar"
          ? "أنا مرتبط ببيانات المشاريع والمهام والسعة. اسألني ما الذي يحتاج انتباهاً أو من لديه وقت غداً."
          : "I’m grounded in your project, task and capacity data. Ask me what needs attention or who has room tomorrow.",
    },
  ]);
  const [input, setInput] = useState("");
  const send = () => {
    if (!input.trim()) return;
    const q = input;
    setMessages((m) => [...m, { role: "user", text: q }]);
    setInput("");
    setTimeout(() => {
      const free = [...data.people].sort(
        (a, b) => a.scheduled / a.capacity - b.scheduled / b.capacity,
      )[0];
      const riskProjects = data.projects.filter((project) =>
        ["At Risk", "Critical"].includes(project.health),
      );
      const blockedTasks = data.tasks.filter(
        (task) => task.status === "Blocked",
      );
      const normalized = q.toLowerCase();
      const asksCapacity =
        normalized.includes("capacity") ||
        normalized.includes("سعة") ||
        normalized.includes("متاح");
      const asksRisk =
        normalized.includes("risk") ||
        normalized.includes("خطر") ||
        normalized.includes("مخاطر");
      const answer = asksCapacity
        ? locale === "ar"
          ? `${free.name} لديه أعلى سعة متاحة اليوم: ${Math.max(0, free.capacity - free.scheduled).toFixed(1)} ساعة من أصل ${free.capacity}.`
          : `${free.name} has the most available capacity today: ${Math.max(0, free.capacity - free.scheduled).toFixed(1)} of ${free.capacity} hours.`
        : asksRisk
          ? locale === "ar"
            ? riskProjects.length
              ? `المشاريع التي تحتاج متابعة: ${riskProjects.map((project) => `${project.name} (${project.health}, المتوقع ${project.predicted})`).join("، ")}. توجد ${blockedTasks.length} مهام متوقفة.`
              : `لا توجد مشاريع عالية المخاطر حاليًا، ويوجد ${blockedTasks.length} مهام متوقفة.`
            : riskProjects.length
              ? `Projects needing attention: ${riskProjects.map((project) => `${project.name} (${project.health}, forecast ${project.predicted})`).join(", ")}. There are ${blockedTasks.length} blocked tasks.`
              : `No projects are currently high risk; ${blockedTasks.length} tasks are blocked.`
          : locale === "ar"
            ? `يوجد ${data.projects.length} مشروعًا و${data.tasks.filter((task) => task.status !== "Completed").length} مهمة نشطة. الأولوية الآن للمهام قيد التنفيذ ثم الاختبار والمراجعة، والجداول مبنية على 8 ساعات يوميًا لكل شخص.`
            : `There are ${data.projects.length} projects and ${data.tasks.filter((task) => task.status !== "Completed").length} active tasks. Work in progress, testing and review come first, with schedules capped at 8 hours per person per day.`;
      setMessages((m) => [...m, { role: "assistant", text: answer }]);
    }, 450);
  };
  return (
    <div className="assistant-layout">
      <section className="assistant-copy">
        <span className="eyebrow">{tr(locale, "assistantLabel")}</span>
        <h1>
          {locale === "ar" ? "اسأل قسمك." : "Ask your division."}
          <br />
          <em>
            {locale === "ar"
              ? "واحصل على إجابة تشغيلية."
              : "Get an operational answer."}
          </em>
        </h1>
        <p>
          {locale === "ar"
            ? "كل إجابة مبنية على المشاريع المعتمدة والجداول وسجل التدقيق، دون اختلاق أي حالة."
            : "Every response is built from approved projects, schedules and audit history — never invented status."}
        </p>
        <div>
          {(locale === "ar"
            ? [
                "ما المشاريع المعرّضة للخطر؟",
                "من لديه سعة متاحة غداً؟",
                "ما العمل المتبقي هذا الأسبوع؟",
              ]
            : [
                "Which projects are at risk?",
                "Who has free capacity tomorrow?",
                "What work remains this week?",
              ]
          ).map((q) => (
            <button key={q} onClick={() => setInput(q)}>
              <Sparkles size={15} />
              {q}
            </button>
          ))}
        </div>
      </section>
      <section className="chat-panel">
        <header>
          <span className="assistant-orb">
            <Bot size={20} />
          </span>
          <div>
            <b>{locale === "ar" ? "مساعد نوفا" : "Nova Assistant"}</b>
            <small>
              <i />
              {locale === "ar"
                ? "متصل ببيانات مساحة العمل المباشرة"
                : "Connected to live workspace data"}
            </small>
          </div>
          <MoreHorizontal size={18} />
        </header>
        <div className="messages">
          {messages.map((m, i) => (
            <div key={i} className={`message ${m.role}`}>
              <span>{m.role === "assistant" ? <Bot size={16} /> : "AN"}</span>
              <p>{m.text}</p>
            </div>
          ))}
        </div>
        <div className="composer">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            placeholder={
              locale === "ar"
                ? "اسأل عن المشاريع أو السعة أو مخاطر التسليم..."
                : "Ask about projects, capacity or delivery risk..."
            }
          />
          <button onClick={send}>
            <ArrowRight size={17} />
          </button>
          <small>
            {locale === "ar"
              ? "الإجابات تستخدم بيانات مساحة العمل · Enter للإرسال"
              : "Answers use workspace data · Enter to send"}
          </small>
        </div>
      </section>
    </div>
  );
}

function ComingView({
  locale,
  title,
  onOpen,
}: {
  locale: Locale;
  title: string;
  onOpen: () => void;
}) {
  return (
    <div className="empty-view">
      <span>
        <CalendarDays size={26} />
      </span>
      <h1>{tr(locale, navKey[title as keyof typeof navKey])}</h1>
      <p>
        {locale === "ar"
          ? "هذا العرض التشغيلي جاهز للبيانات والفلاتر المتصلة."
          : "This operational view is ready for connected data and filters."}
      </p>
      <button className="primary-button" onClick={onOpen}>
        {locale === "ar"
          ? title === "Reports"
            ? "فتح بيانات المهام"
            : "فتح جدولي"
          : title === "Reports"
            ? "Open task data"
            : "Open my schedule"}
      </button>
    </div>
  );
}

function CommandPalette({
  locale,
  data,
  close,
  navigate,
  openTask,
}: {
  locale: Locale;
  data: Data;
  close: () => void;
  navigate: (n: any) => void;
  openTask: (id: string) => void;
}) {
  const [q, setQ] = useState("");
  const results = useMemo(
    () =>
      [
        ...data.projects.map((p) => ({
          id: p.id,
          label: p.name,
          type: "Project",
          action: () => {
            navigate("Projects");
            close();
          },
        })),
        ...data.tasks.map((t) => ({
          id: t.id,
          label: t.title,
          type: "Task",
          action: () => openTask(t.id),
        })),
        ...nav.map((n) => ({
          id: n,
          label: n,
          type: "Navigate",
          action: () => {
            navigate(n);
            close();
          },
        })),
      ]
        .filter((x) => x.label.toLowerCase().includes(q.toLowerCase()))
        .slice(0, 9),
    [q, data],
  );
  return (
    <div className="modal-scrim" onMouseDown={close}>
      <div className="command-modal" onMouseDown={(e) => e.stopPropagation()}>
        <div className="command-input">
          <Search size={19} />
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={
              locale === "ar"
                ? "ابحث في المشاريع والمهام والأشخاص والأوامر..."
                : "Search projects, tasks, people or commands..."
            }
          />
          <kbd>ESC</kbd>
        </div>
        <div className="command-results">
          <span>{locale === "ar" ? "أفضل النتائج" : "Best matches"}</span>
          {results.map((r) => (
            <button key={r.type + r.id} onClick={r.action}>
              <i>
                {r.type === "Project" ? (
                  <FolderKanban size={16} />
                ) : r.type === "Task" ? (
                  <CheckCircle2 size={16} />
                ) : (
                  <Command size={16} />
                )}
              </i>
              <b>{r.label}</b>
              <em>{r.type}</em>
              <ArrowRight size={14} />
            </button>
          ))}
          {!results.length && (
            <p>{locale === "ar" ? "لا توجد نتائج." : "No results found."}</p>
          )}
        </div>
        <footer>
          <span>
            <kbd>↑↓</kbd> {locale === "ar" ? "تنقل" : "Navigate"}
          </span>
          <span>
            <kbd>↵</kbd> {locale === "ar" ? "فتح" : "Open"}
          </span>
          <span>
            {locale === "ar" ? "بدعم بحث نوفا" : "Powered by Nova Search"}
          </span>
        </footer>
      </div>
    </div>
  );
}

function TaskModal({
  locale,
  data,
  close,
  save,
}: {
  locale: Locale;
  data: Data;
  close: () => void;
  save: (task: {
    projectId: string;
    title: string;
    description: string;
    assigneeId: string;
    priority: Task["priority"];
    estimate: number;
    due: string;
    requiredSkills: string[];
    acceptance: string[];
  }) => Promise<void>;
}) {
  const [projectId, setProjectId] = useState(data.projects[0]?.id ?? "");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [assigneeId, setAssigneeId] = useState(data.people[0]?.id ?? "");
  const [priority, setPriority] = useState<Task["priority"]>("High");
  const [estimate, setEstimate] = useState(4);
  const [due, setDue] = useState(() => {
    const date = new Date();
    date.setDate(date.getDate() + 1);
    return date.toISOString().slice(0, 10);
  });
  const [skills, setSkills] = useState("OpenAI API, Testing");
  const [acceptance, setAcceptance] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await save({
        projectId,
        title,
        description,
        assigneeId,
        priority,
        estimate,
        due,
        requiredSkills: skills
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        acceptance: acceptance
          .split("\n")
          .map((item) => item.trim())
          .filter(Boolean),
      });
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : locale === "ar"
            ? "تعذر إنشاء المهمة"
            : "The task could not be created",
      );
      setSaving(false);
    }
  };
  return (
    <div className="modal-scrim">
      <form className="employee-modal task-modal" onSubmit={submit}>
        <header>
          <div>
            <span className="brand-mark">
              <ListChecks size={17} />
            </span>
            <div>
              <b>{locale === "ar" ? "إضافة مهمة جديدة" : "Add a new task"}</b>
              <small>
                {locale === "ar"
                  ? "مهمة يومية بحد أقصى 8 ساعات"
                  : "A focused daily task capped at 8 hours"}
              </small>
            </div>
          </div>
          <button type="button" className="icon-button" onClick={close}>
            <X size={18} />
          </button>
        </header>
        <div className="modal-body">
          <div className="field-pair">
            <label>
              {locale === "ar" ? "المشروع" : "Project"}
              <select
                required
                value={projectId}
                onChange={(event) => setProjectId(event.target.value)}
              >
                {data.projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {locale === "ar" ? "المسؤول" : "Assignee"}
              <select
                required
                value={assigneeId}
                onChange={(event) => setAssigneeId(event.target.value)}
              >
                {data.people
                  .filter((person) =>
                    ["manager", "employee"].includes(person.role),
                  )
                  .map((person) => (
                    <option key={person.id} value={person.id}>
                      {person.name} — {person.position}
                    </option>
                  ))}
              </select>
            </label>
          </div>
          <label>
            {locale === "ar" ? "عنوان المهمة" : "Task title"}
            <input
              required
              minLength={3}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder={
                locale === "ar"
                  ? "مثال: اختبار إجابات أسعار السيارات"
                  : "e.g. Evaluate vehicle pricing answers"
              }
            />
          </label>
          <label>
            {locale === "ar" ? "وصف التنفيذ" : "Implementation brief"}
            <textarea
              required
              minLength={8}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder={
                locale === "ar"
                  ? "اشرح المطلوب والبيانات والنتيجة المتوقعة..."
                  : "Describe the work, inputs and expected result..."
              }
            />
          </label>
          <div className="field-pair task-field-trio">
            <label>
              {locale === "ar" ? "الأولوية" : "Priority"}
              <select
                value={priority}
                onChange={(event) =>
                  setPriority(event.target.value as Task["priority"])
                }
              >
                <option>Critical</option>
                <option>High</option>
                <option>Medium</option>
                <option>Low</option>
              </select>
            </label>
            <label>
              {locale === "ar" ? "الساعات" : "Hours"}
              <input
                type="number"
                min={0.5}
                max={8}
                step={0.5}
                value={estimate}
                onChange={(event) => setEstimate(Number(event.target.value))}
              />
            </label>
            <label>
              {locale === "ar" ? "الموعد النهائي" : "Deadline"}
              <input
                required
                type="date"
                value={due}
                onChange={(event) => setDue(event.target.value)}
              />
            </label>
          </div>
          <label>
            {locale === "ar" ? "المهارات المطلوبة" : "Required skills"}
            <input
              required
              value={skills}
              onChange={(event) => setSkills(event.target.value)}
            />
            <small className="field-help">
              {locale === "ar"
                ? "افصل المهارات بفاصلة"
                : "Separate skills with commas"}
            </small>
          </label>
          <label>
            {locale === "ar" ? "معايير القبول" : "Acceptance criteria"}
            <textarea
              required
              value={acceptance}
              onChange={(event) => setAcceptance(event.target.value)}
              placeholder={
                locale === "ar"
                  ? "اكتب كل معيار في سطر منفصل"
                  : "Write one criterion per line"
              }
            />
          </label>
          {error && (
            <div className="form-error">
              <AlertTriangle size={15} /> {error}
            </div>
          )}
        </div>
        <footer>
          <button type="button" className="secondary-button" onClick={close}>
            {tr(locale, "cancel")}
          </button>
          <button className="primary-button" disabled={saving}>
            {saving
              ? locale === "ar"
                ? "جارٍ الإضافة والجدولة…"
                : "Adding and scheduling…"
              : locale === "ar"
                ? "إضافة وجدولة"
                : "Add and schedule"}
          </button>
        </footer>
      </form>
    </div>
  );
}

function EmployeeModal({
  locale,
  close,
  save,
}: {
  locale: Locale;
  close: () => void;
  save: (employee: {
    fullName: string;
    email: string;
    position: string;
    department: string;
    role: "employee" | "viewer";
    dailyCapacity: number;
    skills: string[];
    temporaryPassword: string;
  }) => Promise<void>;
}) {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [position, setPosition] = useState("AI Engineer");
  const [department, setDepartment] = useState("Applied AI");
  const [role, setRole] = useState<"employee" | "viewer">("employee");
  const [dailyCapacity, setDailyCapacity] = useState(8);
  const [skills, setSkills] = useState("Python, OpenAI API");
  const [temporaryPassword, setTemporaryPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await save({
        fullName,
        email,
        position,
        department,
        role,
        dailyCapacity,
        skills: skills
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        temporaryPassword,
      });
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : tr(locale, "employeeError"),
      );
    } finally {
      setSaving(false);
    }
  };
  return (
    <div className="modal-scrim">
      <form className="employee-modal" onSubmit={submit}>
        <header>
          <div>
            <span className="brand-mark">
              <UserPlus size={17} />
            </span>
            <div>
              <b>{tr(locale, "addEmployeeTitle")}</b>
              <small>{tr(locale, "profileBasics")}</small>
            </div>
          </div>
          <button type="button" className="icon-button" onClick={close}>
            <X size={18} />
          </button>
        </header>
        <div className="modal-body">
          <div className="field-pair">
            <label>
              {tr(locale, "fullName")}
              <input
                required
                minLength={2}
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder={
                  locale === "ar" ? "مثال: سارة أحمد" : "e.g. Sara Ahmad"
                }
              />
            </label>
            <label>
              {tr(locale, "email")}
              <input
                required
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@company.com"
              />
            </label>
          </div>
          <div className="field-pair">
            <label>
              {tr(locale, "position")}
              <select
                value={position}
                onChange={(e) => setPosition(e.target.value)}
              >
                {[
                  "AI Engineer",
                  "Senior AI Engineer",
                  "ML Engineer",
                  "Data Engineer",
                  "Backend Engineer",
                  "Frontend Engineer",
                  "Full Stack Developer",
                  "DevOps Engineer",
                  "QA Engineer",
                  "UI/UX Designer",
                  "Project Manager",
                ].map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </label>
            <label>
              {tr(locale, "department")}
              <input
                required
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
              />
            </label>
          </div>
          <div className="field-pair">
            <label>
              {tr(locale, "accessRole")}
              <select
                value={role}
                onChange={(e) =>
                  setRole(e.target.value as "employee" | "viewer")
                }
              >
                <option value="employee">{tr(locale, "employee")}</option>
                <option value="viewer">{tr(locale, "viewer")}</option>
              </select>
            </label>
            <label>
              {tr(locale, "dailyCapacity")}
              <select
                value={dailyCapacity}
                onChange={(e) => setDailyCapacity(Number(e.target.value))}
              >
                {[4, 6, 7, 8].map((hours) => (
                  <option key={hours} value={hours}>
                    {hours} {locale === "ar" ? "ساعات" : "hours"}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label>
            {tr(locale, "skills")}
            <input
              required
              value={skills}
              onChange={(e) => setSkills(e.target.value)}
            />
            <small className="field-help">{tr(locale, "skillsHelp")}</small>
          </label>
          <label>
            {locale === "ar" ? "كلمة مرور مؤقتة" : "Temporary password"}
            <input
              required
              type="password"
              minLength={10}
              autoComplete="new-password"
              value={temporaryPassword}
              onChange={(e) => setTemporaryPassword(e.target.value)}
              placeholder={
                locale === "ar" ? "10 أحرف على الأقل" : "At least 10 characters"
              }
            />
            <small className="field-help">
              {locale === "ar"
                ? "سلّمها للموظف عبر قناة آمنة."
                : "Share it with the employee through a secure channel."}
            </small>
          </label>
          {error && (
            <div className="form-error">
              <AlertTriangle size={15} />
              {error}
            </div>
          )}
        </div>
        <footer>
          <button type="button" className="secondary-button" onClick={close}>
            {tr(locale, "cancel")}
          </button>
          <button className="primary-button" disabled={saving}>
            {saving ? tr(locale, "saving") : tr(locale, "saveEmployee")}
          </button>
        </footer>
      </form>
    </div>
  );
}

function DeactivateEmployeeModal({
  locale,
  person,
  tasks,
  close,
  confirm,
}: {
  locale: Locale;
  person: Person;
  tasks: Task[];
  close: () => void;
  confirm: (person: Person) => Promise<void>;
}) {
  const [working, setWorking] = useState(false),
    [error, setError] = useState("");
  const assigned = tasks.filter(
    (task) => task.assigneeId === person.id && task.status !== "Completed",
  ).length;
  const run = async () => {
    setWorking(true);
    setError("");
    try {
      await confirm(person);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : tr(locale, "employeeError"),
      );
      setWorking(false);
    }
  };
  return (
    <div className="modal-scrim">
      <div className="confirm-modal">
        <span className="confirm-icon">
          <UserRoundX size={23} />
        </span>
        <h2>{tr(locale, "removeTitle")}</h2>
        <div className="confirm-person">
          <i className="avatar" style={{ background: person.accent }}>
            {person.initials}
          </i>
          <span>
            <b>{person.name}</b>
            <small>{person.position}</small>
          </span>
        </div>
        <p>{tr(locale, "removeBody")}</p>
        {assigned > 0 && (
          <strong className="task-impact">
            <AlertTriangle size={15} />
            {assigned} {tr(locale, "activeAssignments")}
          </strong>
        )}
        {error && (
          <div className="form-error">
            <AlertTriangle size={15} />
            {error}
          </div>
        )}
        <footer>
          <button className="secondary-button" onClick={close}>
            {tr(locale, "keepEmployee")}
          </button>
          <button className="danger-button" onClick={run} disabled={working}>
            {working ? tr(locale, "removing") : tr(locale, "confirmRemove")}
          </button>
        </footer>
      </div>
    </div>
  );
}

function EditProjectModal({
  locale,
  project,
  people,
  close,
  save,
}: {
  locale: Locale;
  project: Project;
  people: Person[];
  close: () => void;
  save: (project: Project) => Promise<void>;
}) {
  const [draft, setDraft] = useState<Project>({ ...project });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const field = <K extends keyof Project>(key: K, value: Project[K]) =>
    setDraft((current) => ({ ...current, [key]: value }));
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await save({ ...draft, code: draft.code.trim().toUpperCase() });
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : locale === "ar"
            ? "تعذر حفظ المشروع"
            : "The project could not be saved",
      );
      setSaving(false);
    }
  };
  return (
    <div className="modal-scrim">
      <form className="employee-modal edit-project-modal" onSubmit={submit}>
        <header>
          <div>
            <span className="brand-mark">
              <Pencil size={17} />
            </span>
            <div>
              <b>{locale === "ar" ? "تعديل المشروع" : "Edit project"}</b>
              <small>
                {locale === "ar"
                  ? "حدّث التفاصيل والحالة والفريق"
                  : "Update details, status and ownership"}
              </small>
            </div>
          </div>
          <button type="button" className="icon-button" onClick={close}>
            <X size={18} />
          </button>
        </header>
        <div className="modal-body">
          <div className="field-pair">
            <label>
              {locale === "ar" ? "اسم المشروع" : "Project name"}
              <input
                required
                minLength={2}
                value={draft.name}
                onChange={(event) => field("name", event.target.value)}
              />
            </label>
            <label>
              {locale === "ar" ? "الرمز" : "Code"}
              <input
                required
                minLength={2}
                maxLength={24}
                value={draft.code}
                onChange={(event) => field("code", event.target.value)}
              />
            </label>
          </div>
          <label>
            {locale === "ar" ? "العميل / الجهة" : "Client / owner"}
            <input
              required
              value={draft.client}
              onChange={(event) => field("client", event.target.value)}
            />
          </label>
          <label>
            {locale === "ar" ? "الوصف والهدف" : "Description and goal"}
            <textarea
              required
              minLength={4}
              value={draft.description}
              onChange={(event) => field("description", event.target.value)}
            />
          </label>
          <div className="field-pair">
            <label>
              {locale === "ar" ? "المرحلة الحالية" : "Current phase"}
              <input
                required
                value={draft.phase}
                onChange={(event) => field("phase", event.target.value)}
              />
            </label>
            <label>
              {locale === "ar" ? "حالة المشروع" : "Project health"}
              <select
                value={draft.health}
                onChange={(event) =>
                  field("health", event.target.value as Project["health"])
                }
              >
                <option value="Healthy">Healthy</option>
                <option value="Watch">Watch</option>
                <option value="At Risk">At Risk</option>
                <option value="Critical">Critical</option>
              </select>
            </label>
          </div>
          <div className="field-pair">
            <label>
              {locale === "ar" ? "الموعد النهائي" : "Deadline"}
              <input
                required
                value={draft.deadline}
                onChange={(event) => field("deadline", event.target.value)}
              />
            </label>
            <label>
              {locale === "ar" ? "التاريخ المتوقع" : "Predicted delivery"}
              <input
                required
                value={draft.predicted}
                onChange={(event) => field("predicted", event.target.value)}
              />
            </label>
          </div>
          <div className="field-pair compact-fields">
            <label>
              {locale === "ar" ? "نسبة الإنجاز" : "Progress"}
              <input
                type="number"
                min={0}
                max={100}
                value={draft.progress}
                onChange={(event) =>
                  field("progress", Number(event.target.value))
                }
              />
            </label>
            <label>
              {locale === "ar" ? "لون المشروع" : "Project color"}
              <input
                className="color-input"
                type="color"
                value={draft.accent}
                onChange={(event) => field("accent", event.target.value)}
              />
            </label>
          </div>
          <fieldset className="team-picker">
            <legend>{locale === "ar" ? "فريق المشروع" : "Project team"}</legend>
            {people.map((person) => (
              <label key={person.id}>
                <input
                  type="checkbox"
                  checked={draft.team.includes(person.id)}
                  onChange={(event) =>
                    field(
                      "team",
                      event.target.checked
                        ? [...new Set([...draft.team, person.id])]
                        : draft.team.filter((id) => id !== person.id),
                    )
                  }
                />
                <i className="avatar" style={{ background: person.accent }}>
                  {person.initials}
                </i>
                <span>
                  <b>{person.name}</b>
                  <small>{person.position}</small>
                </span>
              </label>
            ))}
          </fieldset>
          {error && (
            <div className="form-error">
              <AlertTriangle size={15} />
              {error}
            </div>
          )}
        </div>
        <footer>
          <button type="button" className="secondary-button" onClick={close}>
            {tr(locale, "cancel")}
          </button>
          <button className="primary-button" disabled={saving}>
            {saving
              ? tr(locale, "saving")
              : locale === "ar"
                ? "حفظ التعديلات"
                : "Save changes"}
          </button>
        </footer>
      </form>
    </div>
  );
}

function ArchiveProjectModal({
  locale,
  project,
  close,
  confirm,
}: {
  locale: Locale;
  project: Project;
  close: () => void;
  confirm: (project: Project) => Promise<void>;
}) {
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const run = async () => {
    setWorking(true);
    setError("");
    try {
      await confirm(project);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : locale === "ar"
            ? "تعذرت أرشفة المشروع"
            : "The project could not be archived",
      );
      setWorking(false);
    }
  };
  return (
    <div className="modal-scrim">
      <div className="confirm-modal">
        <span className="confirm-icon project-archive-icon">
          <Trash2 size={23} />
        </span>
        <h2>{locale === "ar" ? "أرشفة المشروع؟" : "Archive project?"}</h2>
        <div className="archive-project-name">
          <i style={{ background: project.accent }} />
          <span>
            <b>{project.name}</b>
            <small>{project.code}</small>
          </span>
        </div>
        <p>
          {locale === "ar"
            ? "سيختفي المشروع ومهامه من مساحة العمل، لكن سنحتفظ بسجل النشاط والبيانات لأغراض المراجعة."
            : "The project and its tasks will leave the workspace, while activity and historical data remain available for audit."}
        </p>
        {error && (
          <div className="form-error">
            <AlertTriangle size={15} />
            {error}
          </div>
        )}
        <footer>
          <button className="secondary-button" onClick={close}>
            {locale === "ar" ? "إبقاء المشروع" : "Keep project"}
          </button>
          <button className="danger-button" onClick={run} disabled={working}>
            {working
              ? locale === "ar"
                ? "جارٍ الأرشفة…"
                : "Archiving…"
              : locale === "ar"
                ? "أرشفة المشروع"
                : "Archive project"}
          </button>
        </footer>
      </div>
    </div>
  );
}

function ProjectModal({
  locale,
  close,
  onCreated,
}: {
  locale: Locale;
  close: () => void;
  onCreated: (p: Project) => void;
}) {
  const [step, setStep] = useState(1),
    [name, setName] = useState(""),
    [desc, setDesc] = useState(""),
    [deadline, setDeadline] = useState("2026-09-30");
  const [planning, setPlanning] = useState(false),
    [plan, setPlan] = useState<{
      totalHours: number;
      phases: number;
      tasks: number;
      risks: number;
      source: string;
      raw: any;
      delivery: any;
    } | null>(null),
    [planError, setPlanError] = useState("");
  const prepare = async () => {
    setPlanning(true);
    setPlanError("");
    try {
      const response = await fetch("/api/ai/plan", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name, description: desc, deadline }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error?.message);
      setPlan({
        totalHours: payload.totalHours,
        phases: payload.plan.phases.length,
        tasks: payload.plan.phases.flatMap((p: any) => p.tasks).length,
        risks: payload.plan.risks.length,
        source: payload.source,
        raw: payload.plan,
        delivery: payload.delivery,
      });
      setStep(3);
    } catch (error) {
      setPlanError(
        error instanceof Error ? error.message : "Planning failed safely.",
      );
    } finally {
      setPlanning(false);
    }
  };
  const create = async () => {
    if (!plan) return;
    setPlanning(true);
    const project: Project = {
      id: `p-${Date.now()}`,
      code:
        name
          .split(" ")
          .map((w) => w[0])
          .join("")
          .slice(0, 3)
          .toUpperCase() + "-01",
      name,
      client: "Internal",
      description: desc,
      progress: 0,
      health: "Healthy",
      deadline,
      predicted: plan.delivery?.forecastDate ?? deadline,
      phase: plan.raw.phases[0]?.name ?? "Planning",
      team: [],
      accent: "#7566ff",
    };
    try {
      const response = await fetch("/api/actions", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          action: "create_project",
          project,
          plan: plan.raw,
          activate: true,
        }),
      });
      if (!response.ok) throw new Error();
      await onCreated(project);
    } catch {
      setPlanError(
        "The approved plan could not be activated. No partial project was created.",
      );
    } finally {
      setPlanning(false);
    }
  };
  return (
    <div className="modal-scrim">
      <div
        className={`project-modal ${step === 3 ? "plan-preview-modal" : ""}`}
      >
        <header>
          <div>
            <span className="brand-mark">
              <Sparkles size={17} />
            </span>
            <div>
              <b>
                {locale === "ar"
                  ? "إنشاء مشروع ذكاء اصطناعي"
                  : "Create AI project"}
              </b>
              <small>
                {locale === "ar" ? `الخطوة ${step} من 3` : `Step ${step} of 3`}
              </small>
            </div>
          </div>
          <button className="icon-button" onClick={close}>
            <X size={18} />
          </button>
        </header>
        <div className="stepper">
          {[1, 2, 3].map((n) => (
            <i key={n} className={n <= step ? "active" : ""} />
          ))}
        </div>
        {step === 1 && (
          <div className="modal-body">
            <span className="eyebrow">
              {locale === "ar" ? "أساس المشروع" : "PROJECT FOUNDATION"}
            </span>
            <h2>{locale === "ar" ? "ماذا سنبني؟" : "What are we building?"}</h2>
            <label>
              {locale === "ar" ? "اسم المشروع" : "Project name"}
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={
                  locale === "ar"
                    ? "مثال: مساعد المطالبات الذكي"
                    : "e.g. Intelligent Claims Assistant"
                }
              />
            </label>
            <label>
              {locale === "ar"
                ? "الوصف التجاري والتقني"
                : "Business and technical brief"}
              <textarea
                value={desc}
                onChange={(e) => setDesc(e.target.value)}
                placeholder={
                  locale === "ar"
                    ? "اشرح الهدف التجاري والمستخدمين والتكاملات والنتيجة المتوقعة..."
                    : "Describe the business goal, users, integrations and expected outcome..."
                }
              />
            </label>
            <div className="field-pair">
              <label>
                {locale === "ar" ? "الأولوية" : "Priority"}
                <select>
                  <option>High</option>
                  <option>Critical</option>
                  <option>Medium</option>
                  <option>Low</option>
                </select>
              </label>
              <label>
                {locale === "ar" ? "الموعد النهائي" : "Deadline"}
                <input
                  type="date"
                  value={deadline}
                  onChange={(e) => setDeadline(e.target.value)}
                />
              </label>
            </div>
          </div>
        )}
        {step === 2 && (
          <div className="modal-body ai-plan-step">
            <span className="ai-plan-icon">
              <Sparkles size={24} />
            </span>
            <span className="eyebrow">
              {locale === "ar" ? "تخطيط الذكاء الاصطناعي" : "AI PLANNING"}
            </span>
            <h2>
              {planning
                ? locale === "ar"
                  ? "جارٍ بناء خطة موثقة…"
                  : "Building a validated plan…"
                : locale === "ar"
                  ? "إنشاء مخطط التسليم"
                  : "Generate the delivery blueprint"}
            </h2>
            <p>
              {locale === "ar"
                ? "تقترح نوفا البنية والمراحل والمهام والمهارات والتقديرات والتبعيات. يتحقق الخادم من المخطط قبل عرضه، ولا يتم تفعيل شيء دون موافقتك."
                : "Nova proposes architecture, phases, tasks, skills, estimates and dependencies. The backend validates the schema before you see it; nothing becomes active without approval."}
            </p>
            <div className="plan-flow">
              <span>{locale === "ar" ? "وصف المشروع" : "Project brief"}</span>
              <ArrowRight />
              <span>{locale === "ar" ? "خطة موثقة" : "Validated plan"}</span>
              <ArrowRight />
              <span>
                {locale === "ar" ? "موافقة المدير" : "Manager approval"}
              </span>
            </div>
            {planError && (
              <em className="plan-error">
                <AlertTriangle size={14} />
                {planError}
              </em>
            )}
          </div>
        )}
        {step === 3 && (
          <div className="modal-body review-step full-plan-review">
            <div className="plan-review-heading">
              <div>
                <span className="eyebrow">
                  {locale === "ar"
                    ? "خطة تسليم كاملة"
                    : "COMPLETE DELIVERY PLAN"}
                </span>
                <h2>
                  {name ||
                    (locale === "ar" ? "مشروع بدون اسم" : "Untitled project")}
                </h2>
              </div>
              <span
                className={`plan-source ${plan?.source === "openai" ? "live" : "fallback"}`}
              >
                <Sparkles size={13} />
                {plan?.source === "openai"
                  ? locale === "ar"
                    ? "خطة OpenAI مباشرة"
                    : "Live OpenAI plan"
                  : locale === "ar"
                    ? "خطة احتياطية موثقة"
                    : "Validated fallback plan"}
              </span>
            </div>
            <section className="plan-overview">
              <p>{plan?.raw.project_summary}</p>
              <div className="architecture-note">
                <b>{locale === "ar" ? "البنية المقترحة" : "Architecture"}</b>
                <span>{plan?.raw.recommended_architecture}</span>
              </div>
            </section>
            <section className="plan-kpis">
              <span>
                <small>{locale === "ar" ? "إجمالي العمل" : "Total work"}</small>
                <b>{plan?.totalHours ?? 0}h</b>
              </span>
              <span>
                <small>{locale === "ar" ? "الخطة" : "Plan shape"}</small>
                <b>
                  {plan?.phases ?? 0} {locale === "ar" ? "مراحل" : "phases"} ·{" "}
                  {plan?.tasks ?? 0} {locale === "ar" ? "مهام" : "tasks"}
                </b>
              </span>
              <span>
                <small>{locale === "ar" ? "بدء التنفيذ" : "Start"}</small>
                <b>{plan?.delivery?.startDate}</b>
              </span>
              <span>
                <small>
                  {locale === "ar" ? "التسليم المتوقع" : "Forecast"}
                </small>
                <b>{plan?.delivery?.forecastDate}</b>
              </span>
              <span
                className={
                  plan?.delivery?.onTime === false ? "late" : "on-time"
                }
              >
                <small>{locale === "ar" ? "الموعد النهائي" : "Deadline"}</small>
                <b>{deadline}</b>
                <em>
                  {plan?.delivery?.onTime === false
                    ? locale === "ar"
                      ? "الخطة تتجاوز الموعد"
                      : "Forecast exceeds deadline"
                    : locale === "ar"
                      ? "ضمن الموعد"
                      : "On track"}
                </em>
              </span>
            </section>
            <section className="plan-distribution">
              <header>
                <div>
                  <b>{locale === "ar" ? "توزيع الفريق" : "Team allocation"}</b>
                  <small>
                    {locale === "ar"
                      ? "حسب المهارات والسعة، بحد أقصى 8 ساعات يوميًا"
                      : "Skill and capacity matched, capped at 8 hours per day"}
                  </small>
                </div>
              </header>
              <div>
                {plan?.delivery?.distribution.map((person: any) => (
                  <article key={person.id}>
                    <i className="avatar" style={{ background: person.accent }}>
                      {person.initials}
                    </i>
                    <span>
                      <b>{person.name}</b>
                      <small>{person.position}</small>
                    </span>
                    <strong>{person.plannedHours}h</strong>
                    <em>
                      {person.taskCount} {locale === "ar" ? "مهام" : "tasks"} ·{" "}
                      {person.workDays} {locale === "ar" ? "أيام" : "days"}
                    </em>
                  </article>
                ))}
              </div>
            </section>
            <section className="phase-plan-list">
              <header>
                <b>
                  {locale === "ar"
                    ? "المراحل والمهام اليومية"
                    : "Phases and daily tasks"}
                </b>
                <small>
                  {locale === "ar"
                    ? "كل مهمة تشمل المسؤول والوقت والنتيجة ومعايير القبول"
                    : "Every task includes ownership, timing, output and acceptance"}
                </small>
              </header>
              {plan?.raw.phases.map((phase: any, phaseIndex: number) => {
                const phaseTasks = plan.delivery.tasks.filter(
                  (task: any) => task.phase === phase.name,
                );
                return (
                  <details key={phase.name} open>
                    <summary>
                      <span>{phaseIndex + 1}</span>
                      <div>
                        <b>{phase.name}</b>
                        <small>{phase.description}</small>
                      </div>
                      <em>
                        {phaseTasks.length} {locale === "ar" ? "مهام" : "tasks"}{" "}
                        ·{" "}
                        {phaseTasks.reduce(
                          (total: number, task: any) =>
                            total + task.estimatedHours,
                          0,
                        )}
                        h
                      </em>
                    </summary>
                    <div className="milestone-row">
                      {phase.milestones.map((milestone: string) => (
                        <span key={milestone}>
                          <Target size={12} /> {milestone}
                        </span>
                      ))}
                    </div>
                    <div className="planned-task-list">
                      {phaseTasks.map((task: any, taskIndex: number) => (
                        <article key={task.id}>
                          <header>
                            <span>
                              {String(taskIndex + 1).padStart(2, "0")}
                            </span>
                            <div>
                              <b>{task.title}</b>
                              <p>{task.description}</p>
                            </div>
                            <em
                              className={`priority ${task.priority.toLowerCase()}`}
                            >
                              {task.priority}
                            </em>
                          </header>
                          <div className="task-plan-meta">
                            <span>
                              <i
                                className="avatar"
                                style={{ background: task.assignee?.accent }}
                              >
                                {task.assignee?.initials}
                              </i>
                              <b>{task.assignee?.name}</b>
                              <small>{task.assignee?.position}</small>
                            </span>
                            <span>
                              <Clock3 size={14} />
                              <b>{task.estimatedHours}h</b>
                              <small>
                                {task.schedule
                                  .map(
                                    (slot: any) =>
                                      `${slot.date} · ${slot.startTime} · ${slot.hours}h`,
                                  )
                                  .join(" / ")}
                              </small>
                            </span>
                          </div>
                          <div className="task-plan-detail">
                            <span>
                              <b>{locale === "ar" ? "المخرج" : "Output"}</b>
                              <p>{task.expectedOutput}</p>
                            </span>
                            <span>
                              <b>
                                {locale === "ar"
                                  ? "معايير القبول"
                                  : "Acceptance"}
                              </b>
                              <ul>
                                {task.acceptanceCriteria.map((item: string) => (
                                  <li key={item}>{item}</li>
                                ))}
                              </ul>
                            </span>
                            <span>
                              <b>{locale === "ar" ? "المهارات" : "Skills"}</b>
                              <p>{task.requiredSkills.join(" · ")}</p>
                            </span>
                            {task.dependencies.length > 0 && (
                              <span>
                                <b>
                                  {locale === "ar" ? "يعتمد على" : "Depends on"}
                                </b>
                                <p>{task.dependencies.join("، ")}</p>
                              </span>
                            )}
                          </div>
                        </article>
                      ))}
                    </div>
                  </details>
                );
              })}
            </section>
            <section className="plan-risks">
              <header>
                <b>
                  {locale === "ar"
                    ? "المخاطر وخطة المعالجة"
                    : "Risks and mitigation"}
                </b>
              </header>
              {plan?.raw.risks.map((risk: any) => (
                <article key={risk.title}>
                  <span className={`priority ${risk.severity.toLowerCase()}`}>
                    {risk.severity}
                  </span>
                  <div>
                    <b>{risk.title}</b>
                    <p>{risk.mitigation}</p>
                  </div>
                </article>
              ))}
            </section>
            <div className="activation-note">
              <CheckCircle2 size={16} />
              {locale === "ar"
                ? "الموافقة ستنشئ نفس المهام والتوزيع والجداول والمواعيد الظاهرة أعلاه."
                : "Approval creates the exact task allocation, schedules and due dates shown above."}
            </div>
          </div>
        )}
        <footer>
          <button
            className="secondary-button"
            onClick={() => (step === 1 ? close() : setStep((s) => s - 1))}
          >
            {step === 1
              ? tr(locale, "cancel")
              : locale === "ar"
                ? "رجوع"
                : "Back"}
          </button>
          <button
            className="primary-button"
            disabled={!name.trim() || !desc.trim() || planning}
            onClick={() =>
              step === 1 ? setStep(2) : step === 2 ? prepare() : create()
            }
          >
            {step === 1 ? (
              locale === "ar" ? (
                "متابعة"
              ) : (
                "Continue"
              )
            ) : step === 2 ? (
              <>
                <Sparkles size={16} />
                {planning
                  ? locale === "ar"
                    ? "جارٍ التخطيط…"
                    : "Planning…"
                  : locale === "ar"
                    ? "إنشاء الخطة"
                    : "Generate plan"}
              </>
            ) : (
              <>
                <Check size={16} />
                {planning
                  ? locale === "ar"
                    ? "جارٍ التفعيل…"
                    : "Activating…"
                  : locale === "ar"
                    ? "موافقة وتفعيل"
                    : "Approve & activate"}
              </>
            )}
          </button>
        </footer>
      </div>
    </div>
  );
}

function TaskDrawer({
  locale,
  task,
  data,
  close,
  update,
  openTask,
  saveNote,
}: {
  locale: Locale;
  task: Task;
  data: Data;
  close: () => void;
  update: (id: string, s: Task["status"]) => void;
  openTask: (id: string) => void;
  saveNote: (id: string, body: string) => Promise<void>;
}) {
  const person = data.people.find((p) => p.id === task.assigneeId),
    project = data.projects.find((p) => p.id === task.projectId);
  const [note, setNote] = useState("");
  const [savingNote, setSavingNote] = useState(false);
  const [noteError, setNoteError] = useState("");
  const submitNote = async () => {
    if (!note.trim()) return;
    setSavingNote(true);
    setNoteError("");
    try {
      await saveNote(task.id, note.trim());
      setNote("");
    } catch (cause) {
      setNoteError(
        cause instanceof Error ? cause.message : "Note could not be saved",
      );
    } finally {
      setSavingNote(false);
    }
  };
  return (
    <div className="drawer-scrim" onClick={close}>
      <aside className="task-drawer" onClick={(e) => e.stopPropagation()}>
        <header>
          <div>
            <span>{project?.code}</span>
            <b>/</b>
            <span>{task.id.toUpperCase()}</span>
          </div>
          <button className="icon-button" onClick={close}>
            <X size={18} />
          </button>
        </header>
        <div className="drawer-body">
          <div className="task-title-row">
            <span className={`priority ${task.priority.toLowerCase()}`}>
              {task.priority}
            </span>
            <h1>{task.title}</h1>
            <p>{task.description}</p>
          </div>
          <div className="drawer-actions">
            {task.status !== "In Progress" && task.status !== "Completed" && (
              <button
                className="primary-button"
                onClick={() => update(task.id, "In Progress")}
              >
                <Play size={16} />
                {locale === "ar" ? "بدء العمل" : "Start work"}
              </button>
            )}
            {task.status === "In Progress" && (
              <button
                className="primary-button"
                onClick={() => update(task.id, "Completed")}
              >
                <Check size={16} />
                {locale === "ar" ? "تحديد كمكتملة" : "Mark complete"}
              </button>
            )}
            <button
              className="secondary-button"
              onClick={() => update(task.id, "Blocked")}
            >
              <AlertTriangle size={16} />
              {locale === "ar" ? "إيقاف بسبب عائق" : "Block"}
            </button>
            <span className="icon-button static-control">
              <MoreHorizontal size={18} />
            </span>
          </div>
          <section className="task-properties">
            <div>
              <span>{locale === "ar" ? "الحالة" : "Status"}</span>
              <b
                className={`property-status ${task.status.toLowerCase().replace(" ", "-")}`}
              >
                {task.status}
              </b>
            </div>
            <div>
              <span>{locale === "ar" ? "المسؤول" : "Assignee"}</span>
              <b className="property-person">
                <i className="avatar" style={{ background: person?.accent }}>
                  {person?.initials}
                </i>
                {person?.name}
              </b>
            </div>
            <div>
              <span>{locale === "ar" ? "التقدير" : "Estimate"}</span>
              <b>
                <Clock3 size={15} />
                {task.estimate} {locale === "ar" ? "ساعات" : "hours"}
              </b>
            </div>
            <div>
              <span>{locale === "ar" ? "موعد الاستحقاق" : "Due date"}</span>
              <b>
                <CalendarDays size={15} />
                {task.due}
              </b>
            </div>
            <div>
              <span>{locale === "ar" ? "المشروع" : "Project"}</span>
              <b>
                <i
                  className="project-dot"
                  style={{ background: project?.accent }}
                />
                {project?.name}
              </b>
            </div>
          </section>
          <section className="acceptance">
            <h3>{locale === "ar" ? "معايير القبول" : "Acceptance criteria"}</h3>
            {task.acceptance.map((a, i) => (
              <label key={a}>
                <input
                  type="checkbox"
                  defaultChecked={task.status === "Completed"}
                />
                <span>{a}</span>
              </label>
            ))}
          </section>
          <section className="dependency">
            <h3>{locale === "ar" ? "التبعيات" : "Dependencies"}</h3>
            {task.dependencies.length ? (
              task.dependencies.map((id) => (
                <button key={id} onClick={() => openTask(id)}>
                  {data.tasks.find((t) => t.id === id)?.title}
                  <ArrowRight size={14} />
                </button>
              ))
            ) : (
              <p>
                {locale === "ar"
                  ? "لا توجد تبعيات معيقة."
                  : "No blocking dependencies."}
              </p>
            )}
          </section>
          <section className="notes">
            <h3>
              {locale === "ar" ? "ملاحظات التنفيذ" : "Implementation notes"}
            </h3>
            <textarea
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder={
                locale === "ar"
                  ? "أضف السياق أو القرارات أو الروابط للمراجعين..."
                  : "Add context, decisions or links for reviewers..."
              }
            />
            {noteError && <div className="form-error">{noteError}</div>}
            <button
              className="secondary-button"
              onClick={() => void submitNote()}
              disabled={!note.trim() || savingNote}
            >
              {savingNote
                ? locale === "ar"
                  ? "جارٍ الحفظ…"
                  : "Saving…"
                : locale === "ar"
                  ? "حفظ الملاحظة"
                  : "Save note"}
            </button>
          </section>
        </div>
      </aside>
    </div>
  );
}
