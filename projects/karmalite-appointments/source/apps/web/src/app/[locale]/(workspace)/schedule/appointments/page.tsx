import { randomUUID } from "node:crypto";

import { canAccessResource } from "@jormall/auth/tenant-policy";
import { isSupportedLocale } from "@jormall/contracts/locales";
import { AppointmentSource, AppointmentStatus } from "@jormall/db/generated/enums";
import Link from "next/link";
import { notFound } from "next/navigation";
import { z } from "zod";

import { ScheduleTabs } from "../../../../../components/workspace-tabs";
import { SubmitButton } from "../../../../../components/submit-button";
import { appointmentFiltersResetHref } from "../../../../../lib/appointment-filter-href";
import { phaseTwoLabel } from "../../../../../messages/phase-two";
import {
  crmAppointmentRepository,
  requirePageCollectionPermission,
} from "../../../../../server/identity";
import AppointmentPage from "../../../dashboard/appointments/[appointmentId]/page";
import { bulkConfirmAppointmentsAction, transitionAppointmentAction } from "../../../actions";

const querySchema = z
  .object({
    appointment: z.uuid().optional(),
    branchId: z.uuid().optional(),
    conflict: z.enum(["missing-resource"]).optional(),
    createdBy: z.enum(["employee", "chatbot"]).optional(),
    day: z.iso.date().optional(),
    dateFrom: z.iso.date().optional(),
    dateTo: z.iso.date().optional(),
    error: z.string().max(100).optional(),
    notice: z.string().max(100).optional(),
    page: z.coerce.number().int().min(1).max(10_000).catch(1),
    providerId: z.uuid().optional(),
    q: z.string().trim().max(100).catch(""),
    reminder: z.enum(["failed", "sent", "not-sent"]).optional(),
    resourceId: z.uuid().optional(),
    serviceId: z.uuid().optional(),
    sort: z.enum(["oldest", "newest"]).catch("oldest"),
    source: z.enum(AppointmentSource).optional(),
    status: z.enum(AppointmentStatus).optional(),
    tab: z.enum(["upcoming", "past", "exceptions", "all"]).catch("upcoming"),
  })
  .strict();

