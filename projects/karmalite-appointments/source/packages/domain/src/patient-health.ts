import { DomainError } from "./errors";

export const healthInformationStates = [
  "NOT_PROVIDED",
  "NONE_REPORTED",
  "PROVIDED",
  "DECLINED",
] as const;

export type HealthInformationState = (typeof healthInformationStates)[number];

export function normalizeHealthInformation(
  state: HealthInformationState,
  suppliedDetails?: string,
): Readonly<{ details: string | null; state: HealthInformationState }> {
  const details = suppliedDetails?.trim() ?? "";
  if (state === "PROVIDED" && details.length === 0) {
    throw new DomainError({
      code: "VALIDATION_FAILED",
      message: "Details are required when health information is provided.",
    });
  }
  if (state !== "PROVIDED" && details.length > 0) {
    throw new DomainError({
      code: "VALIDATION_FAILED",
      message: "Details are only permitted for provided health information.",
    });
  }
  if (details.length > 4_000) {
    throw new DomainError({
      code: "VALIDATION_FAILED",
      message: "Health information exceeds the permitted length.",
    });
  }
  return { details: details || null, state };
}

export function requiresHealthConsent(states: readonly HealthInformationState[]): boolean {
  return states.some((state) => state !== "NOT_PROVIDED");
}
