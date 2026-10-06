import { test, expect } from './guided-test.mjs';
import { SYNTHETIC } from './guided-service.mjs';
import { makeIpa } from '../fixtures.mjs';
import { readFileSync } from 'node:fs';
import { ZipReader, Uint8ArrayReader, Uint8ArrayWriter } from '@zip.js/zip.js';
let ipa;
test.beforeAll(async () => { ipa = Buffer.from(await makeIpa()); });
async function chooseCustom(page, deviceRoute = 'existing') {
  await page.goto('.'); await expect(page.locator('#account-form')).toBeVisible();
  if (deviceRoute !== 'existing') await page.locator('#device-route').selectOption(deviceRoute);
  await page.locator('#app-options > summary').click(); await page.locator('#app-source').selectOption('custom');
  await page.setInputFiles('#ipa', { name: 'Fixture.ipa', mimeType: 'application/zip', buffer: ipa });
}
async function credentials(page) {
  await page.locator('#apple-id').fill(SYNTHETIC.appleId); await page.locator('#apple-password').fill(SYNTHETIC.password); await page.locator('#login-consent').check();
}
async function authenticate(page, { selectDevice = true } = {}) {
  await credentials(page); await page.locator('#login-button').click(); await expect(page.locator('#two-factor')).toBeVisible();
  await page.locator('#verification-code').fill(SYNTHETIC.code); await page.locator('#verify-button').click(); await expect(page.locator('#provision-form')).toBeVisible();
  if (!selectDevice) return;
  if (await page.locator('#device-route').inputValue() === 'existing') { await expect(page.locator('#existing-device')).toBeEnabled(); await page.locator('#existing-device').selectOption(SYNTHETIC.udid); }
  else await page.locator('#account-udid').fill(SYNTHETIC.udid);
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
test('synthetic guided account: custom IPA, explicit registered-device selection/consent, 2FA and mutation preview feed real browser WASM', async ({ page, guided }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 }); await chooseCustom(page);
  await page.locator('#apple-id').fill(SYNTHETIC.appleId); await page.locator('#apple-password').fill(SYNTHETIC.password); await page.locator('#login-button').click();
  expect(guided.calls.filter(c => c.name === 'login')).toHaveLength(0);
  await authenticate(page); await expect(page.locator('#provision-plan')).toContainText(SYNTHETIC.bundleId); await expect(page.locator('#team-summary')).toContainText(SYNTHETIC.teamId);
  await page.locator('#provision-button').click(); expect(guided.provisioningBodies).toHaveLength(0);
  await testInfo.attach('synthetic-guided-mutation-preview', { body: await page.screenshot({ fullPage: true }), contentType: 'image/png' });
  await approveProvision(page); await assertRealOutput(page, guided); expect(guided.provisioningBodies).toHaveLength(1); expect(JSON.parse(guided.provisioningBodies[0]).device.existingOnly).toBe(true); expect(JSON.parse(guided.provisioningBodies[0]).consent).toBe('use-existing-device-register-app-ids-and-issue-certificate');
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
test('synthetic guided account: new-device registration stays an explicit separate consent path', async ({ page, guided }) => {
  await chooseCustom(page, 'new'); await expect(page.locator('#device-route-hint')).toContainText('重新登入'); await authenticate(page);
  await expect(page.locator('#registered-device-panel')).toBeHidden(); await expect(page.locator('#provision-consent-text')).toContainText('註冊此裝置');
  await approveProvision(page); await assertRealOutput(page, guided);
  const body = JSON.parse(guided.provisioningBodies[0]); expect(body.device.existingOnly).toBeUndefined(); expect(body.consent).toBe('register-device-app-ids-and-issue-certificate');
  expect(guided.calls.some(call => call.path.endsWith('/devices'))).toBe(false);
});
test('synthetic registered devices: errors and empty lists block mutations; cancelled list responses stay dismissed', async ({ page, guided }) => {
  guided.failNextDevices = true; await chooseCustom(page); await authenticate(page, { selectDevice: false });
  await expect(page.locator('#existing-status')).toContainText('無法讀取'); await expect(page.locator('#provision-button')).toBeDisabled();
  guided.deviceLists.set(SYNTHETIC.teamId, []); await page.locator('#reload-devices').click(); await expect(page.locator('#existing-status')).toContainText('沒有可用');
  await expect(page.locator('#device-route')).toHaveValue('existing'); expect(guided.provisioningBodies).toHaveLength(0);
  const count = guided.completed.filter(call => call.path.endsWith('/devices')).length;
  const hold = guided.holdNext(`devices:${SYNTHETIC.teamId}`);
  try {
    await page.locator('#reload-devices').click(); await hold.entered; await page.locator('#logout').click(); hold.release();
    await expect.poll(() => guided.completed.filter(call => call.path.endsWith('/devices')).length).toBe(count + 1);
    await expect(page.locator('#account-form')).toBeVisible(); await expect(page.locator('#registered-device-panel')).toBeHidden(); await expect(page.locator('#provision-form')).toBeHidden();
  } finally { hold.release(); }
});
test('synthetic registered devices: Team changes clear consent and a stale old-Team response cannot replace the selected device', async ({ page, guided }) => {
  const secondTeam = 'TESTTEAM02', secondUdid = '22222222-2222222222222222';
  guided.teams.push({ id: secondTeam, name: 'Second synthetic Team', type: 'organization' }); guided.deviceLists.set(secondTeam, [{ udid: secondUdid, name: 'Second Team device', status: 'active', selectable: true }]);
  await chooseCustom(page); await authenticate(page, { selectDevice: false }); await expect(page.locator('#team')).toHaveValue('');
  const hold = guided.holdNext(`devices:${SYNTHETIC.teamId}`);
  try {
    await page.locator('#team').selectOption(SYNTHETIC.teamId); await hold.entered;
    await page.locator('#team').selectOption(secondTeam); await expect(page.locator('#provision-consent')).not.toBeChecked(); await expect(page.locator('#existing-device')).toBeEnabled();
    await page.locator('#existing-device').selectOption(secondUdid); await page.locator('#provision-consent').check(); hold.release();
    await expect.poll(() => guided.completed.some(call => call.path.endsWith(`/teams/${SYNTHETIC.teamId}/devices`))).toBe(true);
    await expect(page.locator('#existing-device')).toHaveValue(secondUdid); await expect(page.locator('#existing-device-summary')).toContainText('Second Team device'); await expect(page.locator('#provision-consent')).toBeChecked();
    await page.locator('#team').selectOption(SYNTHETIC.teamId); await expect(page.locator('#provision-consent')).not.toBeChecked(); await expect(page.locator('#existing-device')).toHaveValue('');
    expect(guided.provisioningBodies).toHaveLength(0);
  } finally { hold.release(); }
});
