import { defineConfig, devices } from "@playwright/test";

/**
 * Three paths, not a coverage target: the demo that gets run fifty times in
 * front of design partners. Sign up -> onboard -> calendar, evidence upload,
 * and invite -> accept -> assign.
 *
 * The stack is assumed to be already running (see e2e/README.md). Starting it
 * from here would hide a broken build behind a test-runner convenience.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  // A flaky compliance demo is worse than a failing one: retries would let a
  // real race pass on the second attempt and reach a customer.
  retries: 0,
  workers: 1, // the suite signs up real orgs against one backend; keep it serial
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{
    name: "chromium",
    use: {
      ...devices["Desktop Chrome"],
      // Use the Chromium already on the image rather than downloading one. The
      // bundled build and the @playwright/test version need not match, and
      // pinning the path keeps CI from fetching ~150MB per run.
      launchOptions: process.env.PLAYWRIGHT_CHROMIUM_PATH
        ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH }
        : {},
    },
  }],
});
