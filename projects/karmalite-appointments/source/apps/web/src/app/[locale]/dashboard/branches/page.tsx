import { canAccessResource } from "@jormall/auth/tenant-policy";
import { isSupportedLocale } from "@jormall/contracts/locales";
import { notFound } from "next/navigation";

import { Feedback } from "../../../../components/feedback";
import { SubmitButton } from "../../../../components/submit-button";
import { phaseOneMessages } from "../../../../messages/phase-one";
import { identityRepository, requirePagePermission } from "../../../../server/identity";
import { createBranchAction, deleteBranchAction, updateBranchAction } from "../../actions";

export default async function BranchesPage({
  params,
  searchParams,
}: PageProps<"/[locale]/dashboard/branches">) {
  const { locale } = await params;
  if (!isSupportedLocale(locale)) notFound();
  const [access, query] = await Promise.all([
    requirePagePermission(locale, "branches.read"),
    searchParams,
  ]);
  const branches = await identityRepository.listBranches(access);
  const canManage = canAccessResource(access, "branches.manage");
  const messages = phaseOneMessages[locale];
  return (
    <section className="page-stack" aria-labelledby="branches-title">
      <div>
        <p className="eyebrow">{messages.activeOrganization}</p>
        <h1 id="branches-title">{messages.branches}</h1>
      </div>
      <Feedback
        error={typeof query.error === "string" ? query.error : undefined}
        locale={locale}
        notice={typeof query.notice === "string" ? query.notice : undefined}
      />
      <div className="card-grid branch-directory">
        {branches.map((branch) => (
          <article className="record-card branch-card" key={branch.id}>
            <header>
              <span className="status status-pending">
                {branch.locationStatus === "APPROVED"
                  ? locale === "ar"
                    ? "معتمد"
                    : "Approved"
                  : locale === "ar"
                    ? "بحاجة للمراجعة"
                    : "Needs review"}
              </span>
              <h2>{locale === "ar" ? branch.nameAr : branch.nameEn}</h2>
              <p className="muted" dir="ltr">
                {branch.timezone}
              </p>
            </header>
            <dl className="branch-contact-list">
              <div>
                <dt>{locale === "ar" ? "العنوان" : "Address"}</dt>
                <dd>{locale === "ar" ? branch.addressAr : branch.addressEn}</dd>
              </div>
              <div>
                <dt>{locale === "ar" ? "الهاتف" : "Contact"}</dt>
                <dd dir="ltr">
                  {branch.phone ?? "—"}
                  <br />
                  {branch.mobilePhone ?? ""}
                </dd>
              </div>
              <div>
                <dt>{locale === "ar" ? "البريد الإلكتروني" : "Email"}</dt>
                <dd dir="ltr">{branch.email ?? "—"}</dd>
              </div>
              <div>
                <dt>{locale === "ar" ? "ساعات العمل" : "Working hours"}</dt>
                <dd>{formatBranchHours(locale, branch.hoursRules)}</dd>
              </div>
            </dl>
            <div className="branch-card-actions">
              {branch.mapUrl ? (
                <a
                  className="button button-secondary"
                  href={branch.mapUrl}
                  rel="noreferrer"
                  target="_blank"
                >
                  {locale === "ar" ? "عرض الموقع" : "View location"}
                </a>
              ) : null}
              {canManage ? (
                <details className="inline-disclosure branch-edit-disclosure">
                  <summary>{locale === "ar" ? "تعديل الفرع" : "Edit branch"}</summary>
                  <form action={updateBranchAction} className="form-grid branch-edit-form">
                    <input name="branchId" type="hidden" value={branch.id} />
                    <input name="locale" type="hidden" value={locale} />
                    <label className="field">
                      <span className="field-label">{messages.englishName}</span>
                      <input
                        className="input"
                        defaultValue={branch.nameEn}
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
                        defaultValue={branch.nameAr}
                        dir="rtl"
                        name="nameAr"
                        required
                      />
                    </label>
                    <label className="field">
                      <span className="field-label">{messages.timezone}</span>
                      <input
                        className="input"
                        defaultValue={branch.timezone}
                        dir="ltr"
                        name="timezone"
                        required
                      />
                    </label>
                    <label className="field">
                      <span className="field-label">{messages.phone}</span>
                      <input
                        className="input"
                        defaultValue={branch.phone ?? ""}
                        dir="ltr"
                        name="phone"
                        type="tel"
                      />
                    </label>
                    <label className="field">
                      <span className="field-label">
                        {locale === "ar" ? "الهاتف المحمول / واتساب" : "Mobile / WhatsApp"}
                      </span>
                      <input
                        className="input"
                        defaultValue={branch.mobilePhone ?? ""}
                        dir="ltr"
                        name="mobilePhone"
                        type="tel"
                      />
                    </label>
                    <label className="field">
                      <span className="field-label">
                        {locale === "ar" ? "البريد الإلكتروني" : "Email"}
                      </span>
                      <input
                        className="input"
                        defaultValue={branch.email ?? ""}
                        dir="ltr"
                        name="email"
                        type="email"
                      />
                    </label>
                    <label className="field">
                      <span className="field-label">
                        {locale === "ar" ? "رابط الموقع على الخريطة" : "Map URL"}
                      </span>
                      <input
                        className="input"
                        defaultValue={branch.mapUrl ?? ""}
                        dir="ltr"
                        name="mapUrl"
                        type="url"
                      />
                    </label>
                    <label className="field">
                      <span className="field-label">{messages.addressEn}</span>
                      <input
                        className="input"
                        defaultValue={branch.addressEn ?? ""}
                        name="addressEn"
                      />
                    </label>
                    <label className="field">
                      <span className="field-label">{messages.addressAr}</span>
                      <input
                        className="input"
                        defaultValue={branch.addressAr ?? ""}
                        dir="rtl"
                        name="addressAr"
                      />
                    </label>
                    <SubmitButton>
                      {locale === "ar" ? "حفظ التعديلات" : "Save changes"}
                    </SubmitButton>
                  </form>
                </details>
              ) : null}
              {canManage && branches.length > 1 ? (
                <details className="inline-disclosure danger-disclosure">
                  <summary>{locale === "ar" ? "إجراءات إضافية" : "More actions"}</summary>
                  <form action={deleteBranchAction}>
                    <input name="branchId" type="hidden" value={branch.id} />
                    <input name="locale" type="hidden" value={locale} />
                    <SubmitButton
                      confirmMessage={
                        locale === "ar"
                          ? "هل أنت متأكد من حذف هذا الفرع؟"
                          : "Delete this branch? This cannot be undone."
                      }
                      tone="danger"
                    >
                      {messages.delete}
                    </SubmitButton>
                  </form>
                </details>
              ) : null}
            </div>
          </article>
        ))}
        {branches.length === 0 ? <p className="empty-state">{messages.noRecords}</p> : null}
      </div>
      {canManage ? (
        <details className="panel action-disclosure branch-create-disclosure">
          <summary>+ {messages.addBranch}</summary>
          <form action={createBranchAction} className="form-grid">
            <input name="locale" type="hidden" value={locale} />
            <label className="field">
              <span className="field-label">{messages.englishName}</span>
              <input className="input" name="nameEn" required />
            </label>
            <label className="field">
              <span className="field-label">الاسم بالعربية</span>
              <input className="input" dir="rtl" name="nameAr" required />
            </label>
            <label className="field">
              <span className="field-label">{messages.timezone}</span>
              <input
                className="input"
                defaultValue="Asia/Amman"
                dir="ltr"
                name="timezone"
                required
              />
            </label>
            <label className="field">
              <span className="field-label">{messages.phone}</span>
              <input className="input" dir="ltr" name="phone" type="tel" />
            </label>
            <label className="field">
              <span className="field-label">
                {locale === "ar" ? "الهاتف المحمول / واتساب" : "Mobile / WhatsApp"}
              </span>
              <input className="input" dir="ltr" name="mobilePhone" type="tel" />
            </label>
            <label className="field">
              <span className="field-label">{locale === "ar" ? "البريد الإلكتروني" : "Email"}</span>
              <input className="input" dir="ltr" name="email" type="email" />
            </label>
            <label className="field">
              <span className="field-label">
                {locale === "ar" ? "رابط الموقع على الخريطة" : "Map URL"}
              </span>
              <input className="input" dir="ltr" name="mapUrl" placeholder="https://" type="url" />
            </label>
            <label className="field">
              <span className="field-label">{messages.addressEn}</span>
              <input className="input" name="addressEn" />
            </label>
            <label className="field">
              <span className="field-label">{messages.addressAr}</span>
              <input className="input" dir="rtl" name="addressAr" />
            </label>
            <div className="form-actions">
              <SubmitButton>{messages.addBranch}</SubmitButton>
            </div>
          </form>
        </details>
      ) : null}
    </section>
  );
}

function formatBranchHours(
  locale: "ar" | "en",
  rules: readonly Readonly<{ endMinuteLocal: number; startMinuteLocal: number; weekday: string }>[],
): string {
  if (rules.length === 0) return locale === "ar" ? "غير محددة" : "Not configured";
  const times = new Set(
    rules.map(({ endMinuteLocal, startMinuteLocal }) => `${startMinuteLocal}-${endMinuteLocal}`),
  );
  if (times.size === 1 && rules.length === 6) {
    const rule = rules[0];
    if (rule) {
      const time = `${formatMinute(rule.startMinuteLocal)}–${formatMinute(rule.endMinuteLocal)}`;
      return locale === "ar"
        ? `السبت–الخميس، ${time} · الجمعة مغلق`
        : `Sat–Thu, ${time} · Friday closed`;
    }
  }
  return locale === "ar" ? `${rules.length} أيام مضبوطة` : `${rules.length} days configured`;
}

function formatMinute(minute: number): string {
  const hour = Math.floor(minute / 60);
  const minutes = minute % 60;
  const suffix = hour >= 12 ? "PM" : "AM";
  const displayHour = hour % 12 || 12;
  return `${displayHour}:${String(minutes).padStart(2, "0")} ${suffix}`;
}
