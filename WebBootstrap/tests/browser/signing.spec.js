import { test, expect } from './local-test.mjs';
import { makeIpa, makeMaterial } from '../fixtures.mjs';
import { makeBinaryIpa } from './binary-fixture.mjs';
import { readFileSync } from 'node:fs';
import { ZipReader, Uint8ArrayReader, Uint8ArrayWriter } from '@zip.js/zip.js';

let fixture;
test.beforeAll(async () => {
  fixture = { ipa: Buffer.from(await makeIpa()), binaryIpa: await makeBinaryIpa(), ...makeMaterial() };
});
async function fill(page, ipa = fixture.ipa) {
  if (await page.locator('#files-mode').isVisible()) await page.locator('#files-mode').click();
  await page.setInputFiles('#ipa', { name: 'Fixture.ipa', mimeType: 'application/zip', buffer: ipa });
  await page.setInputFiles('#p12', { name: 'test.p12', mimeType: 'application/x-pkcs12', buffer: fixture.p12 });
  await page.setInputFiles('#profiles', { name: 'test.mobileprovision', mimeType: 'application/octet-stream', buffer: fixture.profile });
  await page.locator('#password').fill(fixture.password);
  await page.locator('#rights').check();
}
async function sign(page) {
  await page.locator('#sign').click();
  await expect(page.locator('#download')).toBeVisible({ timeout: 60_000 });
  await expect(page.locator('#status')).toContainText('尚未驗證 iOS 安裝');
  await expect(page.locator('#sign')).toBeEnabled();
}
async function assertSignedDownload(page, input = fixture.ipa) {
  const promise = page.waitForEvent('download');
  await page.locator('#download').click();
  const download = await promise;
  expect(download.suggestedFilename()).toBe('Fixture-signed.ipa');
  const bytes = readFileSync(await download.path());
  expect(bytes.equals(input)).toBe(false);
  const reader = new ZipReader(new Uint8ArrayReader(bytes));
  try {
    const entries = await reader.getEntries();
    expect(entries.some((entry) => entry.filename === 'Payload/Fixture.app/_CodeSignature/CodeResources')).toBe(true);
    const profile = entries.find((entry) => entry.filename === 'Payload/Fixture.app/embedded.mobileprovision');
    expect(profile).toBeDefined();
    const embedded = await profile.getData(new Uint8ArrayWriter());
    expect(Buffer.from(embedded).equals(fixture.profile)).toBe(true);
  } finally { await reader.close(); }
}

// The original six cases remain, and each runs at root and the real project path.
test('static page never presents an Apple password field and stays local', async ({ page, baseURL, localTraffic }) => {
  await page.goto('.');
  await expect(page.locator('#apple-password')).toBeHidden();
  await expect(page.locator('#account-unavailable')).toContainText('不收集 Apple 密碼');
  await expect(page.locator('body')).toContainText('免費 Personal Team 的 Safari 首裝仍待實機驗證');
  await expect.poll(() => localTraffic.responses.some((r) => r.url === new URL('config.json', baseURL).href && r.status === 200)).toBe(true);
  expect(localTraffic.blocked).toEqual([]);
});

test('requires explicit rights acknowledgement', async ({ page, localTraffic }) => {
  await page.goto('.');
  await page.locator('#files-mode').click();
  await page.locator('#sign').click();
  await expect(page.locator('#status')).toContainText('確認你有權');
  expect(localTraffic.workers).toEqual([]);
});

test('rejects wrong password with no output and permits a fresh attempt', async ({ page }) => {
  await page.goto('.');
  await fill(page);
  await page.locator('#password').fill('incorrect');
  await page.locator('#sign').click();
  await expect(page.locator('#status')).toContainText('P12 could not be opened');
  await expect(page.locator('#download')).toBeHidden();
  await expect(page.locator('#password')).toHaveValue('');
  await expect(page.locator('#sign')).toBeEnabled();
  await page.locator('#password').fill(fixture.password);
  await sign(page);
  await assertSignedDownload(page);
});

test('real WASM signs a synthetic IPA, preserves bundle profile, and gates Personal Team OTA', async ({ page }) => {
  await page.goto('.');
  await fill(page);
  await sign(page);
  await assertSignedDownload(page);
  await page.locator('#ota-details').click();
  await page.locator('#manifest').click();
  await expect(page.locator('#ota-status')).toContainText('免費／development profiles');
  expect(await page.evaluate(() => [localStorage.length, sessionStorage.length])).toEqual([0, 0]);
  await page.locator('#clear').click();
  await expect(page.locator('#download')).toBeHidden();
  await expect(page.locator('#password')).toHaveValue('');
});

test('cancel during inspection cannot publish a stale successful result', async ({ page, localTraffic }) => {
  await page.goto('.');
  await fill(page);
  // Both handlers run in one browser task, before asynchronous inspection finishes.
  await page.evaluate(() => {
    document.getElementById('sign').click();
    document.getElementById('cancel').click();
  });
  await expect(page.locator('#status')).toContainText('已取消');
  await expect(page.locator('#download')).toBeHidden();
  await expect(page.locator('#sign')).toBeEnabled();
  // Completing a subsequent real operation also lets the old inspection settle.
  await fill(page);
  await sign(page);
  expect(localTraffic.workers.filter((url) => url.endsWith('/sign-worker.js'))).toHaveLength(1);
  await assertSignedDownload(page);
});

