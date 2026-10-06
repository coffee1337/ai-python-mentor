import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "@playwright/test";

const directory = path.dirname(fileURLToPath(import.meta.url));
const repository = path.resolve(directory, "../..");
const artifacts = process.env.UI_ARTIFACT_DIR || path.join(directory, "artifacts");

export default defineConfig({
  testDir: directory,
  testMatch: "journey.spec.mjs",
  timeout: 180_000,
  expect: { timeout: 15_000 },
  workers: 1,
  retries: 0,
  outputDir: path.join(artifacts, "results"),
  reporter: [["list"], ["html", { outputFolder: path.join(artifacts, "report"), open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:3000",
    browserName: "chromium",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    reducedMotion: "reduce",
  },
  projects: [
    { name: "desktop", use: { viewport: { width: 1440, height: 900 } } },
    { name: "mobile", use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } },
  ],
  webServer: [
    {
      command: "python -m uvicorn app.main:app --host 127.0.0.1 --port 8000",
      cwd: path.join(repository, "apps/api"),
      url: "http://127.0.0.1:8000/ready",
      timeout: 60_000,
      reuseExistingServer: !process.env.CI,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      command: "npm run start -- --hostname 127.0.0.1 --port 3000",
      cwd: path.join(repository, "apps/web"),
      url: "http://127.0.0.1:3000/auth",
      timeout: 60_000,
      reuseExistingServer: !process.env.CI,
      stdout: "pipe",
      stderr: "pipe",
    },
  ],
});
