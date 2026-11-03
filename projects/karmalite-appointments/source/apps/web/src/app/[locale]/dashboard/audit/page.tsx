import { isSupportedLocale } from "@jormall/contracts/locales";
import { notFound } from "next/navigation";
import { z } from "zod";

import { phaseSevenMessages } from "../../../../messages/phase-seven";
import {
  operationsIntelligenceRepository,
  requirePagePermission,
} from "../../../../server/identity";

export default async function AuditPage({
  params,
  searchParams,
}: PageProps<"/[locale]/dashboard/audit">) {
  const { locale } = await params;
  if (!isSupportedLocale(locale)) notFound();
  const query = await searchParams;
  const parsed = z
    .object({
      action: z.string().trim().max(120).catch(""),
      actor: z.string().trim().max(160).catch(""),
      branchId: z.uuid().optional(),
      endsOn: z.iso.date().optional(),
      page: z.coerce.number().int().min(1).max(10_000).catch(1),
      startsOn: z.iso.date().optional(),
      targetType: z.string().trim().max(100).catch(""),
    })
    .safeParse(query);
  const filters = parsed.success ? parsed.data : { action: "", actor: "", page: 1, targetType: "" };
  const page = filters.page;
  const access = await requirePagePermission(locale, "audit.read");
  const events = await operationsIntelligenceRepository.listAudit(access, page, {
    ...(filters.action ? { action: filters.action } : {}),
    ...(filters.actor ? { actor: filters.actor } : {}),
    ...(access.activeBranchId ? { branchId: access.activeBranchId } : {}),
    ...(filters.endsOn ? { endsAt: new Date(`${filters.endsOn}T23:59:59.999Z`) } : {}),
    ...(filters.startsOn ? { startsAt: new Date(`${filters.startsOn}T00:00:00.000Z`) } : {}),
    ...(filters.targetType ? { targetType: filters.targetType } : {}),
  });
  const messages = phaseSevenMessages[locale];
  return (
    <section className="page-stack" aria-labelledby="audit-title">
      <div>
        <p className="eyebrow">Phase 7</p>
        <h1 id="audit-title">{messages.audit}</h1>
        <p className="muted">{messages.auditDescription}</p>
      </div>
      <form className="panel filter-toolbar" method="get">
        <label className="field">
          <span className="field-label">{locale === "ar" ? "الفاعل" : "Actor"}</span>
          <input className="input" defaultValue={filters.actor} name="actor" />
        </label>
        <label className="field">
          <span className="field-label">{locale === "ar" ? "الإجراء" : "Action"}</span>
          <input className="input" defaultValue={filters.action} name="action" />
        </label>
        <label className="field">
          <span className="field-label">{locale === "ar" ? "نوع السجل" : "Entity type"}</span>
          <input className="input" defaultValue={filters.targetType} name="targetType" />
        </label>
        <label className="field">
          <span className="field-label">{locale === "ar" ? "من" : "From"}</span>
          <input
            className="input"
            defaultValue={filters.startsOn ?? ""}
            name="startsOn"
            type="date"
          />
        </label>
        <label className="field">
          <span className="field-label">{locale === "ar" ? "إلى" : "To"}</span>
          <input className="input" defaultValue={filters.endsOn ?? ""} name="endsOn" type="date" />
        </label>
        <button className="button" type="submit">
          {locale === "ar" ? "تطبيق" : "Apply"}
        </button>
      </form>
      <div className="panel table-wrap">
        <table>
          <caption>{messages.audit}</caption>
          <thead>
            <tr>
              <th>{locale === "ar" ? "الوقت" : "Time"}</th>
              <th>{locale === "ar" ? "الفاعل" : "Actor"}</th>
              <th>{locale === "ar" ? "الإجراء" : "Action"}</th>
              <th>{locale === "ar" ? "الهدف" : "Target"}</th>
            </tr>
          </thead>
          <tbody>
            {events.map((event) => (
              <tr key={event.id}>
                <td>{event.createdAt.toLocaleString(locale)}</td>
                <td>
                  {event.actor?.name ??
                    event.actor?.email ??
                    (locale === "ar" ? "النظام" : "System")}
                </td>
                <td>{event.action}</td>
                <td>{event.targetType ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <nav aria-label={locale === "ar" ? "صفحات التدقيق" : "Audit pages"}>
        <a href={`?page=${Math.max(1, page - 1)}`}>{locale === "ar" ? "السابق" : "Previous"}</a> ·{" "}
        <a href={`?page=${page + 1}`}>{locale === "ar" ? "التالي" : "Next"}</a>
      </nav>
    </section>
  );
}
