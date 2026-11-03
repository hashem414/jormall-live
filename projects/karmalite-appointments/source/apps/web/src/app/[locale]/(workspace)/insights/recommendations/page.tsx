import { isSupportedLocale } from "@jormall/contracts/locales";
import Link from "next/link";
import { notFound } from "next/navigation";

import CopilotPage from "../../../dashboard/copilot/page";
import PredictionsPage from "../../../dashboard/predictions/page";

type RecommendationView = "copilot" | "predictions";

export default async function RecommendationsPage({
  params,
  searchParams,
}: Readonly<{
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}>) {
  const [{ locale }, query] = await Promise.all([params, searchParams]);
  if (!isSupportedLocale(locale)) notFound();
  const selected: RecommendationView = query.view === "copilot" ? "copilot" : "predictions";
  const childQuery = Promise.resolve(
    Object.fromEntries(Object.entries(query).filter(([key]) => key !== "view")),
  );

  return (
    <section className="page-stack">
      <nav
        aria-label={locale === "ar" ? "أقسام التوصيات" : "Recommendation sections"}
        className="workspace-tabs"
      >
        <Link
          aria-current={selected === "predictions" ? "page" : undefined}
          href={`/${locale}/insights/recommendations?view=predictions`}
        >
          {locale === "ar" ? "التوصيات التنبؤية" : "Predictive recommendations"}
        </Link>
        <Link
          aria-current={selected === "copilot" ? "page" : undefined}
          href={`/${locale}/insights/recommendations?view=copilot`}
        >
          {locale === "ar" ? "توصيات مساعد الموظفين" : "Staff Copilot recommendations"}
        </Link>
      </nav>
      {selected === "copilot" ? (
        <CopilotPage params={Promise.resolve({ locale })} searchParams={childQuery} />
      ) : (
        <PredictionsPage params={Promise.resolve({ locale })} searchParams={childQuery} />
      )}
    </section>
  );
}
