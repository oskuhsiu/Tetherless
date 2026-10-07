// SPDX-License-Identifier: AGPL-3.0-only
import { test, expect } from '@playwright/test';
import { createHarness, GATE_URL, ORIGIN, PUBLIC_CODE, PUBLIC_DIGEST, FIXTURE_EXPIRY } from './harness.mjs';

let h;
test.afterEach(async ({}, testInfo) => {
  if (!h) return;
  const current = h;
  h = undefined;
  const failed = testInfo.status !== testInfo.expectedStatus;
  try {
    if (failed) {
      const screenshot = testInfo.outputPath('public-fixture-failure.png');
      await current.page.screenshot({ path: screenshot, fullPage: true });
      await testInfo.attach('public-fixture-screenshot', { path: screenshot, contentType: 'image/png' });
    }
  } finally {
    const tracePath = failed ? testInfo.outputPath('public-fixture-trace.zip') : undefined;
    await current.close({ tracePath });
    if (tracePath) await testInfo.attach('public-fixture-trace', { path: tracePath, contentType: 'application/zip' });
  }
});
async function setup(browser, options) {
  h = await createHarness(browser, options);
  const response = await h.openGate();
  expect(response.status()).toBe(200);
  return h.page;
}
async function generate(page) {
  await expect(page.locator('#generate-code')).toBeEnabled();
  await page.locator('#generate-code').click(); // Genuine Chromium user gesture, fixture RNG only.
  await expect(page.locator('#access-code')).toHaveValue(PUBLIC_CODE);
  await expect(page.locator('#test-access-sha256')).toHaveText(PUBLIC_DIGEST);
  expect(await page.locator('#test-access-sha256').textContent()).toBe(PUBLIC_DIGEST);
  await expect(page.locator('details')).not.toHaveAttribute('open');
  await expect(page.locator('#open-test')).toBeEnabled();
}
async function assertPrivateState(page) {
  expect(await page.evaluate(() => ({
    visibleText: document.body.textContent,
    html: document.documentElement.outerHTML,
    local: localStorage.length,
    session: sessionStorage.length,
    attempts: __publicGateFixture.storageAttempts,
    violations: __publicGateFixture.cspViolations,
  }))).toEqual({ visibleText: expect.not.stringContaining(PUBLIC_CODE),
    html: expect.not.stringContaining(PUBLIC_CODE), local: 0, session: 0, attempts: [], violations: [] });
  await expect(page.locator('#access-code')).toHaveAttribute('type', 'password');
  await expect(page.locator('#access-code')).toHaveAttribute('readonly', '');
  expect((await h.context.storageState()).origins).toEqual([]);
  expect(await page.evaluate(() => indexedDB.databases())).toEqual([]);
  expect(await page.evaluate(() => caches.keys())).toEqual([]);
}

// Traces/reports may contain PUBLIC_CODE. It is fixed test data, never a secret.
test('initial gate executes under its real CSP without randomness, submission or persistence', async ({ browser }) => {
  const page = await setup(browser);
  await expect(page.locator('#generate-code')).toBeEnabled();
  await expect(page.locator('#access-code')).toHaveValue('');
  await expect(page.locator('#test-access-sha256')).toHaveText('');
  await expect(page.locator('#open-test')).toBeDisabled();
  await expect(page.locator('#test-expiry')).toHaveText(FIXTURE_EXPIRY);
  await expect(page.locator('#test-expiry')).toHaveAttribute('datetime', FIXTURE_EXPIRY);
  expect(await page.evaluate(() => ({ secure: isSecureContext, random: __publicGateFixture.randomCalls,
    digest: __publicGateFixture.digestCalls }))).toEqual({ secure: true, random: 0, digest: 1 });
  expect(h.requests).toEqual([{ method: 'GET', path: '/_test/access', origin: null, resourceType: 'document', hasCookie: false }]);
  expect(h.upstreamRequests).toEqual([]);
  const csp = await page.evaluate(async () => {
    // Inspect policy through the existing document's meta-independent violation
    // behavior. Unhashed inline script is blocked by the actual response policy.
    const script = document.createElement('script');
    script.textContent = 'globalThis.__unapprovedGateScriptRan = true';
    document.head.append(script); script.remove();
    await new Promise(resolve => setTimeout(resolve, 0));
    return { ran: globalThis.__unapprovedGateScriptRan === true, violations: __publicGateFixture.cspViolations.splice(0) };
  });
  expect(csp.ran).toBe(false);
  expect(csp.violations).toContain('script-src-elem');
  await assertPrivateState(page);
});

