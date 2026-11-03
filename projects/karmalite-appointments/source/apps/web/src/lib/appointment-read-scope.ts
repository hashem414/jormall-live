export function defaultProviderIdForAppointmentRead(
  grants: readonly Readonly<{ code: string; scope: string }>[],
  staffProfileId: string | undefined,
): string | undefined {
  const scopes = grants
    .filter(({ code }) => code === "appointments.read")
    .map(({ scope }) => scope);
  const hasBroaderScope = scopes.some(
    (scope) => scope === "ORGANIZATION" || scope === "ASSIGNED_BRANCHES",
  );
  return !hasBroaderScope && scopes.includes("SELF") ? staffProfileId : undefined;
}
