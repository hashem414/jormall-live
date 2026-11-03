import { isSupportedLocale } from "@jormall/contracts/locales";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Feedback } from "../../../../components/feedback";
import { SubmitButton } from "../../../../components/submit-button";
import { operationalWorkflowsRepository, requirePagePermission } from "../../../../server/identity";
import { markAllNotificationsDoneAction, updateNotificationAction } from "../../actions";

export default async function NotificationsPage({
  params,
  searchParams,
}: PageProps<"/[locale]/notifications">) {
  const [{ locale }, query] = await Promise.all([params, searchParams]);
  if (!isSupportedLocale(locale)) notFound();
  const access = await requirePagePermission(locale, "notifications.read");
  const state =
    query.tab === "unread"
      ? "UNREAD"
      : query.tab === "read"
        ? "READ"
        : query.tab === "done"
          ? "DONE"
          : "ALL";
  const notifications = await operationalWorkflowsRepository.listNotifications(access, state);
  const labels =
    locale === "ar"
      ? {
          all: "الكل",
          done: "منتهية",
          empty: "لا توجد إشعارات في هذا القسم.",
          heading: "الإشعارات",
          markAll: "تحديد الكل كمنتهٍ",
          open: "فتح السجل المرتبط",
          read: "مقروءة",
          unread: "غير مقروءة",
        }
      : {
          all: "All",
          done: "Done",
          empty: "There are no notifications in this section.",
          heading: "Notifications",
          markAll: "Mark All as Done",
          open: "Open Related Record",
          read: "Read",
          unread: "Unread",
        };
  return (
    <section className="page-stack">
      <div>
        <p className="eyebrow">Karmalite</p>
        <h1>{labels.heading}</h1>
      </div>
      <Feedback
        error={typeof query.error === "string" ? query.error : undefined}
        locale={locale}
        notice={typeof query.notice === "string" ? query.notice : undefined}
      />
      <nav className="workspace-tabs" aria-label={labels.heading}>
        {[
          ["all", labels.all],
          ["unread", labels.unread],
          ["read", labels.read],
          ["done", labels.done],
        ].map(([tab, label]) => (
          <Link
            aria-current={(query.tab ?? "all") === tab ? "page" : undefined}
            href={`/${locale}/notifications?tab=${tab}`}
            key={tab}
          >
            {label}
          </Link>
        ))}
      </nav>
      <form action={markAllNotificationsDoneAction} className="inline-form">
        <input name="locale" type="hidden" value={locale} />
        <label>
          <input name="confirmation" type="checkbox" value="CONFIRM_HIGH_PRIORITY" />{" "}
          {locale === "ar"
            ? "أؤكد إنهاء الإشعارات عالية الأولوية"
            : "Confirm high-priority notifications"}
        </label>
        <SubmitButton tone="secondary">{labels.markAll}</SubmitButton>
      </form>
      {notifications.length === 0 ? (
        <p className="panel">{labels.empty}</p>
      ) : (
        <div className="card-grid">
          {notifications.map((notification) => (
            <article className="record-card" key={notification.id}>
              <div>
                <span className="status">{notification.priority}</span>
                <h2>{locale === "ar" ? notification.titleAr : notification.titleEn}</h2>
                <p>{locale === "ar" ? notification.messageAr : notification.messageEn}</p>
                <small>
                  {notification.createdAt.toLocaleString(locale === "ar" ? "ar-JO" : "en-JO")}
                </small>
              </div>
              <div className="inline-form">
                <form action={updateNotificationAction}>
                  <input name="locale" type="hidden" value={locale} />
                  <input name="id" type="hidden" value={notification.id} />
                  <input name="state" type="hidden" value="READ" />
                  <input
                    name="target"
                    type="hidden"
                    value={`/${locale}${notification.targetRoute}`}
                  />
                  <SubmitButton>{labels.open}</SubmitButton>
                </form>
                <form action={updateNotificationAction}>
                  <input name="locale" type="hidden" value={locale} />
                  <input name="id" type="hidden" value={notification.id} />
                  <input
                    name="state"
                    type="hidden"
                    value={notification.doneAt ? "UNREAD" : "DONE"}
                  />
                  <SubmitButton tone="secondary">
                    {notification.doneAt ? labels.unread : labels.done}
                  </SubmitButton>
                </form>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