test('only trusted Generate creates one fixture code and exposes only its verifier', async ({ browser }) => {
  const page = await setup(browser);
  await expect(page.locator('#generate-code')).toBeEnabled();
  await page.locator('#generate-code').evaluate(button => button.click());
  expect(await page.evaluate(() => __publicGateFixture.randomCalls)).toBe(0);
  await generate(page);
  await expect(page.locator('#generate-code')).toBeDisabled();
  const box = await page.locator('#generate-code').boundingBox();
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2, { clickCount: 2 });
  await page.locator('#open-test').evaluate(button => button.click()); // Synthetic Open is ignored too.
  expect(await page.evaluate(() => __publicGateFixture.randomCalls)).toBe(1);
  expect(await page.evaluate(() => __publicGateFixture.trustedClicks)).toContainEqual({ id: 'generate-code', trusted: true });
  expect(h.requests).toHaveLength(1);
  expect(h.upstreamRequests).toEqual([]);
  expect(await h.context.cookies()).toEqual([]);
  await assertPrivateState(page);
});

test('rejected Open retains the original masked code and never navigates or automatically retries', async ({ browser }) => {
  const page = await setup(browser);
  await generate(page);
  await page.locator('#open-test').click();
  await expect(page.locator('#gate-status')).toContainText('測試碼仍保留');
  await expect(page.locator('#open-test')).toBeEnabled();
  await expect(page).toHaveURL(GATE_URL);
  await expect(page.locator('#access-code')).toHaveValue(PUBLIC_CODE);
  await expect(page.locator('#test-access-sha256')).toHaveText(PUBLIC_DIGEST);
  expect(h.responses.at(-1).status).toBe(401);
  await page.clock.fastForward(30_000);
  expect(h.requests.filter(request => request.method === 'POST')).toHaveLength(1);
  expect(h.upstreamRequests).toEqual([]);
  await assertPrivateState(page);
});

test('successful explicit Open follows real 303 and secure cookie readback before root navigation', async ({ browser }) => {
  const page = await setup(browser, { configured: true });
  await generate(page);
  await page.locator('#open-test').click();
  await expect(page).toHaveURL(`${ORIGIN}/`);
  await expect(page.locator('#synthetic-open')).toBeVisible();
  expect(h.responses).toEqual([
    { method: 'GET', path: '/_test/access', status: 200, marker: null },
    { method: 'POST', path: '/_test/access', status: 303, marker: null },
    { method: 'GET', path: '/', status: 200, marker: 'granted' },
    { method: 'GET', path: '/', status: 200, marker: 'granted' },
  ]);
  // Pinned Chromium CDP reports the redirected fetch readback as XHR.
  expect(h.requests.slice(2).map(request => ({ type: request.resourceType, cookie: request.hasCookie })))
    .toEqual([{ type: 'xhr', cookie: true }, { type: 'document', cookie: true }]);
  expect(h.upstreamRequests).toEqual([{ method: 'GET', path: '/' }, { method: 'GET', path: '/' }]);
  const cookies = await h.context.cookies();
  expect(cookies).toHaveLength(1);
  expect(cookies[0]).toMatchObject({ name: '__Host-tetherless-test', domain: 'bootstrap.example.com',
    path: '/', secure: true, httpOnly: true, sameSite: 'Lax' });
  expect(await page.evaluate(() => document.cookie)).toBe('');
});

