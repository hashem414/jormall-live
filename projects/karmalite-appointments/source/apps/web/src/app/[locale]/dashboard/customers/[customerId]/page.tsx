import { canAccessResource } from "@jormall/auth/tenant-policy";
import { isSupportedLocale } from "@jormall/contracts/locales";
import { ConsentStatus } from "@jormall/db/generated/enums";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Feedback } from "../../../../../components/feedback";
import { SubmitButton } from "../../../../../components/submit-button";
import { MessageTimeline } from "../../../../../components/message-timeline";
import { phaseOneMessages } from "../../../../../messages/phase-one";
import { phaseTwoMessages } from "../../../../../messages/phase-two";
import { phaseSixKind, phaseSixMessages } from "../../../../../messages/phase-six";
import {
  communicationRepository,
  copilotRepository,
  crmAppointmentRepository,
  identityRepository,
  requireTenantAccess,
} from "../../../../../server/identity";
import {
  addCustomerNoteAction,
  recordConsentAction,
  generateCopilotInsightAction,
  setCommunicationPreferenceAction,
  updateCustomerAction,
} from "../../../actions";

export default async function CustomerProfilePage({
  params,
  searchParams,
}: PageProps<"/[locale]/dashboard/customers/[customerId]">) {
  const { customerId, locale } = await params;
  if (!isSupportedLocale(locale)) notFound();
  const [access, query] = await Promise.all([requireTenantAccess(locale), searchParams]);
  const customer = await crmAppointmentRepository.getCustomer(access, customerId);
  const branches = canAccessResource(access, "branches.read")
    ? await identityRepository.listBranches(access)
    : [];
  const activeBranch = access.activeBranchId
    ? branches.find(({ id }) => id === access.activeBranchId)
    : undefined;
  const phaseOne = phaseOneMessages[locale];
  const messages = phaseTwoMessages[locale];
  const canWrite = canAccessResource(access, "customers.write");
  const canRecordConsent = canAccessResource(access, "consent.record");
  const canManagePreferences = canAccessResource(access, "communication_preferences.manage");
  const canReadMessages = canAccessResource(access, "messages.read");
  const canUseCopilot = access.grants.some(({ code }) => code === "reports.read");
  const customerInsights = canUseCopilot
    ? await copilotRepository.listInsights(access, "CUSTOMER_SUMMARY")
    : [];
  const latestCustomerInsight = customerInsights.find(({ subjectId }) => subjectId === customer.id);
  const [messageTimeline, preferences] = canReadMessages
    ? await Promise.all([
        communicationRepository.listCustomerMessages(access, customer.id),
        communicationRepository.listCustomerPreferences(access, customer.id),
      ])
    : [[], []];
  const primaryPhone = customer.contacts.find((contact) => contact.isPrimary)?.originalValue ?? "";
  return (
    <section className="page-stack" aria-labelledby="customer-title">
      <div className="split-heading">
        <div>
          <p className="eyebrow">{messages.customerProfile}</p>
          <h1 id="customer-title">{customer.displayName}</h1>
          <p className="muted">{customer.referenceCode}</p>
        </div>
        <div>
          <Link
            className="button button-primary"
            href={`/${locale}/schedule/calendar?patient=${customer.id}#create-appointment-title`}
          >
            + {messages.bookAppointment}
          </Link>
        </div>
      </div>
      <Feedback
        error={typeof query.error === "string" ? query.error : undefined}
        locale={locale}
        notice={typeof query.notice === "string" ? query.notice : undefined}
      />
      {Number(query.duplicates) > 0 ? (
        <div className="feedback feedback-info" role="status">
          {locale === "ar"
            ? `عُثر على ${Number(query.duplicates)} سجل/سجلات محتملة مشابهة. لم يتم دمج أي سجل.`
            : `${Number(query.duplicates)} likely duplicate record(s) found. No records were merged.`}
        </div>
      ) : null}
      {canUseCopilot ? (
        <section className="panel page-stack" aria-labelledby="customer-copilot-title">
          <div className="split-heading">
            <div>
              <p className="eyebrow">{phaseSixMessages[locale].facts}</p>
              <h2 id="customer-copilot-title">
                {locale === "ar" ? "ملخص العميل الموثق" : "Evidence-linked customer summary"}
              </h2>
            </div>
            <form action={generateCopilotInsightAction}>
              <input name="locale" type="hidden" value={locale} />
              <input name="insightType" type="hidden" value="CUSTOMER_SUMMARY" />
              <input name="subjectId" type="hidden" value={customer.id} />
              <SubmitButton tone="secondary">{phaseSixMessages[locale].generate}</SubmitButton>
            </form>
          </div>
          {latestCustomerInsight ? (
            <>
              <ul className="copilot-statements">
                {latestCustomerInsight.statements.map((statement) => (
                  <li key={statement.projectionItemId}>
                    <span className={`statement-kind kind-${statement.kind.toLowerCase()}`}>
                      {phaseSixKind(locale, statement.kind)}
                    </span>
                    <p>{statement.text}</p>
                    <div className="evidence-links">
                      {statement.evidenceIds.map((evidenceId) => {
                        const source = latestCustomerInsight.evidence.find(
                          ({ id }) => id === evidenceId,
                        );
                        return source ? (
                          <a href={source.href} key={`${statement.projectionItemId}-${evidenceId}`}>
                            {source.label}
                          </a>
                        ) : null;
                      })}
                    </div>
                  </li>
                ))}
              </ul>
              <small className="muted">
                {latestCustomerInsight.modelIdentifier} · {phaseSixMessages[locale].dataWatermark}:{" "}
                {new Date(latestCustomerInsight.dataWatermark).toLocaleString(
                  locale === "ar" ? "ar-JO" : "en-JO",
                )}
              </small>
            </>
          ) : (
            <p className="muted">{phaseSixMessages[locale].noInsights}</p>
          )}
        </section>
      ) : null}
      {canWrite ? (
        <form action={updateCustomerAction} className="panel form-grid">
          <input name="locale" type="hidden" value={locale} />
          <input name="customerId" type="hidden" value={customer.id} />
          <input name="expectedVersion" type="hidden" value={customer.version} />
          <label className="field">
            <span className="field-label">{phaseOne.name}</span>
            <input
              className="input"
              defaultValue={customer.displayName}
              name="displayName"
              required
            />
          </label>
          <label className="field">
            <span className="field-label">
              {locale === "ar" ? "الفرع المفضل" : "Preferred branch"}
            </span>
            {activeBranch ? (
              <>
                <input name="preferredBranchId" type="hidden" value={activeBranch.id} />
                <span className="input" aria-readonly="true">
                  {locale === "ar" ? activeBranch.nameAr : activeBranch.nameEn}
                </span>
              </>
            ) : null}
          </label>
          <label className="field">
            <span className="field-label">{locale === "ar" ? "الوسوم" : "Tags"}</span>
            <input className="input" defaultValue={customer.tags.join(", ")} name="tags" />
          </label>
          <label className="field">
            <span className="field-label">{phaseOne.phone}</span>
            <input
              className="input"
              defaultValue={primaryPhone}
              dir="ltr"
              name="phoneOriginal"
              type="tel"
            />
          </label>
          <label className="field">
            <span className="field-label">{phaseOne.defaultLocale}</span>
            <select
              className="select"
              defaultValue={customer.preferredLocale}
              name="preferredLocale"
            >
              <option value="en">English</option>
              <option value="ar">العربية</option>
            </select>
          </label>
          <div className="form-actions">
            <SubmitButton>{phaseOne.save}</SubmitButton>
          </div>
        </form>
      ) : null}
      <section className="panel page-stack" aria-labelledby="customer-notes-title">
        <div className="split-heading">
          <div>
            <p className="eyebrow">{locale === "ar" ? "داخلي" : "Internal"}</p>
            <h2 id="customer-notes-title">
              {locale === "ar" ? "ملاحظات العميل" : "Customer notes"}
            </h2>
          </div>
        </div>
        {canWrite ? (
          <form action={addCustomerNoteAction} className="form-grid">
            <input name="locale" type="hidden" value={locale} />
            <input name="customerId" type="hidden" value={customer.id} />
            <label className="field field-wide">
              <span className="field-label">
                {locale === "ar" ? "ملاحظة داخلية" : "Internal note"}
              </span>
              <textarea className="textarea" maxLength={2000} name="body" required rows={3} />
            </label>
            <div className="form-actions">
              <SubmitButton tone="secondary">
                {locale === "ar" ? "إضافة الملاحظة" : "Add note"}
              </SubmitButton>
            </div>
          </form>
        ) : null}
        {customer.notes.length > 0 ? (
          <ol className="timeline-list">
            {customer.notes.map((note) => (
              <li key={note.id}>
                <strong>{note.author.name}</strong>
                <p>{note.body}</p>
                <small>
                  {new Intl.DateTimeFormat(locale === "ar" ? "ar-JO" : "en-JO", {
                    dateStyle: "medium",
                    timeStyle: "short",
                  }).format(note.createdAt)}
                </small>
              </li>
            ))}
          </ol>
        ) : (
          <p className="muted">
            {locale === "ar" ? "لا توجد ملاحظات داخلية." : "No internal notes yet."}
          </p>
        )}
      </section>
      {canRecordConsent ? (
        <section className="panel" aria-labelledby="consent-title">
          <h2 id="consent-title">{locale === "ar" ? "الموافقات" : "Consent"}</h2>
          <form action={recordConsentAction} className="form-grid">
            <input name="locale" type="hidden" value={locale} />
            <input name="customerId" type="hidden" value={customer.id} />
            <label className="field">
              <span className="field-label">{locale === "ar" ? "الغرض" : "Purpose"}</span>
              <input
                className="input"
                defaultValue="appointment_messages"
                name="purpose"
                required
              />
            </label>
            <label className="field">
              <span className="field-label">{locale === "ar" ? "الإصدار" : "Text version"}</span>
              <input className="input" defaultValue="v1" name="textVersion" required />
            </label>
            <label className="field">
              <span className="field-label">{phaseOne.status}</span>
              <select className="select" name="status">
                <option value={ConsentStatus.GRANTED}>{locale === "ar" ? "منح" : "Grant"}</option>
                <option value={ConsentStatus.REVOKED}>{locale === "ar" ? "سحب" : "Revoke"}</option>
              </select>
            </label>
            <label className="field">
              <span className="field-label">
                {locale === "ar" ? "معرّف الموافقة المسحوبة" : "Consent to revoke"}
              </span>
              <select className="select" name="revokesConsentId">
                <option value="">{locale === "ar" ? "لا يوجد" : "None"}</option>
                {customer.consents
                  .filter((consent) => consent.status === ConsentStatus.GRANTED)
                  .map((consent) => (
                    <option key={consent.id} value={consent.id}>
                      {consent.purpose} · {consent.textVersion}
                    </option>
                  ))}
              </select>
            </label>
            <label className="field">
              <span className="field-label">
                {locale === "ar" ? "دليل / ملاحظة" : "Evidence / note"}
              </span>
              <input className="input" name="evidence" />
            </label>
            <div className="form-actions">
              <SubmitButton tone="secondary">
                {locale === "ar" ? "تسجيل الموافقة" : "Record consent"}
              </SubmitButton>
            </div>
          </form>
        </section>
      ) : null}
      <section className="panel" aria-labelledby="consent-history-title">
        <h2 id="consent-history-title">{locale === "ar" ? "سجل الموافقات" : "Consent history"}</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{locale === "ar" ? "الغرض" : "Purpose"}</th>
                <th>{phaseOne.status}</th>
                <th>{locale === "ar" ? "الوقت" : "Recorded"}</th>
              </tr>
            </thead>
            <tbody>
              {customer.consents.map((consent) => (
                <tr key={consent.id}>
                  <td>
                    {consent.purpose} · {consent.textVersion}
                  </td>
                  <td>{consent.status}</td>
                  <td>{consent.recordedAt.toLocaleString(locale === "ar" ? "ar-JO" : "en-JO")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      {canManagePreferences ? (
        <section className="panel page-stack" aria-labelledby="preferences-title">
          <h2 id="preferences-title">
            {locale === "ar" ? "تفضيلات الاتصال" : "Communication preferences"}
          </h2>
          <p className="muted">
            {locale === "ar"
              ? "يتطلب الإرسال أيضاً موافقة سارية لغرض appointment_messages."
              : "Sending also requires current consent for appointment_messages."}
          </p>
          <div className="row-actions">
            {(["SMS", "WHATSAPP"] as const).map((channel) => {
              const current =
                preferences.find((preference) => preference.channel === channel)?.isEnabled ??
                false;
              return (
                <form
                  action={setCommunicationPreferenceAction}
                  className="inline-form"
                  key={channel}
                >
                  <input name="locale" type="hidden" value={locale} />
                  <input name="customerId" type="hidden" value={customer.id} />
                  <input name="channel" type="hidden" value={channel} />
                  <input name="enabled" type="hidden" value={String(!current)} />
                  <span>
                    {channel}:{" "}
                    {current
                      ? locale === "ar"
                        ? "مفعّل"
                        : "Enabled"
                      : locale === "ar"
                        ? "متوقف"
                        : "Disabled"}
                  </span>
                  <SubmitButton tone="secondary">
                    {current
                      ? locale === "ar"
                        ? "إيقاف"
                        : "Disable"
                      : locale === "ar"
                        ? "تفعيل"
                        : "Enable"}
                  </SubmitButton>
                </form>
              );
            })}
          </div>
        </section>
      ) : null}
      {canReadMessages ? <MessageTimeline locale={locale} messages={messageTimeline} /> : null}
      <section className="panel" aria-labelledby="customer-appointments-title">
        <h2 id="customer-appointments-title">{messages.appointments}</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{messages.startTime}</th>
                <th>{phaseOne.service}</th>
                <th>{messages.provider}</th>
                <th>{messages.status}</th>
              </tr>
            </thead>
            <tbody>
              {customer.appointments.map((appointment) => (
                <tr key={appointment.id}>
                  <td>
                    {appointment.startsAt.toLocaleString(locale === "ar" ? "ar-JO" : "en-JO", {
                      timeZone: appointment.branch.timezone,
                    })}
                  </td>
                  <td>
                    {locale === "ar" ? appointment.service.nameAr : appointment.service.nameEn}
                  </td>
                  <td>
                    {locale === "ar"
                      ? appointment.provider.displayNameAr
                      : appointment.provider.displayNameEn}
                  </td>
                  <td>{appointment.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}
