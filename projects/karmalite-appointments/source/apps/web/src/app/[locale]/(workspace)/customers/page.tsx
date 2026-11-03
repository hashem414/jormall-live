import { canAccessResource } from "@jormall/auth/tenant-policy";
import { isSupportedLocale } from "@jormall/contracts/locales";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Feedback } from "../../../../components/feedback";
import { PatientDirectorySearch } from "../../../../components/patient-directory-search";
import { crmAppointmentRepository, requirePagePermission } from "../../../../server/identity";

export default async function PatientsPage({
  params,
  searchParams,
}: PageProps<"/[locale]/customers">) {
  const { locale } = await params;
  if (!isSupportedLocale(locale)) notFound();
  const query = await searchParams;
  const access = await requirePagePermission(locale, "patients.directory.read");
  const search = typeof query.q === "string" ? query.q.slice(0, 160) : "";
  const page = Math.max(1, Number(typeof query.page === "string" ? query.page : "1") || 1);
  const result = await crmAppointmentRepository.listPatients(access, {
    page,
    pageSize: 25,
    query: search,
  });
  const canBook = canAccessResource(access, "appointments.create");
  const appointmentDate = new Intl.DateTimeFormat(locale === "ar" ? "ar-JO" : "en-JO", {
    dateStyle: "medium",
    timeZone: "Asia/Amman",
  });
  const now = new Date();
  return (
    <section
      className="page-stack product-directory patients-directory"
      aria-labelledby="patients-title"
    >
      <header className="page-heading">
        <div>
          <p className="eyebrow">Karmalite</p>
          <h1 id="patients-title">{locale === "ar" ? "المرضى" : "Patients"}</h1>
          <p className="page-description">
            {locale === "ar"
              ? "دليل المرضى ومعلومات الاتصال المصرح بها."
              : "Patient directory and authorized contact information."}
          </p>
        </div>
        {canBook ? (
          <Link className="button" href={`/${locale}/schedule/calendar#create-appointment-title`}>
            {locale === "ar" ? "موعد جديد" : "New appointment"}
          </Link>
        ) : null}
      </header>
      <Feedback
        error={typeof query.error === "string" ? query.error : undefined}
        locale={locale}
        notice={typeof query.notice === "string" ? query.notice : undefined}
      />
      <PatientDirectorySearch initialValue={search} locale={locale} />
      <div className="table-wrap">
        <table>
          <caption className="sr-only">
            {locale === "ar" ? "دليل المرضى" : "Patient directory"}
          </caption>
          <thead>
            <tr>
              <th>{locale === "ar" ? "رقم المريض" : "Patient ID"}</th>
              <th>{locale === "ar" ? "اسم المريض" : "Patient Name"}</th>
              <th>{locale === "ar" ? "رقم الهاتف" : "Phone Number"}</th>
              <th>{locale === "ar" ? "البريد الإلكتروني" : "Email"}</th>
              <th>{locale === "ar" ? "الموعد القادم" : "Next Appointment"}</th>
              <th>{locale === "ar" ? "آخر زيارة" : "Last Visit"}</th>
            </tr>
          </thead>
          <tbody>
            {result.rows.map((patient) => (
              <tr key={patient.id}>
                <td>
                  <span className="status">{patient.referenceCode}</span>
                </td>
                <td>
                  <Link className="directory-person" href={`/${locale}/customers/${patient.id}`}>
                    <span className="avatar-initials" aria-hidden="true">
                      {patient.displayName
                        .trim()
                        .split(/\s+/u)
                        .slice(0, 2)
                        .map((part) => part[0]?.toUpperCase())
                        .join("")}
                    </span>
                    <strong>{patient.displayName}</strong>
                  </Link>
                </td>
                <td dir="ltr">
                  {patient.contacts?.find(({ kind }) => kind === "PHONE")?.originalValue ?? "—"}
                </td>
                <td>
                  {patient.contacts?.find(({ kind }) => kind === "EMAIL")?.originalValue ?? "—"}
                </td>
                <td>
                  {formatPatientAppointment(patient.appointments, now, "next", appointmentDate)}
                </td>
                <td>
                  {formatPatientAppointment(patient.appointments, now, "previous", appointmentDate)}
                </td>
              </tr>
            ))}
            {result.rows.length === 0 ? (
              <tr>
                <td className="table-empty-cell" colSpan={6}>
                  {locale === "ar" ? "لم يتم العثور على مرضى." : "No patients found."}
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
      {result.total > result.pageSize ? (
        <nav className="pagination" aria-label={locale === "ar" ? "صفحات المرضى" : "Patient pages"}>
          {page > 1 ? (
            <Link href={`/${locale}/customers?q=${encodeURIComponent(search)}&page=${page - 1}`}>
              {locale === "ar" ? "السابق" : "Previous"}
            </Link>
          ) : null}
          <span>
            {page} / {Math.ceil(result.total / result.pageSize)}
          </span>
          {page * result.pageSize < result.total ? (
            <Link href={`/${locale}/customers?q=${encodeURIComponent(search)}&page=${page + 1}`}>
              {locale === "ar" ? "التالي" : "Next"}
            </Link>
          ) : null}
        </nav>
      ) : null}
    </section>
  );
}

function formatPatientAppointment(
  appointments: readonly Readonly<{ startsAt: Date; status: string }>[],
  now: Date,
  direction: "next" | "previous",
  formatter: Intl.DateTimeFormat,
): string {
  const relevant = appointments
    .filter(({ startsAt, status }) =>
      direction === "next"
        ? startsAt >= now && !["CANCELLED", "NO_SHOW"].includes(status)
        : startsAt < now,
    )
    .sort((left, right) =>
      direction === "next"
        ? left.startsAt.getTime() - right.startsAt.getTime()
        : right.startsAt.getTime() - left.startsAt.getTime(),
    )[0];
  return relevant ? formatter.format(relevant.startsAt) : "—";
}
