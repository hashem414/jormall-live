import { canAccessResource } from "@jormall/auth/tenant-policy";
import { isSupportedLocale } from "@jormall/contracts/locales";
import { isPermissionCode } from "@jormall/domain/identity";
import { notFound } from "next/navigation";

import { Feedback } from "../../../../components/feedback";
import { PermissionSelector } from "../../../../components/permission-selector";
import { StaffInvitationForm } from "../../../../components/staff-invitation-form";
import { SubmitButton } from "../../../../components/submit-button";
import { phaseOneMessages, phaseOneValueLabel } from "../../../../messages/phase-one";
import { identityRepository, requirePagePermission } from "../../../../server/identity";
import { createRoleAction, deleteRoleAction, updateRoleAction } from "../../actions";

const permissionSectionOrder = [
  "inventory",
  "appointments",
  "patients",
  "team",
  "business",
  "communications",
  "insights",
  "settings",
] as const;

type PermissionSectionKey = (typeof permissionSectionOrder)[number];

function permissionSection(code: string): PermissionSectionKey {
  if (code.startsWith("inventory.")) return "inventory";
  if (
    code.startsWith("appointment") ||
    code.startsWith("appointments.") ||
    code.startsWith("schedules.") ||
    code.startsWith("waitlist.") ||
    code.startsWith("slot_offers.") ||
    code.startsWith("room.") ||
    code.startsWith("doctor.queue.")
  )
    return "appointments";
  if (code.startsWith("patients.") || code.startsWith("customers.") || code.startsWith("consent."))
    return "patients";
  if (code.startsWith("staff.") || code.startsWith("roles.")) return "team";
  if (
    code.startsWith("branches.") ||
    code.startsWith("services.") ||
    code.startsWith("resources.") ||
    code.startsWith("organization.")
  )
    return "business";
  if (
    code.startsWith("messages.") ||
    code.startsWith("conversations.") ||
    code.startsWith("communication_") ||
    code.startsWith("chatbot_") ||
    code.startsWith("notifications.") ||
    code.startsWith("recordings.")
  )
    return "communications";
  if (code.startsWith("reports.") || code.startsWith("predictions.") || code.startsWith("ai."))
    return "insights";
  return "settings";
}

