import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  use: {
    baseURL: process.env.E2E_BASE_URL || (process.env.E2E_EXTERNAL_SERVER
      ? "http://127.0.0.1:3000" : "http://127.0.0.1:3100"),
    browserName: "chromium",
    channel: process.env.CI ? undefined : "msedge",
    headless: true,
  },
  webServer: process.env.E2E_EXTERNAL_SERVER ? undefined : {
    command: "npm run start -- --hostname 127.0.0.1 --port 3100",
    url: "http://127.0.0.1:3100",
    reuseExistingServer: false,
    timeout: 60000,
  },
});
