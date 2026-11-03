import { z } from "zod";
import { login, sessionCookie } from "../../../../lib/server-store";

const schema = z.object({
  email: z.string().email().max(180),
  password: z.string().min(1).max(128),
});

export async function POST(request: Request) {
  try {
    const input = schema.parse(await request.json());
    const result = await login(input.email, input.password);
    const secure =
      request.headers.get("x-forwarded-proto")?.split(",")[0].trim() ===
        "https" || new URL(request.url).protocol === "https:";
    return Response.json(
      { ok: true, user: result.actor },
      {
        headers: {
          "set-cookie": sessionCookie(result.token, result.expiresAt, secure),
        },
      },
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : "INVALID_LOGIN";
    const locked = message === "LOGIN_LOCKED";
    return Response.json(
      {
        error: {
          code: locked ? "LOGIN_LOCKED" : "INVALID_LOGIN",
          message: locked
            ? "Too many attempts. Try again in 15 minutes."
            : "Email or password is incorrect.",
        },
      },
      { status: locked ? 429 : 401 },
    );
  }
}
