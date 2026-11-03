import { randomUUID } from "node:crypto";

import { canAccessResource } from "@jormall/auth/tenant-policy";
import { isSupportedLocale } from "@jormall/contracts/locales";
import { AppointmentStatus } from "@jormall/db/generated/enums";
import { utcRangeForLocalDate } from "@jormall/domain/timezone";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Feedback } from "../../../../components/feedback";
import { AppointmentKanban } from "../../../../components/appointment-kanban";
import { DoctorScheduleControls } from "../../../../components/doctor-schedule-controls";
import { OperationDialog } from "../../../../components/operation-dialog";
import { defaultProviderIdForAppointmentRead } from "../../../../lib/appointment-read-scope";
import { appointmentKanbanMoves } from "../../../../lib/appointment-kanban";
import { ScheduleTabs } from "../../../../components/workspace-tabs";
import { SubmitButton } from "../../../../components/submit-button";
import { formatServicePrice } from "../../../../components/service-price";
import { PrintScheduleButton } from "../../../../components/print-schedule-button";
import { phaseOneMessages } from "../../../../messages/phase-one";
import { phaseTwoLabel, phaseTwoMessages } from "../../../../messages/phase-two";
import {
  crmAppointmentRepository,
  identityRepository,
  operationalWorkflowsRepository,
  requireTenantAccess,
} from "../../../../server/identity";
import {
  bulkConfirmAppointmentsAction,
  callAppointmentToRoomAction,
  changeAppointmentRoomAction,
  combinedAppointmentTransitionAction,
  resendRoomMessageAction,
  startAppointmentServiceAction,
  transitionAppointmentAction,
} from "../../actions";

type AppointmentRow = Awaited<ReturnType<typeof crmAppointmentRepository.listAppointments>>[number];
type OperationalRoom = Awaited<
  ReturnType<typeof crmAppointmentRepository.listOperationalRooms>
>[number];

type ProviderOption = Readonly<{
  availabilityRules: readonly Readonly<{
    branchId: string | null;
    endMinuteLocal: number;
    startMinuteLocal: number;
    weekday: string;
  }>[];
  branchIds: readonly string[];
  breaks: readonly Readonly<{
    branchId: string;
    endMinuteLocal: number;
    label: string | null;
    startMinuteLocal: number;
    weekday: string;
  }>[];
  displayNameAr: string;
  displayNameEn: string;
  id: string;
  serviceIds: readonly string[];
  timeOffEntries: readonly Readonly<{
    branchId: string | null;
    endsAt: Date;
    reason: string | null;
    startsAt: Date;
  }>[];
}>;

