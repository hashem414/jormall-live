"use client";

import type { SupportedLocale } from "@jormall/contracts/locales";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

export function DashboardBackButton({
  fallbackHref,
  label,
}: Readonly<{ fallbackHref: string; label: string }>) {
  const router = useRouter();

  function goBack() {
    if (window.history.length > 1) {
      router.back();
      return;
    }
    router.push(fallbackHref);
  }

  return (
    <button aria-label={label} className="header-back-button" onClick={goBack} type="button">
      <span aria-hidden="true">←</span>
      <span>{label}</span>
    </button>
  );
}

export function DashboardLocaleSwitch({
  label,
  locale,
}: Readonly<{ label: string; locale: SupportedLocale }>) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const nextLocale: SupportedLocale = locale === "en" ? "ar" : "en";
  const localizedPath = pathname.replace(/^\/(?:en|ar)(?=\/|$)/u, `/${nextLocale}`);
  const localizedHref = localizedPath === pathname ? `/${nextLocale}/dashboard` : localizedPath;
  const query = searchParams.toString();
  const href = query ? `${localizedHref}?${query}` : localizedHref;

  return (
    <Link aria-label={label} className="locale-switch" href={href} hrefLang={nextLocale}>
      <span className={locale === "en" ? "is-active" : undefined}>EN</span>
      <span aria-hidden="true" className="locale-switch-divider">
        |
      </span>
      <span className={locale === "ar" ? "is-active" : undefined}>AR</span>
    </Link>
  );
}
