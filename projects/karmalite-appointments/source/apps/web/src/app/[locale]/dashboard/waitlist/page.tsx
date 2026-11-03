import { randomUUID } from "node:crypto";

import { canAccessResource } from "@jormall/auth/tenant-policy";
import { isSupportedLocale } from "@jormall/contracts/locales";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Feedback } from "../../../../components/feedback";
import { PatientFormCombobox } from "../../../../components/patient-form-combobox";
import { SubmitButton } from "../../../../components/submit-button";
import { WaitlistScheduleFields } from "../../../../components/waitlist-schedule-fields";
import { phaseOneMessages } from "../../../../messages/phase-one";
import { phaseTwoMessages } from "../../../../messages/phase-two";
import { phaseThreeLabel, phaseThreeMessages } from "../../../../messages/phase-three";
import { requireTenantAccess, schedulingRepository } from "../../../../server/identity";
import {
  acceptSlotOfferAction,
  bookWaitlistOpeningAction,
  cancelWaitlistEntryAction,
  createWaitlistEntryAction,
  declineSlotOfferAction,
  expireSlotOfferAction,
} from "../../actions";

export default async function WaitlistPage({
  params,
  searchParams,
}: PageProps<"/[locale]/dashboard/waitlist">) {
  const { locale } = await params;
  if (!isSupportedLocale(locale)) notFound();
  const query = await searchParams;
  const access = await requireTenantAccess(locale);
  const canRead = canAccessResource(access, "waitlist.read", {
    ...(access.staffProfileId ? { staffProfileId: access.staffProfileId } : {}),
  });
  if (!canRead) notFound();
  const canManage = canAccessResource(access, "waitlist.manage");
  const [entries, options, cancelledOpenings] = await Promise.all([
    schedulingRepository.listWaitlist(access),
    canManage ? schedulingRepository.listWaitlistFormOptions(access) : Promise.resolve(null),
    schedulingRepository.listCancelledWaitlistOpenings(access),
  ]);
  const messages = phaseThreeMessages[locale];
  const phaseOne = phaseOneMessages[locale];
  const phaseTwo = phaseTwoMessages[locale];
  const tab = query.tab === "openings" || query.tab === "closed" ? query.tab : "active";
  const tabs =
    locale === "ar"
      ? {
          active: "قائمة الانتظار",
          openings: "المواعيد الملغاة المتاحة",
          closed: "السجل",
        }
      : { active: "Waiting List", openings: "Cancelled Openings", closed: "History" };
  const visibleEntries = entries.filter((entry) =>
    tab === "closed"
      ? ["CONVERTED", "FULFILLED", "CANCELLED", "CLOSED"].includes(entry.status)
      : tab === "active"
        ? ["ACTIVE", "MATCHED", "OFFERED"].includes(entry.status)
        : false,
  );
  return (
    <section className="page-stack" aria-labelledby="waitlist-title">
      <div>
        <p className="eyebrow">{phaseOne.activeOrganization}</p>
        <h1 id="waitlist-title">{messages.waitlist}</h1>
      </div>
      <Feedback
        error={typeof query.error === "string" ? query.error : undefined}
        locale={locale}
        notice={typeof query.notice === "string" ? query.notice : undefined}
      />
      <nav
        className="workspace-tabs"
        aria-label={
          locale === "ar"
            ? "\u0623\u0642\u0633\u0627\u0645 \u0642\u0627\u0626\u0645\u0629 \u0627\u0644\u0627\u0646\u062a\u0638\u0627\u0631"
            : "Waitlist sections"
        }
      >
        {(["active", "openings", "closed"] as const).map((value) => (
          <Link
            aria-current={tab === value ? "page" : undefined}
            href={`/${locale}/schedule/waitlist?tab=${value}`}
            key={value}
          >
            {tabs[value]}
          </Link>
        ))}
      </nav>
      {tab === "active" && options ? (
        <section className="panel" aria-labelledby="waitlist-form-title">
          <h2 id="waitlist-form-title">{messages.addToWaitlist}</h2>
          <form action={createWaitlistEntryAction} className="form-grid">
            <input name="locale" type="hidden" value={locale} />
            <PatientFormCombobox
              label={phaseTwo.customer}
              locale={locale}
              options={options.customers}
            />
            <label className="field">
              <span className="field-label">{phaseOne.service}</span>
              <select className="select" name="serviceId" required>
                {options.services.map((service) => (
                  <option key={service.id} value={service.id}>
                    {locale === "ar" ? service.nameAr : service.nameEn}
                  </option>
                ))}
              </select>
            </label>
            {options.branches[0] ? (
              <label className="field">
                <span className="field-label">{locale === "ar" ? "الفرع" : "Branch"}</span>
                <input name="branchIds" type="hidden" value={options.branches[0].id} />
                <span className="input" aria-readonly="true">
                  {locale === "ar" ? options.branches[0].nameAr : options.branches[0].nameEn}
                </span>
              </label>
            ) : null}
            <label className="field">
              <span className="field-label">
                {locale === "ar" ? "الطبيب المطلوب" : "Requested Doctor"}
              </span>
              <select className="select" name="providerIds" required>
                <option value="">{locale === "ar" ? "اختر الطبيب" : "Select Doctor"}</option>
                {options.providers.map((provider) => (
                  <option key={provider.id} value={provider.id}>
                    {locale === "ar" ? provider.displayNameAr : provider.displayNameEn}
                  </option>
                ))}
              </select>
            </label>
            {options.branches[0] ? (
              <WaitlistScheduleFields
                branchHours={options.branches[0].hoursRules.map((rule) => ({
                  ...(rule.effectiveFrom
                    ? { effectiveFrom: rule.effectiveFrom.toISOString().slice(0, 10) }
                    : {}),
                  ...(rule.effectiveUntil
                    ? { effectiveUntil: rule.effectiveUntil.toISOString().slice(0, 10) }
                    : {}),
                  endMinuteLocal: rule.endMinuteLocal,
                  startMinuteLocal: rule.startMinuteLocal,
                  weekday: rule.weekday,
                }))}
                locale={locale}
                timezone={options.branches[0].timezone}
              />
            ) : null}
            <label className="field">
              <span className="field-label">{messages.priority}</span>
              <select className="select" defaultValue="2" name="priority" required>
                <option value="1">{locale === "ar" ? "منخفضة" : "Low"}</option>
                <option value="2">{locale === "ar" ? "عادية" : "Normal"}</option>
                <option value="3">{locale === "ar" ? "عالية" : "High"}</option>
                <option value="4">{locale === "ar" ? "عاجلة" : "Urgent"}</option>
              </select>
            </label>
            <label className="field">
              <span className="field-label">
                {locale === "ar"
                  ? "سبب الأولوية (مطلوب للعالية والعاجلة)"
                  : "Priority reason (required for High and Urgent)"}
              </span>
              <textarea className="input textarea" maxLength={500} name="priorityReason" />
            </label>
            <label className="field">
              <span className="field-label">
                {locale === "ar"
                  ? "معرّف موعد لإعادة الجدولة (اختياري)"
                  : "Appointment ID to reschedule (optional)"}
              </span>
              <input className="input" dir="ltr" name="appointmentId" />
            </label>
            <label className="field">
              <span className="field-label">
                {locale === "ar" ? "ملاحظات التفضيل" : "Preference notes"}
              </span>
              <textarea className="input textarea" maxLength={500} name="notes" />
            </label>
            <div className="form-actions">
              <SubmitButton>{messages.addToWaitlist}</SubmitButton>
            </div>
          </form>
        </section>
      ) : null}
      <div className="card-grid">
        {visibleEntries.map((entry) => (
          <article className="record-card" key={entry.id}>
            <div>
              <span className="status">{phaseThreeLabel(locale, entry.status)}</span>
              <span className="status">
                {messages.priority}: {waitlistPriorityLabel(locale, entry.priority)}
              </span>
              <h2>{entry.customer.displayName}</h2>
              <strong>
                {entry.providers.length === 0
                  ? locale === "ar"
                    ? "أي طبيب"
                    : "Any Doctor"
                  : entry.providers
                      .map(({ provider }) =>
                        locale === "ar" ? provider.displayNameAr : provider.displayNameEn,
                      )
                      .join(", ")}
              </strong>
              <p>{locale === "ar" ? entry.service.nameAr : entry.service.nameEn}</p>
              <p className="muted">
                {entry.preferredStartDate.toLocaleDateString(locale === "ar" ? "ar-JO" : "en-JO", {
                  timeZone: "UTC",
                })}
                {" — "}
                {entry.preferredEndDate.toLocaleDateString(locale === "ar" ? "ar-JO" : "en-JO", {
                  timeZone: "UTC",
                })}
                {` · ${formatMinuteAsTime(locale, entry.preferredStartMinute)}–${formatMinuteAsTime(locale, entry.preferredEndMinute)}`}
              </p>
            </div>
            {canManage && ["ACTIVE", "OFFERED"].includes(entry.status) ? (
              <div className="inline-form">
                <form action={cancelWaitlistEntryAction}>
                  <input name="locale" type="hidden" value={locale} />
                  <input name="entryId" type="hidden" value={entry.id} />
                  <input name="expectedVersion" type="hidden" value={entry.version} />
                  <SubmitButton tone="danger">{phaseTwo.cancel}</SubmitButton>
                </form>
              </div>
            ) : null}
            {tab === "active" && entry.offers.length > 0 ? (
              <div>
                <h3>{messages.slotOffers}</h3>
                <ul className="history-list">
                  {entry.offers.map((offer) => (
                    <li key={offer.id}>
                      <span className="status">{phaseThreeLabel(locale, offer.status)}</span>
                      <span>
                        {offer.startsAt.toLocaleString(locale === "ar" ? "ar-JO" : "en-JO", {
                          timeZone: offer.timezone,
                        })}
                      </span>
                      <small>
                        {messages.expires}:{" "}
                        {offer.expiresAt.toLocaleString(locale === "ar" ? "ar-JO" : "en-JO", {
                          timeZone: offer.timezone,
                        })}
                      </small>
                      {canManage && offer.status === "PENDING" ? (
                        <div className="inline-form">
                          <OfferAction
                            action={acceptSlotOfferAction}
                            label={messages.acceptOffer}
                            locale={locale}
                            offerId={offer.id}
                          />
                          <OfferAction
                            action={declineSlotOfferAction}
                            label={messages.declineOffer}
                            locale={locale}
                            offerId={offer.id}
                            tone="danger"
                          />
                          {offer.expiresAt <= new Date() ? (
                            <OfferAction
                              action={expireSlotOfferAction}
                              label={messages.expireOffer}
                              locale={locale}
                              offerId={offer.id}
                            />
                          ) : null}
                        </div>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </article>
        ))}
      </div>
      {tab === "openings" ? (
        <section className="panel" aria-labelledby="slots-title">
          <h2 id="slots-title">
            {locale === "ar" ? "المواعيد الملغاة المتاحة" : "Available Cancelled Appointments"}
          </h2>
          <p className="muted">
            {locale === "ar"
              ? "يتم اختيار المريض حسب الأولوية أولاً، ثم حسب أقدم طلب متوافق مع الطبيب والخدمة والوقت."
              : "Patients are selected by priority first, then by the earliest compatible request for the same Doctor, service, and time."}
          </p>
          {cancelledOpenings.length === 0 ? (
            <p>
              {locale === "ar"
                ? "لا توجد مواعيد ملغاة تطابق قائمة الانتظار حالياً."
                : "No cancelled appointments currently match the waiting list."}
            </p>
          ) : (
            <div className="card-grid">
              {cancelledOpenings.map(({ entry, opening }) => (
                <article className="record-card" key={opening.id}>
                  <strong>
                    {opening.startsAt.toLocaleString(locale === "ar" ? "ar-JO" : "en-JO", {
                      timeZone: opening.timezone,
                    })}
                  </strong>
                  <span>{locale === "ar" ? opening.service.nameAr : opening.service.nameEn}</span>
                  <span>
                    {locale === "ar"
                      ? opening.provider.displayNameAr
                      : opening.provider.displayNameEn}
                  </span>
                  <span>{locale === "ar" ? opening.branch.nameAr : opening.branch.nameEn}</span>
                  <div>
                    <span className="status">
                      {messages.priority}: {waitlistPriorityLabel(locale, entry.priority)}
                    </span>
                    <h3>{entry.customer.displayName}</h3>
                    <small>
                      {locale === "ar" ? "أعلى طلب مؤهل" : "Next eligible patient"} ·{" "}
                      {entry.createdAt.toLocaleDateString(locale === "ar" ? "ar-JO" : "en-JO")}
                    </small>
                  </div>
                  {canManage ? (
                    <form action={bookWaitlistOpeningAction}>
                      <input name="locale" type="hidden" value={locale} />
                      <input name="waitlistEntryId" type="hidden" value={entry.id} />
                      <input name="cancelledAppointmentId" type="hidden" value={opening.id} />
                      <input name="requestKey" type="hidden" value={randomUUID()} />
                      <SubmitButton>
                        {locale === "ar" ? "إسناد الموعد للمريض" : "Assign Appointment to Patient"}
                      </SubmitButton>
                    </form>
                  ) : null}
                </article>
              ))}
            </div>
          )}
        </section>
      ) : null}
    </section>
  );
}

function OfferAction({
  action,
  label,
  locale,
  offerId,
  tone = "secondary",
}: Readonly<{
  action: (formData: FormData) => Promise<never>;
  label: string;
  locale: "ar" | "en";
  offerId: string;
  tone?: "danger" | "secondary";
}>) {
  return (
    <form action={action}>
      <input name="locale" type="hidden" value={locale} />
      <input name="offerId" type="hidden" value={offerId} />
      <input name="requestKey" type="hidden" value={randomUUID()} />
      <SubmitButton tone={tone}>{label}</SubmitButton>
    </form>
  );
}

function formatMinuteAsTime(locale: "ar" | "en", minute: number): string {
  const date = new Date(Date.UTC(2000, 0, 1, Math.floor(minute / 60) % 24, minute % 60));
  return new Intl.DateTimeFormat(locale === "ar" ? "ar-JO" : "en-JO", {
    hour: "numeric",
    hour12: true,
    minute: "2-digit",
    timeZone: "UTC",
  }).format(date);
}

function waitlistPriorityLabel(locale: "ar" | "en", priority: number): string {
  if (priority === 4) return locale === "ar" ? "عاجلة" : "Urgent";
  if (priority === 3) return locale === "ar" ? "عالية" : "High";
  if (priority === 1) return locale === "ar" ? "منخفضة" : "Low";
  return locale === "ar" ? "عادية" : "Normal";
}
