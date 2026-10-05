import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { defineConfig, devices } from "@playwright/test";

// End-to-end tests run the real API (fresh demo database) serving the built app at /app.
// Run with: npm run build && npm run e2e
const PORT = process.env.E2E_PORT ?? "8013";
// Prefer the project's virtualenv (backend/.venv) so a different active venv can't be picked up.
// Absolute and quoted: Windows runs this through cmd.exe, and the project path may contain spaces.
const VENV_PYTHON = resolve(process.cwd(), "..", "backend", ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const PYTHON = process.env.E2E_PYTHON ?? (existsSync(VENV_PYTHON) ? `"${VENV_PYTHON}"` : "python");
const SERVER_SCRIPT = `"${resolve(process.cwd(), "..", "backend", "scripts", "e2e_server.py")}"`;

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./test-results",
  fullyParallel: false,
  workers: 1, // all projects share one demo database
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
  webServer: {
    command: `${PYTHON} ${SERVER_SCRIPT} ${PORT}`,
    url: `http://127.0.0.1:${PORT}/health`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
