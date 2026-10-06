import { test, expect } from './guided-test.mjs';
import { SYNTHETIC } from './guided-service.mjs';
import { makeIpa } from '../fixtures.mjs';
import { readFileSync } from 'node:fs';
import { ZipReader, Uint8ArrayReader, Uint8ArrayWriter } from '@zip.js/zip.js';
let ipa;
test.beforeAll(async () => { ipa = Buffer.from(await makeIpa()); });
async function chooseCustom(page) {
  await page.goto('.'); await expect(page.locator('#account-form')).toBeVisible();
  await page.locator('#app-options > summary').click(); await page.locator('#app-source').selectOption('custom');
  await page.setInputFiles('#ipa', { name: 'Fixture.ipa', mimeType: 'application/zip', buffer: ipa });
}
async function credentials(page) {
  await page.locator('#apple-id').fill(SYNTHETIC.appleId); await page.locator('#apple-password').fill(SYNTHETIC.password); await page.locator('#login-consent').check();
}
async function authenticate(page) {
  await credentials(page); await page.locator('#login-button').click(); await expect(page.locator('#two-factor')).toBeVisible();
  await page.locator('#verification-code').fill(SYNTHETIC.code); await page.locator('#verify-button').click(); await expect(page.locator('#provision-form')).toBeVisible();
  await page.locator('#account-udid').fill(SYNTHETIC.udid);
}
async function approveProvision(page) { await page.locator('#provision-consent').check(); await page.locator('#provision-button').click(); }
async function assertRealOutput(page, guided) {
  await expect(page.locator('#download')).toBeVisible({ timeout: 60_000 });
  await expect(page.locator('#install-unavailable')).toBeDisabled(); await expect(page.locator('#install-link')).toBeHidden();
  await expect(page.locator('#status')).toContainText('尚未驗證 iOS 安裝');
  const pending = page.waitForEvent('download'); await page.locator('#download').click(); const download = await pending;
  const bytes = readFileSync(await download.path()); expect(bytes.equals(ipa)).toBe(false);
  const reader = new ZipReader(new Uint8ArrayReader(bytes));
  try {
    const entries = await reader.getEntries(); expect(entries.some(e => e.filename === 'Payload/Fixture.app/_CodeSignature/CodeResources')).toBe(true);
    const profile = entries.find(e => e.filename === 'Payload/Fixture.app/embedded.mobileprovision'); expect(profile).toBeDefined();
    expect(Buffer.from(await profile.getData(new Uint8ArrayWriter())).equals(guided.profiles.at(-1))).toBe(true);
  } finally { await reader.close(); }
  expect(guided.workers.some(url => url.endsWith('/sign-worker.js'))).toBe(true);
}
test('synthetic guided account: custom IPA, explicit consent, 2FA and mutation preview feed real browser WASM', async ({ page, guided }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 }); await chooseCustom(page);
  await page.locator('#apple-id').fill(SYNTHETIC.appleId); await page.locator('#apple-password').fill(SYNTHETIC.password); await page.locator('#login-button').click();
  expect(guided.calls.filter(c => c.name === 'login')).toHaveLength(0);
  await authenticate(page); await expect(page.locator('#provision-plan')).toContainText(SYNTHETIC.bundleId); await expect(page.locator('#team-summary')).toContainText(SYNTHETIC.teamId);
  await page.locator('#provision-button').click(); expect(guided.provisioningBodies).toHaveLength(0);
  await testInfo.attach('synthetic-guided-mutation-preview', { body: await page.screenshot({ fullPage: true }), contentType: 'image/png' });
  await approveProvision(page); await assertRealOutput(page, guided); expect(guided.provisioningBodies).toHaveLength(1);
  await testInfo.attach('synthetic-guided-signed-install-blocked', { body: await page.screenshot({ fullPage: true }), contentType: 'image/png' });
  expect(await page.evaluate(() => [localStorage.length, sessionStorage.length])).toEqual([0, 0]);
});
test('synthetic guided account: cancel a delayed login then retry without a stale session changing the view', async ({ page, guided }) => {
  await chooseCustom(page); await credentials(page); const hold = guided.holdNext('login');
  try {
  await page.locator('#login-button').click(); await hold.entered; await page.locator('#logout').click();
  await expect(page.locator('#account-form')).toBeVisible(); await expect(page.locator('#apple-password')).toHaveValue('');
  await authenticate(page); await expect(page.locator('#provision-plan')).toContainText(SYNTHETIC.bundleId); hold.release();
  await expect.poll(() => guided.completed.filter(c => c.path === 'v1/sessions').length).toBe(2);
  await expect(page.locator('#provision-form')).toBeVisible(); await expect(page.locator('#download')).toBeHidden();
  expect(guided.calls.filter(c => c.name === 'login')).toHaveLength(2);
  await page.locator('#logout').click(); await expect(page.locator('#account-form')).toBeVisible();
  } finally { hold.release(); }
});
test('synthetic guided account: same-CSR provisioning retry signs once; cancelled late provisioning cannot revive output', async ({ page, guided }) => {
  await chooseCustom(page); await authenticate(page); guided.failNextProvision = true;
  await approveProvision(page); await expect(page.locator('#provision-button')).toContainText('同一私鑰'); await expect(page.locator('#ipa')).toBeDisabled();
  await page.locator('#provision-button').click(); await assertRealOutput(page, guided);
  expect(guided.provisioningBodies).toHaveLength(2); expect(guided.provisioningBodies[0]).toBe(guided.provisioningBodies[1]);
  await page.locator('#clear').click(); await chooseCustom(page); await authenticate(page); const hold = guided.holdNext('provision');
  try {
  await approveProvision(page); await hold.entered; await page.locator('#logout').click(); hold.release();
  await expect.poll(() => guided.completed.filter(c => c.path.endsWith('/provision')).length).toBe(3);
  await expect(page.locator('#account-form')).toBeVisible(); await expect(page.locator('#download')).toBeHidden(); await expect(page.locator('#install-panel')).toBeHidden();
  expect(guided.workers.filter(url => url.endsWith('/sign-worker.js'))).toHaveLength(1);
  } finally { hold.release(); }
});
