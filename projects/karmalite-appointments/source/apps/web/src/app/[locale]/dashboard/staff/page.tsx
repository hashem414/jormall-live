import { canAccessResource } from "@jormall/auth/tenant-policy";
import { isSupportedLocale } from "@jormall/contracts/locales";
import { MembershipStatus } from "@jormall/db/generated/enums";
import Link from "next/link";
import { notFound } from "next/navigation";

import { DashboardPageHero } from "../../../../components/dashboard-page-hero";
import { Feedback } from "../../../../components/feedback";
import { StaffInvitationForm } from "../../../../components/staff-invitation-form";
import { SubmitButton } from "../../../../components/submit-button";
import { ownerWorkspaceMessages } from "../../../../messages/owner-workspace";
import { phaseOneMessages, phaseOneValueLabel } from "../../../../messages/phase-one";
import { identityRepository, requirePagePermission } from "../../../../server/identity";
import {
  configureProviderBookingAction,
  replaceMembershipRoleAction,
  revokeInvitationAction,
  setMembershipStatusAction,
} from "../../actions";

export default async function StaffPage({
  params,
  searchParams,
}: PageProps<"/[locale]/dashboard/staff">) {
  const { locale } = await params;
  if (!isSupportedLocale(locale)) notFound();
  const [access, query] = await Promise.all([
    requirePagePermission(locale, "staff.read"),
    searchParams,
  ]);
  const canManage = canAccessResource(access, "staff.manage");
  const canManageRoles = canAccessResource(access, "roles.manage");
  const canManageSchedules =
    canManage &&
    canAccessResource(access, "schedules.manage") &&
    canAccessResource(access, "branches.read") &&
    canAccessResource(access, "services.read");
  const [staff, invitations, roles, branches, services] = await Promise.all([
    identityRepository.listStaff(access),
    canManage ? identityRepository.listInvitations(access) : Promise.resolve([]),
    canManage ? identityRepository.listRoles(access) : Promise.resolve([]),
    canManageSchedules ? identityRepository.listBranches(access) : Promise.resolve([]),
    canManageSchedules ? identityRepository.listServices(access) : Promise.resolve([]),
  ]);
  const messages = phaseOneMessages[locale];
  const workspace = ownerWorkspaceMessages[locale];
  const activeCount = staff.filter(({ status }) => status === MembershipStatus.ACTIVE).length;
  const providerCount = staff.filter(({ roles: memberRoles }) =>
    memberRoles.some(({ role }) => role.key === "PROVIDER"),
  ).length;
  const pendingInvitations = invitations.filter(({ status }) => status === "PENDING").length;

  return (
    <section className="page-stack" aria-labelledby="staff-title">
      <DashboardPageHero
        description={workspace.staffDescription}
        eyebrow={workspace.workspace}
        icon="♙"
        title={locale === "ar" ? "مقدمو الخدمات" : "Service Providers"}
        titleId="staff-title"
      />
      <Feedback
        error={typeof query.error === "string" ? query.error : undefined}
        locale={locale}
        notice={typeof query.notice === "string" ? query.notice : undefined}
      />

      <dl className="workspace-metrics">
        <div>
          <span aria-hidden="true">◎</span>
          <dt>{workspace.teamSize}</dt>
          <dd>{staff.length}</dd>
        </div>
        <div>
          <span aria-hidden="true">✓</span>
          <dt>{workspace.activeStaff}</dt>
          <dd>{activeCount}</dd>
        </div>
        <div>
          <span aria-hidden="true">♙</span>
          <dt>{workspace.providerTeam}</dt>
          <dd>{providerCount}</dd>
        </div>
        <div>
          <span aria-hidden="true">✉</span>
          <dt>{workspace.pendingInvitations}</dt>
          <dd>{pendingInvitations}</dd>
        </div>
      </dl>

      {canManage ? (
        <details className="panel action-disclosure workspace-action">
          <summary>+ {workspace.inviteSummary}</summary>
          <div className="disclosure-heading">
            <h2>{workspace.inviteSummary}</h2>
            <p>{workspace.inviteDescription}</p>
          </div>
          <StaffInvitationForm embedded locale={locale} roles={roles} />
        </details>
      ) : null}

      <div className="section-heading workspace-section-heading">
        <div>
          <p className="eyebrow">{workspace.businessSetup}</p>
          <h2>{workspace.staffDirectory}</h2>
        </div>
        {canManageRoles ? (
          <Link className="button button-secondary" href={`/${locale}/business/roles-access`}>
            {workspace.manageRoles}
          </Link>
        ) : null}
      </div>

      <div className="team-directory-grid">
        {staff.map((member) => (
          <article className="record-card team-member-card" key={member.id}>
            <header className="team-member-heading">
              <span className="team-avatar" aria-hidden="true">
                {initials(member.user.name)}
              </span>
              <div>
                <div className="team-member-name">
                  <h3>{member.user.name}</h3>
                  {access.membershipId === member.id ? (
                    <span className="current-user-badge">{workspace.you}</span>
                  ) : null}
                </div>
                <p dir="ltr">{member.user.email}</p>
              </div>
              <span className={`status status-${member.status.toLowerCase()}`}>
                {phaseOneValueLabel(locale, member.status)}
              </span>
            </header>

            <div className="team-role-summary">
              <span>{messages.roles}</span>
              <strong>
                {member.roles
                  .map(({ role }) => (locale === "ar" ? role.nameAr : role.nameEn))
                  .join(", ")}
              </strong>
            </div>

            {canManageSchedules && member.staffProfile ? (
              <details className="inline-disclosure provider-schedule-disclosure">
                <summary>
                  {locale === "ar" ? "إعداد الحجز وساعات العمل" : "Booking and working hours"}
                </summary>
                <form action={configureProviderBookingAction} className="form-stack">
                  <input name="locale" type="hidden" value={locale} />
                  <input name="staffProfileId" type="hidden" value={member.staffProfile.id} />
                  <label className="field">
                    <span className="field-label">{messages.branch}</span>
                    <select className="select" name="branchId" required>
                      {branches.map((branch) => (
                        <option key={branch.id} value={branch.id}>
                          {locale === "ar" ? branch.nameAr : branch.nameEn}
                        </option>
                      ))}
                    </select>
                  </label>
                  <fieldset className="choice-fieldset">
                    <legend>{locale === "ar" ? "الخدمات" : "Services"}</legend>
                    <div className="choice-grid">
                      {services.map((service) => (
                        <label className="check-field" key={service.id}>
                          <input
                            defaultChecked={member.staffProfile?.services.some(
                              ({ serviceId }) => serviceId === service.id,
                            )}
                            name="serviceIds"
                            type="checkbox"
                            value={service.id}
                          />
                          <span>{locale === "ar" ? service.nameAr : service.nameEn}</span>
                        </label>
                      ))}
                    </div>
                  </fieldset>
                  <fieldset className="choice-fieldset">
                    <legend>{locale === "ar" ? "أيام العمل" : "Working days"}</legend>
                    <div className="weekday-choice-grid">
                      {weekdayOptions.map((weekday) => (
                        <label className="check-field" key={weekday}>
                          <input
                            defaultChecked={member.staffProfile?.availabilityRules.some(
                              (rule) => rule.weekday === weekday,
                            )}
                            name="weekdays"
                            type="checkbox"
                            value={weekday}
                          />
                          <span>{weekdayLabel(locale, weekday)}</span>
                        </label>
                      ))}
                    </div>
                  </fieldset>
                  <div className="form-grid">
                    <label className="field">
                      <span className="field-label">
                        {locale === "ar" ? "وقت البدء" : "Start time"}
                      </span>
                      <input
                        className="input"
                        defaultValue={minuteInput(
                          Math.min(
                            ...member.staffProfile.availabilityRules.map(
                              ({ startMinuteLocal }) => startMinuteLocal,
                            ),
                            540,
                          ),
                        )}
                        name="startTime"
                        required
                        type="time"
                      />
                    </label>
                    <label className="field">
                      <span className="field-label">
                        {locale === "ar" ? "وقت الانتهاء" : "End time"}
                      </span>
                      <input
                        className="input"
                        defaultValue={minuteInput(
                          Math.max(
                            ...member.staffProfile.availabilityRules.map(
                              ({ endMinuteLocal }) => endMinuteLocal,
                            ),
                            1140,
                          ),
                        )}
                        name="endTime"
                        required
                        type="time"
                      />
                    </label>
                  </div>
                  <p className="field-hint">
                    {locale === "ar"
                      ? "يجب أن تكون ساعات مقدم الخدمة ضمن ساعات عمل الفرع."
                      : "Service-provider hours must fit within the branch working hours."}
                  </p>
                  <SubmitButton tone="secondary">
                    {locale === "ar" ? "حفظ إعداد الحجز" : "Save booking setup"}
                  </SubmitButton>
                </form>
              </details>
            ) : null}

            {canManage ? (
              <details className="inline-disclosure team-access-disclosure">
                <summary>{workspace.updateMember}</summary>
                {canManageRoles ? (
                  <form action={replaceMembershipRoleAction} className="form-stack">
                    <input name="locale" type="hidden" value={locale} />
                    <input name="membershipId" type="hidden" value={member.id} />
                    <label className="field">
                      <span className="field-label">{messages.roles}</span>
                      <select
                        className="select"
                        defaultValue={member.roles[0]?.roleId ?? ""}
                        name="roleId"
                        required
                      >
                        {roles.map((role) => (
                          <option key={role.id} value={role.id}>
                            {locale === "ar" ? role.nameAr : role.nameEn}
                          </option>
                        ))}
                      </select>
                    </label>
                    <SubmitButton tone="secondary">{messages.save}</SubmitButton>
                  </form>
                ) : null}
                {access.membershipId !== member.id ? (
                  <form action={setMembershipStatusAction} className="team-status-action">
                    <input name="locale" type="hidden" value={locale} />
                    <input name="membershipId" type="hidden" value={member.id} />
                    <input
                      name="status"
                      type="hidden"
                      value={
                        member.status === MembershipStatus.ACTIVE
                          ? MembershipStatus.SUSPENDED
                          : MembershipStatus.ACTIVE
                      }
                    />
                    <SubmitButton
                      tone={member.status === MembershipStatus.ACTIVE ? "danger" : "secondary"}
                    >
                      {member.status === MembershipStatus.ACTIVE
                        ? messages.suspend
                        : messages.activate}
                    </SubmitButton>
                  </form>
                ) : null}
              </details>
            ) : null}
          </article>
        ))}
      </div>

      {canManage ? (
        <details className="panel action-disclosure invitation-history">
          <summary>
            {workspace.invitationHistory} <span>{invitations.length}</span>
          </summary>
          {invitations.length === 0 ? (
            <p className="muted">{workspace.noInvitations}</p>
          ) : (
            <ul className="invitation-list">
              {invitations.map((invitation) => (
                <li key={invitation.id}>
                  <div>
                    <strong dir="ltr">{invitation.email}</strong>
                    <span>{locale === "ar" ? invitation.role.nameAr : invitation.role.nameEn}</span>
                  </div>
                  <span className={`status status-${invitation.status.toLowerCase()}`}>
                    {phaseOneValueLabel(locale, invitation.status)}
                  </span>
                  {invitation.status === "PENDING" ? (
                    <form action={revokeInvitationAction}>
                      <input name="invitationId" type="hidden" value={invitation.id} />
                      <input name="locale" type="hidden" value={locale} />
                      <SubmitButton tone="danger">{messages.revoke}</SubmitButton>
                    </form>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </details>
      ) : null}
    </section>
  );
}

function initials(name: string): string {
  return name
    .trim()
    .split(/\s+/u)
    .slice(0, 2)
    .map((part) => part.slice(0, 1).toUpperCase())
    .join("");
}

const weekdayOptions = [
  "SATURDAY",
  "SUNDAY",
  "MONDAY",
  "TUESDAY",
  "WEDNESDAY",
  "THURSDAY",
  "FRIDAY",
] as const;

function weekdayLabel(locale: "ar" | "en", weekday: (typeof weekdayOptions)[number]): string {
  const labels = {
    ar: {
      FRIDAY: "الجمعة",
      MONDAY: "الاثنين",
      SATURDAY: "السبت",
      SUNDAY: "الأحد",
      THURSDAY: "الخميس",
      TUESDAY: "الثلاثاء",
      WEDNESDAY: "الأربعاء",
    },
    en: {
      FRIDAY: "Friday",
      MONDAY: "Monday",
      SATURDAY: "Saturday",
      SUNDAY: "Sunday",
      THURSDAY: "Thursday",
      TUESDAY: "Tuesday",
      WEDNESDAY: "Wednesday",
    },
  } as const;
  return labels[locale][weekday];
}

function minuteInput(minute: number): string {
  return `${Math.floor(minute / 60)
    .toString()
    .padStart(2, "0")}:${(minute % 60).toString().padStart(2, "0")}`;
}
