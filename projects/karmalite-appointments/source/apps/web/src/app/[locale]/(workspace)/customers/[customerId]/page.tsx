import { canAccessResource } from "@jormall/auth/tenant-policy";
import { isSupportedLocale } from "@jormall/contracts/locales";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Feedback } from "../../../../../components/feedback";
import { MessageTimeline } from "../../../../../components/message-timeline";
import { SubmitButton } from "../../../../../components/submit-button";
import {
  communicationRepository,
  crmAppointmentRepository,
  requirePagePermission,
} from "../../../../../server/identity";
import { updatePatientSafetyIntakeAction } from "../../../actions";

const tabs = ["overview", "appointments", "notes", "health", "communications", "audit"] as const;
type PatientTab = (typeof tabs)[number];
type HealthState = "DECLINED" | "NONE_REPORTED" | "NOT_PROVIDED" | "PROVIDED";

export default async function PatientProfilePage({
  params,
  searchParams,
}: PageProps<"/[locale]/customers/[customerId]">) {
  const { customerId, locale } = await params;
  if (!isSupportedLocale(locale)) notFound();
  const query = await searchParams;
  const access = await requirePagePermission(locale, "patients.profile.read");
  const customer = await crmAppointmentRepository.getCustomer(access, customerId);
  const requestedTab = typeof query.tab === "string" ? query.tab : "overview";
  const tab: PatientTab = tabs.includes(requestedTab as PatientTab)
    ? (requestedTab as PatientTab)
    : "overview";
  const canReadHealth = canAccessResource(access, "patients.health.read");
  const canWriteHealth = canAccessResource(access, "patients.health.write");
  const canReadDoctorNotes = canAccessResource(access, "patients.doctor_notes.read");
  const canReadAudit = canAccessResource(access, "audit.read");
  const canReadMessages = canAccessResource(access, "messages.read");
  const health = canReadHealth
    ? await crmAppointmentRepository.getPatientSafetyIntake(access, customer.id)
    : null;
  const doctorNotes =
    tab === "notes" && canReadDoctorNotes
      ? await crmAppointmentRepository.listPatientDoctorNotes(access, customer.id)
      : [];
  const audit =
    tab === "audit" && canReadAudit
      ? await crmAppointmentRepository.listPatientAudit(access, customer.id)
      : [];
  const communications =
    tab === "communications" && canReadMessages
      ? await communicationRepository.listCustomerMessages(access, customer.id)
      : [];
  const formatter = new Intl.DateTimeFormat(locale === "ar" ? "ar-JO" : "en-JO", {
    dateStyle: "medium",
    timeStyle: "short",
  });
  const labels = copy[locale];
  const now = new Date().getTime();
  const nextAppointment = customer.appointments
    .filter(({ startsAt }) => startsAt.getTime() >= now)
    .toSorted((left, right) => left.startsAt.getTime() - right.startsAt.getTime())[0];
  const lastAppointment = customer.appointments
    .filter(({ startsAt }) => startsAt.getTime() < now)
    .toSorted((left, right) => right.startsAt.getTime() - left.startsAt.getTime())[0];
  const upcomingAppointments =
    tab === "appointments"
      ? customer.appointments
          .filter(({ startsAt }) => startsAt.getTime() >= now)
          .toSorted((left, right) => left.startsAt.getTime() - right.startsAt.getTime())
      : [];
  const previousAppointments =
    tab === "appointments"
      ? customer.appointments
          .filter(({ startsAt }) => startsAt.getTime() < now)
          .toSorted((left, right) => left.startsAt.getTime() - right.startsAt.getTime())
          .toReversed()
      : [];
  const appointmentTable = (appointments: typeof customer.appointments) => (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>{labels.when}</th>
            <th>{labels.service}</th>
            <th>{labels.doctor}</th>
            <th>{labels.room}</th>
            <th>{labels.status}</th>
          </tr>
        </thead>
        <tbody>
          {appointments.map((appointment) => (
            <tr key={appointment.id}>
              <td>{formatter.format(appointment.startsAt)}</td>
              <td>{locale === "ar" ? appointment.service.nameAr : appointment.service.nameEn}</td>
              <td>
                {locale === "ar"
                  ? appointment.provider.displayNameAr
                  : appointment.provider.displayNameEn}
              </td>
              <td>
                {appointment.room
                  ? locale === "ar"
                    ? appointment.room.nameAr
                    : appointment.room.nameEn
                  : "—"}
              </td>
              <td>
                <Link href={`/${locale}/schedule/appointments?appointment=${appointment.id}`}>
                  {appointment.status}
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  return (
    <section className="page-stack patient-profile" aria-labelledby="patient-title">
      <header className="page-heading patient-profile-heading">
        <div>
          <p className="eyebrow">{labels.patientProfile}</p>
          <div className="patient-profile-identity">
            <span className="avatar-initials avatar-initials-large" aria-hidden="true">
              {customer.displayName
                .trim()
                .split(/\s+/u)
                .slice(0, 2)
                .map((part) => part[0]?.toUpperCase())
                .join("")}
            </span>
            <span>
              <h1 id="patient-title">{customer.displayName}</h1>
              <p className="muted">{customer.referenceCode}</p>
            </span>
          </div>
        </div>
        <Link
          className="button button-secondary"
          href={`/${locale}/schedule/calendar?patient=${customer.id}#create-appointment-title`}
        >
          {labels.bookAppointment}
        </Link>
      </header>
      <Feedback
        error={typeof query.error === "string" ? query.error : undefined}
        locale={locale}
        notice={typeof query.notice === "string" ? query.notice : undefined}
      />
      <nav className="workspace-tabs" aria-label={labels.patientSections}>
        {tabs.map((item) => {
          const restricted =
            (item === "health" && !canReadHealth) ||
            (item === "notes" && !canReadDoctorNotes) ||
            (item === "communications" && !canReadMessages) ||
            (item === "audit" && !canReadAudit);
          return restricted ? null : (
            <Link
              aria-current={tab === item ? "page" : undefined}
              className={tab === item ? "active" : undefined}
              href={`/${locale}/customers/${customer.id}?tab=${item}`}
              key={item}
            >
              {labels.tabs[item]}
            </Link>
          );
        })}
      </nav>

      {tab === "overview" ? (
        <div className="detail-grid">
          <section className="panel page-stack">
            <h2>{labels.contact}</h2>
            <dl className="detail-list">
              <div>
                <dt>{labels.phone}</dt>
                <dd dir="ltr">{contact(customer.contacts, "PHONE")}</dd>
              </div>
              <div>
                <dt>{labels.email}</dt>
                <dd>{contact(customer.contacts, "EMAIL")}</dd>
              </div>
              <div>
                <dt>{labels.preferredLanguage}</dt>
                <dd>{customer.preferredLocale === "ar" ? "العربية" : "English"}</dd>
              </div>
              <div>
                <dt>{labels.preferredBranch}</dt>
                <dd>
                  {customer.preferredBranch
                    ? locale === "ar"
                      ? customer.preferredBranch.nameAr
                      : customer.preferredBranch.nameEn
                    : "—"}
                </dd>
              </div>
              <div>
                <dt>{labels.nextAppointment}</dt>
                <dd>{nextAppointment ? formatter.format(nextAppointment.startsAt) : "—"}</dd>
              </div>
              <div>
                <dt>{labels.lastAppointment}</dt>
                <dd>{lastAppointment ? formatter.format(lastAppointment.startsAt) : "—"}</dd>
              </div>
            </dl>
          </section>
          {canReadHealth ? (
            <section className="panel page-stack" aria-labelledby="safety-summary-title">
              <div>
                <p className="eyebrow">{labels.restricted}</p>
                <h2 id="safety-summary-title">{labels.safetySummary}</h2>
              </div>
              <p>
                {health?.allergyState === "PROVIDED"
                  ? labels.allergyAvailable
                  : labels.healthStates[health?.allergyState ?? "NOT_PROVIDED"]}
              </p>
              <p>
                {health?.medicalConditionState === "PROVIDED"
                  ? labels.conditionAvailable
                  : labels.healthStates[health?.medicalConditionState ?? "NOT_PROVIDED"]}
              </p>
              {!health ||
              (health.allergyState === "NOT_PROVIDED" &&
                health.medicalConditionState === "NOT_PROVIDED") ? (
                <p>{labels.healthNotProvided}</p>
              ) : null}
              <Link href={`/${locale}/customers/${customer.id}?tab=health`}>
                {labels.openSafetyIntake}
              </Link>
            </section>
          ) : null}
        </div>
      ) : null}

      {tab === "appointments" ? (
        <section className="panel page-stack">
          <h2>{labels.appointmentHistory}</h2>
          <h3>{labels.upcoming}</h3>
          {upcomingAppointments.length ? (
            appointmentTable(upcomingAppointments)
          ) : (
            <p className="muted">{labels.noUpcomingAppointments}</p>
          )}
          <h3>{labels.previous}</h3>
          {previousAppointments.length ? (
            appointmentTable(previousAppointments)
          ) : (
            <p className="muted">{labels.noPreviousAppointments}</p>
          )}
        </section>
      ) : null}

      {tab === "notes" && canReadDoctorNotes ? (
        <section className="panel page-stack">
          <h2>{labels.doctorNotes}</h2>
          {doctorNotes.length ? (
            <ol className="timeline-list">
              {doctorNotes.map((note) => (
                <li key={note.id}>
                  <strong>{note.author.name}</strong>
                  <p>{note.body}</p>
                  <small>
                    {note.appointment.referenceCode} · {formatter.format(note.createdAt)}
                  </small>
                </li>
              ))}
            </ol>
          ) : (
            <p className="muted">{labels.noDoctorNotes}</p>
          )}
        </section>
      ) : null}

      {tab === "health" && canReadHealth ? (
        <section className="panel page-stack" aria-labelledby="health-title">
          <div>
            <p className="eyebrow">{labels.restricted}</p>
            <h2 id="health-title">{labels.safetyIntake}</h2>
            <p className="muted">{labels.safetyPurpose}</p>
          </div>
          {canWriteHealth ? (
            <form action={updatePatientSafetyIntakeAction} className="form-grid">
              <input name="locale" type="hidden" value={locale} />
              <input name="customerId" type="hidden" value={customer.id} />
              <HealthField
                details={health?.allergyDetails ?? ""}
                label={labels.allergies}
                locale={locale}
                name="allergy"
                state={health?.allergyState ?? "NOT_PROVIDED"}
              />
              <HealthField
                details={health?.medicalConditionDetails ?? ""}
                label={labels.knownConditions}
                locale={locale}
                name="medicalCondition"
                state={health?.medicalConditionState ?? "NOT_PROVIDED"}
              />
              <label className="field field-wide checkbox-row">
                <input name="consentConfirmed" required type="checkbox" />
                <span>{labels.consentConfirmation}</span>
              </label>
              <div className="form-actions">
                <SubmitButton>{labels.saveSafetyIntake}</SubmitButton>
              </div>
            </form>
          ) : (
            <dl className="detail-list">
              <div>
                <dt>{labels.allergies}</dt>
                <dd>
                  {health
                    ? labels.healthStates[health.allergyState]
                    : labels.healthStates.NOT_PROVIDED}
                  {health?.allergyDetails ? ` · ${health.allergyDetails}` : ""}
                </dd>
              </div>
              <div>
                <dt>{labels.knownConditions}</dt>
                <dd>
                  {health
                    ? labels.healthStates[health.medicalConditionState]
                    : labels.healthStates.NOT_PROVIDED}
                  {health?.medicalConditionDetails ? ` · ${health.medicalConditionDetails}` : ""}
                </dd>
              </div>
            </dl>
          )}
          {health ? (
            <div className="page-stack compact-stack">
              <small className="muted">
                {labels.lastUpdated}: {formatter.format(health.updatedAt)} · {health.updatedBy.name}
              </small>
              {health.consent ? (
                <small className="muted">
                  {labels.provenance}: {labels.consentSources[health.consent.source]} ·{" "}
                  {labels.consentChannels[health.consent.channel]} ·{" "}
                  {formatter.format(health.consent.recordedAt)}
                </small>
              ) : null}
            </div>
          ) : null}
        </section>
      ) : null}

      {tab === "communications" && canReadMessages ? (
        <section className="panel page-stack">
          <h2>{labels.communications}</h2>
          <MessageTimeline locale={locale} messages={communications} />
        </section>
      ) : null}

      {tab === "audit" && canReadAudit ? (
        <section className="panel page-stack">
          <h2>{labels.audit}</h2>
          {audit.length ? (
            <ol className="timeline-list">
              {audit.map((event) => (
                <li key={event.id}>
                  <strong>{event.action}</strong>
                  <p>{event.actor?.name ?? "System"}</p>
                  <small>{formatter.format(event.createdAt)}</small>
                </li>
              ))}
            </ol>
          ) : (
            <p className="muted">{labels.noAudit}</p>
          )}
        </section>
      ) : null}
    </section>
  );
}

function HealthField({
  details,
  label,
  locale,
  name,
  state,
}: Readonly<{
  details: string;
  label: string;
  locale: "ar" | "en";
  name: "allergy" | "medicalCondition";
  state: HealthState;
}>) {
  const labels = copy[locale];
  return (
    <fieldset className="field field-wide">
      <legend className="field-label">{label}</legend>
      <select className="select" defaultValue={state} name={`${name}State`}>
        {Object.entries(labels.healthStates).map(([value, text]) => (
          <option key={value} value={value}>
            {text}
          </option>
        ))}
      </select>
      <label className="field">
        <span className="field-label">{labels.detailsWhenProvided}</span>
        <textarea
          className="textarea"
          defaultValue={details}
          maxLength={4000}
          name={`${name}Details`}
          rows={3}
        />
      </label>
    </fieldset>
  );
}

function contact(
  contacts: readonly Readonly<{ kind: string; originalValue: string }>[],
  kind: "EMAIL" | "PHONE",
): string {
  return contacts.find((entry) => entry.kind === kind)?.originalValue ?? "—";
}

const copy = {
  en: {
    allergies: "Allergies",
    allergyAvailable: "Allergy information available",
    appointmentHistory: "Appointments",
    audit: "Audit history",
    bookAppointment: "Book appointment",
    communications: "Communications",
    conditionAvailable: "Medical-condition information available",
    contact: "Contact details",
    consentConfirmation:
      "I confirm the patient provided this information or authorized staff to record it.",
    consentChannels: {
      API: "Authorized API record",
      IMPORT: "Authorized import",
      PUBLIC_BOOKING: "Public booking consent",
      STAFF: "Recorded by staff",
      WEBSITE: "Website consent",
    },
    consentSources: {
      API: "Authorized API record",
      IMPORT: "Authorized import",
      PUBLIC_BOOKING: "Provided during public booking",
      STAFF: "Patient authorized staff",
      VOICE_AI: "Authorized voice assistant",
      WEBSITE_AI: "Authorized website assistant",
      WHATSAPP_AI: "Authorized WhatsApp assistant",
    },
    detailsWhenProvided: "Details (required only when Provided is selected)",
    doctor: "Doctor",
    doctorNotes: "Doctor notes",
    email: "Email",
    healthNotProvided: "Health information not provided",
    healthStates: {
      DECLINED: "Patient declined to provide information",
      NONE_REPORTED: "Patient reports none",
      NOT_PROVIDED: "Information not provided",
      PROVIDED: "Information provided",
    },
    knownConditions: "Known diseases or medical conditions",
    lastAppointment: "Last appointment",
    lastUpdated: "Last updated",
    nextAppointment: "Next appointment",
    noAppointments: "No appointments found.",
    noPreviousAppointments: "No previous appointments.",
    noUpcomingAppointments: "No upcoming appointments.",
    noAudit: "No matching audit activity.",
    noDoctorNotes: "No authorized doctor notes.",
    openSafetyIntake: "Open protected safety intake",
    patientProfile: "Patient profile",
    patientSections: "Patient profile sections",
    phone: "Phone",
    preferredBranch: "Preferred branch",
    preferredLanguage: "Preferred language",
    previous: "Previous",
    provenance: "Consent and provenance",
    restricted: "Restricted patient-safety data",
    room: "Room",
    safetyIntake: "Patient safety intake",
    safetyPurpose:
      "Used only for safe intake and appointment handling. This is not a medical record.",
    safetySummary: "Safety information status",
    saveSafetyIntake: "Save protected intake",
    service: "Service",
    status: "Status",
    tabs: {
      appointments: "Appointments",
      audit: "Audit",
      communications: "Communications",
      health: "Health & allergies",
      notes: "Doctor notes",
      overview: "Overview",
    },
    upcoming: "Upcoming",
    when: "Date and time",
  },
  ar: {
    allergies: "الحساسيات",
    allergyAvailable: "معلومات الحساسية متوفرة",
    appointmentHistory: "المواعيد",
    audit: "سجل التدقيق",
    bookAppointment: "حجز موعد",
    communications: "الاتصالات",
    conditionAvailable: "معلومات الحالة الصحية متوفرة",
    contact: "بيانات الاتصال",
    consentConfirmation: "أؤكد أن المريض قدّم هذه المعلومات أو فوّض الموظف بتسجيلها.",
    consentChannels: {
      API: "سجل واجهة برمجية مصرح به",
      IMPORT: "استيراد مصرح به",
      PUBLIC_BOOKING: "موافقة الحجز العام",
      STAFF: "سجلها الموظف",
      WEBSITE: "موافقة عبر الموقع",
    },
    consentSources: {
      API: "سجل واجهة برمجية مصرح به",
      IMPORT: "استيراد مصرح به",
      PUBLIC_BOOKING: "قدمها المريض أثناء الحجز العام",
      STAFF: "فوّض المريض الموظف",
      VOICE_AI: "مساعد صوتي مصرح به",
      WEBSITE_AI: "مساعد الموقع المصرح به",
      WHATSAPP_AI: "مساعد واتساب المصرح به",
    },
    detailsWhenProvided: "التفاصيل (مطلوبة فقط عند اختيار تم تقديم المعلومات)",
    doctor: "الطبيب",
    doctorNotes: "ملاحظات الطبيب",
    email: "البريد الإلكتروني",
    healthNotProvided: "لم يتم تقديم معلومات صحية",
    healthStates: {
      DECLINED: "رفض المريض تقديم المعلومات",
      NONE_REPORTED: "أفاد المريض بعدم وجودها",
      NOT_PROVIDED: "لم يتم تقديم المعلومات",
      PROVIDED: "تم تقديم المعلومات",
    },
    knownConditions: "الأمراض أو الحالات الصحية المعروفة",
    lastAppointment: "آخر موعد",
    lastUpdated: "آخر تحديث",
    nextAppointment: "الموعد القادم",
    noAppointments: "لا توجد مواعيد.",
    noPreviousAppointments: "لا توجد مواعيد سابقة.",
    noUpcomingAppointments: "لا توجد مواعيد قادمة.",
    noAudit: "لا يوجد نشاط تدقيق مطابق.",
    noDoctorNotes: "لا توجد ملاحظات طبيب مصرح بها.",
    openSafetyIntake: "فتح نموذج السلامة المحمي",
    patientProfile: "ملف المريض",
    patientSections: "أقسام ملف المريض",
    phone: "الهاتف",
    preferredBranch: "الفرع المفضل",
    preferredLanguage: "اللغة المفضلة",
    previous: "السابقة",
    provenance: "الموافقة ومصدر المعلومات",
    restricted: "بيانات سلامة المريض المقيّدة",
    room: "الغرفة",
    safetyIntake: "نموذج سلامة المريض",
    safetyPurpose: "تُستخدم فقط لسلامة الاستقبال والتعامل مع الموعد. هذا ليس سجلاً طبياً.",
    safetySummary: "حالة معلومات السلامة",
    saveSafetyIntake: "حفظ بيانات السلامة المحمية",
    service: "الخدمة",
    status: "الحالة",
    tabs: {
      appointments: "المواعيد",
      audit: "التدقيق",
      communications: "الاتصالات",
      health: "الصحة والحساسيات",
      notes: "ملاحظات الطبيب",
      overview: "نظرة عامة",
    },
    upcoming: "قادم",
    when: "التاريخ والوقت",
  },
} as const;
