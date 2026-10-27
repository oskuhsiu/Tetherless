import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests/discovery-browser', testMatch: '**/*.spec.js',
  timeout: 15_000, globalTimeout: 120_000, workers: 1, retries: 0, forbidOnly: !!process.env.CI,
  use: { headless: true, serviceWorkers: 'block', trace: 'retain-on-failure' },
  projects: [ { name: 'discovery-chromium', use: { browserName: 'chromium' } }, { name: 'discovery-webkit', use: { browserName: 'webkit' } } ],
  outputDir: './test-results/discovery',
  reporter: [['list'], ['html', { outputFolder: 'playwright-discovery-report', open: 'never' }], ['junit', { outputFile: 'test-results/discovery-junit.xml' }]],
});
