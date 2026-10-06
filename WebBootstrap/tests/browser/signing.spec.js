import { test, expect } from '@playwright/test';
import { makeIpa, makeMaterial } from '../fixtures.mjs';
import { readFileSync } from 'node:fs';
import { ZipReader, Uint8ArrayReader, Uint8ArrayWriter } from '@zip.js/zip.js';
let fixture;
test.beforeAll(async () => { fixture = { ipa: Buffer.from(await makeIpa()), ...makeMaterial() }; });
async function fill(page) {
  await page.setInputFiles('#ipa', { name: 'Fixture.ipa', mimeType: 'application/zip', buffer: fixture.ipa });
  await page.setInputFiles('#p12', { name: 'test.p12', mimeType: 'application/x-pkcs12', buffer: fixture.p12 });
  await page.setInputFiles('#profiles', { name: 'test.mobileprovision', mimeType: 'application/octet-stream', buffer: fixture.profile });
  await page.locator('#password').fill(fixture.password); await page.locator('#rights').check();
}
test('static page never presents an Apple password field and stays local', async ({ page }) => {
  const external = []; page.on('request', (r) => { if (!r.url().startsWith('http://127.0.0.1:4173/')) external.push(r.url()); });
  await page.goto('/'); await page.locator('#account-mode').click();
  await expect(page.locator('#apple-password')).toBeHidden(); await expect(page.locator('#account-unavailable')).toContainText('不收集 Apple 密碼');
  await expect(page.locator('body')).toContainText('免費帳號的 Safari 首裝尚未實機驗證'); expect(external).toEqual([]);
});
test('requires explicit rights acknowledgement', async ({ page }) => { await page.goto('/'); await page.locator('#sign').click(); await expect(page.locator('#status')).toContainText('確認你有權'); });
test('rejects wrong password with no output', async ({ page }) => { await page.goto('/'); await fill(page); await page.locator('#password').fill('incorrect'); await page.locator('#sign').click(); await expect(page.locator('#status')).toContainText('P12 could not be opened'); await expect(page.locator('#download')).toBeHidden(); });
test('real WASM signs a synthetic IPA, preserves bundle profile, and gates Personal Team OTA', async ({ page }) => {
  await page.goto('/'); await fill(page); await page.locator('#sign').click();
  await expect(page.locator('#download')).toBeVisible({ timeout: 60000 });
  await expect(page.locator('#status')).toContainText('尚未驗證 iOS 安裝');
  const downloadPromise = page.waitForEvent('download'); await page.locator('#download').click(); const download = await downloadPromise;
  const bytes = readFileSync(await download.path()); expect(bytes.equals(fixture.ipa)).toBe(false);
  const reader = new ZipReader(new Uint8ArrayReader(bytes)); const entries = await reader.getEntries();
  expect(entries.some((e) => e.filename === 'Payload/Fixture.app/_CodeSignature/CodeResources')).toBe(true);
  const embedded = await entries.find((e) => e.filename === 'Payload/Fixture.app/embedded.mobileprovision').getData(new Uint8ArrayWriter()); expect(Buffer.from(embedded).equals(fixture.profile)).toBe(true);
  await reader.close();
  await page.locator('#ota-details').click(); await page.locator('#manifest').click(); await expect(page.locator('#ota-status')).toContainText('免費／development profiles');
  expect(await page.evaluate(() => [localStorage.length, sessionStorage.length])).toEqual([0, 0]);
  await page.locator('#clear').click(); await expect(page.locator('#download')).toBeHidden(); await expect(page.locator('#password')).toHaveValue('');
});
test('cancel during inspection cannot publish a stale successful result', async ({ page }) => { await page.goto('/'); await fill(page); await page.locator('#sign').click(); await page.locator('#cancel').click(); await expect(page.locator('#status')).toContainText('已取消'); await expect(page.locator('#download')).toBeHidden(); await expect(page.locator('#sign')).toBeEnabled(); });
test('mobile layout has no horizontal overflow and exposes the local workflow', async ({ page }) => { await page.setViewportSize({ width: 390, height: 844 }); await page.goto('/'); expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true); await expect(page.locator('#p12')).toBeVisible(); await page.screenshot({ path: 'test-results/mobile-bootstrap.png', fullPage: true }); });
