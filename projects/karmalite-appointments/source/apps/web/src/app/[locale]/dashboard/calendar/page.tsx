import { randomUUID } from "node:crypto";

import { canAccessResource } from "@jormall/auth/tenant-policy";
import { isSupportedLocale } from "@jormall/contracts/locales";
import { AppointmentSource, AppointmentStatus } from "@jormall/db/generated/enums";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Feedback } from "../../../../components/feedback";
import { AppointmentWizard } from "../../../../components/appointment-wizard";
import { CalendarTimeGrid } from "../../../../components/calendar-time-grid";
import { ScheduleTabs } from "../../../../components/workspace-tabs";
import { SubmitButton } from "../../../../components/submit-button";
import { phaseOneMessages } from "../../../../messages/phase-one";
import { phaseTwoLabel, phaseTwoMessages } from "../../../../messages/phase-two";
import { phaseThreeMessages } from "../../../../messages/phase-three";
import {
  crmAppointmentRepository,
  identityRepository,
  requireTenantAccess,
} from "../../../../server/identity";

const statuses = Object.values(AppointmentStatus);
const sources = Object.values(AppointmentSource);
const calendarViews = ["day", "week", "doctor", "room", "resource", "branch"] as const;
type CalendarView = (typeof calendarViews)[number];

export default async function CalendarPage({
  params,
  searchParams,
}: PageProps<"/[locale]/dashboard/calendar">) {
  const { locale } = await params;
  if (!isSupportedLocale(locale)) notFound();
  const query = await searchParams;
  const access = await requireTenantAccess(locale);
  const view = calendarViews.includes(stringQuery(query.view) as CalendarView)
    ? (stringQuery(query.view) as CalendarView)
    : "day";
  const selectedDay = validDay(stringQuery(query.day)) ?? ammanDay(new Date());
  const week = weekAround(selectedDay);
  const filter = {
    branchId: access.activeBranchId,
    day: selectedDay,
    providerId: stringQuery(query.providerId),
    resourceId: stringQuery(query.resourceId),
    serviceId: stringQuery(query.serviceId),
    source: sources.includes(stringQuery(query.source) as AppointmentSource)
      ? (stringQuery(query.source) as AppointmentSource)
      : undefined,
    status: statuses.includes(stringQuery(query.status) as AppointmentStatus)
      ? (stringQuery(query.status) as AppointmentStatus)
      : undefined,
  };
  const canCreate =
    canAccessResource(access, "appointments.create") && canAccessResource(access, "customers.read");
  const canCreateCustomer = canAccessResource(access, "customers.write");
  const canReadPatientHealth = canAccessResource(access, "patients.health.read");
  const canWritePatientHealth = canAccessResource(access, "patients.health.write");
  const canReadDoctors = access.grants.some(({ code }) => code === "doctors.directory.read");
  const canReadRooms = access.grants.some(({ code }) => code === "resources.read");
  const [appointmentSets, options, doctors, rooms] = await Promise.all([
    Promise.all(
      (view === "week" ? week.map(({ value }) => value) : [filter.day]).map((day) =>
        crmAppointmentRepository.listAppointments(access, { ...filter, day }),
      ),
    ),
    canCreate ? crmAppointmentRepository.listAppointmentFormOptions(access) : Promise.resolve(null),
    canReadDoctors ? identityRepository.listDoctors(access) : Promise.resolve([]),
    canReadRooms ? crmAppointmentRepository.listOperationalRooms(access) : Promise.resolve([]),
  ]);
  const phaseOne = phaseOneMessages[locale];
  const messages = phaseTwoMessages[locale];
  const phaseThree = phaseThreeMessages[locale];
  const appointments = appointmentSets.flat();
  const distinct = {
    branches: distinctBy(appointments.map((appointment) => appointment.branch)),
    providers: distinctBy(appointments.map((appointment) => appointment.provider)),
    services: distinctBy(appointments.map((appointment) => appointment.service)),
    resources: rooms,
  };
  const groups = calendarGroups(appointments, view, locale, week, doctors, rooms, filter.day);
  return (
    <section className="page-stack calendar-workspace" aria-labelledby="calendar-title">
      <ScheduleTabs locale={locale} />
      <header className="page-heading calendar-heading">
        <div>
          <p className="eyebrow">{phaseOne.activeOrganization}</p>
          <h1 id="calendar-title">{messages.calendar}</h1>
          <p className="page-description">
            {new Intl.DateTimeFormat(locale === "ar" ? "ar-JO" : "en-JO", {
              dateStyle: "long",
              timeZone: "UTC",
            }).format(new Date(`${filter.day}T00:00:00Z`))}
          </p>
        </div>
        <Link className="button button-secondary" href={`/${locale}/schedule/today`}>
          {locale === "ar" ? "عمليات اليوم" : "Today operations"}
        </Link>
      </header>
      <Feedback
        error={typeof query.error === "string" ? query.error : undefined}
        locale={locale}
        notice={typeof query.notice === "string" ? query.notice : undefined}
      />
      {options ? (
        <details
          className="panel action-disclosure calendar-create calendar-primary-action"
          open={Boolean(query.patient || query.serviceId || query.create)}
        >
          <summary id="create-appointment-title">+ {messages.createAppointment}</summary>
          <AppointmentWizard
            canConfirmAppointment={access.grants.some(({ code }) => code === "appointment.confirm")}
            canCreateCustomer={canCreateCustomer}
            canReadPatientHealth={canReadPatientHealth}
            canWritePatientHealth={canWritePatientHealth}
            idempotencyKey={randomUUID()}
            initialBranchId={filter.branchId}
            initialDate={filter.day}
            initialPatientId={stringQuery(query.patient) || undefined}
            initialProviderId={stringQuery(query.providerId)}
            initialServiceId={stringQuery(query.serviceId) || undefined}
            initialStartsAtLocal={
              /^\d{2}:\d{2}$/u.test(stringQuery(query.time) ?? "")
                ? `${filter.day}T${stringQuery(query.time)}`
                : undefined
            }
            locale={locale}
            options={options}
          />
        </details>
      ) : null}
      <nav
        className="calendar-week-strip"
        aria-label={locale === "ar" ? "اختيار يوم" : "Choose day"}
      >
        {week.map((day) => (
          <Link
            aria-current={day.value === filter.day ? "date" : undefined}
            href={calendarHref(locale, day.value, filter)}
            key={day.value}
          >
            <small>
              {new Intl.DateTimeFormat(locale === "ar" ? "ar-JO" : "en-JO", {
                weekday: "short",
                timeZone: "UTC",
              }).format(day.date)}
            </small>
            <strong>
              {new Intl.DateTimeFormat(locale === "ar" ? "ar-JO" : "en-JO", {
                day: "numeric",
                timeZone: "UTC",
              }).format(day.date)}
            </strong>
          </Link>
        ))}
      </nav>
      <nav
        className="workspace-tabs calendar-view-tabs"
        aria-label={locale === "ar" ? "طريقة عرض التقويم" : "Calendar view"}
      >
        {calendarViews.map((candidate) => (
          <Link
            aria-current={candidate === view ? "page" : undefined}
            href={calendarViewHref(locale, candidate, filter.day, filter)}
            key={candidate}
          >
            {calendarViewLabel(locale, candidate)}
          </Link>
        ))}
      </nav>
      <details
        className="panel calendar-filters"
        open={Boolean(
          filter.branchId ||
          filter.providerId ||
          filter.resourceId ||
          filter.serviceId ||
          filter.source ||
          filter.status,
        )}
      >
        <summary>{locale === "ar" ? "فلترة التقويم" : "Filter calendar"}</summary>
        <form action={`/${locale}/schedule/calendar`} className="form-grid" method="get">
          <input name="view" type="hidden" value={view} />
          <label className="field">
            <span className="field-label">{locale === "ar" ? "اليوم" : "Day"}</span>
            <input className="input" defaultValue={filter.day} name="day" type="date" />
          </label>
          <label className="field">
            <span className="field-label">{messages.provider}</span>
            <select className="select" defaultValue={filter.providerId ?? ""} name="providerId">
              <option value="">{locale === "ar" ? "كل الأطباء" : "All Doctors"}</option>
              {(doctors.length > 0 ? doctors : distinct.providers).map((provider) => (
                <option key={provider.id} value={provider.id}>
                  {locale === "ar" ? provider.displayNameAr : provider.displayNameEn}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">{phaseOne.service}</span>
            <select className="select" defaultValue={filter.serviceId ?? ""} name="serviceId">
              <option value="">{locale === "ar" ? "كل الخدمات" : "All services"}</option>
              {distinct.services.map((service) => (
                <option key={service.id} value={service.id}>
                  {locale === "ar" ? service.nameAr : service.nameEn}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">{messages.status}</span>
            <select className="select" defaultValue={filter.status ?? ""} name="status">
              <option value="">{locale === "ar" ? "كل الحالات" : "All statuses"}</option>
              {statuses.map((status) => (
                <option key={status} value={status}>
                  {phaseTwoLabel(locale, status)}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">{locale === "ar" ? "الغرفة" : "Room"}</span>
            <select className="select" defaultValue={filter.resourceId ?? ""} name="resourceId">
              <option value="">{locale === "ar" ? "كل الغرف" : "All Rooms"}</option>
              {distinct.resources.map((resource) => (
                <option key={resource.id} value={resource.id}>
                  {locale === "ar" ? resource.nameAr : resource.nameEn}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">{locale === "ar" ? "مصدر الحجز" : "Booking source"}</span>
            <select className="select" defaultValue={filter.source ?? ""} name="source">
              <option value="">{locale === "ar" ? "كل المصادر" : "All sources"}</option>
              {sources.map((source) => (
                <option key={source} value={source}>
                  {sourceLabel(locale, source)}
                </option>
              ))}
            </select>
          </label>
          <div className="form-actions">
            <SubmitButton tone="secondary">{messages.filters}</SubmitButton>
          </div>
        </form>
      </details>
      {groups.length === 0 ? (
        <div className="empty-state calendar-empty">
          <span className="empty-state-icon" aria-hidden="true">
            ▦
          </span>
          <h2>{locale === "ar" ? "اليوم فاضي" : "This day is clear"}</h2>
          <p>
            {locale === "ar"
              ? "ما في مواعيد حسب الفلاتر الحالية."
              : "No appointments match the current filters."}
          </p>
          {options ? (
            <a className="button button-primary" href="#create-appointment-title">
              {messages.createAppointment}
            </a>
          ) : null}
        </div>
      ) : (
        <div className="calendar-board" data-view={view}>
          {groups.map((group) => (
            <section
              className="calendar-column"
              key={group.id}
              aria-labelledby={`calendar-group-${group.id}`}
            >
              <header className="calendar-column-heading">
                <h2 id={`calendar-group-${group.id}`}>{group.label}</h2>
                <span>{group.appointments.length}</span>
              </header>
              {group.slots.length > 0 ? (
                <CalendarTimeGrid
                  appointments={group.appointments.map((appointment) => ({
                    appointmentId: appointment.id,
                    canReschedule:
                      (appointment.status === AppointmentStatus.PENDING ||
                        appointment.status === AppointmentStatus.CONFIRMED) &&
                      canAccessResource(access, "appointment.reschedule", {
                        branchId: appointment.branchId,
                        staffProfileId: appointment.providerId,
                      }),
                    expectedVersion: appointment.version,
                    href: `/${locale}/schedule/appointments?appointment=${appointment.id}`,
                    patient: appointment.customer.displayName,
                    room:
                      (appointment.actualRoom ?? appointment.room)
                        ? locale === "ar"
                          ? ((appointment.actualRoom ?? appointment.room)?.nameAr ?? "—")
                          : ((appointment.actualRoom ?? appointment.room)?.nameEn ?? "—")
                        : "—",
                    service:
                      locale === "ar" ? appointment.service.nameAr : appointment.service.nameEn,
                    startsAtLocal: localDateTimeValue(appointment.startsAt, appointment.timezone),
                    status: phaseTwoLabel(locale, appointment.status),
                  }))}
                  branchId={
                    filter.branchId ??
                    doctors
                      .find(({ id }) => id === group.id)
                      ?.branchAssignments.toSorted((left, right) =>
                        left.branch.nameEn.localeCompare(right.branch.nameEn),
                      )[0]?.branchId
                  }
                  breaks={group.breaks}
                  day={filter.day}
                  locale={locale}
                  providerId={group.id}
                  returnTo={calendarViewHref(locale, view, filter.day, filter)}
                  slots={group.slots}
                />
              ) : group.appointments.length === 0 ? (
                <div className="calendar-column-empty">
                  <p>{locale === "ar" ? "لا توجد مواعيد" : "No appointments"}</p>
                  {options ? (
                    <Link
                      href={`${calendarHref(locale, filter.day, {
                        ...filter,
                        providerId:
                          (view === "day" || view === "doctor") && group.id !== "unassigned"
                            ? group.id
                            : filter.providerId,
                      })}#create-appointment-title`}
                    >
                      {messages.createAppointment}
                    </Link>
                  ) : null}
                </div>
              ) : (
                <ol
                  className="calendar-agenda"
                  aria-label={`${messages.appointments}: ${group.label}`}
                >
                  {group.appointments.map((appointment) => (
                    <li key={`${group.id}:${appointment.id}`}>
                      <time>
                        {appointment.startsAt.toLocaleTimeString(
                          locale === "ar" ? "ar-JO" : "en-JO",
                          {
                            hour: "2-digit",
                            minute: "2-digit",
                            timeZone: appointment.timezone,
                          },
                        )}
                      </time>
                      <article
                        className="calendar-appointment"
                        data-status={appointment.status.toLowerCase()}
                      >
                        <div className="calendar-appointment-main">
                          <span className="status">
                            {phaseTwoLabel(locale, appointment.status)}
                          </span>
                          <h2>
                            <Link
                              href={`/${locale}/schedule/appointments?appointment=${appointment.id}`}
                            >
                              {appointment.customer.displayName}
                            </Link>
                          </h2>
                          <p>
                            {locale === "ar"
                              ? appointment.service.nameAr
                              : appointment.service.nameEn}
                          </p>
                          <p>
                            {locale === "ar" ? "الطبيب: " : "Doctor: "}
                            {locale === "ar"
                              ? appointment.provider.displayNameAr
                              : appointment.provider.displayNameEn}
                          </p>
                          <p>
                            {locale === "ar" ? "الغرفة: " : "Room: "}
                            {(appointment.actualRoom ?? appointment.room)
                              ? locale === "ar"
                                ? (appointment.actualRoom ?? appointment.room)?.nameAr
                                : (appointment.actualRoom ?? appointment.room)?.nameEn
                              : "—"}
                          </p>
                          <p>
                            {appointment.startsAt.toLocaleTimeString(
                              locale === "ar" ? "ar-JO" : "en-JO",
                              {
                                hour: "2-digit",
                                minute: "2-digit",
                                timeZone: appointment.timezone,
                              },
                            )}
                            {" – "}
                            {appointment.endsAt.toLocaleTimeString(
                              locale === "ar" ? "ar-JO" : "en-JO",
                              {
                                hour: "2-digit",
                                minute: "2-digit",
                                timeZone: appointment.timezone,
                              },
                            )}
                          </p>
                        </div>
                        <span
                          className={
                            appointment.conflictIndicator === "MISSING_RESOURCE"
                              ? "status status-suspended"
                              : "status status-active"
                          }
                        >
                          {appointment.conflictIndicator === "MISSING_RESOURCE"
                            ? locale === "ar"
                              ? "يلزم ضبط الموارد"
                              : "Resource setup required"
                            : appointment.conflictIndicator === "RELEASED"
                              ? locale === "ar"
                                ? "تم تحرير الحجز"
                                : "Reservation released"
                              : phaseThree.conflictProtected}
                        </span>
                      </article>
                    </li>
                  ))}
                </ol>
              )}
            </section>
          ))}
        </div>
      )}
    </section>
  );
}

function stringQuery(value: string | string[] | undefined): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function validDay(value: string | undefined): string | undefined {
  return value && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : undefined;
}

function distinctBy<T extends { id: string }>(values: readonly T[]): T[] {
  return [...new Map(values.map((value) => [value.id, value])).values()];
}

function ammanDay(date: Date): string {
  return new Intl.DateTimeFormat("en-CA", {
    day: "2-digit",
    month: "2-digit",
    timeZone: "Asia/Amman",
    year: "numeric",
  }).format(date);
}

function weekAround(day: string): readonly Readonly<{ date: Date; value: string }>[] {
  const selected = new Date(`${day}T00:00:00Z`);
  return Array.from({ length: 7 }, (_, index) => {
    const date = new Date(selected);
    date.setUTCDate(selected.getUTCDate() + index - 3);
    return { date, value: date.toISOString().slice(0, 10) };
  });
}

function calendarHref(
  locale: "ar" | "en",
  day: string,
  filter: Readonly<{
    branchId?: string | undefined;
    providerId?: string | undefined;
    resourceId?: string | undefined;
    serviceId?: string | undefined;
    source?: AppointmentSource | undefined;
    status?: AppointmentStatus | undefined;
    view?: CalendarView | undefined;
  }>,
): string {
  const query = new URLSearchParams({ day });
  if (filter.branchId) query.set("branchId", filter.branchId);
  if (filter.providerId) query.set("providerId", filter.providerId);
  if (filter.resourceId) query.set("resourceId", filter.resourceId);
  if (filter.serviceId) query.set("serviceId", filter.serviceId);
  if (filter.source) query.set("source", filter.source);
  if (filter.status) query.set("status", filter.status);
  if (filter.view) query.set("view", filter.view);
  return `/${locale}/schedule/calendar?${query.toString()}`;
}

function calendarViewHref(
  locale: "ar" | "en",
  view: CalendarView,
  day: string,
  filter: Parameters<typeof calendarHref>[2],
): string {
  return calendarHref(locale, day, { ...filter, view });
}

function calendarViewLabel(locale: "ar" | "en", view: CalendarView): string {
  const labels = {
    ar: {
      day: "اليوم",
      doctor: "الطبيب",
      room: "الغرفة",
      week: "الأسبوع",
      resource: "الموارد",
      branch: "الفروع",
    },
    en: {
      day: "Day",
      doctor: "Doctor",
      room: "Room",
      week: "Week",
      resource: "Resource",
      branch: "Branch",
    },
  } as const;
  return labels[locale][view];
}

function sourceLabel(locale: "ar" | "en", source: AppointmentSource): string {
  const english = source.replaceAll("_", " ").toLocaleLowerCase("en");
  if (locale === "en") return english.replace(/^./u, (letter) => letter.toUpperCase());
  const arabic: Readonly<Record<AppointmentSource, string>> = {
    API: "واجهة برمجة التطبيقات",
    IMPORT: "استيراد",
    PUBLIC_BOOKING: "حجز عام",
    STAFF: "الموظفون",
    VOICE_AI: "المساعد الصوتي",
    WEBSITE_AI: "مساعد الموقع",
    WHATSAPP_AI: "مساعد واتساب",
  };
  return arabic[source];
}

type CalendarAppointment = Awaited<
  ReturnType<typeof crmAppointmentRepository.listAppointments>
>[number];
type CalendarDoctor = Awaited<ReturnType<typeof identityRepository.listDoctors>>[number];
type CalendarRoom = Awaited<
  ReturnType<typeof crmAppointmentRepository.listOperationalRooms>
>[number];

function calendarGroups(
  appointments: readonly CalendarAppointment[],
  view: CalendarView,
  locale: "ar" | "en",
  week: readonly Readonly<{ date: Date; value: string }>[],
  doctors: readonly CalendarDoctor[],
  rooms: readonly CalendarRoom[],
  selectedDay: string,
) {
  if (view === "week") {
    return week.map(({ date, value }) => ({
      appointments: appointments.filter(
        (appointment) => localDay(appointment.startsAt, appointment.timezone) === value,
      ),
      id: value,
      breaks: [] as readonly string[],
      label: new Intl.DateTimeFormat(locale === "ar" ? "ar-JO" : "en-JO", {
        day: "numeric",
        month: "short",
        weekday: "short",
        timeZone: "UTC",
      }).format(date),
      slots: [] as readonly string[],
    }));
  }
  if (view === "room" || view === "resource") {
    const configured = rooms.map((room) => ({
      appointments: appointments.filter(
        (appointment) => (appointment.actualRoomId ?? appointment.roomId) === room.id,
      ),
      id: room.id,
      breaks: [] as readonly string[],
      label: `${locale === "ar" ? room.nameAr : room.nameEn} · ${room.availableCapacity}/${room.capacity}`,
      slots: [] as readonly string[],
    }));
    const unassigned = appointments.filter(
      (appointment) => !(appointment.actualRoomId ?? appointment.roomId),
    );
    return unassigned.length > 0
      ? [
          ...configured,
          {
            appointments: unassigned,
            breaks: [] as readonly string[],
            id: "unassigned",
            label: locale === "ar" ? "دون غرفة" : "No assigned room",
            slots: [] as readonly string[],
          },
        ]
      : configured;
  }
  if (view === "branch") {
    return groupedAppointments(
      appointments,
      (appointment) => appointment.branch.id,
      (appointment) => (locale === "ar" ? appointment.branch.nameAr : appointment.branch.nameEn),
    ).map((group) => ({
      ...group,
      breaks: [] as readonly string[],
      slots: [] as readonly string[],
    }));
  }
  if (doctors.length > 0) {
    return doctors
      .filter(({ isActive }) => isActive)
      .map((doctor) => {
        const doctorAppointments = appointments.filter(
          ({ providerId }) => providerId === doctor.id,
        );
        return {
          appointments: doctorAppointments,
          breaks: doctorBreakSlots(doctor, selectedDay),
          id: doctor.id,
          label: `${locale === "ar" ? doctor.displayNameAr : doctor.displayNameEn} · ${doctorDayStatus(doctor, selectedDay, locale)}`,
          slots: [
            ...new Set([
              ...doctorSlots(doctor, selectedDay),
              ...doctorAppointments.map((appointment) =>
                localDateTimeValue(appointment.startsAt, appointment.timezone).slice(11),
              ),
            ]),
          ].toSorted(),
        };
      });
  }
  return groupedAppointments(
    appointments,
    (appointment) => appointment.provider.id,
    (appointment) =>
      locale === "ar" ? appointment.provider.displayNameAr : appointment.provider.displayNameEn,
  ).map((group) => ({ ...group, breaks: [] as readonly string[], slots: [] as readonly string[] }));
}

function doctorDayStatus(doctor: CalendarDoctor, day: string, locale: "ar" | "en"): string {
  if (doctorIsOnLeave(doctor, day)) {
    return locale === "ar" ? "في إجازة" : "On leave";
  }
  const weekday = ["SUNDAY", "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"][
    new Date(`${day}T00:00:00Z`).getUTCDay()
  ];
  const hours = doctor.availabilityRules
    .filter((rule) => rule.weekday === weekday)
    .map((rule) => `${minuteLabel(rule.startMinuteLocal)}–${minuteLabel(rule.endMinuteLocal)}`)
    .join(", ");
  return hours || (locale === "ar" ? "غير مجدول" : "Not scheduled");
}

function doctorBreakSlots(doctor: CalendarDoctor, day: string): readonly string[] {
  const weekday = ["SUNDAY", "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"][
    new Date(`${day}T00:00:00Z`).getUTCDay()
  ];
  return doctor.breaks
    .filter((rule) => rule.weekday === weekday)
    .flatMap((rule) => {
      const values: string[] = [];
      for (let minute = rule.startMinuteLocal; minute < rule.endMinuteLocal; minute += 30) {
        values.push(minuteLabel(minute));
      }
      return values;
    });
}

function minuteLabel(minute: number): string {
  return `${Math.floor(minute / 60)
    .toString()
    .padStart(2, "0")}:${(minute % 60).toString().padStart(2, "0")}`;
}

function doctorSlots(doctor: CalendarDoctor, day: string): readonly string[] {
  if (doctorIsOnLeave(doctor, day)) return [];
  const weekday = ["SUNDAY", "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"][
    new Date(`${day}T00:00:00Z`).getUTCDay()
  ];
  return doctor.availabilityRules
    .filter((rule) => rule.weekday === weekday)
    .flatMap((rule) => {
      const values: string[] = [];
      for (let minute = rule.startMinuteLocal; minute < rule.endMinuteLocal; minute += 30) {
        values.push(minuteLabel(minute));
      }
      return values;
    });
}

function doctorIsOnLeave(doctor: CalendarDoctor, day: string): boolean {
  const dayStart = new Date(`${day}T00:00:00Z`);
  const dayEnd = new Date(dayStart);
  dayEnd.setUTCDate(dayEnd.getUTCDate() + 1);
  return doctor.timeOffEntries.some((entry) => entry.startsAt < dayEnd && entry.endsAt > dayStart);
}

function localDateTimeValue(date: Date, timezone: string): string {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      day: "2-digit",
      hour: "2-digit",
      hour12: false,
      hourCycle: "h23",
      minute: "2-digit",
      month: "2-digit",
      timeZone: timezone,
      year: "numeric",
    })
      .formatToParts(date)
      .filter(({ type }) => type !== "literal")
      .map(({ type, value }) => [type, value]),
  );
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}

function groupedAppointments(
  appointments: readonly CalendarAppointment[],
  idFor: (appointment: CalendarAppointment) => string,
  labelFor: (appointment: CalendarAppointment) => string,
) {
  const groups = new Map<
    string,
    { appointments: CalendarAppointment[]; id: string; label: string }
  >();
  for (const appointment of appointments) {
    const id = idFor(appointment);
    const group = groups.get(id) ?? { appointments: [], id, label: labelFor(appointment) };
    group.appointments.push(appointment);
    groups.set(id, group);
  }
  return [...groups.values()];
}

function localDay(date: Date, timezone: string): string {
  return new Intl.DateTimeFormat("en-CA", {
    day: "2-digit",
    month: "2-digit",
    timeZone: timezone,
    year: "numeric",
  }).format(date);
}