test('service reconfiguration keeps the original page and code available for the next explicit Open', async ({ browser }) => {
  const page = await setup(browser);
  await generate(page);
  await page.locator('#open-test').click();
  await expect(page.locator('#gate-status')).toContainText('測試碼仍保留');
  await h.restart(true);
  await expect(page).toHaveURL(GATE_URL);
  await expect(page.locator('#access-code')).toHaveValue(PUBLIC_CODE);
  await expect(page.locator('#test-expiry')).toHaveText(FIXTURE_EXPIRY);
  expect(h.requests).toHaveLength(2);
  expect(await page.evaluate(() => __publicGateFixture.randomCalls)).toBe(1);
  await page.locator('#open-test').click();
  await expect(page.locator('#synthetic-open')).toBeVisible();
  expect(h.requests.filter(request => request.method === 'POST')).toHaveLength(2);
});

test('restart between 303 and readback cannot mistake a fresh gate for access, and explicit retry works', async ({ browser }) => {
  const page = await setup(browser, { configured: true });
  await generate(page);
  h.restartAfterNextUnlock();
  await page.locator('#open-test').click();
  await expect(page.locator('#gate-status')).toContainText('測試碼仍保留');
  await expect(page).toHaveURL(GATE_URL);
  await expect(page.locator('#access-code')).toHaveValue(PUBLIC_CODE);
  expect(h.responses.slice(-2)).toEqual([
    { method: 'POST', path: '/_test/access', status: 303, marker: null },
    { method: 'GET', path: '/', status: 200, marker: null },
  ]);
  expect(h.upstreamRequests).toEqual([]);
  await page.locator('#open-test').click();
  await expect(page.locator('#synthetic-open')).toBeVisible();
});

for (const mode of ['missing', 'blocked']) {
  test(`${mode} WebCrypto fails closed without randomness or network submission`, async ({ browser }) => {
    const page = await setup(browser, { cryptoMode: mode });
    await expect(page.locator('#gate-status')).toContainText('無法產生測試碼');
    await expect(page.locator('#generate-code')).toBeDisabled();
    await expect(page.locator('#open-test')).toBeDisabled();
    await expect(page.locator('#access-code')).toHaveValue('');
    expect(await page.evaluate(() => __publicGateFixture.randomCalls)).toBe(0);
    expect(h.requests).toHaveLength(1);
    await assertPrivateState(page);
  });
}

test('repeated gestures and a digest finishing after expiry cannot publish or submit a late code', async ({ browser }) => {
  const page = await setup(browser, { cryptoMode: 'deferred' });
  await expect(page.locator('#generate-code')).toBeEnabled();
  const box = await page.locator('#generate-code').boundingBox();
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2, { clickCount: 2 });
  await expect(page.locator('#generate-code')).toBeDisabled();
  expect(await page.evaluate(() => __publicGateFixture.randomCalls)).toBe(1);
  await page.clock.fastForward(3_600_001);
  await page.evaluate(() => __publicGateFixture.releaseDigest());
  await expect(page.locator('#gate-status')).toContainText('測試期限已結束');
  await expect(page.locator('#access-code')).toHaveValue('');
  await expect(page.locator('#test-access-sha256')).toHaveText('');
  await expect(page.locator('#generate-code')).toBeDisabled();
  await expect(page.locator('#open-test')).toBeDisabled();
  expect(h.requests).toHaveLength(1);
  await assertPrivateState(page);
});

test('duplicate Open gestures remain single-flight and pagehide invalidates an outstanding result', async ({ browser }) => {
  const page = await setup(browser, { configured: true });
  await generate(page);
  const release = h.holdNextPost();
  const box = await page.locator('#open-test').boundingBox();
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2, { clickCount: 2 });
  await expect.poll(() => h.requests.filter(request => request.method === 'POST').length).toBe(1);
  await expect(page.locator('#open-test')).toBeDisabled();
  await page.evaluate(() => dispatchEvent(new Event('pagehide')));
  release();
  await expect(page.locator('#access-code')).toHaveValue('');
  await expect(page.locator('#test-access-sha256')).toHaveText('');
  await expect(page.locator('#gate-status')).toContainText('此頁未保留測試碼');
  await expect(page.locator('#open-test')).toBeDisabled();
  await expect(page).toHaveURL(GATE_URL);
  expect(h.requests.filter(request => request.method === 'POST')).toHaveLength(1);
  await assertPrivateState(page);
});
