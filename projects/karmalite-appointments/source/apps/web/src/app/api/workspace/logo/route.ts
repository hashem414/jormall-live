import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

import { identityRepository, requireTenantPermission } from "../../../../server/identity";

const karmaliteSlug = "karmalite-medical-esthetic";

export async function GET(): Promise<Response> {
  const access = await requireTenantPermission("en", "organization.read");
  const overview = await identityRepository.listTenantOverview(access);
  if (overview.organization?.slug !== karmaliteSlug) {
    return new Response(null, { status: 404 });
  }

  const logo = await readKarmaliteLogo();
  return new Response(new Uint8Array(logo), {
    headers: {
      "Cache-Control": "private, max-age=3600",
      "Content-Type": "image/png",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

async function readKarmaliteLogo(): Promise<Buffer> {
  try {
    return await readFile(resolve(process.cwd(), "Karmalite Logo.png"));
  } catch {
    return readFile(resolve(process.cwd(), "../../Karmalite Logo.png"));
  }
}
