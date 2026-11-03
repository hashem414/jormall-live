import { describe, expect, it } from "vitest";

import { feedbackMessages } from "./phase-one";

describe("appointment feedback messages", () => {
  it("shows a specific success message after creating an appointment", () => {
    expect(feedbackMessages.en.APPOINTMENT_CREATED).toBe("Appointment created successfully.");
    expect(feedbackMessages.ar.APPOINTMENT_CREATED).toBe("تم إنشاء الموعد بنجاح.");
    expect(feedbackMessages.en.APPOINTMENT_CREATED).not.toBe(feedbackMessages.en.INTERNAL_ERROR);
  });

  it("contains specific messages for every active workspace save result", () => {
    const resultCodes = [
      "BULK_CONFIRM_COMPLETED",
      "DOCTOR_SAVED",
      "DOCTOR_SCHEDULE_SAVED",
      "DOCTOR_TIME_OFF_SAVED",
      "ESCALATION_UPDATED",
      "NOTE_ADDED",
      "NOTIFICATIONS_DONE",
      "ORDER_APPROVED",
      "ORDER_PLACED",
      "ORDER_RECEIVED",
      "ORDER_REJECTED",
      "ORDER_REQUESTED",
      "PATIENT_SAFETY_INTAKE_UPDATED",
      "PROPOSAL_APPROVED",
      "PROPOSAL_CREATED",
      "PROPOSAL_REVIEWED",
      "ROOM_UPDATED",
      "SERVICE_UPDATED",
      "WAITLIST_CONVERTED",
    ] as const;

    for (const locale of ["en", "ar"] as const) {
      for (const code of resultCodes) {
        expect(feedbackMessages[locale][code]).toBeTruthy();
        expect(feedbackMessages[locale][code]).not.toBe(feedbackMessages[locale].INTERNAL_ERROR);
      }
    }
  });
});