export default async function RolesPage({
  params,
  searchParams,
}: PageProps<"/[locale]/dashboard/roles">) {
  const { locale } = await params;
  if (!isSupportedLocale(locale)) notFound();
  const [access, query] = await Promise.all([
    requirePagePermission(locale, "roles.read"),
    searchParams,
  ]);
  const canManage = canAccessResource(access, "roles.manage");
  const [roles, availablePermissions, actorRoles] = await Promise.all([
    identityRepository.listRoles(access, canManage ? undefined : access.membershipId),
    canManage ? identityRepository.listPermissions() : Promise.resolve([]),
    access.membershipId
      ? identityRepository.listRoles(access, access.membershipId)
      : Promise.resolve([]),
  ]);
  const actorIsOwner = actorRoles.some(({ systemKey }) => systemKey === "ORGANIZATION_OWNER");
  const delegationResource = {
    ...(access.assignedBranchIds[0] ? { branchId: access.assignedBranchIds[0] } : {}),
    ...(access.staffProfileId ? { staffProfileId: access.staffProfileId } : {}),
  };
  const canInvite = canAccessResource(access, "staff.manage", delegationResource);
  const permissions = availablePermissions.filter(
    (permission) =>
      isPermissionCode(permission.code) &&
      canAccessResource(access, permission.code, delegationResource),
  );
  const permissionSections = permissionSectionOrder
    .map((key) => ({
      key,
      permissions: permissions.filter((permission) => permissionSection(permission.code) === key),
    }))
    .filter(({ permissions: sectionPermissions }) => sectionPermissions.length > 0);
  const messages = phaseOneMessages[locale];
  const addPerson = locale === "ar" ? "إضافة شخص بنفس الدور" : "Add person with this role";
  const selectAll = locale === "ar" ? "تحديد كل الصلاحيات" : "Select all access";
  const clearAll = locale === "ar" ? "إلغاء تحديد الكل" : "Clear all access";
  const maximizeRole = locale === "ar" ? "توسيع" : "Maximize";
  const minimizeRole = locale === "ar" ? "تصغير" : "Minimize";
  const pageTitle = locale === "ar" ? "الأدوار والصلاحيات" : "Roles & Access";
  const pageDescription =
    locale === "ar"
      ? "أنشئ أدوارًا مخصصة وحدد الصلاحيات المناسبة لكل دور."
      : "Create custom roles and choose exactly which areas each role can access.";
  const editRole = locale === "ar" ? "تعديل الدور" : "Edit role";
  const deleteRole = locale === "ar" ? "حذف الدور" : "Delete role";
  const saveChanges = locale === "ar" ? "حفظ التغييرات" : "Save changes";
  const deleteWarning =
    locale === "ar"
      ? "يمكن حذف الأدوار المخصصة غير المستخدمة فقط. أزل الدور من الموظفين والدعوات أولاً."
      : "Only unused custom roles can be deleted. Remove the role from staff and invitations first.";
  const confirmDelete =
    locale === "ar"
      ? "أؤكد أنني أريد حذف هذا الدور."
      : "I confirm that I want to delete this role.";
  const sectionLabels: Readonly<Record<PermissionSectionKey, string>> =
    locale === "ar"
      ? {
          appointments: "المواعيد والجدولة",
          business: "إعدادات المركز",
          communications: "التواصل والإشعارات",
          insights: "التقارير والرؤى",
          inventory: "المخزون وطلبات الأصناف",
          patients: "المرضى والموافقات",
          settings: "الإعدادات والإدارة",
          team: "الفريق والصلاحيات",
        }
      : {
          appointments: "Appointments & scheduling",
          business: "Center setup",
          communications: "Communications & notifications",
          insights: "Reports & insights",
          inventory: "Inventory & item requests",
          patients: "Patients & consent",
          settings: "Settings & administration",
          team: "Team & access",
        };
  const inventoryHelp =
    locale === "ar"
      ? "صلاحية طلب صنف جديد تسمح للموظف بإرسال طلب فقط. الموافقة والشراء والاستلام وتعديل الرصيد صلاحيات منفصلة."
      : "Request new inventory items only allows staff to submit a request. Approval, purchasing, receiving, and stock changes are separate permissions.";
  return (
    <section className="page-stack" aria-labelledby="roles-title">
      <div>
        <p className="eyebrow">{messages.activeOrganization}</p>
        <h1 id="roles-title">{pageTitle}</h1>
        <p className="page-description">{pageDescription}</p>
      </div>
      <Feedback
        error={typeof query.error === "string" ? query.error : undefined}
        locale={locale}
        notice={typeof query.notice === "string" ? query.notice : undefined}
      />
      {canManage ? (
        <form action={createRoleAction} className="panel form-grid">
          <input name="locale" type="hidden" value={locale} />
          <label className="field">
            <span className="field-label">{messages.englishName}</span>
            <input className="input" name="nameEn" required />
          </label>
          <label className="field">
            <span className="field-label">
              {locale === "ar" ? "الاسم بالعربية" : "Arabic name"}
            </span>
            <input className="input" dir="rtl" name="nameAr" required />
          </label>
          <PermissionSelector
            clearAllLabel={clearAll}
            legend={messages.permissions}
            sections={permissionSections.map((section) => ({
              ...(section.key === "inventory" ? { description: inventoryHelp } : {}),
              key: section.key,
              label: sectionLabels[section.key],
              permissions: section.permissions.map((permission) => ({
                code: permission.code,
                id: permission.id,
                label: locale === "ar" ? permission.nameAr : permission.nameEn,
              })),
            }))}
            selectAllLabel={selectAll}
          />
          <div className="form-actions">
            <SubmitButton>{messages.addRole}</SubmitButton>
          </div>
        </form>
      ) : null}
      <div className="card-grid">
        {roles.map((role) => (
          <article className="record-card role-card" key={role.id}>
            <details className="role-card-disclosure">
              <summary className="role-card-summary">
                <span className="role-card-title">
                  <span className="status">
                    {phaseOneValueLabel(locale, role.isSystem ? "SYSTEM" : "CUSTOM")}
                  </span>
                  <strong>{locale === "ar" ? role.nameAr : role.nameEn}</strong>
                </span>
                <span className="role-card-toggle">
                  <svg aria-hidden="true" viewBox="0 0 24 24">
                    <path d="m6 9 6 6 6-6" />
                  </svg>
                  <span className="sr-only role-card-toggle-closed">{maximizeRole}</span>
                  <span className="sr-only role-card-toggle-open">{minimizeRole}</span>
                </span>
              </summary>
              <div className="role-card-content">
                <ul>
                  {role.permissions.map(({ permission, scope }) => (
                    <li key={permission.id}>
                      <span>{locale === "ar" ? permission.nameAr : permission.nameEn}</span>
                      <small>{phaseOneValueLabel(locale, scope)}</small>
                    </li>
                  ))}
                </ul>
                {canManage && (!role.isSystem || actorIsOwner) ? (
                  <div className="form-actions">
                    <details className="inline-disclosure">
                      <summary className="button button-secondary">{editRole}</summary>
                      <form action={updateRoleAction} className="form-stack">
                        <input name="locale" type="hidden" value={locale} />
                        <input name="roleId" type="hidden" value={role.id} />
                        <label className="field">
                          <span className="field-label">{messages.englishName}</span>
                          <input
                            className="input"
                            defaultValue={role.nameEn}
                            name="nameEn"
                            required
                          />
                        </label>
                        <label className="field">
                          <span className="field-label">
                            {locale === "ar" ? "الاسم بالعربية" : "Arabic name"}
                          </span>
                          <input
                            className="input"
                            defaultValue={role.nameAr}
                            dir="rtl"
                            name="nameAr"
                            required
                          />
                        </label>
                        <PermissionSelector
                          clearAllLabel={clearAll}
                          initialPermissionCodes={role.permissions.map(
                            ({ permission }) => permission.code,
                          )}
                          legend={messages.permissions}
                          sections={permissionSections.map((section) => ({
                            ...(section.key === "inventory" ? { description: inventoryHelp } : {}),
                            key: section.key,
                            label: sectionLabels[section.key],
                            permissions: section.permissions.map((permission) => ({
                              code: permission.code,
                              id: permission.id,
                              label: locale === "ar" ? permission.nameAr : permission.nameEn,
                            })),
                          }))}
                          selectAllLabel={selectAll}
                        />
                        <SubmitButton>{saveChanges}</SubmitButton>
                      </form>
                    </details>
                    {!role.isSystem ? (
                      <details className="inline-disclosure">
                        <summary className="button button-danger">{deleteRole}</summary>
                        <form action={deleteRoleAction} className="form-stack">
                          <input name="locale" type="hidden" value={locale} />
                          <input name="roleId" type="hidden" value={role.id} />
                          <p className="muted">{deleteWarning}</p>
                          <label className="check-field">
                            <input
                              name="confirmation"
                              required
                              type="checkbox"
                              value="DELETE_CUSTOM_ROLE"
                            />
                            <span>{confirmDelete}</span>
                          </label>
                          <SubmitButton tone="danger">{deleteRole}</SubmitButton>
                        </form>
                      </details>
                    ) : null}
                  </div>
                ) : null}
                {canInvite && (role.systemKey !== "ORGANIZATION_OWNER" || actorIsOwner) ? (
                  <details className="inline-disclosure role-invite-disclosure">
                    <summary className="button button-primary">{addPerson}</summary>
                    <StaffInvitationForm
                      embedded
                      fixedRoleId={role.id}
                      locale={locale}
                      roles={[role]}
                    />
                  </details>
                ) : null}
              </div>
            </details>
          </article>
        ))}
      </div>
    </section>
  );
}
