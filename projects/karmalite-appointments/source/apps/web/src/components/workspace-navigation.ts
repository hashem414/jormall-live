import type { SupportedLocale } from "@jormall/contracts/locales";
import type { PermissionCode, PermissionGrant } from "@jormall/domain/identity";

import type { DashboardNavigationGroup, DashboardNavigationItem } from "./dashboard-navigation";

type Candidate = DashboardNavigationItem & Readonly<{ permissions: readonly PermissionCode[] }>;

const labels = {
  ar: {
    actions: "الإجراءات",
    aiStudio: "استوديو الذكاء الاصطناعي",
    appointments: "المواعيد",
    attribution: "الإسناد",
    audit: "التدقيق",
    behavior: "السلوك",
    bookingRules: "قواعد الحجز",
    branches: "الفروع",
    branding: "الهوية البصرية",
    business: "النشاط",
    calendar: "التقويم",
    channels: "القنوات والتكاملات",
    conversations: "المحادثات",
    communications: "التواصل",
    customers: "المرضى",
    customerCare: "خدمة المرضى",
    doctors: "الأطباء",
    deliveryIssues: "مشكلات التسليم",
    escalations: "تصعيدات المساعد الآلي",
    handoffs: "التحويلات",
    home: "الرئيسية",
    imports: "الاستيراد",
    inventory: "المخزون",
    inbox: "صندوق الوارد",
    insights: "التحليلات",
    knowledge: "المعرفة",
    messages: "الرسائل",
    management: "الإدارة",
    organization: "المؤسسة",
    operations: "العمليات",
    notifications: "الإشعارات",
    recommendations: "التوصيات",
    reports: "التقارير",
    resources: "الموارد",
    schedule: "الجدول",
    services: "الخدمات",
    settings: "الإعدادات",
    team: "الفريق والصلاحيات",
    testAi: "اختبار الذكاء الاصطناعي",
    today: "اليوم",
    usage: "الاستخدام",
    waitlist: "قائمة الانتظار",
  },
  en: {
    actions: "Actions",
    aiStudio: "AI Studio",
    appointments: "Appointments",
    attribution: "Attribution",
    audit: "Audit",
    behavior: "Behavior",
    bookingRules: "Booking Rules",
    branches: "Branches",
    branding: "Branding",
    business: "Business",
    calendar: "Calendar",
    channels: "Channels & Integrations",
    conversations: "Conversations",
    communications: "Communications",
    customers: "Patients",
    customerCare: "Customer care",
    doctors: "Doctors",
    deliveryIssues: "Delivery Issues",
    escalations: "Chatbot Escalations",
    handoffs: "Handoffs",
    home: "Home",
    imports: "Imports",
    inventory: "Inventory",
    inbox: "Inbox",
    insights: "Insights",
    knowledge: "Knowledge",
    messages: "Messages",
    management: "Management",
    organization: "Organization",
    operations: "Operations",
    notifications: "Notifications",
    recommendations: "Recommendations",
    reports: "Reports",
    resources: "Resources",
    schedule: "Schedule",
    services: "Services",
    settings: "Settings",
    team: "Team & Access",
    testAi: "Test AI",
    today: "Today",
    usage: "Usage",
    waitlist: "Waiting List",
  },
} as const;

function permitted(candidate: Candidate, grants: ReadonlySet<PermissionCode>): boolean {
  return candidate.permissions.some((permission) => grants.has(permission));
}

export function createWorkspaceNavigation(
  locale: SupportedLocale,
  grants: readonly PermissionGrant[],
): readonly DashboardNavigationGroup[] {
  const text = labels[locale];
  const root = `/${locale}`;
  const granted = new Set(grants.map(({ code }) => code));
  const groups: readonly Readonly<{
    items: readonly Candidate[];
    label: string;
  }>[] = [
    {
      items: [
        {
          href: `${root}/dashboard`,
          icon: "home",
          label: text.home,
          permissions: ["organization.read"],
        },
        {
          activePrefixes: [
            `${root}/schedule/today`,
            `${root}/schedule/appointments`,
            `${root}/schedule/calendar`,
          ],
          href: `${root}/schedule/today`,
          icon: "appointments",
          label: text.appointments,
          permissions: ["appointments.read"],
        },
        {
          href: `${root}/schedule/waitlist`,
          icon: "waitlist",
          label: text.waitlist,
          permissions: ["waitlist.read"],
        },
        {
          href: `${root}/customers`,
          icon: "customers",
          label: text.customers,
          permissions: ["patients.directory.read"],
        },
      ],
      label: text.operations,
    },
    {
      items: [
        {
          href: `${root}/business/doctors`,
          icon: "doctors",
          label: text.doctors,
          permissions: ["doctors.directory.read"],
        },
        {
          href: `${root}/business/team`,
          icon: "team",
          label: text.team,
          permissions: ["staff.read", "roles.read"],
        },
        {
          href: `${root}/business/roles-access`,
          icon: "team",
          label: locale === "ar" ? "الأدوار والصلاحيات" : "Roles & Access",
          permissions: ["roles.manage"],
        },
        {
          href: `${root}/business/services`,
          icon: "services",
          label: text.services,
          permissions: ["services.read"],
        },
        {
          href: `${root}/business/resources`,
          icon: "resources",
          label: text.resources,
          permissions: ["resources.read"],
        },
        {
          href: `${root}/business/inventory`,
          icon: "inventory",
          label: text.inventory,
          permissions: ["inventory.items.read"],
        },
      ],
      label: text.business,
    },
    {
      items: [
        {
          href: `${root}/inbox/escalations`,
          icon: "sparkles",
          label: text.escalations,
          permissions: ["chatbot_escalations.read"],
        },
        {
          activePrefixes: [`${root}/inbox`],
          href: `${root}/inbox?tab=conversations`,
          icon: "communications",
          label: text.communications,
          mobileLabel: text.inbox,
          permissions: ["messages.read", "conversations.read"],
        },
      ],
      label: text.customerCare,
    },
    {
      items: [
        {
          activePrefixes: [`${root}/insights`],
          href: `${root}/insights/reports`,
          icon: "reports",
          label: text.reports,
          permissions: ["reports.read"],
        },
        {
          activePrefixes: [`${root}/settings`],
          href: `${root}/settings/organization`,
          icon: "settings",
          label: text.settings,
          permissions: ["organization.settings.manage"],
        },
      ],
      label: text.management,
    },
  ];

  return groups
    .map((group) => ({ ...group, items: group.items.filter((item) => permitted(item, granted)) }))
    .filter((group) => group.items.length > 0);
}
