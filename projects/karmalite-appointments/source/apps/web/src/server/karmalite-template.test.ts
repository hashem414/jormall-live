import { describe, expect, it } from "vitest";

import { karmaliteTemplate } from "./karmalite-template";

describe("Karmalite beauty-center template", () => {
  it("contains exactly the five clean-draft services with unpublished prices", () => {
    expect(karmaliteTemplate.services.map(({ nameEn }) => nameEn)).toEqual([
      "Laser Hair Removal",
      "Deep Cleansing Facial & Skincare",
      "Body Contouring & Cellulite Appearance Care",
      "Hair & Scalp Care",
      "Mineral Screening Session (Oligo Check)",
    ]);
    expect(
      karmaliteTemplate.services.every(
        (service) =>
          !("defaultPriceMinor" in service) &&
          !("priceMinor" in service) &&
          service.configurationStatus === "DRAFT" &&
          service.isOnlineBookable === false &&
          service.minimumNoticeMins === null,
      ),
    ).toBe(true);
  });

  it("uses the exact bilingual organization and branch identity", () => {
    expect(karmaliteTemplate.organization).toMatchObject({
      nameAr: "كارمالايت للتجميل الطبي",
      nameEn: "Karmalite Medical Esthetic",
      slug: "karmalite-medical-esthetic",
    });
    expect(karmaliteTemplate.branch).toMatchObject({
      email: "info@karmalite.com",
      mobilePhone: "+962 77 586 8024",
      nameAr: "كارمالايت للتجميل الطبي - الصويفية",
      nameEn: "Karmalite Medical Esthetic - Sweifieh",
      phone: "+962 6 586 8024",
    });
  });

  it("keeps the Owner login private and applies the approved supplied identity", () => {
    const serialized = JSON.stringify(karmaliteTemplate);
    expect(serialized).not.toContain("raja@karmalite.com");
    expect(karmaliteTemplate.branding).toMatchObject({
      accentColor: "#A7B4B4",
      logoUrl: "/api/workspace/logo",
      primaryColor: "#4D6160",
    });
  });

  it("marks booking policy and durations provisional and closes Friday", () => {
    expect(karmaliteTemplate.settings).toMatchObject({
      bookingPolicyStatus: "DRAFT",
      bookingWindowDays: null,
      confirmationEnabled: false,
      defaultAppointmentStatus: "PENDING",
      reminderLeadMins: 1440,
      secondaryReminderLeadMins: 240,
    });
    expect(karmaliteTemplate.hours.map(({ weekday }) => String(weekday))).not.toContain("FRIDAY");
    expect(
      karmaliteTemplate.services.map(({ defaultDurationMins }) => defaultDurationMins),
    ).toEqual([60, 60, 45, 30, 20]);
  });

  it("contains no placeholder staff or excluded active service catalog", () => {
    const serviceCatalog = JSON.stringify(karmaliteTemplate.services).toLocaleLowerCase("en");
    for (const excluded of [
      "botox",
      "clinic",
      "doctor",
      "filler",
      "gynecology",
      "huda",
      "insurance",
      "patient",
      "sarah",
      "surgery",
    ]) {
      expect(serviceCatalog).not.toContain(excluded);
    }
  });
});
