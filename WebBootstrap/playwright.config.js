import { defineConfig } from '@playwright/test';

// Use the Chromium revision bundled with package-lock.json's Playwright 1.58.2.
// No system executable override, browser channel, or custom sandbox arguments.
export default defineConfig({
  testDir: './tests/browser',
  testMatch: '**/*.spec.js',
  timeout: 90_000,
  globalTimeout: 8 * 60_000,
  expect: { timeout: 10_000 },
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  outputDir: './test-results/browser',
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
    ['junit', { outputFile: 'test-results/browser-junit.xml' }],
  ],
  use: {
    browserName: 'chromium',
    headless: true,
    acceptDownloads: true,
    serviceWorkers: 'block',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    actionTimeout: 10_000,
    navigationTimeout: 15_000,
  },
  projects: [
    { name: 'root-chromium', use: { baseURL: 'http://127.0.0.1:4173/' } },
    { name: 'project-subpath-chromium', use: { baseURL: 'http://127.0.0.1:4173/Tetherless/' } },
  ],
  webServer: {
    command: 'node tests/browser/preview.mjs',
    url: 'http://127.0.0.1:4173/',
    timeout: 15_000,
    reuseExistingServer: false,
    gracefulShutdown: { signal: 'SIGTERM', timeout: 5_000 },
  },
});