export default async function AppointmentsPage({
  params,
  searchParams,
}: Readonly<{
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}>) {
  const [{ locale }, rawQuery] = await Promise.all([params, searchParams]);
  if (!isSupportedLocale(locale)) notFound();
  const parsedQuery = querySchema.safeParse(rawQuery);
  const query = parsedQuery.success ? parsedQuery.data : querySchema.parse({});
  const access = await requirePageCollectionPermission(locale, "appointments.read");
  const filters = {
    ...(access.activeBranchId ? { branchId: access.activeBranchId } : {}),
    ...(query.dateFrom || query.day ? { dateFrom: query.dateFrom ?? query.day } : {}),
    ...(query.dateTo || query.day ? { dateTo: query.dateTo ?? query.day } : {}),
    ...(query.providerId ? { providerId: query.providerId } : {}),
    ...(query.q ? { q: query.q } : {}),
    ...(query.resourceId ? { resourceId: query.resourceId } : {}),
    ...(query.serviceId ? { serviceId: query.serviceId } : {}),
    ...(query.source ? { source: query.source } : {}),
  };
  const canCreate =
    canAccessResource(access, "appointments.create") && canAccessResource(access, "customers.read");
  const [appointments, options] = await Promise.all([
    crmAppointmentRepository.listAppointments(access, filters),
    canCreate
      ? crmAppointmentRepository.listAppointmentFormOptions(access)
      : Promise.resolve({ branches: [], customers: [], providers: [], services: [] }),
  ]);
  const filterOptions = canCreate
    ? options
    : {
        branches: [...new Map(appointments.map(({ branch }) => [branch.id, branch])).values()],
        customers: [],
        providers: [
          ...new Map(appointments.map(({ provider }) => [provider.id, provider])).values(),
        ],
        services: [...new Map(appointments.map(({ service }) => [service.id, service])).values()],
      };
  const now = new Date();
  const tabFiltered = appointments.filter((appointment) => {
    if (query.tab === "all") return true;
    if (query.tab === "exceptions") {
      return (
        appointment.status === AppointmentStatus.CANCELLED ||
        appointment.status === AppointmentStatus.NO_SHOW
      );
    }
    if (query.tab === "past") {
      return (
        appointment.startsAt < now &&
        appointment.status !== AppointmentStatus.CANCELLED &&
        appointment.status !== AppointmentStatus.NO_SHOW
      );
    }
    return (
      appointment.endsAt >= now &&
      appointment.status !== AppointmentStatus.CANCELLED &&
      appointment.status !== AppointmentStatus.NO_SHOW
    );
  });
  const statusFiltered = query.status
    ? tabFiltered.filter(({ status }) => status === query.status)
    : tabFiltered;
  const conflictFiltered = query.conflict
    ? statusFiltered.filter(({ conflictIndicator }) => conflictIndicator === "MISSING_RESOURCE")
    : statusFiltered;
  // The tenant-scoped repository already searches customer contacts and references.
  // Filtering again without contact fields discarded valid telephone matches.
  const matching = conflictFiltered.filter((appointment) => {
    const messageStatus = appointment.messages[0]?.status;
    const reminderMatches =
      !query.reminder ||
      (query.reminder === "failed" &&
        (messageStatus === "FAILED" || messageStatus === "DEAD_LETTER")) ||
      (query.reminder === "sent" && (messageStatus === "SENT" || messageStatus === "DELIVERED")) ||
      (query.reminder === "not-sent" && !messageStatus);
    const aiSources: readonly AppointmentSource[] = [
      AppointmentSource.VOICE_AI,
      AppointmentSource.WEBSITE_AI,
      AppointmentSource.WHATSAPP_AI,
    ];
    const aiSource = aiSources.includes(appointment.source);
    const creatorMatches =
      !query.createdBy ||
      (query.createdBy === "chatbot"
        ? aiSource
        : appointment.source === AppointmentSource.STAFF && appointment.createdBy !== null);
    return reminderMatches && creatorMatches;
  });
  const sorted = query.sort === "newest" ? matching.toReversed() : matching;
  const pageSize = 20;
  const pageCount = Math.max(1, Math.ceil(sorted.length / pageSize));
  const currentPage = Math.min(query.page, pageCount);
  const visible = sorted.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const listParameters = new URLSearchParams();
  for (const [key, filterValue] of Object.entries({
    conflict: query.conflict,
    createdBy: query.createdBy,
    dateFrom: query.dateFrom,
    dateTo: query.dateTo,
    providerId: query.providerId,
    q: query.q || undefined,
    reminder: query.reminder,
    resourceId: query.resourceId,
    serviceId: query.serviceId,
    sort: query.sort === "oldest" ? undefined : query.sort,
    source: query.source,
    status: query.status,
    tab: query.tab === "upcoming" ? undefined : query.tab,
  })) {
    if (filterValue) listParameters.set(key, filterValue);
  }
  const listHref = (changes: Readonly<Record<string, number | string | undefined>>) => {
    const parameters = new URLSearchParams(listParameters);
    for (const [key, nextValue] of Object.entries(changes)) {
      if (nextValue === undefined) parameters.delete(key);
      else parameters.set(key, String(nextValue));
    }
    const serialized = parameters.toString();
    return `/${locale}/schedule/appointments${serialized ? `?${serialized}` : ""}`;
  };
  const clearFiltersHref = appointmentFiltersResetHref(locale, query.tab);
  const advancedFilterCount = [
    query.createdBy,
    query.providerId,
    query.reminder,
    query.serviceId,
    query.sort === "newest" ? query.sort : undefined,
    query.source,
  ].filter(Boolean).length;
  const appointmentCounts = {
    all: appointments.length,
    checkedIn: appointments.filter(({ status }) => status === AppointmentStatus.CHECKED_IN).length,
    completed: appointments.filter(({ status }) => status === AppointmentStatus.COMPLETED).length,
    confirmed: appointments.filter(({ status }) => status === AppointmentStatus.CONFIRMED).length,
    exceptions: appointments.filter(
      ({ status }) =>
        status === AppointmentStatus.CANCELLED || status === AppointmentStatus.NO_SHOW,
    ).length,
    inService: appointments.filter(({ status }) => status === AppointmentStatus.IN_PROGRESS).length,
    pending: appointments.filter(({ status }) => status === AppointmentStatus.PENDING).length,
  };
  const canBulkConfirmVisible = visible.some(
    (appointment) =>
      appointment.status === AppointmentStatus.PENDING &&
      canAccessResource(access, "appointment.bulkConfirm", {
        branchId: appointment.branchId,
        staffProfileId: appointment.providerId,
      }),
  );
  const labels =
    locale === "ar"
      ? {
          action: "\u0627\u0644\u0625\u062c\u0631\u0627\u0621",
          bookingSource: "\u0645\u0635\u062f\u0631 \u0627\u0644\u062d\u062c\u0632",
          categories: "\u0641\u0626\u0627\u062a \u0627\u0644\u0645\u0648\u0627\u0639\u064a\u062f",
          confirm: "\u062a\u0623\u0643\u064a\u062f",
          confirmSelected: "\u062a\u0623\u0643\u064a\u062f \u0627\u0644\u0645\u062d\u062f\u062f",
          createdBy: "\u0623\u0646\u0634\u0623\u0647",
          endTime: "\u0648\u0642\u062a \u0627\u0644\u0627\u0646\u062a\u0647\u0627\u0621",
          open: "\u0641\u062a\u062d",
          select: "\u062a\u062d\u062f\u064a\u062f",
          startTime: "\u0648\u0642\u062a \u0627\u0644\u0628\u062f\u0621",
          tabs: {
            all: "\u0627\u0644\u0643\u0644",
            exceptions:
              "\u0627\u0644\u0645\u0644\u063a\u0627\u0629 \u0648\u0639\u062f\u0645 \u0627\u0644\u062d\u0636\u0648\u0631",
            past: "\u0627\u0644\u0633\u0627\u0628\u0642\u0629",
            upcoming: "\u0627\u0644\u0642\u0627\u062f\u0645\u0629",
          },
          all: "الكل",
          allAppointments: "جميع المواعيد",
          appointments: "المواعيد",
          checkedIn: "تم تسجيل الوصول",
          branch: "الفرع",
          customer: "المريض",
          date: "التاريخ",
          dateAndTime: "التاريخ والوقت",
          exceptions: "الملغاة وعدم الحضور",
          filters: "تصفية المواعيد",
          next: "التالي",
          noAppointments: "لا توجد مواعيد تطابق عوامل التصفية المحددة.",
          moreFilters: "المزيد من عوامل التصفية",
          previous: "السابق",
          removeAllFilters: "إزالة جميع عوامل التصفية",
          provider: "الطبيب",
          results: "نتيجة",
          room: "الغرفة",
          search: "ابحث عن مريض أو هاتف أو مرجع",
          service: "الخدمة",
          sort: "الترتيب",
          source: "المصدر",
          status: "الحالة",
          inService: "قيد الخدمة",
        }
      : {
          action: "Action",
          bookingSource: "Booking Source",
          categories: "Appointment categories",
          confirm: "Confirm",
          confirmSelected: "Confirm Selected",
          createdBy: "Created By",
          endTime: "End Time",
          open: "Open",
          select: "Select",
          startTime: "Start Time",
          tabs: {
            all: "All",
            exceptions: "Cancelled & No-show",
            past: "Past",
            upcoming: "Upcoming",
          },
          all: "All",
          allAppointments: "All appointments",
          appointments: "Appointments",
          checkedIn: "Checked in",
          branch: "Branch",
          customer: "Patient",
          date: "Date",
          dateAndTime: "Date & time",
          exceptions: "Cancelled / no-show",
          filters: "Filter appointments",
          next: "Next",
          noAppointments: "No appointments match the selected filters.",
          moreFilters: "More filters",
          previous: "Previous",
          removeAllFilters: "Remove all filters",
          provider: "Doctor",
          results: "results",
          room: "Room",
          search: "Search patient, phone, or reference",
          service: "Service",
          sort: "Sort",
          source: "Source",
          status: "Status",
          inService: "In service",
        };

  return (
    <section className="page-stack" aria-labelledby="appointments-title">
      <ScheduleTabs locale={locale} />
      <header className="page-heading">
        <p className="eyebrow">{locale === "ar" ? "الجدول" : "Schedule"}</p>
        <h1 id="appointments-title">{labels.appointments}</h1>
        <p className="page-description">
          {locale === "ar"
            ? "ابحث وصفِّ المواعيد مع الحفاظ على نطاق الفروع ومقدمي الخدمات المسموح لك به."
            : "Search and filter appointments within your permitted branch and provider scope."}
        </p>
      </header>

      <div
        className="appointments-kpi-grid"
        aria-label={locale === "ar" ? "ملخص المواعيد" : "Appointment summary"}
      >
        <AppointmentMetricCard
          href={listHref({ page: 1, status: undefined, tab: "all" })}
          label={labels.allAppointments}
          value={appointmentCounts.all}
        />
        <AppointmentMetricCard
          href={listHref({ page: 1, status: AppointmentStatus.PENDING, tab: "all" })}
          label={phaseTwoLabel(locale, AppointmentStatus.PENDING)}
          tone="attention"
          value={appointmentCounts.pending}
        />
        <AppointmentMetricCard
          href={listHref({ page: 1, status: AppointmentStatus.CONFIRMED, tab: "all" })}
          label={phaseTwoLabel(locale, AppointmentStatus.CONFIRMED)}
          value={appointmentCounts.confirmed}
        />
        <AppointmentMetricCard
          href={listHref({ page: 1, status: AppointmentStatus.CHECKED_IN, tab: "all" })}
          label={labels.checkedIn}
          value={appointmentCounts.checkedIn}
        />
        <AppointmentMetricCard
          href={listHref({ page: 1, status: AppointmentStatus.IN_PROGRESS, tab: "all" })}
          label={labels.inService}
          value={appointmentCounts.inService}
        />
        <AppointmentMetricCard
          href={listHref({ page: 1, status: AppointmentStatus.COMPLETED, tab: "all" })}
          label={phaseTwoLabel(locale, AppointmentStatus.COMPLETED)}
          value={appointmentCounts.completed}
        />
        <AppointmentMetricCard
          href={listHref({ page: 1, status: undefined, tab: "exceptions" })}
          label={labels.exceptions}
          tone="critical"
          value={appointmentCounts.exceptions}
        />
      </div>

      <nav className="appointment-category-tabs" aria-label={labels.categories}>
        {(["upcoming", "past", "exceptions", "all"] as const).map((tab) => (
          <Link
            aria-current={query.tab === tab ? "page" : undefined}
            href={listHref({ page: 1, tab })}
            key={tab}
          >
            {labels.tabs[tab]}
          </Link>
        ))}
      </nav>

      <nav
        className="appointment-status-filters"
        aria-label={locale === "ar" ? "تصفية حسب الحالة" : "Filter by status"}
      >
        <Link
          aria-current={!query.status ? "page" : undefined}
          href={listHref({ page: 1, status: undefined })}
        >
          {labels.all}
        </Link>
        {Object.values(AppointmentStatus).map((status) => (
          <Link
            aria-current={query.status === status ? "page" : undefined}
            href={listHref({ page: 1, status, tab: "all" })}
            key={status}
          >
            {phaseTwoLabel(locale, status)}
          </Link>
        ))}
      </nav>

      <form
        action={`/${locale}/schedule/appointments`}
        className="appointment-filter-panel"
        method="get"
      >
        {query.tab !== "upcoming" ? <input name="tab" type="hidden" value={query.tab} /> : null}
        {query.status ? <input name="status" type="hidden" value={query.status} /> : null}
        <label className="field appointment-filter-search">
          <span className="field-label">{locale === "ar" ? "بحث" : "Search"}</span>
          <input
            className="input"
            defaultValue={query.q}
            name="q"
            placeholder={labels.search}
            type="search"
          />
        </label>
        <label className="field">
          <span className="field-label">{locale === "ar" ? "من تاريخ" : "Date from"}</span>
          <input
            className="input"
            defaultValue={query.dateFrom ?? query.day ?? ""}
            name="dateFrom"
            type="date"
          />
        </label>
        <input
          aria-hidden="true"
          name="day"
          type="hidden"
          value={query.dateFrom ?? query.day ?? ""}
        />
        <label className="field">
          <span className="field-label">{locale === "ar" ? "إلى تاريخ" : "Date to"}</span>
          <input
            className="input"
            defaultValue={query.dateTo ?? query.day ?? ""}
            name="dateTo"
            type="date"
          />
        </label>

        <div className="appointment-filter-actions">
          <button className="button button-primary" type="submit">
            {locale === "ar" ? "تطبيق التصفية" : "Apply filters"}
          </button>
          <Link className="button button-secondary" href={clearFiltersHref}>
            {labels.removeAllFilters}
          </Link>
        </div>

        <details className="appointment-advanced-filters" open={advancedFilterCount > 0}>
          <summary>
            {labels.moreFilters}
            {advancedFilterCount > 0 ? <span>{advancedFilterCount}</span> : null}
          </summary>
          <div className="appointment-advanced-filter-grid">
            <label className="field">
              <span className="field-label">{labels.service}</span>
              <select className="select" defaultValue={query.serviceId ?? ""} name="serviceId">
                <option value="">{labels.all}</option>
                {filterOptions.services.map((service) => (
                  <option key={service.id} value={service.id}>
                    {locale === "ar" ? service.nameAr : service.nameEn}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span className="field-label">{labels.provider}</span>
              <select className="select" defaultValue={query.providerId ?? ""} name="providerId">
                <option value="">{labels.all}</option>
                {filterOptions.providers.map((provider) => (
                  <option key={provider.id} value={provider.id}>
                    {locale === "ar" ? provider.displayNameAr : provider.displayNameEn}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span className="field-label">{labels.source}</span>
              <select className="select" defaultValue={query.source ?? ""} name="source">
                <option value="">{labels.all}</option>
                {Object.values(AppointmentSource).map((source) => (
                  <option key={source} value={source}>
                    {source.replaceAll("_", " ")}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span className="field-label">
                {locale === "ar" ? "حالة التذكير" : "Reminder status"}
              </span>
              <select className="select" defaultValue={query.reminder ?? ""} name="reminder">
                <option value="">{labels.all}</option>
                <option value="failed">{locale === "ar" ? "فشل" : "Failed"}</option>
                <option value="sent">{locale === "ar" ? "تم الإرسال" : "Sent"}</option>
                <option value="not-sent">{locale === "ar" ? "لم يُرسل" : "Not sent"}</option>
              </select>
            </label>
            <label className="field">
              <span className="field-label">{locale === "ar" ? "المنشئ" : "Created by"}</span>
              <select className="select" defaultValue={query.createdBy ?? ""} name="createdBy">
                <option value="">{labels.all}</option>
                <option value="employee">{locale === "ar" ? "الموظف" : "Employee"}</option>
                <option value="chatbot">{locale === "ar" ? "المساعد الآلي" : "Chatbot"}</option>
              </select>
            </label>
            <label className="field">
              <span className="field-label">{labels.sort}</span>
              <select className="select" defaultValue={query.sort} name="sort">
                <option value="oldest">{locale === "ar" ? "الأقدم أولاً" : "Oldest first"}</option>
                <option value="newest">{locale === "ar" ? "الأحدث أولاً" : "Newest first"}</option>
              </select>
            </label>
          </div>
        </details>
      </form>
      <section className="appointment-table-card" aria-label={labels.appointments}>
        <header className="appointment-table-toolbar">
          <p>
            <strong>{sorted.length}</strong> {labels.results}
          </p>
          {canBulkConfirmVisible ? (
            <form action={bulkConfirmAppointmentsAction} id="appointments-bulk-confirm">
              <input name="locale" type="hidden" value={locale} />
              <input name="returnTo" type="hidden" value={listHref({ page: currentPage })} />
              <SubmitButton>{labels.confirmSelected}</SubmitButton>
            </form>
          ) : null}
        </header>
        <div className="table-wrap appointment-table-wrap">
          <table className="appointment-table">
            <thead>
              <tr>
                <th>
                  <span className="sr-only">{labels.select}</span>
                </th>
                <th>{labels.dateAndTime}</th>
                <th>{labels.customer}</th>
                <th>{labels.service}</th>
                <th>{labels.provider}</th>
                <th>{labels.room}</th>
                <th>{labels.status}</th>
                <th className="appointment-secondary-column">{labels.bookingSource}</th>
                <th className="appointment-secondary-column">
                  {locale === "ar" ? "حالة التذكير" : "Reminder Status"}
                </th>
                <th>{labels.action}</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((appointment) => (
                <tr key={appointment.id}>
                  <td>
                    {appointment.status === AppointmentStatus.PENDING &&
                    canAccessResource(access, "appointment.confirm", {
                      branchId: appointment.branchId,
                      staffProfileId: appointment.providerId,
                    }) &&
                    canAccessResource(access, "appointment.bulkConfirm", {
                      branchId: appointment.branchId,
                      staffProfileId: appointment.providerId,
                    }) ? (
                      <input
                        aria-label={`${labels.select} ${appointment.customer.displayName}`}
                        form="appointments-bulk-confirm"
                        name="appointments"
                        type="checkbox"
                        value={`${appointment.id}:${appointment.version}`}
                      />
                    ) : null}
                  </td>
                  <td className="appointment-date-cell">
                    <strong>
                      {appointment.startsAt.toLocaleDateString(
                        locale === "ar" ? "ar-JO" : "en-JO",
                        {
                          day: "numeric",
                          month: "short",
                          timeZone: appointment.branch.timezone,
                        },
                      )}
                    </strong>
                    <span>
                      {formatRegisterTime(
                        appointment.startsAt,
                        appointment.branch.timezone,
                        locale,
                      )}
                    </span>
                  </td>
                  <td className="appointment-patient-cell">
                    <Link href={listHref({ appointment: appointment.id, page: currentPage })}>
                      <strong>{appointment.customer.displayName}</strong>
                      <small>{appointment.referenceCode}</small>
                    </Link>
                  </td>
                  <td>
                    {locale === "ar" ? appointment.service.nameAr : appointment.service.nameEn}
                  </td>
                  <td>
                    {locale === "ar"
                      ? appointment.provider.displayNameAr
                      : appointment.provider.displayNameEn}
                  </td>
                  <td>
                    {(appointment.actualRoom ?? appointment.room)
                      ? locale === "ar"
                        ? (appointment.actualRoom ?? appointment.room)?.nameAr
                        : (appointment.actualRoom ?? appointment.room)?.nameEn
                      : "—"}
                  </td>
                  <td>
                    <span className="product-status" data-status={appointment.status.toLowerCase()}>
                      {phaseTwoLabel(locale, appointment.status)}
                    </span>
                  </td>
                  <td className="appointment-secondary-column">
                    {appointment.source.replaceAll("_", " ")}
                  </td>
                  <td className="appointment-secondary-column">
                    {appointment.messages[0]?.status?.replaceAll("_", " ") ??
                      (locale === "ar" ? "لم يُرسل" : "Not sent")}
                  </td>
                  <td>
                    {appointment.status === AppointmentStatus.PENDING &&
                    canAccessResource(access, "appointment.confirm", {
                      branchId: appointment.branchId,
                      staffProfileId: appointment.providerId,
                    }) ? (
                      <form action={transitionAppointmentAction}>
                        <input name="locale" type="hidden" value={locale} />
                        <input name="appointmentId" type="hidden" value={appointment.id} />
                        <input name="expectedVersion" type="hidden" value={appointment.version} />
                        <input name="idempotencyKey" type="hidden" value={randomUUID()} />
                        <input
                          name="returnTo"
                          type="hidden"
                          value={listHref({ page: currentPage })}
                        />
                        <input name="toStatus" type="hidden" value={AppointmentStatus.CONFIRMED} />
                        <SubmitButton>{labels.confirm}</SubmitButton>
                      </form>
                    ) : (
                      <Link
                        className="button button-secondary"
                        href={listHref({ appointment: appointment.id, page: currentPage })}
                      >
                        {labels.open}
                      </Link>
                    )}
                  </td>
                </tr>
              ))}
              {!visible.length ? (
                <tr>
                  <td className="appointment-empty-row" colSpan={10}>
                    {labels.noAppointments}
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        <nav
          aria-label={locale === "ar" ? "صفحات المواعيد" : "Appointment pages"}
          className="pagination appointment-pagination"
        >
          {currentPage > 1 ? (
            <Link href={listHref({ page: currentPage - 1 })}>{labels.previous}</Link>
          ) : (
            <span />
          )}
          <span>
            {currentPage} / {pageCount}
          </span>
          {currentPage < pageCount ? (
            <Link href={listHref({ page: currentPage + 1 })}>{labels.next}</Link>
          ) : (
            <span />
          )}
        </nav>
      </section>
      {query.appointment ? (
        <aside
          aria-label={locale === "ar" ? "تفاصيل الموعد" : "Appointment details"}
          className="appointment-drawer"
        >
          <Link className="drawer-close" href={listHref({ page: currentPage })}>
            {locale === "ar" ? "إغلاق" : "Close"}
          </Link>
          <AppointmentPage
            params={Promise.resolve({ appointmentId: query.appointment, locale })}
            searchParams={searchParams}
          />
        </aside>
      ) : null}
    </section>
  );
}

function AppointmentMetricCard({
  href,
  label,
  tone,
  value,
}: Readonly<{
  href: string;
  label: string;
  tone?: "attention" | "critical";
  value: number;
}>) {
  return (
    <Link className="appointment-metric-card" data-tone={tone} href={href}>
      <strong>{value}</strong>
      <span>{label}</span>
    </Link>
  );
}

function formatRegisterTime(date: Date, timezone: string, locale: "ar" | "en"): string {
  return date.toLocaleTimeString(locale === "ar" ? "ar-JO" : "en-JO", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: timezone,
  });
}
