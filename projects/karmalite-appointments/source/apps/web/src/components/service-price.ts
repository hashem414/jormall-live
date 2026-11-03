export function formatServicePrice(
  locale: "ar" | "en",
  minor: number | null,
  currency: string,
): string {
  if (minor === null) {
    return locale === "ar"
      ? "يرجى التواصل مع كارمالايت لمعرفة السعر الحالي."
      : "Contact Karmalite for the current price.";
  }
  try {
    return new Intl.NumberFormat(locale === "ar" ? "ar-JO" : "en-JO", {
      currency,
      maximumFractionDigits: 2,
      minimumFractionDigits: 2,
      style: "currency",
    }).format(minor / 100);
  } catch {
    return `${(minor / 100).toFixed(2)} ${currency}`;
  }
}
