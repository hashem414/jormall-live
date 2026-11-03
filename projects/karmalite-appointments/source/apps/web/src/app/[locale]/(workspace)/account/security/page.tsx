import { isSupportedLocale } from "@jormall/contracts/locales";
import { notFound } from "next/navigation";

import { Feedback } from "../../../../../components/feedback";
import { SubmitButton } from "../../../../../components/submit-button";
import { requireTenantAccess } from "../../../../../server/identity";
import { changePasswordAction } from "../../../actions";

export default async function AccountSecurityPage({
  params,
  searchParams,
}: PageProps<"/[locale]/account/security">) {
  const [{ locale }, query] = await Promise.all([params, searchParams]);
  if (!isSupportedLocale(locale)) notFound();
  await requireTenantAccess(locale);

  return (
    <section className="page-stack" aria-labelledby="account-security-title">
      <div>
        <p className="eyebrow">{locale === "ar" ? "الحساب" : "Account"}</p>
        <h1 id="account-security-title">{locale === "ar" ? "أمان الحساب" : "Account Security"}</h1>
        <p className="muted">
          {locale === "ar"
            ? "غيّر كلمة مرورك بأمان. سيتم تسجيل خروج الجلسات الأخرى."
            : "Change your password securely. Other signed-in sessions will be revoked."}
        </p>
      </div>
      <Feedback
        error={typeof query.error === "string" ? query.error : undefined}
        locale={locale}
        notice={typeof query.notice === "string" ? query.notice : undefined}
      />
      <form action={changePasswordAction} className="panel form-stack account-security-form">
        <input name="locale" type="hidden" value={locale} />
        <PasswordField
          autoComplete="current-password"
          label={locale === "ar" ? "كلمة المرور الحالية" : "Current password"}
          name="currentPassword"
        />
        <PasswordField
          autoComplete="new-password"
          label={locale === "ar" ? "كلمة المرور الجديدة" : "New password"}
          minLength={12}
          name="newPassword"
        />
        <PasswordField
          autoComplete="new-password"
          label={locale === "ar" ? "تأكيد كلمة المرور الجديدة" : "Confirm new password"}
          minLength={12}
          name="confirmPassword"
        />
        <p className="field-hint">
          {locale === "ar"
            ? "استخدم 12 حرفاً على الأقل ولا تعِد استخدام كلمة المرور الحالية."
            : "Use at least 12 characters and do not reuse your current password."}
        </p>
        <SubmitButton>{locale === "ar" ? "تغيير كلمة المرور" : "Change Password"}</SubmitButton>
      </form>
    </section>
  );
}

function PasswordField({
  autoComplete,
  label,
  minLength,
  name,
}: Readonly<{
  autoComplete: "current-password" | "new-password";
  label: string;
  minLength?: number;
  name: string;
}>) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      <input
        autoComplete={autoComplete}
        className="input"
        maxLength={128}
        minLength={minLength}
        name={name}
        required
        type="password"
      />
    </label>
  );
}
