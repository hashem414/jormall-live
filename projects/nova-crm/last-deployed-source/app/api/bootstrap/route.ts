import { getActor, getBootstrap } from "../../../lib/server-store";

export async function GET() {
  try {
    const actor = await getActor();
    return Response.json(await getBootstrap(actor), {
      headers: { "cache-control": "no-store" },
    });
  } catch (error) {
    console.error(error);
    const unauthenticated =
      error instanceof Error && error.message === "UNAUTHENTICATED";
    return Response.json(
      {
        error: {
          code: unauthenticated ? "UNAUTHENTICATED" : "BOOTSTRAP_FAILED",
          message: unauthenticated
            ? "Please sign in."
            : "Workspace data could not be loaded.",
        },
      },
      { status: unauthenticated ? 401 : 500 },
    );
  }
}
