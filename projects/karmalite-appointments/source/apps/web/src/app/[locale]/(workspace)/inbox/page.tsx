import { isSupportedLocale } from "@jormall/contracts/locales";
import Link from "next/link";
import { notFound } from "next/navigation";

import AIConversationsPage from "../../dashboard/ai-conversations/page";
import CommunicationsPage from "../../dashboard/communications/page";

const tabs = ["conversations", "messages", "delivery-issues"] as const;
type InboxTab = (typeof tabs)[number];

export default async function InboxPage({
  params,
  searchParams,
}: Readonly<{
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}>) {
  const [{ locale }, query] = await Promise.all([params, searchParams]);
  if (!isSupportedLocale(locale) || query.tab === "handoffs") notFound();
  const selected =
    typeof query.tab === "string" && tabs.includes(query.tab as InboxTab)
      ? (query.tab as InboxTab)
      : "conversations";
  const labels: Readonly<Record<InboxTab, string>> =
    locale === "ar"
      ? {
          conversations: "المحادثات",
          "delivery-issues": "مشكلات التسليم",
          messages: "الرسائل",
        }
      : {
          conversations: "Conversations",
          "delivery-issues": "Delivery Issues",
          messages: "Messages",
        };

  return (
    <section className="page-stack">
      <nav
        aria-label={locale === "ar" ? "أقسام صندوق الوارد" : "Inbox sections"}
        className="workspace-tabs"
      >
        {tabs.map((tab) => (
          <Link
            aria-current={selected === tab ? "page" : undefined}
            href={`/${locale}/inbox?tab=${tab}`}
            key={tab}
          >
            {labels[tab]}
          </Link>
        ))}
      </nav>
      {selected === "conversations" ? (
        <AIConversationsPage params={Promise.resolve({ locale })} searchParams={searchParams} />
      ) : (
        <CommunicationsPage params={Promise.resolve({ locale })} searchParams={searchParams} />
      )}
    </section>
  );
}
