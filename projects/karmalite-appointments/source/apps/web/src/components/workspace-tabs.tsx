"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

import { appointmentTabHref } from "../lib/appointment-tab-context";

export type WorkspaceTab = Readonly<{ href: string; label: string }>;

export function WorkspaceTabs({
  ariaLabel,
  tabs,
  preserveAppointmentContext = false,
}: Readonly<{
  ariaLabel: string;
  tabs: readonly WorkspaceTab[];
  preserveAppointmentContext?: boolean;
}>) {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  return (
    <nav aria-label={ariaLabel} className="workspace-tabs">
      {tabs.map((tab) => (
        <Link
          aria-current={pathname === tab.href ? "page" : undefined}
          href={
            preserveAppointmentContext
              ? appointmentTabHref(tab.href, searchParams.toString())
              : tab.href
          }
          key={tab.href}
        >
          {tab.label}
        </Link>
      ))}
    </nav>
  );
}

export function ScheduleTabs({ locale }: Readonly<{ locale: "ar" | "en" }>) {
  const labels =
    locale === "ar"
      ? {
          appointments: "كل المواعيد",
          today: "اليوم",
        }
      : {
          appointments: "All Appointments",
          today: "Today",
        };
  const root = `/${locale}/schedule`;

  return (
    <WorkspaceTabs
      ariaLabel={locale === "ar" ? "أقسام الجدول" : "Schedule sections"}
      preserveAppointmentContext
      tabs={[
        { href: `${root}/today`, label: labels.today },
        { href: `${root}/appointments`, label: labels.appointments },
      ]}
    />
  );
}