const appointmentStatuses = Object.values(AppointmentStatus);
const visibleAppointmentStatuses = appointmentStatuses.filter(
  (status) => status !== AppointmentStatus.CALLED,
);
const terminalStatuses: readonly AppointmentStatus[] = [
  AppointmentStatus.COMPLETED,
  AppointmentStatus.CANCELLED,
  AppointmentStatus.NO_SHOW,
];
export default async function TodayPage({
  params,
  searchParams,
}: PageProps<"/[locale]/dashboard/today">) {
  const [{ locale }, query] = await Promise.all([params, searchParams]);
  if (!isSupportedLocale(locale)) notFound();
  const access = await requireTenantAccess(locale);
  const renderedAt = new Date();
  const canCreate =
    canAccessResource(access, "appointments.create") && canAccessResource(access, "customers.read");
  const canReadDoctors = access.grants.some(({ code }) => code === "doctors.directory.read");
  const canReadRooms = access.grants.some(({ code }) => code === "resources.read");
  const [options, doctorRows, operationalRooms] = await Promise.all([
    canCreate ? crmAppointmentRepository.listAppointmentFormOptions(access) : Promise.resolve(null),
    canReadDoctors ? identityRepository.listDoctors(access) : Promise.resolve([]),
    canReadRooms ? crmAppointmentRepository.listOperationalRooms(access) : Promise.resolve([]),
  ]);
  const branchId = access.activeBranchId;
  const providerId =
    text(query.providerId) ??
    defaultProviderIdForAppointmentRead(access.grants, access.staffProfileId);
  const serviceId = text(query.serviceId);
  const q = text(query.q);
  const view = todayView(text(query.view));
  const status = appointmentStatuses.includes(text(query.status) as AppointmentStatus)
    ? (text(query.status) as AppointmentStatus)
    : undefined;
  const timezone =
    options?.branches.find((branch) => branch.id === branchId)?.timezone ??
    options?.branches[0]?.timezone ??
    "Asia/Amman";
  const day = validDate(text(query.day)) ?? localDay(new Date(), timezone);
  const allAppointments = await crmAppointmentRepository.listAppointments(access, {
    ...(branchId ? { branchId } : {}),
    day,
    ...(providerId ? { providerId } : {}),
    ...(q ? { q } : {}),
    ...(serviceId ? { serviceId } : {}),
  });
  const appointments = status
    ? allAppointments.filter((appointment) => appointment.status === status)
    : allAppointments;
  const services = options?.services ?? distinct(appointments.map(({ service }) => service));
  const configuredProviders: readonly ProviderOption[] =
    doctorRows.length > 0
      ? doctorRows
          .filter(({ isActive }) => isActive)
          .map((provider) => ({
            availabilityRules: provider.availabilityRules,
            branchIds: provider.branchAssignments.map(({ branchId }) => branchId),
            breaks: provider.breaks,
            displayNameAr: provider.displayNameAr,
            displayNameEn: provider.displayNameEn,
            id: provider.id,
            serviceIds: provider.services.map(({ serviceId }) => serviceId),
            timeOffEntries: provider.timeOffEntries,
          }))
      : options
        ? options.providers
        : distinct(appointments.map(({ provider }) => provider)).map((provider) => ({
            ...provider,
            availabilityRules: [],
            branchIds: [],
            breaks: [],
            serviceIds: [],
            timeOffEntries: [],
          }));
  const returnTo = todayHref(locale, { branchId, day, providerId, q, serviceId, status, view });
  const phaseOne = phaseOneMessages[locale];
  const messages = phaseTwoMessages[locale];
  const labels = todayLabels[locale];
  const pendingAppointments = appointments.filter(
    (appointment) =>
      appointment.status === AppointmentStatus.PENDING &&
      canAccessResource(access, "appointment.confirm", rowResource(appointment)) &&
      canAccessResource(access, "appointment.bulkConfirm", rowResource(appointment)),
  );
  const attention = attentionRows(appointments, configuredProviders, day, timezone, locale);
  const workflowAttention = canAccessResource(access, "notifications.read")
    ? (await operationalWorkflowsRepository.listNotifications(access, "UNREAD", 20)).filter(
        ({ type }) =>
          [
            "WAITLIST_MATCH",
            "EMERGENCY_ESCALATION",
            "INVENTORY_ITEM_APPROVAL",
            "INVENTORY_ORDER_REQUEST",
            "INVENTORY_DELIVERY_OVERDUE",
          ].includes(type),
      )
    : [];

  return (
    <section className="page-stack operations-workspace" aria-labelledby="today-title">
      <ScheduleTabs locale={locale} />
      <header className="page-heading operations-heading">
        <div>
          <p className="eyebrow">{timezone}</p>
          <h1 id="today-title">{labels.pageTitle}</h1>
          <p className="page-description">
            {new Intl.DateTimeFormat(locale === "ar" ? "ar-JO" : "en-JO", {
              dateStyle: "full",
              timeZone: "UTC",
            }).format(new Date(`${day}T00:00:00Z`))}
          </p>
        </div>
        <div className="row-actions no-print">
          <PrintScheduleButton label={phaseTwoMessages[locale].printSchedule} />
          {canCreate ? (
            <Link
              className="button button-primary"
              href={`/${locale}/schedule/calendar?day=${day}#create-appointment-title`}
            >
              {labels.newAppointment}
            </Link>
          ) : null}
        </div>
      </header>
      <Feedback
        error={typeof query.error === "string" ? query.error : undefined}
        locale={locale}
        notice={typeof query.notice === "string" ? query.notice : undefined}
      />
      {query.notice === "BULK_CONFIRM_COMPLETED" ? (
        <p className="feedback feedback-info" role="status">
          {labels.bulkResult(numberQuery(query.succeeded), numberQuery(query.failed))}
        </p>
      ) : null}

      <dl className="operations-summary">
        <StatusMetric
          active={!status}
          href={todayHref(locale, {
            branchId,
            day,
            providerId,
            q,
            serviceId,
            view,
          })}
          label={labels.totalToday}
          value={allAppointments.length}
        />
        {(
          [
            AppointmentStatus.PENDING,
            AppointmentStatus.CONFIRMED,
            AppointmentStatus.CHECKED_IN,
            AppointmentStatus.IN_PROGRESS,
            AppointmentStatus.COMPLETED,
            AppointmentStatus.NO_SHOW,
          ] as const
        ).map((value) => (
          <StatusMetric
            active={status === value}
            href={todayHref(locale, {
              branchId,
              day,
              providerId,
              q,
              serviceId,
              status: status === value ? undefined : value,
              view,
            })}
            key={value}
            label={phaseTwoLabel(locale, value)}
            value={allAppointments.filter((appointment) => appointment.status === value).length}
          />
        ))}
      </dl>

      <form action={`/${locale}/schedule/today`} className="panel filter-toolbar" method="get">
        <input name="view" type="hidden" value={view} />
        <label className="field">
          <span className="field-label">{labels.date}</span>
          <input className="input" defaultValue={day} name="day" type="date" />
        </label>
        <label className="field">
          <span className="field-label">{messages.provider}</span>
          <select className="select" defaultValue={providerId ?? ""} name="providerId">
            <option value="">{labels.allProviders}</option>
            {configuredProviders.map((provider) => (
              <option key={provider.id} value={provider.id}>
                {locale === "ar" ? provider.displayNameAr : provider.displayNameEn}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span className="field-label">{phaseOne.service}</span>
          <select className="select" defaultValue={serviceId ?? ""} name="serviceId">
            <option value="">{labels.allServices}</option>
            {services.map((service) => (
              <option key={service.id} value={service.id}>
                {locale === "ar" ? service.nameAr : service.nameEn}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span className="field-label">{messages.status}</span>
          <select className="select" defaultValue={status ?? ""} name="status">
            <option value="">{labels.allStatuses}</option>
            {visibleAppointmentStatuses.map((value) => (
              <option key={value} value={value}>
                {phaseTwoLabel(locale, value)}
              </option>
            ))}
          </select>
        </label>
        <label className="field filter-search">
          <span className="field-label">{labels.search}</span>
          <input
            className="input"
            defaultValue={q ?? ""}
            name="q"
            placeholder={labels.searchHint}
            type="search"
          />
        </label>
        <button className="button button-primary" type="submit">
          {messages.filters}
        </button>
        <Link className="button button-secondary" href={`/${locale}/schedule/today`}>
          {labels.reset}
        </Link>
      </form>

      <nav className="appointment-display-tabs" aria-label={labels.appointmentViews}>
        {(["table", "kanban", "list"] as const).map((tab) => (
          <Link
            aria-current={view === tab ? "page" : undefined}
            href={todayHref(locale, { branchId, day, providerId, q, serviceId, status, view: tab })}
            key={tab}
          >
            {labels.views[tab]}
          </Link>
        ))}
      </nav>

      {view === "table" ? (
        <AllAppointments
          access={access}
          appointments={appointments}
          canCreate={canCreate}
          day={day}
          labels={labels}
          locale={locale}
          pendingAppointments={pendingAppointments}
          returnTo={returnTo}
          rooms={operationalRooms}
        />
      ) : null}
      {view === "kanban" ? (
        <AppointmentKanban
          appointments={appointments.map((appointment) => ({
            doctor: providerName(appointment, locale),
            href: `/${locale}/schedule/appointments?appointment=${appointment.id}`,
            id: appointment.id,
            moves: appointmentKanbanMoves({
              canCheckIn: canAccessResource(
                access,
                "appointment.checkIn",
                rowResource(appointment),
              ),
              canClaimRoom: canAccessResource(
                access,
                "room.occupancy.claim",
                rowResource(appointment),
              ),
              canConfirm: canAccessResource(
                access,
                "appointment.confirm",
                rowResource(appointment),
              ),
              canStartService: canAccessResource(
                access,
                "appointment.startService",
                rowResource(appointment),
              ),
              renderedAt,
              roomId: appointment.roomId,
              startsAt: appointment.startsAt,
              status: appointment.status,
            }),
            patient: appointment.customer.displayName,
            room: appointmentRoomName(appointment, locale) || labels.none,
            service: locale === "ar" ? appointment.service.nameAr : appointment.service.nameEn,
            status: appointment.status,
            time: formatTime(appointment.startsAt, appointment.timezone, locale),
            version: appointment.version,
          }))}
          columns={visibleAppointmentStatuses.map((appointmentStatus) => ({
            label: phaseTwoLabel(locale, appointmentStatus),
            status: appointmentStatus,
          }))}
          locale={locale}
          returnTo={returnTo}
        />
      ) : null}
      {view === "list" ? (
        <ListAppointments
          access={access}
          appointments={appointments}
          canCreate={canCreate}
          day={day}
          labels={labels}
          locale={locale}
          returnTo={returnTo}
          rooms={operationalRooms}
        />
      ) : null}
      {view === "provider" ? (
        <ProviderAppointments
          access={access}
          appointments={appointments}
          day={day}
          labels={labels}
          locale={locale}
          providers={configuredProviders.filter(
            (provider) => !providerId || provider.id === providerId,
          )}
          rooms={operationalRooms}
          returnTo={returnTo}
          timezone={timezone}
        />
      ) : null}
      {view === "attention" ? (
        <>
          {workflowAttention.length > 0 ? (
            <div className="card-grid">
              {workflowAttention.map((item) => (
                <article className="record-card" key={item.id}>
                  <span className="status">{item.priority}</span>
                  <h2>{locale === "ar" ? item.titleAr : item.titleEn}</h2>
                  <p>{locale === "ar" ? item.messageAr : item.messageEn}</p>
                  <Link className="button button-secondary" href={`/${locale}${item.targetRoute}`}>
                    {labels.open}
                  </Link>
                </article>
              ))}
            </div>
          ) : null}
          <AttentionTable
            attention={attention}
            labels={labels}
            locale={locale}
            returnTo={returnTo}
          />
        </>
      ) : null}
    </section>
  );
}

function AllAppointments({
  access,
  appointments,
  canCreate,
  day,
  labels,
  locale,
  pendingAppointments,
  returnTo,
  rooms,
}: Readonly<{
  access: Awaited<ReturnType<typeof requireTenantAccess>>;
  appointments: readonly AppointmentRow[];
  canCreate: boolean;
  day: string;
  labels: TodayLabels;
  locale: "ar" | "en";
  pendingAppointments: readonly AppointmentRow[];
  returnTo: string;
  rooms: readonly OperationalRoom[];
}>) {
  if (appointments.length === 0) {
    return <ScheduleEmpty canCreate={canCreate} day={day} labels={labels} locale={locale} />;
  }
  return (
    <section className="page-stack" aria-labelledby="all-appointments-title">
      <div className="section-heading">
        <div>
          <h2 id="all-appointments-title">{labels.views.table}</h2>
          <p className="muted">{labels.sortedHint}</p>
        </div>
        {pendingAppointments.length > 0 ? (
          <form action={bulkConfirmAppointmentsAction} id="bulk-confirm-form">
            <input name="locale" type="hidden" value={locale} />
            <input name="returnTo" type="hidden" value={returnTo} />
            <SubmitButton>{labels.confirmSelected}</SubmitButton>
          </form>
        ) : null}
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>
                <span className="sr-only">{labels.select}</span>
              </th>
              <th>{labels.time}</th>
              <th>{labels.customer}</th>
              <th>{labels.service}</th>
              <th>{labels.provider}</th>
              <th>{labels.resources}</th>
              <th>{labels.status}</th>
              <th>{labels.reminder}</th>
              <th>{labels.nextAction}</th>
            </tr>
          </thead>
          <tbody>
            {appointments.map((appointment) => {
              const selectable = pendingAppointments.some(({ id }) => id === appointment.id);
              return (
                <tr data-status={appointment.status.toLowerCase()} key={appointment.id}>
                  <td>
                    {selectable ? (
                      <input
                        aria-label={`${labels.select} ${appointment.customer.displayName}`}
                        form="bulk-confirm-form"
                        name="appointments"
                        type="checkbox"
                        value={`${appointment.id}:${appointment.version}`}
                      />
                    ) : null}
                  </td>
                  <td>
                    <Link href={`/${locale}/schedule/appointments?appointment=${appointment.id}`}>
                      {formatTime(appointment.startsAt, appointment.timezone, locale)}
                    </Link>
                  </td>
                  <td>
                    <Link href={`/${locale}/customers/${appointment.customer.id}`}>
                      {appointment.customer.displayName}
                    </Link>
                  </td>
                  <td>
                    <span>
                      {locale === "ar" ? appointment.service.nameAr : appointment.service.nameEn}
                    </span>
                    <small className="muted" style={{ display: "block", fontSize: "0.8rem" }}>
                      {formatServicePrice(
                        locale,
                        appointment.service.defaultPriceMinor,
                        appointment.service.currency,
                      )}
                    </small>
                  </td>
                  <td>{providerName(appointment, locale)}</td>
                  <td>{appointmentRoomName(appointment, locale) || labels.none}</td>
                  <td>
                    <span className="status">{phaseTwoLabel(locale, appointment.status)}</span>
                  </td>
                  <td>{reminderLabel(appointment, labels)}</td>
                  <td>
                    <AppointmentActions
                      access={access}
                      appointment={appointment}
                      labels={labels}
                      locale={locale}
                      returnTo={returnTo}
                      rooms={rooms}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ListAppointments({
  access,
  appointments,
  canCreate,
  day,
  labels,
  locale,
  returnTo,
  rooms,
}: Readonly<{
  access: Awaited<ReturnType<typeof requireTenantAccess>>;
  appointments: readonly AppointmentRow[];
  canCreate: boolean;
  day: string;
  labels: TodayLabels;
  locale: "ar" | "en";
  returnTo: string;
  rooms: readonly OperationalRoom[];
}>) {
  if (appointments.length === 0) {
    return <ScheduleEmpty canCreate={canCreate} day={day} labels={labels} locale={locale} />;
  }
  return (
    <section className="appointment-list-view" aria-label={labels.views.list}>
      {appointments.map((appointment) => (
        <article className="appointment-list-card" key={appointment.id}>
          <div className="appointment-list-time">
            <time>{formatTime(appointment.startsAt, appointment.timezone, locale)}</time>
            <span className="status">{phaseTwoLabel(locale, appointment.status)}</span>
          </div>
          <div className="appointment-list-patient">
            <Link href={`/${locale}/schedule/appointments?appointment=${appointment.id}`}>
              <strong>{appointment.customer.displayName}</strong>
            </Link>
            <span>{locale === "ar" ? appointment.service.nameAr : appointment.service.nameEn}</span>
            <small className="muted">
              {formatServicePrice(
                locale,
                appointment.service.defaultPriceMinor,
                appointment.service.currency,
              )}
            </small>
          </div>
          <div className="appointment-list-assignment">
            <span>{providerName(appointment, locale)}</span>
            <small>{appointmentRoomName(appointment, locale) || labels.none}</small>
          </div>
          <AppointmentActions
            access={access}
            appointment={appointment}
            labels={labels}
            locale={locale}
            returnTo={returnTo}
            rooms={rooms}
          />
        </article>
      ))}
    </section>
  );
}

function ProviderAppointments({
  access,
  appointments,
  day,
  labels,
  locale,
  providers,
  returnTo,
  rooms,
  timezone,
}: Readonly<{
  access: Awaited<ReturnType<typeof requireTenantAccess>>;
  appointments: readonly AppointmentRow[];
  day: string;
  labels: TodayLabels;
  locale: "ar" | "en";
  providers: readonly ProviderOption[];
  returnTo: string;
  rooms: readonly OperationalRoom[];
  timezone: string;
}>) {
  const unassigned = appointments.filter(({ provider }) => !provider.isDoctor);
  if (providers.length === 0 && unassigned.length === 0)
    return <p className="empty-state">{labels.noProviders}</p>;
  return (
    <section className="page-stack" aria-labelledby="provider-view-title">
      <div className="section-heading">
        <h2 id="provider-view-title">{labels.views.provider}</h2>
        <p className="muted">{labels.providerHint}</p>
      </div>
      <DoctorScheduleControls
        collapseLabel={labels.collapseAll}
        doctors={[
          ...providers.map((provider) => ({
            id: provider.id,
            label: locale === "ar" ? provider.displayNameAr : provider.displayNameEn,
          })),
          ...(unassigned.length > 0
            ? [{ id: "unassigned", label: labels.unassignedAppointments }]
            : []),
        ]}
        expandLabel={labels.expandAll}
        selectLabel={labels.selectDoctor}
      />
      {providers.map((provider) => {
        const rows = appointments.filter((appointment) => appointment.providerId === provider.id);
        const onLeave = providerIsOff(provider, day, timezone);
        const hours = providerHours(provider, day);
        const breaks = providerBreaks(provider, day);
        const next = rows
          .filter(({ status }) => status === AppointmentStatus.CHECKED_IN)
          .toSorted(
            (left, right) =>
              left.startsAt.getTime() - right.startsAt.getTime() ||
              (left.checkedInAt?.getTime() ?? Number.MAX_SAFE_INTEGER) -
                (right.checkedInAt?.getTime() ?? Number.MAX_SAFE_INTEGER) ||
              left.createdAt.getTime() - right.createdAt.getTime(),
          )[0];
        const doctorBusy = rows.some(
          ({ status }) =>
            status === AppointmentStatus.CALLED || status === AppointmentStatus.IN_PROGRESS,
        );
        const compatibleRooms = next
          ? rooms.filter(
              (room) =>
                room.branchId === next.branchId &&
                room.serviceIds.includes(next.serviceId) &&
                room.status === "ACTIVE" &&
                room.availableCapacity > 0,
            )
          : [];
        const canCallNext = Boolean(
          next &&
          day === localDay(new Date(), timezone) &&
          hours &&
          !onLeave &&
          !doctorBusy &&
          compatibleRooms.length > 0 &&
          canAccessResource(access, "doctor.queue.next", rowResource(next)) &&
          canAccessResource(access, "appointment.callToRoom", rowResource(next)) &&
          canAccessResource(access, "room.occupancy.claim", rowResource(next)),
        );
        return (
          <details
            className="panel doctor-schedule"
            data-doctor-id={provider.id}
            data-doctor-schedule
            key={provider.id}
            open
          >
            <summary>
              {locale === "ar" ? provider.displayNameAr : provider.displayNameEn} · {rows.length}{" "}
              {labels.appointments}
            </summary>
            <div className="section-heading">
              <div>
                <strong>{labels.nextAppointment}</strong>
                <p className="muted">
                  {next ? next.customer.displayName : labels.noCheckedInPatient}
                </p>
              </div>
              {next ? (
                <OperationDialog closeLabel={labels.close} label={labels.nextAppointment}>
                  <dl className="details-list">
                    <div>
                      <dt>{labels.customer}</dt>
                      <dd>{next.customer.displayName}</dd>
                    </div>
                    <div>
                      <dt>{labels.service}</dt>
                      <dd>{locale === "ar" ? next.service.nameAr : next.service.nameEn}</dd>
                    </div>
                    <div>
                      <dt>{labels.scheduledTime}</dt>
                      <dd>{formatTime(next.startsAt, next.timezone, locale)}</dd>
                    </div>
                    <div>
                      <dt>{labels.waitingSince}</dt>
                      <dd>
                        {next.checkedInAt
                          ? formatTime(next.checkedInAt, next.timezone, locale)
                          : labels.none}
                      </dd>
                    </div>
                  </dl>
                  <form action={callAppointmentToRoomAction} className="form-grid">
                    <input name="locale" type="hidden" value={locale} />
                    <input name="appointmentId" type="hidden" value={next.id} />
                    <input name="expectedVersion" type="hidden" value={next.version} />
                    <input name="idempotencyKey" type="hidden" value={randomUUID()} />
                    <input name="returnTo" type="hidden" value={returnTo} />
                    <input name="asNext" type="hidden" value="true" />
                    <label className="field">
                      <span className="field-label">{labels.compatibleRoom}</span>
                      <select className="select" disabled={!canCallNext} name="roomId" required>
                        <option value="">{labels.selectRoom}</option>
                        {compatibleRooms.map((room) => (
                          <option key={room.id} value={room.id}>
                            {locale === "ar" ? room.nameAr : room.nameEn} ({room.availableCapacity})
                          </option>
                        ))}
                      </select>
                    </label>
                    <SubmitButton disabled={!canCallNext}>{labels.callPatient}</SubmitButton>
                  </form>
                </OperationDialog>
              ) : null}
            </div>
            <dl className="details-list">
              <div>
                <dt>{labels.workingStatus}</dt>
                <dd>
                  {onLeave ? labels.doctorOnLeave : hours ? labels.working : labels.notScheduled}
                </dd>
              </div>
              <div>
                <dt>{labels.workingHours}</dt>
                <dd>{hours || labels.notConfigured}</dd>
              </div>
              <div>
                <dt>{labels.breaks}</dt>
                <dd>{breaks || labels.none}</dd>
              </div>
              <div>
                <dt>{labels.totalAppointments}</dt>
                <dd>{rows.length}</dd>
              </div>
              <div>
                <dt>{phaseTwoLabel(locale, AppointmentStatus.CHECKED_IN)}</dt>
                <dd>{countStatus(rows, AppointmentStatus.CHECKED_IN)}</dd>
              </div>
              <div>
                <dt>{phaseTwoLabel(locale, AppointmentStatus.IN_PROGRESS)}</dt>
                <dd>
                  {countStatus(rows, AppointmentStatus.CALLED) +
                    countStatus(rows, AppointmentStatus.IN_PROGRESS)}
                </dd>
              </div>
              <div>
                <dt>{phaseTwoLabel(locale, AppointmentStatus.COMPLETED)}</dt>
                <dd>{countStatus(rows, AppointmentStatus.COMPLETED)}</dd>
              </div>
            </dl>
            {rows.length === 0 ? (
              <p className="muted">
                {onLeave
                  ? labels.doctorOnLeave
                  : hours
                    ? labels.noProviderAppointments
                    : labels.notScheduled}
              </p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>{labels.time}</th>
                      <th>{labels.customer}</th>
                      <th>{labels.service}</th>
                      <th>{labels.resources}</th>
                      <th>{labels.status}</th>
                      <th>{labels.nextAction}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((appointment) => (
                      <tr key={appointment.id}>
                        <td>
                          <Link
                            href={`/${locale}/schedule/appointments?appointment=${appointment.id}`}
                          >
                            {formatTime(appointment.startsAt, appointment.timezone, locale)}
                          </Link>
                        </td>
                        <td>
                          <Link href={`/${locale}/customers/${appointment.customer.id}`}>
                            {appointment.customer.displayName}
                          </Link>
                        </td>
                        <td>
                          {locale === "ar"
                            ? appointment.service.nameAr
                            : appointment.service.nameEn}
                        </td>
                        <td>{appointmentRoomName(appointment, locale) || labels.none}</td>
                        <td>
                          <span className="status">
                            {phaseTwoLabel(locale, appointment.status)}
                          </span>
                        </td>
                        <td>
                          <AppointmentActions
                            access={access}
                            appointment={appointment}
                            labels={labels}
                            locale={locale}
                            returnTo={returnTo}
                            rooms={rooms}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </details>
        );
      })}
      {unassigned.length > 0 ? (
        <details
          className="panel doctor-schedule"
          data-doctor-id="unassigned"
          data-doctor-schedule
          open
        >
          <summary>
            {labels.unassignedAppointments} · {unassigned.length}
          </summary>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{labels.time}</th>
                  <th>{labels.customer}</th>
                  <th>{labels.service}</th>
                  <th>{labels.resources}</th>
                  <th>{labels.status}</th>
                  <th>{labels.nextAction}</th>
                </tr>
              </thead>
              <tbody>
                {unassigned.map((appointment) => (
                  <tr key={appointment.id}>
                    <td>{formatTime(appointment.startsAt, appointment.timezone, locale)}</td>
                    <td>{appointment.customer.displayName}</td>
                    <td>
                      {locale === "ar" ? appointment.service.nameAr : appointment.service.nameEn}
                    </td>
                    <td>{appointmentRoomName(appointment, locale) || labels.none}</td>
                    <td>{phaseTwoLabel(locale, appointment.status)}</td>
                    <td>
                      <Link
                        className="button button-secondary"
                        href={`/${locale}/schedule/appointments?appointment=${appointment.id}`}
                      >
                        {labels.open}
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      ) : null}
    </section>
  );
}

function AttentionTable({
  attention,
  labels,
  locale,
  returnTo,
}: Readonly<{
  attention: readonly AttentionRow[];
  labels: TodayLabels;
  locale: "ar" | "en";
  returnTo: string;
}>) {
  if (attention.length === 0) return <p className="empty-state">{labels.noAttention}</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>{labels.issue}</th>
            <th>{labels.time}</th>
            <th>{labels.customer}</th>
            <th>{labels.service}</th>
            <th>{labels.provider}</th>
            <th>{labels.recommendedAction}</th>
          </tr>
        </thead>
        <tbody>
          {attention.map((row) => (
            <tr key={`${row.appointment.id}:${row.issue}`}>
              <td>
                <span className="status status-suspended">{row.issue}</span>
              </td>
              <td>{formatTime(row.appointment.startsAt, row.appointment.timezone, locale)}</td>
              <td>{row.appointment.customer.displayName}</td>
              <td>
                {locale === "ar" ? row.appointment.service.nameAr : row.appointment.service.nameEn}
              </td>
              <td>{providerName(row.appointment, locale)}</td>
              <td>
                <Link
                  className="button button-secondary"
                  href={`/${locale}/schedule/appointments?appointment=${row.appointment.id}&returnTo=${encodeURIComponent(returnTo)}`}
                >
                  {labels.open}
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AppointmentActions({
  access,
  appointment,
  labels,
  locale,
  returnTo,
  rooms,
}: Readonly<{
  access: Awaited<ReturnType<typeof requireTenantAccess>>;
  appointment: AppointmentRow;
  labels: TodayLabels;
  locale: "ar" | "en";
  returnTo: string;
  rooms: readonly OperationalRoom[];
}>) {
  const resource = rowResource(appointment);
  const viewHref = `/${locale}/schedule/appointments?appointment=${appointment.id}`;
  const compatibleRooms = rooms.filter(
    (room) =>
      room.branchId === appointment.branchId &&
      room.serviceIds.includes(appointment.serviceId) &&
      room.status === "ACTIVE" &&
      room.availableCapacity > 0,
  );
  const canWriteCompletionNote = canAccessResource(access, "appointment_records.write", resource);
  const canClaimRoom = canAccessResource(access, "room.occupancy.claim", resource);
  const canReleaseRoom = canAccessResource(access, "room.occupancy.release", resource);
  if (terminalStatuses.includes(appointment.status)) {
    return (
      <Link className="button button-secondary" href={viewHref}>
        {labels.view}
      </Link>
    );
  }
  const primary =
    appointment.status === AppointmentStatus.PENDING &&
    canAccessResource(access, "appointment.confirm", resource) ? (
      <TransitionForm
        appointment={appointment}
        label={labels.confirm}
        locale={locale}
        returnTo={returnTo}
        status={AppointmentStatus.CONFIRMED}
      />
    ) : appointment.status === AppointmentStatus.CONFIRMED &&
      canAccessResource(access, "appointment.checkIn", resource) ? (
      <TransitionForm
        appointment={appointment}
        label={labels.checkIn}
        locale={locale}
        returnTo={returnTo}
        status={AppointmentStatus.CHECKED_IN}
      />
    ) : appointment.status === AppointmentStatus.CHECKED_IN &&
      canAccessResource(access, "appointment.callToRoom", resource) &&
      canClaimRoom ? (
      <RoomOperationForm
        action="call"
        appointment={appointment}
        label={labels.callToRoom}
        locale={locale}
        returnTo={returnTo}
        rooms={compatibleRooms}
      />
    ) : appointment.status === AppointmentStatus.CALLED &&
      canAccessResource(access, "appointment.startService", resource) &&
      canClaimRoom ? (
      <StartServiceForm
        appointment={appointment}
        label={labels.startService}
        locale={locale}
        returnTo={returnTo}
      />
    ) : appointment.status === AppointmentStatus.IN_PROGRESS &&
      canAccessResource(access, "appointment.complete", resource) &&
      canReleaseRoom ? (
      <OperationDialog closeLabel={labels.close} label={labels.complete}>
        <form action={transitionAppointmentAction} className="form-grid compact-form">
          <OperationFields appointment={appointment} locale={locale} returnTo={returnTo} />
          <input name="toStatus" type="hidden" value={AppointmentStatus.COMPLETED} />
          {canWriteCompletionNote ? (
            <>
              <label className="field">
                <span className="field-label">{labels.doctorNote}</span>
                <textarea className="textarea" name="recordSummary" required rows={3} />
              </label>
              <label className="field">
                <span className="field-label">{labels.administrativeNote}</span>
                <textarea className="textarea" name="recordDetails" rows={2} />
              </label>
            </>
          ) : null}
          <SubmitButton>{labels.complete}</SubmitButton>
        </form>
      </OperationDialog>
    ) : (
      <Link className="button button-secondary" href={viewHref}>
        {labels.view}
      </Link>
    );
  return (
    <div className="row-actions">
      {primary}
      {!terminalStatuses.includes(appointment.status) ? (
        <details className="action-disclosure">
          <summary>{labels.more}</summary>
          <div className="row-actions">
            {appointment.status === AppointmentStatus.PENDING &&
            canAccessResource(access, "appointment.confirm", resource) &&
            canAccessResource(access, "appointment.checkIn", resource) ? (
              <CombinedTransitionForm
                appointment={appointment}
                command="CONFIRM_AND_CHECK_IN"
                label={labels.confirmAndCheckIn}
                locale={locale}
                returnTo={returnTo}
              />
            ) : appointment.status === AppointmentStatus.CONFIRMED &&
              canAccessResource(access, "appointment.checkIn", resource) &&
              canAccessResource(access, "appointment.startService", resource) &&
              canClaimRoom ? (
              <CombinedTransitionForm
                appointment={appointment}
                command="CHECK_IN_AND_START"
                label={labels.checkInAndStart}
                locale={locale}
                returnTo={returnTo}
                rooms={compatibleRooms}
              />
            ) : appointment.status === AppointmentStatus.CHECKED_IN &&
              canAccessResource(access, "appointment.startService", resource) &&
              canClaimRoom ? (
              <StartServiceForm
                appointment={appointment}
                label={labels.startService}
                locale={locale}
                returnTo={returnTo}
                rooms={compatibleRooms}
              />
            ) : appointment.status === AppointmentStatus.CALLED ? (
              <>
                {canAccessResource(access, "appointment.callToRoom", resource) ? (
                  <form action={resendRoomMessageAction}>
                    <OperationFields
                      appointment={appointment}
                      locale={locale}
                      returnTo={returnTo}
                    />
                    <SubmitButton tone="secondary">{labels.sendAgain}</SubmitButton>
                  </form>
                ) : null}
                {canAccessResource(access, "room.assignment.change", resource) &&
                canClaimRoom &&
                canReleaseRoom ? (
                  <RoomOperationForm
                    action="change"
                    appointment={appointment}
                    label={labels.changeRoom}
                    locale={locale}
                    returnTo={returnTo}
                    rooms={compatibleRooms.filter((room) => room.id !== appointment.actualRoomId)}
                  />
                ) : null}
              </>
            ) : null}
            <Link
              className="button button-secondary"
              href={
                appointment.status === AppointmentStatus.CHECKED_IN
                  ? `/${locale}/customers/${appointment.customer.id}`
                  : viewHref
              }
            >
              {appointment.status === AppointmentStatus.IN_PROGRESS
                ? labels.addNote
                : appointment.status === AppointmentStatus.CHECKED_IN
                  ? labels.openPatient
                  : appointment.status === AppointmentStatus.CALLED
                    ? labels.view
                    : labels.rescheduleOrCancel}
            </Link>
          </div>
        </details>
      ) : null}
    </div>
  );
}

function OperationFields({
  appointment,
  locale,
  returnTo,
}: Readonly<{
  appointment: { id: string; version: number };
  locale: "ar" | "en";
  returnTo: string;
}>) {
  return (
    <>
      <input name="locale" type="hidden" value={locale} />
      <input name="appointmentId" type="hidden" value={appointment.id} />
      <input name="expectedVersion" type="hidden" value={appointment.version} />
      <input name="idempotencyKey" type="hidden" value={randomUUID()} />
      <input name="returnTo" type="hidden" value={returnTo} />
    </>
  );
}

function RoomOperationForm({
  action,
  appointment,
  label,
  locale,
  returnTo,
  rooms,
}: Readonly<{
  action: "call" | "change";
  appointment: { id: string; version: number };
  label: string;
  locale: "ar" | "en";
  returnTo: string;
  rooms: readonly OperationalRoom[];
}>) {
  return (
    <form
      action={action === "call" ? callAppointmentToRoomAction : changeAppointmentRoomAction}
      className="row-actions"
    >
      <OperationFields appointment={appointment} locale={locale} returnTo={returnTo} />
      <select aria-label={label} className="select" name="roomId" required>
        <option value="">{label}</option>
        {rooms.map((room) => (
          <option key={room.id} value={room.id}>
            {locale === "ar" ? room.nameAr : room.nameEn} ({room.availableCapacity})
          </option>
        ))}
      </select>
      <SubmitButton disabled={rooms.length === 0}>{label}</SubmitButton>
    </form>
  );
}

function StartServiceForm({
  appointment,
  label,
  locale,
  returnTo,
  rooms,
}: Readonly<{
  appointment: { id: string; version: number };
  label: string;
  locale: "ar" | "en";
  returnTo: string;
  rooms?: readonly OperationalRoom[] | undefined;
}>) {
  return (
    <form action={startAppointmentServiceAction} className="row-actions">
      <OperationFields appointment={appointment} locale={locale} returnTo={returnTo} />
      {rooms ? (
        <select aria-label={label} className="select" name="roomId" required>
          <option value="">{label}</option>
          {rooms.map((room) => (
            <option key={room.id} value={room.id}>
              {locale === "ar" ? room.nameAr : room.nameEn} ({room.availableCapacity})
            </option>
          ))}
        </select>
      ) : null}
      <SubmitButton disabled={rooms?.length === 0}>{label}</SubmitButton>
    </form>
  );
}

function TransitionForm({
  appointment,
  label,
  locale,
  returnTo,
  status,
}: Readonly<{
  appointment: { id: string; version: number };
  label: string;
  locale: "ar" | "en";
  returnTo: string;
  status: AppointmentStatus;
}>) {
  return (
    <form action={transitionAppointmentAction}>
      <OperationFields appointment={appointment} locale={locale} returnTo={returnTo} />
      <input name="toStatus" type="hidden" value={status} />
      <SubmitButton>{label}</SubmitButton>
    </form>
  );
}

function CombinedTransitionForm({
  appointment,
  command,
  label,
  locale,
  returnTo,
  rooms,
}: Readonly<{
  appointment: { id: string; version: number };
  command: "CHECK_IN_AND_START" | "CONFIRM_AND_CHECK_IN";
  label: string;
  locale: "ar" | "en";
  returnTo: string;
  rooms?: readonly OperationalRoom[] | undefined;
}>) {
  return (
    <form action={combinedAppointmentTransitionAction}>
      <OperationFields appointment={appointment} locale={locale} returnTo={returnTo} />
      <input name="command" type="hidden" value={command} />
      {rooms ? (
        <select aria-label={label} className="select" name="roomId" required>
          <option value="">{label}</option>
          {rooms.map((room) => (
            <option key={room.id} value={room.id}>
              {locale === "ar" ? room.nameAr : room.nameEn}
            </option>
          ))}
        </select>
      ) : null}
      <SubmitButton tone="secondary">{label}</SubmitButton>
    </form>
  );
}

function StatusMetric({
  active,
  href,
  label,
  value,
}: Readonly<{ active: boolean; href: string; label: string; value: number }>) {
  return (
    <div data-active={active}>
      <dt>
        <Link href={href}>{label}</Link>
      </dt>
      <dd>{value}</dd>
    </div>
  );
}

function ScheduleEmpty({
  canCreate,
  day,
  labels,
  locale,
}: Readonly<{
  canCreate: boolean;
  day: string;
  labels: TodayLabels;
  locale: "ar" | "en";
}>) {
  return (
    <div className="empty-state">
      <h2>{labels.noAppointments}</h2>
      <p>{labels.noAppointmentsHint}</p>
      {canCreate ? (
        <Link
          className="button"
          href={`/${locale}/schedule/calendar?day=${day}#create-appointment-title`}
        >
          {labels.newAppointment}
        </Link>
      ) : null}
    </div>
  );
}

type AttentionRow = Readonly<{ appointment: AppointmentRow; issue: string }>;

function attentionRows(
  appointments: readonly AppointmentRow[],
  providers: readonly ProviderOption[],
  day: string,
  timezone: string,
  locale: "ar" | "en",
): AttentionRow[] {
  const labels = todayLabels[locale];
  const now = new Date();
  const providerMap = new Map(providers.map((provider) => [provider.id, provider]));
  return appointments.flatMap((appointment) => {
    const issues: string[] = [];
    if (appointment.status === AppointmentStatus.PENDING) issues.push(labels.pendingConfirmation);
    if (appointment.status === AppointmentStatus.CONFIRMED && appointment.startsAt < now)
      issues.push(labels.lateCustomer);
    if (!appointment.provider.isDoctor) issues.push(labels.unassignedDoctor);
    if (appointment.conflictIndicator === "MISSING_RESOURCE") issues.push(labels.missingResource);
    if (appointment.actualRoom?.status === "MAINTENANCE") issues.push(labels.roomUnavailable);
    if (appointment.resourceReservations.some(({ resource }) => resource.status === "MAINTENANCE"))
      issues.push(labels.resourceMaintenance);
    if (
      appointment.messages[0]?.status === "FAILED" ||
      appointment.messages[0]?.status === "DEAD_LETTER"
    )
      issues.push(labels.failedReminder);
    if (appointment.customer.contacts.length === 0) issues.push(labels.invalidContact);
    const provider = providerMap.get(appointment.providerId);
    if (provider && providerIsOff(provider, day, timezone)) issues.push(labels.providerAbsent);
    return issues.map((issue) => ({ appointment, issue }));
  });
}

function rowResource(appointment: AppointmentRow) {
  return { branchId: appointment.branchId, staffProfileId: appointment.providerId };
}

function countStatus(rows: readonly AppointmentRow[], status: AppointmentStatus): number {
  return rows.filter((row) => row.status === status).length;
}
function providerName(appointment: AppointmentRow, locale: "ar" | "en"): string {
  return locale === "ar" ? appointment.provider.displayNameAr : appointment.provider.displayNameEn;
}
function appointmentRoomName(appointment: AppointmentRow, locale: "ar" | "en"): string {
  const room = appointment.actualRoom ?? appointment.room;
  return room ? (locale === "ar" ? room.nameAr : room.nameEn) : "";
}
function reminderLabel(appointment: AppointmentRow, labels: TodayLabels): string {
  const status = appointment.messages[0]?.status;
  return status ? status.replaceAll("_", " ") : labels.notSent;
}
function formatTime(date: Date, timezone: string, locale: "ar" | "en"): string {
  return date.toLocaleTimeString(locale === "ar" ? "ar-JO" : "en-JO", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: timezone,
  });
}
function formatMinute(minute: number): string {
  return `${Math.floor(minute / 60)
    .toString()
    .padStart(2, "0")}:${(minute % 60).toString().padStart(2, "0")}`;
}
function providerHours(provider: ProviderOption, day: string): string {
  const weekday = ["SUNDAY", "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"][
    new Date(`${day}T00:00:00Z`).getUTCDay()
  ];
  return provider.availabilityRules
    .filter((rule) => rule.weekday === weekday)
    .map((rule) => `${formatMinute(rule.startMinuteLocal)}–${formatMinute(rule.endMinuteLocal)}`)
    .join(", ");
}
function providerBreaks(provider: ProviderOption, day: string): string {
  const weekday = ["SUNDAY", "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"][
    new Date(`${day}T00:00:00Z`).getUTCDay()
  ];
  return provider.breaks
    .filter((rule) => rule.weekday === weekday)
    .map(
      (rule) =>
        `${formatMinute(rule.startMinuteLocal)}–${formatMinute(rule.endMinuteLocal)}${rule.label ? ` (${rule.label})` : ""}`,
    )
    .join(", ");
}
function providerIsOff(provider: ProviderOption, day: string, timezone: string): boolean {
  const range = utcRangeForLocalDate(day, timezone);
  return provider.timeOffEntries.some(
    (entry) => entry.startsAt < range.endsAt && entry.endsAt > range.startsAt,
  );
}
function text(value: string | string[] | undefined): string | undefined {
  return typeof value === "string" && value ? value : undefined;
}
function numberQuery(value: string | string[] | undefined): number {
  const parsed = Number(text(value));
  return Number.isFinite(parsed) ? parsed : 0;
}
function validDate(value: string | undefined): string | undefined {
  return value && /^\d{4}-\d{2}-\d{2}$/u.test(value) ? value : undefined;
}
function todayView(
  value: string | undefined,
): "attention" | "kanban" | "list" | "provider" | "table" {
  return value === "attention" || value === "kanban" || value === "list" || value === "provider"
    ? value
    : "table";
}
function localDay(date: Date, timezone: string): string {
  return new Intl.DateTimeFormat("en-CA", {
    day: "2-digit",
    month: "2-digit",
    timeZone: timezone,
    year: "numeric",
  }).format(date);
}
function distinct<T extends { id: string }>(values: readonly T[]): T[] {
  return [...new Map(values.map((value) => [value.id, value])).values()];
}
function todayHref(
  locale: "ar" | "en",
  values: Readonly<Record<string, string | undefined>>,
): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) if (value) query.set(key, value);
  const serialized = query.toString();
  return `/${locale}/schedule/today${serialized ? `?${serialized}` : ""}`;
}

const todayLabels = {
  en: {
    administrativeNote: "Optional Administrative Note",
    addNote: "Add Note",
    allBranches: "All branches",
    allProviders: "All Doctors",
    allServices: "All services",
    allStatuses: "All statuses",
    appointments: "appointments",
    appointmentViews: "Appointment views",
    breaks: "Breaks",
    bulkResult: (succeeded: number, failed: number) =>
      `${succeeded} confirmed; ${failed} could not be confirmed.`,
    checkIn: "Check In",
    checkInAndStart: "Check In & Start",
    callPatient: "Call Patient",
    callToRoom: "Call to Room",
    changeRoom: "Change Room",
    close: "Close",
    collapseAll: "Collapse All",
    compatibleRoom: "Compatible Room",
    complete: "Service Done",
    confirm: "Confirm",
    confirmAndCheckIn: "Confirm & Check In",
    confirmSelected: "Confirm Selected",
    customer: "Patient",
    date: "Date",
    failedReminder: "Failed reminder",
    doctorNote: "Doctor Note / Feedback",
    doctorOnLeave: "Doctor is on leave today.",
    expandAll: "Expand All",
    invalidContact: "Invalid patient contact",
    issue: "Issue",
    lateCustomer: "Patient late",
    missingResource: "Missing resource",
    more: "More actions",
    newAppointment: "New Appointment",
    nextAppointment: "Next Appointment",
    nextAction: "Next Action",
    noAppointments: "No appointments scheduled for this day.",
    noAppointmentsHint: "Create an appointment or change the current filters.",
    noAttention: "No appointments need attention.",
    noCheckedInPatient: "No eligible checked-in Patient.",
    noProviderAppointments: "No appointments scheduled for this Doctor.",
    noProviders: "No configured active Doctors.",
    none: "None",
    notConfigured: "Not configured",
    notSent: "Not sent",
    notScheduled: "Doctor is not scheduled to work today.",
    open: "Open",
    openPatient: "Open Patient",
    pageTitle: "Appointments",
    pendingConfirmation: "Pending confirmation",
    provider: "Doctor",
    providerAbsent: "Doctor absent",
    providerHint: "Configured active Doctors and their appointments in scheduled-time order.",
    recommendedAction: "Recommended Action",
    reminder: "Reminder Status",
    reset: "Reset filters",
    rescheduleOrCancel: "Reschedule or cancel",
    resourceMaintenance: "Resource under maintenance",
    roomUnavailable: "Assigned room is unavailable",
    resources: "Room",
    search: "Patient Search",
    searchHint: "Search name, telephone, or reference",
    sendAgain: "Send Room Message Again",
    select: "Select",
    selectDoctor: "Select Doctor",
    selectRoom: "Select room",
    scheduledTime: "Scheduled Time",
    service: "Service",
    sortedHint: "Appointments remain in scheduled-time order.",
    startService: "Start Service",
    status: "Status",
    time: "Time",
    timeOff: "Time off",
    totalAppointments: "Total Appointments",
    totalToday: "Total Today",
    unassignedDoctor: "Unassigned Doctor",
    unassignedAppointments: "Unassigned Appointments",
    view: "View",
    views: {
      attention: "Needs Attention",
      kanban: "Kanban",
      list: "List",
      provider: "By Doctor",
      table: "Table",
    },
    working: "Working",
    workingHours: "Working hours",
    workingStatus: "Working status",
    waitingSince: "Waiting Since",
  },
  ar: {
    administrativeNote: "ملاحظة إدارية اختيارية",
    addNote: "إضافة ملاحظة",
    allBranches: "كل الفروع",
    allProviders: "كل الأطباء",
    allServices: "كل الخدمات",
    allStatuses: "كل الحالات",
    appointments: "مواعيد",
    appointmentViews: "طرق عرض المواعيد",
    breaks: "فترات الاستراحة",
    bulkResult: (succeeded: number, failed: number) =>
      `تم تأكيد ${succeeded}؛ وتعذر تأكيد ${failed}.`,
    checkIn: "تسجيل الوصول",
    checkInAndStart: "تسجيل الوصول وبدء الخدمة",
    callPatient: "استدعاء المريض",
    callToRoom: "استدعاء إلى الغرفة",
    changeRoom: "تغيير الغرفة",
    close: "إغلاق",
    collapseAll: "طي الكل",
    compatibleRoom: "الغرفة المتوافقة",
    complete: "إتمام الخدمة",
    confirm: "تأكيد",
    confirmAndCheckIn: "تأكيد وتسجيل الوصول",
    confirmSelected: "تأكيد المحدد",
    customer: "المريض",
    date: "التاريخ",
    failedReminder: "فشل التذكير",
    doctorNote: "ملاحظة الطبيب / التقييم",
    doctorOnLeave: "الطبيب في إجازة اليوم.",
    expandAll: "توسيع الكل",
    invalidContact: "بيانات اتصال المريض غير صالحة",
    issue: "المشكلة",
    lateCustomer: "تأخر المريض",
    missingResource: "مورد غير معيّن",
    more: "إجراءات أخرى",
    newAppointment: "موعد جديد",
    nextAppointment: "الموعد التالي",
    nextAction: "الإجراء التالي",
    noAppointments: "لا توجد مواعيد مجدولة لهذا اليوم.",
    noAppointmentsHint: "أنشئ موعداً أو غيّر عوامل التصفية الحالية.",
    noAttention: "لا توجد مواعيد تحتاج إلى متابعة.",
    noCheckedInPatient: "لا يوجد مريض مؤهل تم تسجيل وصوله.",
    noProviderAppointments: "لا توجد مواعيد مجدولة لهذا الطبيب.",
    noProviders: "لا يوجد أطباء نشطون مهيؤون.",
    none: "لا يوجد",
    notConfigured: "غير مهيأ",
    notSent: "لم يُرسل",
    notScheduled: "الطبيب غير مجدول للعمل اليوم.",
    open: "فتح",
    openPatient: "فتح ملف المريض",
    pageTitle: "المواعيد",
    pendingConfirmation: "بانتظار التأكيد",
    provider: "الطبيب",
    providerAbsent: "الطبيب غائب",
    providerHint: "الأطباء النشطون ومواعيدهم مرتبة حسب الوقت المجدول.",
    recommendedAction: "الإجراء المقترح",
    reminder: "حالة التذكير",
    reset: "إعادة ضبط التصفية",
    rescheduleOrCancel: "إعادة الجدولة أو الإلغاء",
    resourceMaintenance: "المورد تحت الصيانة",
    roomUnavailable: "الغرفة المعينة غير متاحة",
    resources: "الغرفة",
    search: "بحث المريض",
    searchHint: "ابحث بالاسم أو الهاتف أو المرجع",
    sendAgain: "إرسال رسالة الغرفة مرة أخرى",
    select: "تحديد",
    selectDoctor: "اختر الطبيب",
    selectRoom: "اختر الغرفة",
    scheduledTime: "الوقت المجدول",
    service: "الخدمة",
    sortedHint: "تبقى المواعيد مرتبة حسب الوقت المجدول.",
    startService: "بدء الخدمة",
    status: "الحالة",
    time: "الوقت",
    timeOff: "إجازة",
    totalAppointments: "إجمالي المواعيد",
    totalToday: "إجمالي اليوم",
    unassignedDoctor: "طبيب غير معيّن",
    unassignedAppointments: "المواعيد غير المعيّنة",
    view: "عرض",
    views: {
      attention: "تحتاج إلى متابعة",
      kanban: "كانبان",
      list: "قائمة",
      provider: "حسب الطبيب",
      table: "جدول",
    },
    working: "يعمل",
    workingHours: "ساعات العمل",
    workingStatus: "حالة العمل",
    waitingSince: "وقت بدء الانتظار",
  },
} as const;

type TodayLabels = (typeof todayLabels)[keyof typeof todayLabels];
