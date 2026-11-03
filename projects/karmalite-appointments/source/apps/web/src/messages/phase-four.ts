import type { SupportedLocale } from "@jormall/contracts/locales";

const en = {
  channel: "Channel",
  communications: "Communications",
  consentNotice:
    "External messages require current appointment-message consent and an enabled channel preference.",
  delivery: "Delivery",
  inbox: "Staff communication inbox",
  messageTimeline: "Message timeline",
  mockNotice: "Test mode is active. No live customer messages will be sent.",
  preference: "Communication preference",
  providerConnections: "Provider connections",
  retry: "Retry failed message",
  sendTemplate: "Send template",
  template: "Template",
  workerHealth: "Worker health",
};

const ar: typeof en = {
  channel: "القناة",
  communications: "الاتصالات",
  consentNotice: "تتطلب الرسائل الخارجية موافقة حالية لرسائل المواعيد وتفعيل تفضيل القناة.",
  delivery: "التسليم",
  inbox: "صندوق اتصالات الموظفين",
  messageTimeline: "الخط الزمني للرسائل",
  mockNotice: "وضع الاختبار مفعّل. لن يتم إرسال رسائل فعلية للعملاء.",
  preference: "تفضيلات الاتصال",
  providerConnections: "اتصالات مزودي الخدمة",
  retry: "إعادة محاولة الرسالة الفاشلة",
  sendTemplate: "إرسال قالب",
  template: "القالب",
  workerHealth: "صحة عامل المهام",
};

export const phaseFourMessages: Readonly<Record<SupportedLocale, typeof en>> = { ar, en };

export function phaseFourLabel(locale: SupportedLocale, value: string): string {
  const labels: Readonly<Record<SupportedLocale, Readonly<Record<string, string>>>> = {
    ar: {
      DEAD_LETTER: "فشل نهائي",
      DELIVERED: "تم التسليم",
      FAILED: "فشل",
      QUEUED: "في قائمة الانتظار",
      SENDING: "قيد الإرسال",
      SENT: "تم الإرسال",
    },
    en: {
      DEAD_LETTER: "Dead letter",
      DELIVERED: "Delivered",
      FAILED: "Failed",
      QUEUED: "Queued",
      SENDING: "Sending",
      SENT: "Sent",
    },
  };
  return labels[locale][value] ?? value;
}

export function communicationDeliveryLabel(
  locale: SupportedLocale,
  value: string,
  integrationMode: "DEVELOPMENT" | "MOCK" | "PRODUCTION" | "TEST" | null | undefined,
): string {
  if (integrationMode !== "PRODUCTION") {
    if (value === "DELIVERED" || value === "SENT") {
      return locale === "ar" ? "نجاح محاكاة" : "Simulated Success";
    }
    if (value === "FAILED" || value === "DEAD_LETTER") {
      return locale === "ar" ? "فشل محاكاة" : "Simulated Failure";
    }
  }
  return phaseFourLabel(locale, value);
}
