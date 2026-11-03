import { clearSessionCookie, logout } from "../../../../lib/server-store";

function tokenFrom(request: Request) {
  return request.headers
    .get("cookie")
    ?.split(";")
    .map((part) => part.trim().split("="))
    .find(([key]) => key === "nova_session")?.[1];
}

export async function POST(request: Request) {
  const token = tokenFrom(request);
  await logout(token ? decodeURIComponent(token) : undefined);
  const secure =
    request.headers.get("x-forwarded-proto")?.split(",")[0].trim() ===
      "https" || new URL(request.url).protocol === "https:";
  return Response.json(
    { ok: true },
    { headers: { "set-cookie": clearSessionCookie(secure) } },
  );
}
