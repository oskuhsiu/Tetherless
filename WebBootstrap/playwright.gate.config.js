import { defineConfig } from '@playwright/test';

// Uses only package-lock.json's Playwright 1.58.2 bundled Chromium revision.
// The harness intercepts every Chromium HTTP hop before bridging approved requests
// to an ephemeral loopback production proxy and a public synthetic upstream.
export default defineConfig({
  testDir: './tests/gate-browser',
  testMatch: '**/*.spec.js',
  timeout: 30_000,
  globalTimeout: 3 * 60_000,
  expect: { timeout: 5_000 },
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  outputDir: './test-results/gate-browser',
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-gate-report', open: 'never' }],
    ['junit', { outputFile: 'test-results/gate-browser-junit.xml' }],
  ],
  use: {
    browserName: 'chromium',
    headless: true,
    serviceWorkers: 'block',
    screenshot: 'only-on-failure',
    trace: 'off', // The harness alone starts/stops traces and attaches failures.
    actionTimeout: 5_000,
    navigationTimeout: 10_000,
  },
  projects: [{ name: 'synthetic-gate-chromium' }],
});
