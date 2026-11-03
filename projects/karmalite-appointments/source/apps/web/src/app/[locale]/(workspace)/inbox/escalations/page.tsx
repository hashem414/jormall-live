import { canAccessResource } from "@jormall/auth/tenant-policy";
import { isSupportedLocale } from "@jormall/contracts/locales";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Feedback } from "../../../../../components/feedback";
import { SubmitButton } from "../../../../../components/submit-button";
import {
  operationalWorkflowsRepository,
  requirePagePermission,
} from "../../../../../server/identity";
import { updateChatbotEscalationAction } from "../../../actions";

export default async function EscalationsPage({
  params,
  searchParams,
}: PageProps<"/[locale]/inbox/escalations">) {
  const [{ locale }, query] = await Promise.all([params, searchParams]);
  if (!isSupportedLocale(locale)) notFound();
  const access = await requirePagePermission(locale, "chatbot_escalations.read");
  const canManage = canAccessResource(access, "chatbot_escalations.manage");
  const [rows, assignees] = await Promise.all([
    operationalWorkflowsRepository.listEscalations(access),
    canManage
      ? operationalWorkflowsRepository.listEscalationAssignees(access)
      : Promise.resolve([]),
  ]);
  const selected = rows.find(({ id }) => id === query.escalation);
  const t =
    locale === "ar"
      ? {
          heading: "تصعيدات المساعد الآلي",
          empty: "لا توجد تصعيدات.",
          patient: "المريض",
          summary: "البلاغ",
          evidence: "الرسالة ذات الصلة",
          contact: "معلومات التواصل",
          open: "فتح",
          update: "تحديث الحالة",
          reason: "ملاحظة الحل أو سبب الرفض",
          warning: "هذه قائمة تشغيلية للتواصل مع المريض ولا تمثل تشخيصاً أو بديلاً لخدمات الطوارئ.",
        }
      : {
          heading: "Chatbot Escalations",
          empty: "No escalations.",
          patient: "Patient",
          summary: "Reported concern",
          evidence: "Relevant message",
          contact: "Contact",
          open: "Open",
          update: "Update status",
          reason: "Resolution note or dismissal reason",
          warning:
            "This is an operational contact queue, not a diagnosis or a replacement for emergency services.",
        };
  return (
    <section className="page-stack">
      <div>
        <p className="eyebrow">Inbox</p>
        <h1>{t.heading}</h1>
        <p>{t.warning}</p>
      </div>
      <Feedback
        error={typeof query.error === "string" ? query.error : undefined}
        locale={locale}
        notice={typeof query.notice === "string" ? query.notice : undefined}
      />
      {rows.length === 0 ? (
        <p className="panel">{t.empty}</p>
      ) : (
        <div className="card-grid">
          {rows.map((row) => (
            <article className="record-card" key={row.id}>
              <span className="status">{row.severity}</span>
              <span className="status">{row.status}</span>
              <h2>{row.customer?.displayName ?? row.patientName}</h2>
              <p>{row.emergencySummary}</p>
              <p dir="ltr">
                {row.phone ?? "—"} · {row.email ?? "—"}
              </p>
              <p>
                {row.assignedMembership?.user.name ??
                  (locale === "ar" ? "غير معيّن" : "Unassigned")}
              </p>
              <Link
                className="button-link"
                href={`/${locale}/inbox/escalations?escalation=${row.id}`}
              >
                {t.open}
              </Link>
            </article>
          ))}
        </div>
      )}
      {selected ? (
        <section className="panel">
          <h2>{selected.patientName}</h2>
          <dl className="detail-list">
            <dt>{t.summary}</dt>
            <dd>{selected.emergencySummary}</dd>
            <dt>{t.evidence}</dt>
            <dd>{selected.relevantMessage}</dd>
            <dt>{t.contact}</dt>
            <dd dir="ltr">
              {selected.phone ?? "—"} · {selected.email ?? "—"}
            </dd>
          </dl>
          <div className="button-row">
            {selected.phone ? (
              <a className="button-link" href={`tel:${selected.phone}`}>
                {locale === "ar" ? "اتصال" : "Call Patient"}
              </a>
            ) : null}
            {selected.email ? (
              <a className="button-link" href={`mailto:${selected.email}`}>
                {locale === "ar" ? "بريد إلكتروني" : "Email Patient"}
              </a>
            ) : null}
            {selected.customerId ? (
              <Link className="button-link" href={`/${locale}/customers/${selected.customerId}`}>
                {locale === "ar" ? "ملف المريض" : "Open Patient Profile"}
              </Link>
            ) : null}
            {selected.appointmentId ? (
              <Link
                className="button-link"
                href={`/${locale}/schedule/appointments/${selected.appointmentId}`}
              >
                {locale === "ar" ? "فتح الموعد" : "Open Appointment"}
              </Link>
            ) : null}
          </div>
          {canManage ? (
            <form action={updateChatbotEscalationAction} className="form-grid">
              <input name="locale" type="hidden" value={locale} />
              <input name="id" type="hidden" value={selected.id} />
              <input name="expectedVersion" type="hidden" value={selected.version} />
              <label className="field">
                <span className="field-label">{t.update}</span>
                <select className="select" name="status">
                  <option value="NEW">{locale === "ar" ? "جديد" : "New"}</option>
                  <option value="ACKNOWLEDGED">Acknowledge</option>
                  <option value="IN_PROGRESS">In Progress</option>
                  <option value="RESOLVED">Resolve</option>
                  <option value="DISMISSED">Dismiss</option>
                </select>
              </label>
              <label className="field">
                <span className="field-label">{locale === "ar" ? "تعيين إلى" : "Assign to"}</span>
                <select
                  className="select"
                  defaultValue={selected.assignedMembershipId ?? ""}
                  name="assignedMembershipId"
                >
                  <option value="">{locale === "ar" ? "غير معيّن" : "Unassigned"}</option>
                  {assignees.map((membership) => (
                    <option key={membership.id} value={membership.id}>
                      {membership.user.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span className="field-label">{t.reason}</span>
                <textarea className="input textarea" name="reason" />
              </label>
              <SubmitButton>{t.update}</SubmitButton>
            </form>
          ) : null}
        </section>
      ) : null}
    </section>
  );
}
