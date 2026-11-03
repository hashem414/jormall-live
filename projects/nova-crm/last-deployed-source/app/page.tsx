import DashboardClient from "./dashboard-client";
import { redirect } from "next/navigation";
import { getOptionalActor } from "../lib/server-store";

export const dynamic = "force-dynamic";

export default async function Home() {
  const actor = await getOptionalActor();
  if (!actor) redirect("/login");
  return (
    <DashboardClient
      displayName={actor.fullName}
      userId={actor.id}
      accessRole={actor.role}
      position={actor.position}
    />
  );
}
