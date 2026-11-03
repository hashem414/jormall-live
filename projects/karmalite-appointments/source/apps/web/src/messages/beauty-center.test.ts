import { describe, expect, it } from "vitest";

import { beautyCenterMessages } from "./beauty-center";

describe("fixed beauty-center terminology", () => {
  it("provides the exact English terminology", () => {
    expect(beautyCenterMessages.en).toEqual({
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
    });
  });

  it("provides the exact Arabic terminology", () => {
    expect(beautyCenterMessages.ar).toEqual({
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
    });
  });
});
