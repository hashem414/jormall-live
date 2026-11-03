export type ExpiryAlertLevel =
  | "EXPIRED"
  | "CRITICAL_7_DAYS"
  | "WARNING_30_DAYS"
  | "NOTICE_60_DAYS"
  | "INFO_90_DAYS"
  | "GOOD"
  | "NO_EXPIRY";

export type StockHealthStatus = "OUT_OF_STOCK" | "LOW_STOCK" | "HEALTHY";

export function computeExpiryAlert(
  expiryDate: Date | string | null | undefined,
  referenceDate: Date = new Date(),
): ExpiryAlertLevel {
  if (!expiryDate) return "NO_EXPIRY";
  const expiry = typeof expiryDate === "string" ? new Date(expiryDate) : expiryDate;
  if (Number.isNaN(expiry.getTime())) return "NO_EXPIRY";

  const diffMs = expiry.getTime() - referenceDate.getTime();
  const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays < 0) return "EXPIRED";
  if (diffDays <= 7) return "CRITICAL_7_DAYS";
  if (diffDays <= 30) return "WARNING_30_DAYS";
  if (diffDays <= 60) return "NOTICE_60_DAYS";
  if (diffDays <= 90) return "INFO_90_DAYS";
  return "GOOD";
}

export type BatchCandidate = Readonly<{
  batchNumber: string;
  expiryDate?: Date | string | null | undefined;
  id: string;
  isActive?: boolean | undefined;
  quantity: number | string;
  receivedDate?: Date | string | null | undefined;
}>;

export function recommendFefoBatch<T extends BatchCandidate>(
  batches: readonly T[],
  referenceDate: Date = new Date(),
): T | null {
  const sorted = fefoSortBatches(batches, referenceDate);
  return sorted[0] ?? null;
}

export function fefoSortBatches<T extends BatchCandidate>(
  batches: readonly T[],
  referenceDate: Date = new Date(),
): readonly T[] {
  const activeAndUsable = batches.filter((b) => {
    if (b.isActive === false) return false;
    const qty = typeof b.quantity === "string" ? Number(b.quantity) : b.quantity;
    if (qty <= 0) return false;
    if (b.expiryDate) {
      const exp = typeof b.expiryDate === "string" ? new Date(b.expiryDate) : b.expiryDate;
      if (exp.getTime() < referenceDate.getTime()) return false; // Expired
    }
    return true;
  });

  return [...activeAndUsable].sort((a, b) => {
    const aExp = a.expiryDate
      ? (typeof a.expiryDate === "string" ? new Date(a.expiryDate) : a.expiryDate).getTime()
      : Number.POSITIVE_INFINITY;
    const bExp = b.expiryDate
      ? (typeof b.expiryDate === "string" ? new Date(b.expiryDate) : b.expiryDate).getTime()
      : Number.POSITIVE_INFINITY;

    if (aExp !== bExp) {
      return aExp - bExp; // Earlier expiry first (FEFO)
    }

    const aRec = a.receivedDate
      ? (typeof a.receivedDate === "string" ? new Date(a.receivedDate) : a.receivedDate).getTime()
      : 0;
    const bRec = b.receivedDate
      ? (typeof b.receivedDate === "string" ? new Date(b.receivedDate) : b.receivedDate).getTime()
      : 0;

    return aRec - bRec;
  });
}

export function calculateStockHealth(
  currentStock: number,
  minimumStock: number,
): StockHealthStatus {
  if (currentStock <= 0) return "OUT_OF_STOCK";
  if (currentStock <= minimumStock) return "LOW_STOCK";
  return "HEALTHY";
}

export function calculateProjectedStock(
  availableStock: number,
  upcomingDemand: number,
): Readonly<{
  isShortage: boolean;
  projectedStock: number;
  shortageQuantity: number;
}> {
  const projectedStock = availableStock - upcomingDemand;
  const isShortage = projectedStock < 0;
  return {
    isShortage,
    projectedStock,
    shortageQuantity: isShortage ? Math.abs(projectedStock) : 0,
  };
}
