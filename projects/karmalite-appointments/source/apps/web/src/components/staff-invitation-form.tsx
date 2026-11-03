"use client";

import type { SupportedLocale } from "@jormall/contracts/locales";
import { useActionState } from "react";

import { createInvitationAction } from "../app/[locale]/actions";
import { phaseOneMessages } from "../messages/phase-one";
import { Feedback } from "./feedback";
import { SubmitButton } from "./submit-button";

type InvitationRole = Readonly<{ id: string; nameAr: string; nameEn: string }>;

export function StaffInvitationForm({
  embedded = false,
  fixedRoleId,
  locale,
  roles,
}: Readonly<{
  embedded?: boolean;
  fixedRoleId?: string;
  locale: SupportedLocale;
  roles: readonly InvitationRole[];
}>) {
  const [state, action] = useActionState(createInvitationAction, {});
  const messages = phaseOneMessages[locale];
  const successful = state.code === "INVITATION_CREATED";
  const fixedRole = fixedRoleId ? roles.find(({ id }) => id === fixedRoleId) : undefined;
  return (
    <div className={embedded ? "embedded-action-stack" : "page-stack"}>
      <Feedback
        error={!successful ? state.code : undefined}
        invitation={state.invitationUrl}
        locale={locale}
        notice={successful ? state.code : undefined}
      />
      <form action={action} className={embedded ? "form-grid workspace-form" : "panel inline-form"}>
        <input name="locale" type="hidden" value={locale} />
        <label className="field">
          <span className="field-label">{messages.email}</span>
          <input className="input" dir="ltr" name="email" required type="email" />
        </label>
        {fixedRole ? (
          <label className="field">
            <span className="field-label">{messages.invitationRole}</span>
            <span className="input role-fixed-value">
              {locale === "ar" ? fixedRole.nameAr : fixedRole.nameEn}
            </span>
            <input name="roleId" type="hidden" value={fixedRole.id} />
          </label>
        ) : (
          <label className="field">
            <span className="field-label">{messages.invitationRole}</span>
            <select className="select" name="roleId" required>
              <option value="">{locale === "ar" ? "اختر دورًا" : "Select a role"}</option>
              {roles.map((role) => (
                <option key={role.id} value={role.id}>
                  {locale === "ar" ? role.nameAr : role.nameEn}
                </option>
              ))}
            </select>
          </label>
        )}
        <SubmitButton>{messages.inviteStaff}</SubmitButton>
      </form>
    </div>
  );
}