test('mobile layout keeps the default journey compact and manual signing progressive', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('.');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(page.locator('#p12')).toBeHidden();
  await expect(page.locator('#signing-panel')).toBeHidden();
  await expect(page.locator('#install-panel')).toBeHidden();
  await expect(page.locator('#account-unavailable')).toBeVisible();
  await expect(page.locator('#release-status')).toContainText('尚未綁定');
  await expect(page.locator('#app-source')).toHaveValue('custom');
  await expect(page.locator('#account-app-prerequisite')).toBeVisible();
  await expect(page.locator('#ipa')).toBeVisible();
  await expect(page.locator('#login-button')).toBeDisabled();
  const screenshot = testInfo.outputPath('mobile-bootstrap.png');
  await page.screenshot({ path: screenshot, fullPage: true });
  await testInfo.attach('mobile-bootstrap', { path: screenshot, contentType: 'image/png' });
  await page.locator('#files-mode').click();
  await expect(page.locator('#p12')).toBeVisible();
  await page.locator('#account-mode').click();
  await expect(page.locator('#p12')).toBeHidden();
  await expect(page.locator('#account-unavailable')).toBeVisible();
});

test('built assets, binary plist worker, and signing WASM resolve under the active project path', async ({ page, baseURL, localTraffic }) => {
  await page.goto('.');
  await fill(page, fixture.binaryIpa);
  await sign(page);
  await assertSignedDownload(page, fixture.binaryIpa);
  const asset = (path) => new URL(path, baseURL).href;
  for (const path of ['sign-worker.js', 'wasm/zsign-mobile.js', 'wasm/zsign-mobile.wasm']) {
    expect(localTraffic.responses.some((r) => r.url === asset(path) && r.status === 200), path).toBe(true);
  }
  const prefix = asset('assets/');
  expect(localTraffic.responses.some((r) => r.url.startsWith(prefix) && /\/index-[^/]+\.js$/.test(r.url) && r.status === 200)).toBe(true);
  expect(localTraffic.responses.some((r) => r.url.startsWith(prefix) && r.url.endsWith('.css') && r.status === 200)).toBe(true);
  expect(localTraffic.responses.some((r) => r.url.startsWith(prefix) && /\/plist-worker-[^/]+\.js$/.test(r.url) && r.status === 200)).toBe(true);
  expect(localTraffic.responses.find((r) => r.url === asset('wasm/zsign-mobile.wasm'))?.type).toBe('application/wasm');
  expect(localTraffic.workers).toContain(asset('sign-worker.js'));
  expect(localTraffic.workers.some((url) => url.startsWith(prefix) && /\/plist-worker-[^/]+\.js$/.test(url))).toBe(true);
  expect(localTraffic.responses.filter((r) => r.status >= 400 && r.url !== asset('health'))).toEqual([]);
});

test('cancel a pending real signing worker load, then retry without stale output', async ({ page, context }) => {
  await page.goto('.');
  await fill(page);
  let release, entered, settled, held = false;
  const gate = new Promise((resolve) => { release = resolve; });
  const loading = new Promise((resolve) => { entered = resolve; });
  const routed = new Promise((resolve) => { settled = resolve; });
  const pattern = '**/sign-worker.js';
  const handler = async (route) => {
    held = true;
    entered();
    try {
      await gate;
      // Delay only. Keep the original worker bytes and the context request guard.
      await route.fallback();
    } finally { settled(); }
  };
  await context.route(pattern, handler);
  try {
    await page.locator('#sign').click();
    await loading;
    await page.locator('#cancel').click();
    await expect(page.locator('#status')).toContainText('已取消');
    await expect(page.locator('#download')).toBeHidden();
    await expect(page.locator('#sign')).toBeEnabled();
  } finally {
    release();
    if (held) await routed;
    await context.unroute(pattern, handler);
  }
  await fill(page);
  await sign(page);
  await assertSignedDownload(page);
});

test('repeated clicks, clear, a second signing, and Back cannot revive stale output', async ({ page, baseURL, localTraffic }) => {
  await page.goto('.');
  await fill(page);
  await page.evaluate(() => {
    document.getElementById('sign').click();
    document.getElementById('sign').click();
  });
  await expect(page.locator('#download')).toBeVisible({ timeout: 60_000 });
  expect(localTraffic.workers.filter((url) => url.endsWith('/sign-worker.js'))).toHaveLength(1);
  const oldOutput = await page.locator('#download').getAttribute('href');
  await page.locator('#clear').click();
  await expect(page.locator('#download')).toBeHidden();
  await expect(page.locator('#password')).toHaveValue('');
  await expect(page.locator('#rights')).not.toBeChecked();
  expect(await page.locator('#ipa').evaluate((element) => element.files.length)).toBe(0);
  expect(await page.evaluate(async (url) => {
    try { await fetch(url); return false; } catch { return true; }
  }, oldOutput), 'Cleared Blob URL must be revoked').toBe(true);
  await fill(page);
  await sign(page);
  await assertSignedDownload(page);
  expect(await page.locator('#download').getAttribute('href')).not.toBe(oldOutput);
  expect(localTraffic.workers.filter((url) => url.endsWith('/sign-worker.js'))).toHaveLength(2);
  await page.locator('a[href="./licenses.html"]').click();
  await expect(page).toHaveURL(new URL('licenses.html', baseURL).href);
  await page.goBack();
  await expect(page).toHaveURL(baseURL);
  await expect(page.locator('#download')).toBeHidden();
  await expect(page.locator('#password')).toHaveValue('');
  await expect(page.locator('#rights')).not.toBeChecked();
});
