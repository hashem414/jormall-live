import { isSupportedLocale } from "@jormall/contracts/locales";
import { notFound, redirect } from "next/navigation";

export default async function PlatformPage({ params }: PageProps<"/[locale]/platform">) {
  const { locale } = await params;
  if (!isSupportedLocale(locale)) notFound();
  redirect(`/${locale}/platform/organizations`);
}
