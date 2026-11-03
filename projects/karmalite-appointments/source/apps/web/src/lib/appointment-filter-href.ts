import type { SupportedLocale } from "@jormall/contracts/locales";

export type AppointmentCategoryTab = "all" | "exceptions" | "past" | "upcoming";

export function appointmentFiltersResetHref(
  locale: SupportedLocale,
  tab: AppointmentCategoryTab,
): string {
  const base = `/${locale}/schedule/appointments`;
  return tab === "upcoming" ? base : `${base}?tab=${tab}`;
}
