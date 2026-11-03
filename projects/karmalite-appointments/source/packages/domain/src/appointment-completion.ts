import type { AppointmentStatusValue } from "./appointment-state";
import { DomainError } from "./errors";

export function completionNote(
  input: Readonly<{
    toStatus: AppointmentStatusValue;
    recordSummary?: string | undefined;
    recordDetails?: string | undefined;
  }>,
): Readonly<{ summary: string; details: string | null; body: string }> | null {
  const summary = input.recordSummary?.trim() ?? "";
  const details = input.recordDetails?.trim() ?? "";
  if (!summary && !details) return null;
  if (
    input.toStatus !== "COMPLETED" ||
    !summary ||
    summary.length > 5000 ||
    details.length > 10000
  ) {
    throw new DomainError({
      code: "VALIDATION_FAILED",
      message: "A completion note requires a summary and valid completion status.",
    });
  }
  return {
    body: details ? `${summary}\n\n${details}` : summary,
    details: details || null,
    summary,
  };
}
