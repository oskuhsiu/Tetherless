import { test, expect } from './guided-test.mjs';
import { SYNTHETIC, GUIDED_APPS } from './guided-service.mjs';
import { OWNED_IPA, loadOwnedIpa, verifyOwnedSignedOutput } from './owned-ipa.mjs';
import { readFileSync } from 'node:fs';

test.use({ guidedApp: 'owned-signing-test' });

test('owned unsigned UIKit IPA: visible custom selection and synthetic consent flow produce real WASM output, with installation blocked', async ({ page, baseURL, guided }, testInfo) => {
  const input = await loadOwnedIpa();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('.');
  await expect(page.locator('#account-form')).toBeVisible();
  await expect(page.locator('#release-status')).toContainText('尚未綁定');
  await page.locator('#app-options > summary').click();
  await page.locator('#app-source').selectOption('custom');
  await expect(page.locator('#ipa')).toBeVisible();
  await page.setInputFiles('#ipa', { name: OWNED_IPA.filename, mimeType: 'application/zip', buffer: input.bytes });

  await page.locator('#apple-id').fill(SYNTHETIC.appleId);
  await page.locator('#apple-password').fill(SYNTHETIC.password);
  await page.locator('#login-button').click();
  expect(guided.calls.filter(call => call.name === 'login')).toHaveLength(0);
  await page.locator('#login-consent').check();
  await page.locator('#login-button').click();
  await expect(page.locator('#two-factor')).toBeVisible();
  await expect(page.locator('#apple-password')).toHaveValue('');
  await page.locator('#verification-code').fill(SYNTHETIC.code);
  await page.locator('#verify-button').click();
  await expect(page.locator('#provision-form')).toBeVisible();
  await expect(page.locator('#existing-device')).toBeEnabled();
  await expect(page.locator('#existing-device')).toHaveValue('');
  await expect(page.locator('#provision-button')).toBeDisabled();
  expect(guided.provisioningBodies).toHaveLength(0);

  await page.locator('#existing-device').selectOption(SYNTHETIC.udid);
  await expect(page.locator('#provision-plan')).toContainText(OWNED_IPA.filename);
  await expect(page.locator('#provision-plan')).toContainText(OWNED_IPA.bundleId);
  await expect(page.locator('#team-summary')).toContainText(SYNTHETIC.teamId);
  await expect(page.locator('#provision-consent-text')).toContainText('有權使用所選 IPA');
  await expect(page.locator('#provision-consent')).not.toBeChecked();
  await page.locator('#provision-button').click();
  expect(guided.provisioningBodies).toHaveLength(0);
  await testInfo.attach('owned-ipa-synthetic-mutation-preview', { body: await page.screenshot({ fullPage: true }), contentType: 'image/png' });
  await page.locator('#provision-consent').check();
  await page.locator('#provision-button').click();

  await expect(page.locator('#download')).toBeVisible({ timeout: 60_000 });
  await expect(page.locator('#summary')).toContainText(OWNED_IPA.bundleId);
  await expect(page.locator('#summary')).toContainText(SYNTHETIC.teamId);
  await expect(page.locator('#status')).toContainText('尚未驗證 iOS 安裝或 App 啟動');
  await expect(page.locator('#install-unavailable')).toBeDisabled();
  await expect(page.locator('#install-link')).toBeHidden();
  expect(guided.provisioningBodies).toHaveLength(1);
  const request = JSON.parse(guided.provisioningBodies[0]);
  expect(request.apps).toEqual([GUIDED_APPS['owned-signing-test']]);
  expect(request.device).toEqual({ udid: SYNTHETIC.udid, name: 'My iPhone', existingOnly: true });
  expect(request.teamId).toBe(SYNTHETIC.teamId);
  expect(request.consent).toBe('use-existing-device-register-app-ids-and-issue-certificate');
  expect(request).not.toHaveProperty('appGroup');
  expect(request.csrPem).toContain('BEGIN CERTIFICATE REQUEST');
  expect(request.csrPem).not.toContain('PRIVATE KEY');
  expect(guided.profiles).toHaveLength(1);
  expect(guided.workers.filter(url => url.endsWith('/sign-worker.js'))).toEqual([new URL('sign-worker.js', baseURL).href]);
  for (const asset of ['sign-worker.js', 'wasm/zsign-mobile.js', 'wasm/zsign-mobile.wasm']) {
    expect(guided.responses.some(response => response.url === new URL(asset, baseURL).href && response.status === 200), asset).toBe(true);
  }

  const pending = page.waitForEvent('download');
  await page.locator('#download').click();
  const download = await pending;
  try {
    expect(download.suggestedFilename()).toBe('Signing-test-app-not-Tetherless-signed.ipa');
    const proof = await verifyOwnedSignedOutput(readFileSync(await download.path()), input, guided.profiles[0]);
    await testInfo.attach('owned-ipa-synthetic-output-proof', { body: Buffer.from(JSON.stringify(proof, null, 2)), contentType: 'application/json' });
  } finally { await download.delete(); }
  // Re-read the immutable fixture after signing; never retain the synthetic IPA.
  expect((await loadOwnedIpa()).bytes.equals(input.bytes)).toBe(true);
  await testInfo.attach('owned-ipa-synthetic-signed-install-blocked', { body: await page.screenshot({ fullPage: true }), contentType: 'image/png' });
  expect(await page.evaluate(() => [localStorage.length, sessionStorage.length])).toEqual([0, 0]);
  await page.locator('#clear').click();
  await expect(page.locator('#download')).toBeHidden();
  await expect(page.locator('#install-panel')).toBeHidden();
  await expect(page.locator('#apple-password')).toHaveValue('');
  await expect(page.locator('#login-consent')).not.toBeChecked();
  await expect(page.locator('#provision-consent')).not.toBeChecked();
});
