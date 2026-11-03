import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import process from "node:process";

const rootEnvironmentPath = fileURLToPath(new URL("../../../.env", import.meta.url));

if (existsSync(rootEnvironmentPath)) {
  process.loadEnvFile(rootEnvironmentPath);
}

// The shared local environment intentionally runs development services, but a
// Next production build must not inherit that mode during prerendering.
if (process.argv[2] === "build") {
  process.env.NODE_ENV = "production";
}

await import("next/dist/bin/next");
