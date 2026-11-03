import { isSupportedLocale } from "@jormall/contracts/locales";
import { PlatformRole } from "@jormall/db/generated/enums";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { DashboardNavigation } from "../../../components/dashboard-navigation";
import { BranchSwitcher } from "../../../components/branch-switcher";
import { DashboardLocaleSwitch } from "../../../components/dashboard-header-controls";
import { GlobalSearch } from "../../../components/global-search";
import { OrganizationLogo } from "../../../components/organization-branding";
import {
  createOrganizationTheme,
  organizationThemeStyle,
} from "../../../components/organization-theme";
import { SubmitButton } from "../../../components/submit-button";
import { createWorkspaceNavigation } from "../../../components/workspace-navigation";
import { WorkspaceAlerts } from "../../../components/workspace-alerts";
import { phaseOneMessages } from "../../../messages/phase-one";
import { identityRepository, requireTenantAccess } from "../../../server/identity";
import { requireSession } from "../../../server/session";
import { endSupportAccessAction, logoutAction, switchOrganizationAction } from "../actions";

export default async function DashboardLayout({
  children,
  params,
}: Readonly<{ children: ReactNode; params: Promise<{ locale: string }> }>) {
  const { locale } = await params;
  if (!isSupportedLocale(locale)) notFound();
  const session = await requireSession(locale);
  const [memberships, user] = await Promise.all([
    identityRepository.listMembershipChoices(session.user.id),
    identityRepository.client.user.findUnique({
      select: { platformRole: true },
      where: { id: session.user.id },
    }),
  ]);
  const messages = phaseOneMessages[locale];
  const activeMembership = memberships.find(
    (membership) =>
      membership.id === session.session.activeMembershipId ||
      membership.organization.id === session.session.activeOrganizationId,
  );
  const availableMemberships = memberships.filter(
    (membership) => membership.status === "ACTIVE" && membership.organization.status === "ACTIVE",
  );
  const activeOrganizationName = activeMembership
    ? locale === "ar"
      ? activeMembership.organization.nameAr
      : activeMembership.organization.nameEn
    : messages.activeOrganization;
  let workspaceBranding: Awaited<ReturnType<typeof identityRepository.getWorkspaceBranding>> = null;
  let permittedBranches: Awaited<ReturnType<typeof identityRepository.listBranches>> = [];
  let tenantAccess: Awaited<ReturnType<typeof requireTenantAccess>> | null = null;
  if (session.session.activeOrganizationId) {
    try {
      tenantAccess = await requireTenantAccess(locale);
      const canReadBranches = tenantAccess.grants.some(({ code }) => code === "branches.read");
      [workspaceBranding, permittedBranches] = await Promise.all([
        identityRepository.getWorkspaceBranding(tenantAccess),
        canReadBranches ? identityRepository.listBranches(tenantAccess) : Promise.resolve([]),
      ]);
    } catch {
      workspaceBranding = null;
      permittedBranches = [];
      tenantAccess = null;
    }
  }
  const theme = createOrganizationTheme({
    accentColor: workspaceBranding?.settings?.brandAccentColor,
    primaryColor: workspaceBranding?.settings?.brandPrimaryColor,
  });
  const root = `/${locale}/dashboard`;
  const navigationGroups = createWorkspaceNavigation(locale, tenantAccess?.grants ?? []);
  const displayedOrganizationName = workspaceBranding
    ? locale === "ar"
      ? workspaceBranding.nameAr
      : workspaceBranding.nameEn
    : activeOrganizationName;
  const canCreateAppointment = Boolean(
    tenantAccess?.grants.some(({ code }) => code === "appointments.create") &&
    tenantAccess.grants.some(({ code }) => code === "customers.read"),
  );

  return (
    <div className="app-shell" style={organizationThemeStyle(theme)}>
      <a className="skip-link" href="#main-content">
        {locale === "ar" ? "انتقل إلى المحتوى" : "Skip to content"}
      </a>
      {session.session.activeSupportAccessId ? (
        <div className="support-banner" role="status">
          {locale === "ar"
            ? "وضع دعم جورمول المدقّق نشط"
            : "Audited JorMall support mode is active"}
        </div>
      ) : null}
      <div className="workspace">
        <header className="app-header">
          <div className="header-context">
            <Link className="header-organization-brand" href={root}>
              <OrganizationLogo
                logoUrl={workspaceBranding?.settings?.brandLogoUrl}
                name={displayedOrganizationName}
              />
              <span>
                <strong>{displayedOrganizationName}</strong>
                <small>{locale === "ar" ? "مركز تجميل" : "Beauty center"}</small>
              </span>
            </Link>
            <BranchSwitcher
              activeBranchId={tenantAccess?.activeBranchId}
              branches={permittedBranches}
              locale={locale}
            />
          </div>
          <GlobalSearch locale={locale} />
          <div className="header-actions">
            {session.session.activeSupportAccessId ? (
              <form action={endSupportAccessAction}>
                <input name="locale" type="hidden" value={locale} />
                <SubmitButton tone="danger">{messages.endSupport}</SubmitButton>
              </form>
            ) : availableMemberships.length > 1 ? (
              <form action={switchOrganizationAction} className="switcher">
                <input name="locale" type="hidden" value={locale} />
                <label className="sr-only" htmlFor="membershipId">
                  {messages.switchOrganization}
                </label>
                <select
                  className="select"
                  defaultValue={activeMembership?.id ?? ""}
                  id="membershipId"
                  name="membershipId"
                  required
                >
                  <option disabled value="">
                    {messages.activeOrganization}
                  </option>
                  {memberships.map((membership) => (
                    <option
                      disabled={
                        membership.status !== "ACTIVE" ||
                        membership.organization.status !== "ACTIVE"
                      }
                      key={membership.id}
                      value={membership.id}
                    >
                      {locale === "ar"
                        ? membership.organization.nameAr
                        : membership.organization.nameEn}
                    </option>
                  ))}
                </select>
                <SubmitButton tone="secondary">{messages.switchOrganization}</SubmitButton>
              </form>
            ) : null}
            {canCreateAppointment ? (
              <Link
                className="button button-primary header-new-appointment"
                href={`/${locale}/schedule/calendar#create-appointment-title`}
              >
                <span aria-hidden="true">+</span>
                {locale === "ar" ? "موعد جديد" : "New appointment"}
              </Link>
            ) : null}
            <WorkspaceAlerts locale={locale} />
            <div className="header-utility-group">
              <DashboardLocaleSwitch label={messages.changeLanguage} locale={locale} />
              <details className="user-menu">
                <summary aria-label={locale === "ar" ? "قائمة المستخدم" : "User menu"}>
                  <span aria-hidden="true">{session.user.name.slice(0, 1).toUpperCase()}</span>
                </summary>
                <div className="user-menu-panel">
                  <strong>{session.user.name}</strong>
                  <small dir="ltr">{session.user.email}</small>
                  <Link href={`/${locale}/account/security`}>
                    {locale === "ar" ? "أمان الحساب" : "Account Security"}
                  </Link>
                  {user?.platformRole === PlatformRole.JORMALL_SUPER_ADMIN ? (
                    <Link href={`/${locale}/platform/organizations`}>{messages.platformAdmin}</Link>
                  ) : null}
                  <form action={logoutAction}>
                    <input name="locale" type="hidden" value={locale} />
                    <SubmitButton tone="secondary">{messages.logout}</SubmitButton>
                  </form>
                </div>
              </details>
            </div>
          </div>
        </header>
        <div className="workspace-body">
          <DashboardNavigation
            ariaLabel={locale === "ar" ? "التنقل الرئيسي" : "Primary navigation"}
            closeSidebarLabel={locale === "ar" ? "إغلاق الشريط الجانبي" : "Close sidebar"}
            groups={navigationGroups}
            menuLabel={messages.navigationMenu}
            openSidebarLabel={locale === "ar" ? "فتح الشريط الجانبي" : "Open sidebar"}
          />
          <main className="main-content" id="main-content">
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}
