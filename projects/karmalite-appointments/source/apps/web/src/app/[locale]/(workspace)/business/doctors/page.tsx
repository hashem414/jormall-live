import { canAccessResource } from "@jormall/auth/tenant-policy";
import { isSupportedLocale } from "@jormall/contracts/locales";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Feedback } from "../../../../../components/feedback";
import { SubmitButton } from "../../../../../components/submit-button";
import { identityRepository, requirePagePermission } from "../../../../../server/identity";
import {
  addDoctorTimeOffAction,
  configureDoctorAction,
  replaceDoctorIndependentScheduleAction,
} from "../../../actions";

const weekdays = [
  "SUNDAY",
  "MONDAY",
  "TUESDAY",
  "WEDNESDAY",
  "THURSDAY",
  "FRIDAY",
  "SATURDAY",
] as const;

export default async function DoctorsPage({
  params,
  searchParams,
}: PageProps<"/[locale]/business/doctors">) {
  const { locale } = await params;
  if (!isSupportedLocale(locale)) notFound();
  const query = await searchParams;
  const access = await requirePagePermission(locale, "doctors.directory.read");
  const canWriteProfile = canAccessResource(access, "doctors.profile.write");
  const canWriteSchedule = canAccessResource(access, "doctors.schedule.write");
  const canWriteTimeOff = canAccessResource(access, "doctors.time_off.write");
  const canReadStaff = canAccessResource(access, "staff.read");
  const canReadBranches = canAccessResource(access, "branches.read");
  const canReadServices = canAccessResource(access, "services.read");
  const { branches, doctors, services, staff } = await identityRepository.loadDoctorsWorkspace(
    access,
    {
      includeBranches: canReadBranches,
      includeServices: canReadServices,
      includeStaff: canWriteProfile && canReadStaff,
    },
  );
  const text = labels[locale];
  const formatter = new Intl.DateTimeFormat(locale === "ar" ? "ar-JO" : "en-JO", {
    dateStyle: "medium",
    timeStyle: "short",
  });

  return (
    <section
      className="page-stack product-directory doctors-directory"
      aria-labelledby="doctors-title"
    >
      <header className="page-heading">
        <div>
          <p className="eyebrow">{text.business}</p>
          <h1 id="doctors-title">{text.doctors}</h1>
          <p className="page-description">{text.description}</p>
        </div>
      </header>
      <Feedback
        error={typeof query.error === "string" ? query.error : undefined}
        locale={locale}
        notice={typeof query.notice === "string" ? query.notice : undefined}
      />

      {doctors.length ? (
        <div className="card-grid">
          {doctors.map((doctor) => (
            <article className="panel page-stack doctor-card" key={doctor.id}>
              <header className="split-heading">
                <span className="avatar-initials avatar-initials-large" aria-hidden="true">
                  {(locale === "ar" ? doctor.displayNameAr : doctor.displayNameEn)
                    .trim()
                    .split(/\s+/u)
                    .slice(0, 2)
                    .map((part) => part[0]?.toUpperCase())
                    .join("")}
                </span>
                <div className="doctor-card-identity">
                  <p className="eyebrow">{doctor.isActive ? text.active : text.inactive}</p>
                  <h2>{locale === "ar" ? doctor.displayNameAr : doctor.displayNameEn}</h2>
                  <p className="muted">
                    {doctor.profession ?? text.doctor} · {doctor.specialty ?? text.noSpecialty}
                  </p>
                </div>
              </header>
              <dl className="detail-list">
                <div>
                  <dt>{text.branches}</dt>
                  <dd>
                    {doctor.branchAssignments
                      .map(({ branch }) => (locale === "ar" ? branch.nameAr : branch.nameEn))
                      .join(", ") || "—"}
                  </dd>
                </div>
                <div>
                  <dt>{text.services}</dt>
                  <dd>
                    {doctor.services
                      .map(({ service }) => (locale === "ar" ? service.nameAr : service.nameEn))
                      .join(", ") || "—"}
                  </dd>
                </div>
                <div>
                  <dt>{text.contact}</dt>
                  <dd>{doctor.phone ?? doctor.email ?? "—"}</dd>
                </div>
                <div>
                  <dt>{text.role}</dt>
                  <dd>
                    {doctor.membership.roles
                      .map(({ role }) => (locale === "ar" ? role.nameAr : role.nameEn))
                      .join(", ") || "—"}
                  </dd>
                </div>
              </dl>
              <Link href={`/${locale}/schedule/appointments?providerId=${doctor.id}`}>
                {text.viewAppointments}
              </Link>
              {canWriteProfile && branches.length ? (
                <details>
                  <summary>{text.editDoctor}</summary>
                  <form action={configureDoctorAction} className="form-grid">
                    <input name="locale" type="hidden" value={locale} />
                    <input name="staffProfileId" type="hidden" value={doctor.id} />
                    <label className="field">
                      <span className="field-label">{text.nameEn}</span>
                      <input
                        className="input"
                        defaultValue={doctor.displayNameEn}
                        name="displayNameEn"
                        required
                      />
                    </label>
                    <label className="field">
                      <span className="field-label">{text.nameAr}</span>
                      <input
                        className="input"
                        defaultValue={doctor.displayNameAr}
                        dir="rtl"
                        name="displayNameAr"
                        required
                      />
                    </label>
                    <label className="field">
                      <span className="field-label">{text.profession}</span>
                      <input
                        className="input"
                        defaultValue={doctor.profession ?? ""}
                        name="profession"
                      />
                    </label>
                    <label className="field">
                      <span className="field-label">{text.specialty}</span>
                      <input
                        className="input"
                        defaultValue={doctor.specialty ?? ""}
                        name="specialty"
                      />
                    </label>
                    <label className="field">
                      <span className="field-label">{text.phone}</span>
                      <input
                        className="input"
                        defaultValue={doctor.phone ?? ""}
                        dir="ltr"
                        name="phone"
                        type="tel"
                      />
                    </label>
                    <label className="field">
                      <span className="field-label">{text.email}</span>
                      <input
                        className="input"
                        defaultValue={doctor.email ?? ""}
                        name="email"
                        type="email"
                      />
                    </label>
                    <fieldset className="field field-wide">
                      <legend className="field-label">{text.branches}</legend>
                      <div className="checkbox-grid">
                        {branches.map((branch) => (
                          <label className="checkbox-row" key={branch.id}>
                            <input
                              defaultChecked={doctor.branchAssignments.some(
                                ({ branchId }) => branchId === branch.id,
                              )}
                              name="branchIds"
                              type="checkbox"
                              value={branch.id}
                            />
                            <span>{locale === "ar" ? branch.nameAr : branch.nameEn}</span>
                          </label>
                        ))}
                      </div>
                    </fieldset>
                    <fieldset className="field field-wide">
                      <legend className="field-label">{text.services}</legend>
                      <div className="checkbox-grid">
                        {services.map((service) => (
                          <label className="checkbox-row" key={service.id}>
                            <input
                              defaultChecked={doctor.services.some(
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
                    <label className="field checkbox-row">
                      <input defaultChecked={doctor.isActive} name="isActive" type="checkbox" />
                      <span>{text.activeAndBookable}</span>
                    </label>
                    <div className="form-actions">
                      <SubmitButton>{text.saveDoctor}</SubmitButton>
                    </div>
                  </form>
                </details>
              ) : null}
              <details>
                <summary>{text.scheduleAndBreaks}</summary>
                {doctor.availabilityRules.length ? (
                  <ul>
                    {doctor.availabilityRules.map((rule) => (
                      <li key={rule.id}>
                        {text.weekdays[rule.weekday]}: {minuteTime(rule.startMinuteLocal)}–
                        {minuteTime(rule.endMinuteLocal)}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">{text.noSchedule}</p>
                )}
                {doctor.breaks.length ? (
                  <ul>
                    {doctor.breaks.map((entry) => (
                      <li key={entry.id}>
                        {text.weekdays[entry.weekday]} · {entry.label ?? text.break}:{" "}
                        {minuteTime(entry.startMinuteLocal)}–{minuteTime(entry.endMinuteLocal)}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </details>
              <details>
                <summary>{text.upcomingTimeOff}</summary>
                {doctor.timeOffEntries.length ? (
                  <ul>
                    {doctor.timeOffEntries.map((entry) => (
                      <li key={entry.id}>
                        {formatter.format(entry.startsAt)} – {formatter.format(entry.endsAt)} ·{" "}
                        {entry.reason} · {text.createdBy}: {entry.createdBy?.name ?? "System"} ·{" "}
                        {formatter.format(entry.createdAt)}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">{text.noTimeOff}</p>
                )}
              </details>

              {canWriteSchedule && branches.length ? (
                <details>
                  <summary>{text.editSchedule}</summary>
                  <form action={replaceDoctorIndependentScheduleAction} className="form-grid">
                    <input name="locale" type="hidden" value={locale} />
                    <input name="staffProfileId" type="hidden" value={doctor.id} />
                    <Select
                      label={text.branch}
                      name="branchId"
                      options={branches.map((branch) => ({
                        label: locale === "ar" ? branch.nameAr : branch.nameEn,
                        value: branch.id,
                      }))}
                    />
                    <div className="field field-wide page-stack">
                      <strong>{text.workingDays}</strong>
                      {weekdays.map((day) => (
                        <ScheduleDay
                          breaks={doctor.breaks.filter((entry) => entry.weekday === day)}
                          day={day}
                          key={day}
                          label={text.weekdays[day]}
                          periods={doctor.availabilityRules.filter(
                            (entry) => entry.weekday === day,
                          )}
                          text={text}
                        />
                      ))}
                    </div>
                    <label className="field field-wide checkbox-row">
                      <input name="confirmAffected" type="checkbox" />
                      <span>{text.confirmScheduleImpact}</span>
                    </label>
                    <div className="form-actions">
                      <SubmitButton>{text.saveSchedule}</SubmitButton>
                    </div>
                  </form>
                </details>
              ) : null}

              {canWriteTimeOff && branches.length ? (
                <details>
                  <summary>{text.addTimeOff}</summary>
                  <form action={addDoctorTimeOffAction} className="form-grid">
                    <input name="locale" type="hidden" value={locale} />
                    <input name="staffProfileId" type="hidden" value={doctor.id} />
                    <Select
                      label={text.branch}
                      name="branchId"
                      options={branches.map((branch) => ({
                        label: locale === "ar" ? branch.nameAr : branch.nameEn,
                        value: branch.id,
                      }))}
                    />
                    <label className="field">
                      <span className="field-label">{text.from}</span>
                      <input
                        className="input"
                        name="startsAtLocal"
                        required
                        type="datetime-local"
                      />
                    </label>
                    <label className="field">
                      <span className="field-label">{text.to}</span>
                      <input className="input" name="endsAtLocal" required type="datetime-local" />
                    </label>
                    <label className="field field-wide">
                      <span className="field-label">{text.reason}</span>
                      <input className="input" maxLength={160} name="reason" required />
                    </label>
                    <label className="field field-wide checkbox-row">
                      <input name="confirmAffected" type="checkbox" />
                      <span>{text.confirmTimeOffImpact}</span>
                    </label>
                    <div className="form-actions">
                      <SubmitButton>{text.saveTimeOff}</SubmitButton>
                    </div>
                  </form>
                </details>
              ) : null}
            </article>
          ))}
        </div>
      ) : (
        <section className="panel empty-state">
          <h2>{text.noDoctors}</h2>
          <p>{text.noDoctorsHelp}</p>
        </section>
      )}

      {canWriteProfile && staff.length && branches.length ? (
        <details className="panel">
          <summary>{text.addDoctor}</summary>
          <form action={configureDoctorAction} className="form-grid">
            <input name="locale" type="hidden" value={locale} />
            <Select
              label={text.teamMember}
              name="staffProfileId"
              options={staff.flatMap((membership) =>
                membership.staffProfile
                  ? [{ label: membership.user.name, value: membership.staffProfile.id }]
                  : [],
              )}
            />
            <label className="field">
              <span className="field-label">{text.nameEn}</span>
              <input className="input" name="displayNameEn" required />
            </label>
            <label className="field">
              <span className="field-label">{text.nameAr}</span>
              <input className="input" dir="rtl" name="displayNameAr" required />
            </label>
            <label className="field">
              <span className="field-label">{text.profession}</span>
              <input className="input" name="profession" />
            </label>
            <label className="field">
              <span className="field-label">{text.specialty}</span>
              <input className="input" name="specialty" />
            </label>
            <label className="field">
              <span className="field-label">{text.phone}</span>
              <input className="input" dir="ltr" name="phone" type="tel" />
            </label>
            <label className="field">
              <span className="field-label">{text.email}</span>
              <input className="input" name="email" type="email" />
            </label>
            <fieldset className="field field-wide">
              <legend className="field-label">{text.branches}</legend>
              <div className="checkbox-grid">
                {branches.map((branch) => (
                  <label className="checkbox-row" key={branch.id}>
                    <input name="branchIds" type="checkbox" value={branch.id} />
                    <span>{locale === "ar" ? branch.nameAr : branch.nameEn}</span>
                  </label>
                ))}
              </div>
            </fieldset>
            <fieldset className="field field-wide">
              <legend className="field-label">{text.services}</legend>
              <div className="checkbox-grid">
                {services.map((service) => (
                  <label className="checkbox-row" key={service.id}>
                    <input name="serviceIds" type="checkbox" value={service.id} />
                    <span>{locale === "ar" ? service.nameAr : service.nameEn}</span>
                  </label>
                ))}
              </div>
            </fieldset>
            <label className="field checkbox-row">
              <input defaultChecked name="isActive" type="checkbox" />
              <span>{text.activeAndBookable}</span>
            </label>
            <div className="form-actions">
              <SubmitButton>{text.saveDoctor}</SubmitButton>
            </div>
          </form>
        </details>
      ) : null}
    </section>
  );
}

function ScheduleDay({
  breaks,
  day,
  label,
  periods,
  text,
}: Readonly<{
  breaks: readonly Readonly<{ endMinuteLocal: number; startMinuteLocal: number }>[];
  day: (typeof weekdays)[number];
  label: string;
  periods: readonly Readonly<{ endMinuteLocal: number; startMinuteLocal: number }>[];
  text: Readonly<{ breakEnd: string; breakStart: string; endTime: string; startTime: string }>;
}>) {
  const period = periods[0];
  return (
    <fieldset className="panel form-grid">
      <legend>{label}</legend>
      <label className="checkbox-row">
        <input defaultChecked={Boolean(period)} name={`working_${day}`} type="checkbox" />
        <span>{label}</span>
      </label>
      <Time
        label={text.startTime}
        name={`start_${day}`}
        value={period ? minuteTime(period.startMinuteLocal) : "09:00"}
      />
      <Time
        label={text.endTime}
        name={`end_${day}`}
        value={period ? minuteTime(period.endMinuteLocal) : "17:00"}
      />
      <Time
        label={`${text.breakStart} 1`}
        name={`breakOneStart_${day}`}
        required={false}
        value={breaks[0] ? minuteTime(breaks[0].startMinuteLocal) : ""}
      />
      <Time
        label={`${text.breakEnd} 1`}
        name={`breakOneEnd_${day}`}
        required={false}
        value={breaks[0] ? minuteTime(breaks[0].endMinuteLocal) : ""}
      />
      <Time
        label={`${text.breakStart} 2`}
        name={`breakTwoStart_${day}`}
        required={false}
        value={breaks[1] ? minuteTime(breaks[1].startMinuteLocal) : ""}
      />
      <Time
        label={`${text.breakEnd} 2`}
        name={`breakTwoEnd_${day}`}
        required={false}
        value={breaks[1] ? minuteTime(breaks[1].endMinuteLocal) : ""}
      />
    </fieldset>
  );
}

function Select({
  label,
  name,
  options,
}: Readonly<{
  label: string;
  name: string;
  options: readonly Readonly<{ label: string; value: string }>[];
}>) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      <select className="select" name={name} required>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
function Time({
  label,
  name,
  required = true,
  value,
}: Readonly<{ label: string; name: string; required?: boolean; value: string }>) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      <input className="input" defaultValue={value} name={name} required={required} type="time" />
    </label>
  );
}
function minuteTime(minutes: number): string {
  return `${Math.floor(minutes / 60)
    .toString()
    .padStart(2, "0")}:${(minutes % 60).toString().padStart(2, "0")}`;
}

const labels = {
  en: {
    active: "Active",
    inactive: "Inactive",
    activeAndBookable: "Active and bookable",
    addDoctor: "Add doctor from an existing team account",
    addTimeOff: "Add time off",
    branch: "Branch",
    branches: "Branches",
    break: "Break",
    breakEnd: "Break ends",
    breakStart: "Break starts",
    business: "Business",
    confirmScheduleImpact: "I reviewed existing appointments that may be affected.",
    confirmTimeOffImpact: "I reviewed appointments during this time off.",
    createdBy: "Created by",
    contact: "Contact",
    description: "Explicit doctor profiles, services, working hours, breaks, and time off.",
    editDoctor: "Edit doctor",
    role: "Role",
    doctor: "Doctor",
    doctors: "Doctors",
    editSchedule: "Edit weekly schedule",
    email: "Email",
    endTime: "Working day ends",
    from: "From",
    nameAr: "Arabic name",
    nameEn: "English name",
    noDoctors: "No doctors configured",
    noDoctorsHelp: "Choose an existing team account below and configure it as a doctor.",
    noSchedule: "No working schedule configured.",
    noSpecialty: "No specialty set",
    noTimeOff: "No upcoming time off.",
    phone: "Phone",
    profession: "Profession",
    reason: "Reason",
    saveDoctor: "Save doctor",
    saveSchedule: "Save schedule",
    saveTimeOff: "Save time off",
    scheduleAndBreaks: "Schedule and breaks",
    services: "Assigned services",
    specialty: "Specialty",
    startTime: "Working day starts",
    teamMember: "Team account",
    to: "To",
    upcomingTimeOff: "Upcoming time off",
    weekdays: {
      FRIDAY: "Friday",
      MONDAY: "Monday",
      SATURDAY: "Saturday",
      SUNDAY: "Sunday",
      THURSDAY: "Thursday",
      TUESDAY: "Tuesday",
      WEDNESDAY: "Wednesday",
    },
    viewAppointments: "View appointments",
    workingDays: "Working days",
  },
  ar: {
    active: "نشط",
    inactive: "غير نشط",
    activeAndBookable: "نشط ومتاح للحجز",
    addDoctor: "إضافة طبيب من حساب فريق موجود",
    addTimeOff: "إضافة إجازة",
    branch: "الفرع",
    branches: "الفروع",
    break: "استراحة",
    breakEnd: "نهاية الاستراحة",
    breakStart: "بداية الاستراحة",
    business: "النشاط",
    confirmScheduleImpact: "راجعت المواعيد الحالية التي قد تتأثر.",
    confirmTimeOffImpact: "راجعت المواعيد خلال فترة الإجازة.",
    createdBy: "أنشأها",
    contact: "الاتصال",
    description: "ملفات الأطباء والخدمات وساعات العمل والاستراحات والإجازات.",
    editDoctor: "تعديل الطبيب",
    role: "الدور",
    doctor: "طبيب",
    doctors: "الأطباء",
    editSchedule: "تعديل الجدول الأسبوعي",
    email: "البريد الإلكتروني",
    endTime: "نهاية يوم العمل",
    from: "من",
    nameAr: "الاسم بالعربية",
    nameEn: "الاسم بالإنجليزية",
    noDoctors: "لا يوجد أطباء معدّون",
    noDoctorsHelp: "اختر حساب فريق موجوداً أدناه وقم بإعداده كطبيب.",
    noSchedule: "لم يتم إعداد جدول عمل.",
    noSpecialty: "لم يحدد التخصص",
    noTimeOff: "لا توجد إجازات قادمة.",
    phone: "الهاتف",
    profession: "المهنة",
    reason: "السبب",
    saveDoctor: "حفظ الطبيب",
    saveSchedule: "حفظ الجدول",
    saveTimeOff: "حفظ الإجازة",
    scheduleAndBreaks: "الجدول والاستراحات",
    services: "الخدمات المعينة",
    specialty: "التخصص",
    startTime: "بداية يوم العمل",
    teamMember: "حساب الفريق",
    to: "إلى",
    upcomingTimeOff: "الإجازات القادمة",
    weekdays: {
      FRIDAY: "الجمعة",
      MONDAY: "الاثنين",
      SATURDAY: "السبت",
      SUNDAY: "الأحد",
      THURSDAY: "الخميس",
      TUESDAY: "الثلاثاء",
      WEDNESDAY: "الأربعاء",
    },
    viewAppointments: "عرض المواعيد",
    workingDays: "أيام العمل",
  },
} as const;
