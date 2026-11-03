import type { SupportedLocale } from "@jormall/contracts/locales";

const en = {
  customer: "Customer",
  customers: "Customers",
  equipment: "Equipment",
  service: "Service",
  serviceProvider: "Service Provider",
  serviceProviders: "Service Providers",
  services: "Services",
  treatment: "Treatment",
  treatmentRooms: "Treatment Rooms",
  treatments: "Treatments",
} as const;

const ar: Record<keyof typeof en, string> = {
  customer: "العميل",
  customers: "العملاء",
  equipment: "المعدات",
  service: "الخدمة",
  serviceProvider: "مقدم الخدمة",
  serviceProviders: "مقدمو الخدمات",
  services: "الخدمات",
  treatment: "العلاج",
  treatmentRooms: "غرف العلاج",
  treatments: "العلاجات",
};

export const beautyCenterMessages: Readonly<
  Record<SupportedLocale, Record<keyof typeof en, string>>
> = {
  ar,
  en,
};
