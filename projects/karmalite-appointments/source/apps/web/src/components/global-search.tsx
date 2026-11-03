"use client";

import Link from "next/link";
import { useEffect, useId, useState } from "react";
import { z } from "zod";

import { WorkspaceIcon } from "./workspace-icon";

const resultSchema = z.object({
  results: z.array(
    z.object({
      href: z.string(),
      id: z.string(),
      label: z.string(),
      secondary: z.string(),
      type: z.enum(["appointment", "branch", "customer", "service", "service_provider"]),
    }),
  ),
});

type SearchResult = z.infer<typeof resultSchema>["results"][number];

export function GlobalSearch({ locale }: Readonly<{ locale: "ar" | "en" }>) {
  const listId = useId();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<readonly SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const normalized = query.trim();
    if (normalized.length < 2) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setLoading(true);
      void fetch(
        `/api/workspace/search?q=${encodeURIComponent(normalized)}&locale=${encodeURIComponent(locale)}`,
        { signal: controller.signal },
      )
        .then(async (response) => resultSchema.safeParse(await response.json()))
        .then((parsed) => {
          if (parsed.success) setResults(parsed.data.results);
        })
        .catch(() => undefined)
        .finally(() => setLoading(false));
    }, 250);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [locale, query]);

  const visible = open && query.trim().length >= 2;
  return (
    <form
      action={`/${locale}/customers`}
      className="global-search"
      method="get"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}
      onFocus={() => setOpen(true)}
      role="search"
    >
      <WorkspaceIcon name="search" />
      <label className="sr-only" htmlFor={`${listId}-input`}>
        {locale === "ar" ? "البحث في مساحة العمل" : "Search workspace"}
      </label>
      <input
        aria-autocomplete="list"
        aria-controls={listId}
        aria-expanded={visible}
        autoComplete="off"
        id={`${listId}-input`}
        name="q"
        onChange={(event) => {
          const next = event.currentTarget.value;
          setQuery(next);
          setOpen(true);
          if (next.trim().length < 2) setResults([]);
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") setOpen(false);
        }}
        placeholder={
          locale === "ar"
            ? "ابحث عن عميل أو موعد أو خدمة"
            : "Search customers, appointments, services"
        }
        role="combobox"
        type="search"
        value={query}
      />
      {visible ? (
        <div className="global-search-results" id={listId} role="listbox">
          {loading ? (
            <p role="status">{locale === "ar" ? "جارٍ البحث…" : "Searching…"}</p>
          ) : results.length === 0 ? (
            <p>{locale === "ar" ? "لا توجد نتائج." : "No results."}</p>
          ) : (
            results.map((result) => (
              <Link href={result.href} key={`${result.type}:${result.id}`} role="option">
                <WorkspaceIcon name={iconName(result.type)} />
                <span>
                  <strong>{result.label}</strong>
                  <small>{result.secondary}</small>
                </span>
              </Link>
            ))
          )}
        </div>
      ) : null}
    </form>
  );
}

function iconName(type: SearchResult["type"]): "branch" | "business" | "calendar" | "customers" {
  switch (type) {
    case "appointment":
      return "calendar";
    case "branch":
      return "branch";
    case "customer":
      return "customers";
    case "service":
      return "business";
    case "service_provider":
      return "customers";
  }
}
