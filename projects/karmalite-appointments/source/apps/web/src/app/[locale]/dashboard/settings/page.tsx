import { canAccessResource } from "@jormall/auth/tenant-policy";
import { isSupportedLocale } from "@jormall/contracts/locales";
import Link from "next/link";
import { notFound } from "next/navigation";

import { DashboardPageHero } from "../../../../components/dashboard-page-hero";
import { Feedback } from "../../../../components/feedback";
import { OrganizationBrandingFields } from "../../../../components/organization-branding-fields";
import { SubmitButton } from "../../../../components/submit-button";
import { ownerWorkspaceMessages } from "../../../../messages/owner-workspace";
import { phaseOneMessages } from "../../../../messages/phase-one";
import { identityRepository, requirePagePermission } from "../../../../server/identity";
import { updateSettingsAction } from "../../actions";

export default async function SettingsPage({
  params,
  searchParams,
}: PageProps<"/[locale]/dashboard/settings">) {
  const { locale } = await params;
  if (!isSupportedLocale(locale)) notFound();
  const [access, query] = await Promise.all([
    requirePagePermission(locale, "organization.settings.manage"),
    searchParams,
  ]);
  const [settings, readinessIssues] = await Promise.all([
    identityRepository.getSettings(access),
    identityRepository.getSetupReadiness(access),
  ]);
  if (!settings) notFound();
  const section =
    query.section === "branding" || query.section === "booking-rules"
      ? query.section
      : "organization";
  const messages = phaseOneMessages[locale];
  const workspace = ownerWorkspaceMessages[locale];
  const organizationName =
    locale === "ar" ? settings.organization.nameAr : settings.organization.nameEn;
  const setupLinks = [
    canAccessResource(access, "branches.read")
      ? { href: `/${locale}/dashboard/branches`, icon: "⌂", label: workspace.manageBranches }
      : null,
    canAccessResource(access, "services.read")
      ? { href: `/${locale}/dashboard/services`, icon: "◇", label: workspace.manageServices }
      : null,
    canAccessResource(access, "staff.read")
      ? { href: `/${locale}/dashboard/staff`, icon: "♙", label: messages.staff }
      : null,
    canAccessResource(access, "roles.read")
      ? { href: `/${locale}/dashboard/roles`, icon: "⚿", label: workspace.manageRoles }
      : null,
    canAccessResource(access, "messages.read")
      ? {
          href: `/${locale}/dashboard/communications`,
          icon: "◌",
          label: workspace.manageConnections,
        }
      : null,
  ].filter((item) => item !== null);

  return (
    <section className="page-stack" aria-labelledby="settings-title">
      <DashboardPageHero
        description={
          section === "branding"
            ? messages.brandAppearanceDescription
            : section === "booking-rules"
              ? locale === "ar"
                ? "تحكّم في نوافذ الحجز والإلغاء والتذكيرات وسياسة عدم الحضور."
                : "Control booking, cancellation, reminder, and no-show rules."
              : workspace.settingsDescription
        }
        eyebrow={workspace.workspace}
        icon="⚙"
        title={
          section === "branding"
            ? messages.brandAppearance
            : section === "booking-rules"
              ? locale === "ar"
                ? "قواعد الحجز"
                : "Booking Rules"
              : messages.organizationSettings
        }
        titleId="settings-title"
      />
      <Feedback
        error={typeof query.error === "string" ? query.error : undefined}
        locale={locale}
        notice={typeof query.notice === "string" ? query.notice : undefined}
      />
      <nav
        aria-label={locale === "ar" ? "أقسام الإعدادات" : "Settings sections"}
        className="workspace-tabs"
      >
        {(
          [
            ["organization", locale === "ar" ? "المؤسسة" : "Organization"],
            ["branding", locale === "ar" ? "الهوية البصرية" : "Branding"],
            ["booking-rules", locale === "ar" ? "قواعد الحجز" : "Booking Rules"],
          ] as const
        ).map(([key, label]) => (
          <Link
            aria-current={section === key ? "page" : undefined}
            href={`/${locale}/settings/${key}`}
            key={key}
          >
            {label}
          </Link>
        ))}
      </nav>

      <dl className="workspace-metrics settings-metrics">
        <div>
          <span aria-hidden="true">◷</span>
          <dt>{messages.timezone}</dt>
          <dd className="metric-text" dir="ltr">
            {settings.timezone}
          </dd>
        </div>
        <div>
          <span aria-hidden="true">¤</span>
          <dt>{messages.currency}</dt>
          <dd className="metric-text">{settings.currency}</dd>
        </div>
        <div>
          <span aria-hidden="true">▦</span>
          <dt>{messages.bookingWindow}</dt>
          <dd>
            {settings.bookingWindowDays === null ? (
              workspace.notConfigured
            ) : (
              <>
                {settings.bookingWindowDays} <small>{workspace.days}</small>
              </>
            )}
          </dd>
        </div>
      </dl>

      <div
        className={`settings-workspace-grid ${section === "organization" ? "" : "settings-workspace-single"}`}
      >
        <form action={updateSettingsAction} className="panel settings-main-form">
          <input name="locale" type="hidden" value={locale} />
          <input name="returnSection" type="hidden" value={section} />
          <div className="settings-section-heading" hidden={section !== "organization"}>
            <span aria-hidden="true">⚙</span>
            <div>
              <h2>{workspace.generalSettings}</h2>
              <p>{workspace.generalSettingsDescription}</p>
            </div>
          </div>
          <div className="form-grid workspace-form">
            <label className="field" hidden={section !== "organization"}>
              <span className="field-label">{messages.defaultLocale}</span>
              <select className="select" defaultValue={settings.defaultLocale} name="defaultLocale">
                <option value="en">English</option>
                <option value="ar">{workspace.arabicLanguage}</option>
              </select>
            </label>
            <label className="field" hidden={section !== "organization"}>
              <span className="field-label">{messages.timezone}</span>
              <input
                className="input"
                defaultValue={settings.timezone}
                dir="ltr"
                name="timezone"
                required
              />
            </label>
            <label className="field" hidden={section !== "organization"}>
              <span className="field-label">{messages.currency}</span>
              <input
                className="input"
                defaultValue={settings.currency}
                dir="ltr"
                maxLength={3}
                name="currency"
                required
              />
            </label>
            <label className="field" hidden={section !== "booking-rules"}>
              <span className="field-label">{messages.bookingWindow}</span>
              <input
                className="input"
                defaultValue={settings.bookingWindowDays ?? ""}
                min={1}
                max={730}
                name="bookingWindowDays"
                type="number"
              />
              <small className="field-hint">{workspace.bookingWindowHint}</small>
            </label>
            <label className="field" hidden={section !== "booking-rules"}>
              <span className="field-label">
                {locale === "ar" ? "مهلة الإلغاء (دقيقة)" : "Cancellation window (minutes)"}
              </span>
              <input
                className="input"
                defaultValue={settings.cancellationWindowMins}
                min={0}
                name="cancellationWindowMins"
                required
                type="number"
              />
            </label>
            <label className="field" hidden={section !== "booking-rules"}>
              <span className="field-label">
                {locale === "ar" ? "مهلة إعادة الجدولة (دقيقة)" : "Rescheduling window (minutes)"}
              </span>
              <input
                className="input"
                defaultValue={settings.rescheduleWindowMins}
                min={0}
                name="rescheduleWindowMins"
                required
                type="number"
              />
            </label>
            <label className="field" hidden={section !== "booking-rules"}>
              <span className="field-label">
                {locale === "ar" ? "الحالة الافتراضية للموعد" : "Default appointment status"}
              </span>
              <select
                className="select"
                defaultValue={settings.defaultAppointmentStatus}
                name="defaultAppointmentStatus"
              >
                <option value="PENDING">{locale === "ar" ? "قيد الانتظار" : "Pending"}</option>
                <option value="CONFIRMED">{locale === "ar" ? "مؤكد" : "Confirmed"}</option>
              </select>
            </label>
            <label className="field" hidden={section !== "booking-rules"}>
              <span className="field-label">
                {locale === "ar" ? "إرسال التذكير قبل (دقيقة)" : "Reminder lead time (minutes)"}
              </span>
              <input
                className="input"
                defaultValue={settings.reminderLeadMins}
                min={0}
                name="reminderLeadMins"
                required
                type="number"
              />
            </label>
            <label className="field" hidden={section !== "booking-rules"}>
              <span className="field-label">
                {locale === "ar"
                  ? "موعد التذكير الإضافي قبل الموعد (بالدقائق)"
                  : "Additional reminder lead time (minutes)"}
              </span>
              <input
                className="input"
                defaultValue={settings.secondaryReminderLeadMins ?? ""}
                min={0}
                name="secondaryReminderLeadMins"
                type="number"
              />
            </label>
            <label className="check-field" hidden={section !== "booking-rules"}>
              <input
                defaultChecked={settings.confirmationEnabled}
                name="confirmationEnabled"
                type="checkbox"
              />
              <span>
                {locale === "ar" ? "تفعيل تأكيدات المواعيد" : "Appointment confirmations enabled"}
              </span>
            </label>
            <p className="field-hint" hidden={section !== "booking-rules"}>
              {workspace.policyReviewStatus}: {workspace.draftStatus}
            </p>
            <label className="field" hidden={section !== "booking-rules"}>
              <span className="field-label">
                {locale === "ar" ? "سياسة عدم الحضور (بالإنجليزية)" : "No-show policy (English)"}
              </span>
              <textarea
                className="input"
                defaultValue={settings.noShowPolicyEn ?? ""}
                name="noShowPolicyEn"
                rows={3}
              />
            </label>
            <label className="field" hidden={section !== "booking-rules"}>
              <span className="field-label">
                {locale === "ar" ? "سياسة عدم الحضور (بالعربية)" : "No-show policy (Arabic)"}
              </span>
              <textarea
                className="input"
                defaultValue={settings.noShowPolicyAr ?? ""}
                dir="rtl"
                name="noShowPolicyAr"
                rows={3}
              />
            </label>
          </div>
          <section
            className="branding-settings"
            aria-labelledby="branding-settings-title"
            hidden={section !== "branding"}
          >
            <div className="settings-section-heading">
              <span aria-hidden="true">◉</span>
              <div>
                <h2 id="branding-settings-title">{messages.brandAppearance}</h2>
                <p>{messages.brandAppearanceDescription}</p>
              </div>
            </div>
            <OrganizationBrandingFields
              accentColor={settings.brandAccentColor}
              locale={locale}
              logoUrl={settings.brandLogoUrl}
              messages={{
                accentColor: messages.brandAccentColor,
                colorExtractionFailed: messages.brandColorExtractionFailed,
                colorHint: messages.brandColorHint,
                colorsExtracted: messages.brandColorsExtracted,
                extractColors: messages.brandExtractColors,
                extractingColors: messages.brandExtractingColors,
                logoFile: messages.brandLogoFile,
                logoFileHint: messages.brandLogoFileHint,
                logoUrl: messages.brandLogoUrl,
                logoUrlHint: messages.brandLogoUrlHint,
                palette: messages.brandPalette,
                preview: messages.brandPreview,
                primaryColor: messages.brandPrimaryColor,
                saveChanges: messages.save,
              }}
              organizationName={organizationName}
              primaryColor={settings.brandPrimaryColor}
            />
          </section>
          {section === "branding" ? null : (
            <div className="form-actions settings-save-actions">
              <SubmitButton>{messages.save}</SubmitButton>
            </div>
          )}
        </form>

        <aside
          className="panel setup-links"
          aria-labelledby="setup-links-title"
          hidden={section !== "organization"}
        >
          <div className="settings-section-heading">
            <span aria-hidden="true">✓</span>
            <div>
              <h2 id="setup-links-title">{workspace.configurationLinks}</h2>
              <p>{workspace.configurationLinksDescription}</p>
            </div>
          </div>
          {readinessIssues.length > 0 ? (
            <section aria-labelledby="setup-readiness-title">
              <h3 id="setup-readiness-title">{workspace.setupReadinessTitle}</h3>
              <p className="muted">{workspace.setupReadinessDescription}</p>
              <ul className="readiness-checklist">
                {readinessIssues.map((issue) => (
                  <li key={issue}>
                    <span aria-hidden="true">!</span>
                    <span>{workspace.setupReadinessItems[issue]}</span>
                  </li>
                ))}
              </ul>
            </section>
          ) : (
            <p>{workspace.setupReadinessComplete}</p>
          )}
          <nav aria-label={workspace.configurationLinks}>
            {setupLinks.map((item) => (
              <Link href={item.href} key={item.href}>
                <span aria-hidden="true">{item.icon}</span>
                <strong>{item.label}</strong>
                <b aria-hidden="true">›</b>
              </Link>
            ))}
          </nav>
        </aside>
      </div>
    </section>
  );
}
