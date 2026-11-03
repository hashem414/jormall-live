import { canAccessResource } from "@jormall/auth/tenant-policy";
import { isSupportedLocale } from "@jormall/contracts/locales";
import { DomainError } from "@jormall/domain/errors";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Feedback } from "../../../components/feedback";
import { OrganizationLogo } from "../../../components/organization-branding";
import { WorkspaceIcon, type WorkspaceIconName } from "../../../components/workspace-icon";
import { phaseOneMessages } from "../../../messages/phase-one";
import { identityRepository, requireTenantPermission } from "../../../server/identity";
import { requireSession } from "../../../server/session";

type HomeQuickAction = Readonly<{
  description: string;
  href: string;
  icon: WorkspaceIconName;
  label: string;
  visible: boolean;
}>;

export default async function DashboardPage({
  params,
  searchParams,
}: PageProps<"/[locale]/dashboard">) {
  const { locale } = await params;
  if (!isSupportedLocale(locale)) notFound();
  const [session, query] = await Promise.all([requireSession(locale), searchParams]);
  const messages = phaseOneMessages[locale];
  let overview: Awaited<ReturnType<typeof identityRepository.listTenantOverview>> | null = null;
  let access: Awaited<ReturnType<typeof requireTenantPermission>> | null = null;
  let branches: Awaited<ReturnType<typeof identityRepository.listBranches>> = [];
  let experience: "manager" | "owner" | "provider" | "secretary" | "custom" = "custom";
  let accessError: string | undefined;

  if (session.session.activeOrganizationId) {
    try {
      access = await requireTenantPermission(locale, "organization.read");
      const membershipChoices = await identityRepository.listMembershipChoices(session.user.id);
      const activeMembership = membershipChoices.find(
        ({ id }) => id === session.session.activeMembershipId,
      );
      const systemRoles = new Set(activeMembership?.roles.map(({ role }) => role.systemKey));
      experience = systemRoles.has("ORGANIZATION_OWNER")
        ? "owner"
        : systemRoles.has("ORGANIZATION_MANAGER")
          ? "manager"
          : systemRoles.has("SECRETARY")
            ? "secretary"
            : systemRoles.has("PROVIDER")
              ? "provider"
              : "custom";
      [overview, branches] = await Promise.all([
        identityRepository.listTenantOverview(access),
        canAccessResource(access, "branches.read")
          ? identityRepository.listBranches(access)
          : Promise.resolve([]),
      ]);
    } catch (error) {
      accessError = error instanceof DomainError ? error.code : "INTERNAL_ERROR";
    }
  }

  if (!overview?.organization || !access) {
    return (
      <section className="page-stack product-home">
        <Feedback
          error={accessError ?? (typeof query.error === "string" ? query.error : undefined)}
          locale={locale}
          notice={typeof query.notice === "string" ? query.notice : undefined}
        />
        <div className="empty-state">
          <p>{messages.noActiveOrganization}</p>
        </div>
      </section>
    );
  }

  const now = new Date();
  const organizationName =
    locale === "ar" ? overview.organization.nameAr : overview.organization.nameEn;
  const activeBranch = branches.find(({ id }) => id === access.activeBranchId);
  const branchName = activeBranch
    ? locale === "ar"
      ? activeBranch.nameAr
      : activeBranch.nameEn
    : branches.length === 1
      ? locale === "ar"
        ? branches[0]?.nameAr
        : branches[0]?.nameEn
      : locale === "ar"
        ? "لا يوجد فرع نشط"
        : "No active branch";
  const timezone = activeBranch?.timezone ?? branches[0]?.timezone ?? "Asia/Amman";
  const firstName = session.user.name.trim().split(/\s+/u)[0] ?? session.user.name;
  const hour = Number(
    new Intl.DateTimeFormat("en-US", {
      hour: "numeric",
      hourCycle: "h23",
      timeZone: timezone,
    }).format(now),
  );
  const greeting =
    locale === "ar"
      ? hour < 12
        ? "صباح الخير"
        : "مساء الخير"
      : hour < 12
        ? "Good morning"
        : "Good afternoon";
  const roleLabel = {
    custom: locale === "ar" ? "مساحة العمل" : "Workspace",
    manager: locale === "ar" ? "مدير" : "Manager",
    owner: locale === "ar" ? "مالك" : "Owner",
    provider: locale === "ar" ? "مقدم خدمة" : "Service provider",
    secretary: locale === "ar" ? "سكرتير" : "Secretary",
  }[experience];
  const granted = new Set(access.grants.map(({ code }) => code));
  const quickActions = (
    [
      {
        description:
          locale === "ar" ? "إدارة الجدول والمواعيد" : "Manage schedules and appointments",
        href: `/${locale}/schedule/today`,
        icon: "appointments",
        label: locale === "ar" ? "المواعيد" : "Appointments",
        visible: granted.has("appointments.read"),
      },
      {
        description:
          locale === "ar"
            ? "إدارة طلبات انتظار المواعيد الملغاة"
            : "Manage requests waiting for cancelled appointments",
        href: `/${locale}/schedule/waitlist`,
        icon: "waitlist",
        label: locale === "ar" ? "قائمة الانتظار" : "Waiting List",
        visible: granted.has("waitlist.read"),
      },
      {
        description: locale === "ar" ? "عرض ملفات المرضى" : "View authorized patient profiles",
        href: `/${locale}/customers`,
        icon: "customers",
        label: locale === "ar" ? "المرضى" : "Patients",
        visible: granted.has("patients.directory.read"),
      },
      {
        description:
          locale === "ar" ? "الجداول والخدمات والتوفر" : "Schedules, services, and availability",
        href: `/${locale}/business/doctors`,
        icon: "doctors",
        label: locale === "ar" ? "الأطباء" : "Doctors",
        visible: granted.has("doctors.directory.read"),
      },
      {
        description: locale === "ar" ? "عرض خدمات كارمالايت" : "View Karmalite services",
        href: `/${locale}/business/services`,
        icon: "services",
        label: locale === "ar" ? "الخدمات" : "Services",
        visible: granted.has("services.read"),
      },
      {
        description: locale === "ar" ? "الغرف وحالة الإشغال" : "Rooms and occupancy status",
        href: `/${locale}/business/resources`,
        icon: "resources",
        label: locale === "ar" ? "الموارد" : "Resources",
        visible: granted.has("resources.read"),
      },
      {
        description: locale === "ar" ? "الفريق والأدوار والصلاحيات" : "Staff, roles, and access",
        href: `/${locale}/business/team`,
        icon: "team",
        label: locale === "ar" ? "الفريق والصلاحيات" : "Team & Access",
        visible: granted.has("staff.read") || granted.has("roles.read"),
      },
      {
        description:
          locale === "ar" ? "العناصر والطلبات والتنبيهات" : "Items, requests, and alerts",
        href: `/${locale}/business/inventory`,
        icon: "inventory",
        label: locale === "ar" ? "المخزون" : "Inventory",
        visible: granted.has("inventory.items.read"),
      },
      {
        description: locale === "ar" ? "المحادثات والرسائل" : "Conversations and messages",
        href: `/${locale}/inbox?tab=conversations`,
        icon: "communications",
        label: locale === "ar" ? "التواصل" : "Communications",
        visible: granted.has("messages.read") || granted.has("conversations.read"),
      },
      {
        description:
          locale === "ar" ? "طلبات المساعدة المحولة للفريق" : "Chatbot requests needing staff help",
        href: `/${locale}/inbox/escalations`,
        icon: "sparkles",
        label: locale === "ar" ? "تصعيدات المساعد الآلي" : "Chatbot Escalations",
        visible: granted.has("chatbot_escalations.read"),
      },
      {
        description:
          locale === "ar" ? "مؤشرات الأداء والتقارير" : "Performance and operational reports",
        href: `/${locale}/insights/reports`,
        icon: "reports",
        label: locale === "ar" ? "التقارير" : "Reports",
        visible: granted.has("reports.read"),
      },
      {
        description: locale === "ar" ? "إعدادات المؤسسة والحجز" : "Organization and booking setup",
        href: `/${locale}/settings/organization`,
        icon: "settings",
        label: locale === "ar" ? "الإعدادات" : "Settings",
        visible: granted.has("organization.settings.manage"),
      },
    ] satisfies readonly HomeQuickAction[]
  ).filter(({ visible }) => visible);

  return (
    <section className="product-home" aria-labelledby="overview-title">
      <header className="home-brand-hero">
        <div className="home-hero-logo">
          <OrganizationLogo
            logoUrl={overview.organization.settings?.brandLogoUrl}
            name={organizationName}
          />
        </div>
        <div className="home-hero-copy">
          <p className="home-greeting">
            {greeting}, {firstName}
          </p>
          <h1 id="overview-title">
            {locale === "ar"
              ? `مرحباً بك في ${organizationName}`
              : `Welcome to ${organizationName}`}
          </h1>
          <p>
            {locale === "ar"
              ? "كل ما تحتاجه لإدارة يومك في مكان واحد."
              : "Everything you need to manage your day in one place."}
          </p>
          <div className="home-hero-meta">
            <span>{roleLabel}</span>
            <span>{branchName}</span>
            <time dateTime={now.toISOString()}>
              {new Intl.DateTimeFormat(locale === "ar" ? "ar-JO" : "en-JO", {
                dateStyle: "full",
                timeZone: timezone,
              }).format(now)}
            </time>
          </div>
        </div>
      </header>

      <Feedback
        error={accessError ?? (typeof query.error === "string" ? query.error : undefined)}
        locale={locale}
        notice={typeof query.notice === "string" ? query.notice : undefined}
      />

      <section className="home-quick-actions" aria-labelledby="home-quick-actions-title">
        <header>
          <p>{locale === "ar" ? "مساحة العمل" : "Workspace"}</p>
          <h2 id="home-quick-actions-title">
            {locale === "ar" ? "الوصول السريع" : "Quick access"}
          </h2>
        </header>
        <div className="home-quick-action-grid">
          {quickActions.map((action) => (
            <Link className="home-quick-action-card" href={action.href} key={action.href}>
              <span className="home-quick-action-icon">
                <WorkspaceIcon name={action.icon} />
              </span>
              <strong>{action.label}</strong>
              <small>{action.description}</small>
            </Link>
          ))}
        </div>
      </section>
    </section>
  );
}
