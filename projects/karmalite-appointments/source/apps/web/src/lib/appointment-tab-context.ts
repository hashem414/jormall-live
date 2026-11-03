import { appointmentStatuses } from "@jormall/domain/appointment-state";
import { z } from "zod";

const contextSchema = z
  .object({
    appointment: z.uuid().optional(),
    branchId: z.uuid().optional(),
    day: z.iso.date().optional(),
    dateFrom: z.iso.date().optional(),
    dateTo: z.iso.date().optional(),
    providerId: z.uuid().optional(),
    q: z.string().trim().max(100).optional(),
    resourceId: z.uuid().optional(),
    serviceId: z.uuid().optional(),
    status: z.enum(appointmentStatuses).optional(),
  })
  .strict();

/** Carry only shared display selectors; authorization and tenant come from the session. */
export function appointmentTabHref(href: string, query: string): string {
  const params = new URLSearchParams(query);
  const target = new URLSearchParams();
  for (const [key, schema] of Object.entries(contextSchema.shape)) {
    const values = params.getAll(key);
    if (values.length !== 1) continue;
    const parsed = schema.safeParse(values[0]);
    if (parsed.success && parsed.data) target.set(key, parsed.data);
  }
  // Waiting-list status belongs to a different state machine.
  if (href.endsWith("/waitlist")) target.delete("status");
  if (href.endsWith("/appointments")) {
    const day = target.get("day");
    target.delete("day");
    if (day) {
      target.set("dateFrom", day);
      target.set("dateTo", day);
    }
  } else {
    const dateFrom = target.get("dateFrom");
    target.delete("dateFrom");
    target.delete("dateTo");
    if (!target.has("day") && dateFrom) target.set("day", dateFrom);
  }
  const search = target.toString();
  return search ? `${href}?${search}` : href;
}
