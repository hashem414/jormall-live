import { redirect } from "next/navigation";
import { getOptionalActor } from "../../lib/server-store";
import LoginClient from "./login-client";

export const dynamic = "force-dynamic";

export default async function LoginPage() {
  const actor = await getOptionalActor();
  if (actor) redirect("/");
  return <LoginClient />;
}
