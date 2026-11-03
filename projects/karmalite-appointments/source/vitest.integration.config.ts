import { existsSync } from "node:fs";

import { defineConfig } from "vitest/config";

if (existsSync(".env")) process.loadEnvFile(".env");

export default defineConfig({
  test: {
    fileParallelism: false,
    include: ["tests/integration/**/*.integration.test.ts"],
    maxWorkers: 1,
    passWithNoTests: false,
    restoreMocks: true,
    testTimeout: 30_000,
  },
});
