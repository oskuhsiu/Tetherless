import { test, expect } from './guided-test.mjs';
import { SYNTHETIC } from './guided-service.mjs';
import { makeIpa } from '../fixtures.mjs';
let ipa;
test.beforeAll(async () => { ipa = Buffer.from(await makeIpa()); });
async function assertClosed(page, guided) {
  await expect(page.locator('#account-form')).toBeHidden();
  await expect(page.locator('#apple-id')).toBeHidden(); await expect(page.locator('#apple-password')).toBeHidden();
  await page.locator('#account-form').evaluate(form => form.dispatchEvent(new Event('submit', { cancelable: true })));
  expect(guided.calls.filter(call => call.name === 'login')).toHaveLength(0);
}
async function assertReady(page, baseURL) {
  await expect(page.locator('#account-form')).toBeVisible();
  await expect(page.locator('#apple-id')).toBeVisible(); await expect(page.locator('#apple-password')).toBeVisible();
  await expect(page.locator('#login-consent')).toBeVisible();
  await expect(page.locator('#service-origin')).toHaveText(new URL(baseURL).origin);
  await expect(page.locator('#account-unavailable')).toBeHidden();
}
for (const failure of ['network', '503']) test(`service discovery: initial ${failure} retries only health then shows the verified account form`, async ({ page, context, baseURL, guided }) => {
  let attempts = 0;
  await context.route(new URL('health', baseURL).href, async route => {
    if (++attempts > 1) return route.fallback();
    if (failure === 'network') return route.abort('failed');
    await route.fulfill({ status: 503, contentType: 'text/plain', body: 'Synthetic unavailable' });
  });
  await page.goto('.'); await assertReady(page, baseURL); expect(attempts).toBe(2);
  await expect(page.locator('#account-app-prerequisite')).toBeVisible(); await expect(page.locator('#ipa')).toBeVisible();
  await expect(page.locator('#login-button')).toBeDisabled(); expect(guided.calls.filter(call => call.name === 'login')).toHaveLength(0);
});
for (const [name, response, expected] of [
  ['HTML', { contentType: 'text/html', body: '<html>Synthetic gateway</html>' }, '回應類型不是 JSON'],
  ['broken JSON', { contentType: 'application/json', body: '{' }, 'JSON 格式無效'],
  ['wrong protocol', { contentType: 'application/json', body: JSON.stringify({ protocol: 2, appleAuthAvailable: true }) }, '服務協定'],
  ['disabled account', { contentType: 'application/json', body: JSON.stringify({ protocol: 1, appleAuthAvailable: false }) }, '未啟用'],
  ['forbidden', { status: 403, contentType: 'text/plain', body: 'Synthetic forbidden' }, 'HTTP 403'],
]) test(`service discovery: ${name} remains closed and exposes safe diagnostics`, async ({ page, context, baseURL, guided }) => {
  let attempts = 0;
  await context.route(new URL('health', baseURL).href, async route => { attempts++; await route.fulfill(response); });
  await page.goto('.'); await expect(page.locator('#recheck-service')).toBeEnabled();
  await expect(page.locator('#account-unavailable')).toContainText(expected); await expect(page.locator('#account-unavailable')).toContainText(new URL('health', baseURL).pathname);
  await assertClosed(page, guided); expect(attempts).toBe(1);
  await page.locator('#recheck-service').click(); await expect.poll(() => attempts).toBe(2); await expect(page.locator('#recheck-service')).toBeEnabled(); await assertClosed(page, guided);
});
test('service discovery: a redirect never follows an alternate endpoint or reveals credentials', async ({ page, context, baseURL, guided }) => {
  let attempts = 0;
  await context.route(new URL('health', baseURL).href, async route => { attempts++; await route.fulfill({ status: 302, headers: { location: 'https://foreign.example/health' } }); });
  await page.goto('.'); await expect(page.locator('#account-unavailable')).toContainText('無法連線');
  await expect(page.locator('#recheck-service')).toBeEnabled(); await assertClosed(page, guided); expect(attempts).toBe(2); expect(guided.blocked).toEqual([]);
});
test('service discovery: persistent failure is bounded and explicit recheck recovers with a real healthy response', async ({ page, context, baseURL, guided }) => {
  let attempts = 0, healthy = false;
  await context.route(new URL('health', baseURL).href, async route => { attempts++; if (healthy) return route.fallback(); await route.fulfill({ status: 502, body: 'Synthetic unavailable' }); });
  await page.goto('.'); await expect(page.locator('#account-unavailable')).toContainText('HTTP 502'); await expect(page.locator('#recheck-service')).toBeEnabled(); await assertClosed(page, guided); expect(attempts).toBe(2);
  healthy = true; await page.locator('#recheck-service').click(); await assertReady(page, baseURL); expect(attempts).toBe(3);
});
test('service discovery: cancel and repeated recheck cannot let a stale completion clear a newer session', async ({ page, baseURL, guided }) => {
  const hold = guided.holdNext('health');
  try {
    await page.goto('.'); await hold.entered; await expect(page.locator('#cancel-service-check')).toBeVisible();
    await page.locator('#recheck-service').evaluate(button => { button.click(); button.click(); });
    expect(guided.calls.filter(call => call.path === 'health')).toHaveLength(1);
    await page.locator('#cancel-service-check').click(); await expect(page.locator('#account-unavailable')).toContainText('已取消'); await assertClosed(page, guided);
    await page.locator('#recheck-service').click(); await assertReady(page, baseURL);
    await page.setInputFiles('#ipa', { name: 'Fixture.ipa', mimeType: 'application/zip', buffer: ipa });
    await page.locator('#apple-id').fill(SYNTHETIC.appleId); await page.locator('#apple-password').fill(SYNTHETIC.password); await page.locator('#login-consent').check(); await page.locator('#login-button').click();
    await expect(page.locator('#two-factor')).toBeVisible(); hold.release();
    await expect.poll(() => guided.completed.filter(call => call.path === 'health').length).toBe(2);
    await page.locator('#recheck-service').evaluate(button => button.click());
    await expect(page.locator('#two-factor')).toBeVisible(); await expect(page.locator('#account-form')).toBeHidden();
    expect(guided.calls.filter(call => call.path === 'health')).toHaveLength(2); expect(guided.calls.filter(call => call.method === 'DELETE')).toHaveLength(0);
  } finally { hold.release(); }
});
test('service discovery: pagehide cancels pending work; persisted pageshow checks again without stale credential UI', async ({ page, baseURL, guided }) => {
  const hold = guided.holdNext('health');
  try {
    await page.goto('.'); await hold.entered;
    await page.evaluate(() => window.dispatchEvent(new PageTransitionEvent('pagehide', { persisted: true })));
    await assertClosed(page, guided); hold.release(); await expect.poll(() => guided.completed.filter(call => call.path === 'health').length).toBe(1); await assertClosed(page, guided);
    await page.evaluate(() => window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true })));
    await assertReady(page, baseURL); expect(guided.calls.filter(call => call.path === 'health')).toHaveLength(2);
  } finally { hold.release(); }
});
test('account prerequisite: null Release exposes own IPA before credentials; selected invalid file never sends credentials', async ({ page, baseURL, guided }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 }); await page.goto('.'); await assertReady(page, baseURL);
  await expect(page.locator('#account-app-prerequisite')).toBeVisible(); await expect(page.locator('#ipa')).toBeVisible(); await expect(page.locator('#manual-panel')).toBeHidden(); await expect(page.locator('#p12')).toBeHidden();
  await expect(page.locator('#login-button')).toBeDisabled(); await expect(page.locator('#ipa-prerequisite-status')).toContainText('尚未選擇');
  expect(await page.locator('#ipa').evaluate(input => input.compareDocumentPosition(document.getElementById('account-form')) & Node.DOCUMENT_POSITION_FOLLOWING)).toBeTruthy();
  await page.setInputFiles('#ipa', { name: 'Invalid.ipa', mimeType: 'application/zip', buffer: Buffer.from('not a ZIP') });
  await expect(page.locator('#ipa-prerequisite-status')).toContainText('仍會檢查'); await expect(page.locator('#login-button')).toBeEnabled();
  await page.locator('#apple-id').fill(SYNTHETIC.appleId); await page.locator('#apple-password').fill(SYNTHETIC.password); await page.locator('#login-consent').check(); await page.locator('#login-button').click();
  await expect(page.locator('#account-form')).toBeVisible(); await expect(page.locator('#login-button')).toBeEnabled(); expect(guided.calls.filter(call => call.name === 'login')).toHaveLength(0);
  await page.setInputFiles('#ipa', []); await expect(page.locator('#login-button')).toBeDisabled();
  await testInfo.attach('verified-service-own-ipa-prerequisite', { body: await page.screenshot({ fullPage: true }), contentType: 'image/png' });
});
