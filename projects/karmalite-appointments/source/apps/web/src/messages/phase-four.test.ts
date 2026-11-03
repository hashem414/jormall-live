import { describe, expect, it } from "vitest";

import { communicationDeliveryLabel } from "./phase-four";

describe("communication delivery presentation", () => {
  it("never presents mock or development outcomes as real delivery", () => {
    expect(communicationDeliveryLabel("en", "DELIVERED", "MOCK")).toBe("Simulated Success");
    expect(communicationDeliveryLabel("en", "FAILED", "DEVELOPMENT")).toBe("Simulated Failure");
    expect(communicationDeliveryLabel("ar", "DELIVERED", "TEST")).toBe("نجاح محاكاة");
    expect(communicationDeliveryLabel("en", "DELIVERED", "PRODUCTION")).toBe("Delivered");
  });
});
