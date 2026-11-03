import { describe, expect, it } from "vitest";

import {
  calculateProjectedStock,
  calculateStockHealth,
  computeExpiryAlert,
  fefoSortBatches,
  recommendFefoBatch,
} from "./inventory";

describe("inventory domain policies", () => {
  const baseDate = new Date("2026-09-14T10:00:00.000Z");

  describe("computeExpiryAlert", () => {
    it("returns NO_EXPIRY when no date provided", () => {
      expect(computeExpiryAlert(null, baseDate)).toBe("NO_EXPIRY");
      expect(computeExpiryAlert(undefined, baseDate)).toBe("NO_EXPIRY");
    });

    it("identifies expired batches", () => {
      expect(computeExpiryAlert(new Date("2026-09-10T00:00:00.000Z"), baseDate)).toBe("EXPIRED");
    });

    it("identifies critical 7-day expiration", () => {
      expect(computeExpiryAlert(new Date("2026-09-18T00:00:00.000Z"), baseDate)).toBe(
        "CRITICAL_7_DAYS",
      );
    });

    it("identifies 30, 60, and 90 day warning levels", () => {
      expect(computeExpiryAlert(new Date("2026-10-05T00:00:00.000Z"), baseDate)).toBe(
        "WARNING_30_DAYS",
      );
      expect(computeExpiryAlert(new Date("2026-11-01T00:00:00.000Z"), baseDate)).toBe(
        "NOTICE_60_DAYS",
      );
      expect(computeExpiryAlert(new Date("2026-12-01T00:00:00.000Z"), baseDate)).toBe(
        "INFO_90_DAYS",
      );
      expect(computeExpiryAlert(new Date("2027-05-01T00:00:00.000Z"), baseDate)).toBe("GOOD");
    });
  });

  describe("fefoSortBatches & recommendFefoBatch", () => {
    it("sorts valid batches by earliest expiry and filters out expired or zero quantity", () => {
      const batches = [
        {
          batchNumber: "B-FAR",
          expiryDate: new Date("2027-01-01"),
          id: "1",
          isActive: true,
          quantity: 10,
        },
        {
          batchNumber: "B-EXPIRED",
          expiryDate: new Date("2026-09-01"),
          id: "2",
          isActive: true,
          quantity: 5,
        },
        {
          batchNumber: "B-NEAR",
          expiryDate: new Date("2026-10-01"),
          id: "3",
          isActive: true,
          quantity: 8,
        },
        {
          batchNumber: "B-ZERO",
          expiryDate: new Date("2026-09-20"),
          id: "4",
          isActive: true,
          quantity: 0,
        },
        {
          batchNumber: "B-INACTIVE",
          expiryDate: new Date("2026-09-25"),
          id: "5",
          isActive: false,
          quantity: 4,
        },
      ];

      const sorted = fefoSortBatches(batches, baseDate);
      expect(sorted).toHaveLength(2);
      expect(sorted[0]?.batchNumber).toBe("B-NEAR");
      expect(sorted[1]?.batchNumber).toBe("B-FAR");

      const recommended = recommendFefoBatch(batches, baseDate);
      expect(recommended?.batchNumber).toBe("B-NEAR");
    });
  });

  describe("calculateStockHealth", () => {
    it("calculates correct health statuses", () => {
      expect(calculateStockHealth(0, 5)).toBe("OUT_OF_STOCK");
      expect(calculateStockHealth(-1, 5)).toBe("OUT_OF_STOCK");
      expect(calculateStockHealth(3, 5)).toBe("LOW_STOCK");
      expect(calculateStockHealth(5, 5)).toBe("LOW_STOCK");
      expect(calculateStockHealth(10, 5)).toBe("HEALTHY");
    });
  });

  describe("calculateProjectedStock", () => {
    it("computes projected balance and detects shortages", () => {
      expect(calculateProjectedStock(10, 4)).toEqual({
        isShortage: false,
        projectedStock: 6,
        shortageQuantity: 0,
      });

      expect(calculateProjectedStock(8, 13)).toEqual({
        isShortage: true,
        projectedStock: -5,
        shortageQuantity: 5,
      });
    });
  });
});
