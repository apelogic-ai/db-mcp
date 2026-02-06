import { defineConfig, devices } from "@playwright/test";

const port = process.env.PW_PORT ? parseInt(process.env.PW_PORT) : 3177;

export default defineConfig({
  testDir: "./e2e",
  // The default E2E suite uses BICP mocks and runs against the Next dev server.
  // The real-config spec requires the python UI server + real external services,
  // and is executed via playwright.real.config.ts.
  testIgnore: /real-config\.spec\.ts/,
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: "html",

  use: {
    baseURL: `http://localhost:${port}`,
    colorScheme: "dark",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  webServer: {
    command: `bun run dev --port ${port}`,
    url: `http://localhost:${port}`,
    reuseExistingServer: false,
  },
});
