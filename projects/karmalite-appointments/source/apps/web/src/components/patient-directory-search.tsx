"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

export function PatientDirectorySearch({
  initialValue,
  locale,
}: Readonly<{ initialValue: string; locale: "ar" | "en" }>) {
  const [value, setValue] = useState(initialValue);
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  useEffect(() => {
    const timer = window.setTimeout(() => {
      const params = new URLSearchParams(searchParams.toString());
      if (value.trim()) params.set("q", value.trim());
      else params.delete("q");
      params.delete("page");
      router.replace(`${pathname}?${params.toString()}`);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [pathname, router, searchParams, value]);
  return (
    <label className="field patient-search">
      <span className="field-label">
        {locale === "ar"
          ? "البحث باسم المريض أو رقم الهاتف"
          : "Search by patient name or phone number"}
      </span>
      <input
        className="input"
        dir="auto"
        onChange={(event) => setValue(event.currentTarget.value)}
        type="search"
        value={value}
      />
    </label>
  );
}
