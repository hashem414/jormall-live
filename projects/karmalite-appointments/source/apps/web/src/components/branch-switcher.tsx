"use client";

import type { SupportedLocale } from "@jormall/contracts/locales";
import { usePathname, useSearchParams } from "next/navigation";

import { switchBranchAction } from "../app/[locale]/actions";

type BranchChoice = Readonly<{ id: string; nameAr: string; nameEn: string }>;

export function BranchSwitcher({
  activeBranchId,
  branches,
  locale,
}: Readonly<{
  activeBranchId: string | null | undefined;
  branches: readonly BranchChoice[];
  locale: SupportedLocale;
}>) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const query = searchParams.toString();
  const returnTo = query ? `${pathname}?${query}` : pathname;

  if (branches.length === 0) return null;

  return (
    <form action={switchBranchAction} className="branch-switcher">
      <input name="locale" type="hidden" value={locale} />
      <input name="returnTo" type="hidden" value={returnTo} />
      <label className="sr-only" htmlFor="activeBranchId">
        {locale === "ar" ? "الفرع النشط" : "Active branch"}
      </label>
      <select
        className="select"
        defaultValue={activeBranchId ?? branches[0]?.id}
        id="activeBranchId"
        name="branchId"
        onChange={(event) => event.currentTarget.form?.requestSubmit()}
        required
      >
        {branches.map((branch) => (
          <option key={branch.id} value={branch.id}>
            {locale === "ar" ? branch.nameAr : branch.nameEn}
          </option>
        ))}
      </select>
    </form>
  );
}
