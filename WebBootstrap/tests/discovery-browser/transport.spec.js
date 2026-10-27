import { test, expect } from '@playwright/test';
import { createDiscoveryFixture } from './server.mjs';
let fixture, origin, blocked;
test.beforeAll(async () => { fixture = createDiscoveryFixture(); origin = await fixture.start(); });
test.afterAll(async () => { await fixture.close(); });
test.beforeEach(async ({ context, page }) => {
  blocked = [];
  await context.route('**/*', async route => {
    const req = route.request();
    if (new URL(req.url()).origin === origin && req.method() === 'GET') return route.continue();
    blocked.push({ method: req.method(), url: req.url() });
    await route.abort('blockedbyclient');
  });
  await context.routeWebSocket('**/*', socket => { blocked.push({ method: 'WEBSOCKET', url: socket.url() }); socket.close(); });
  await page.goto(origin);
});
test.afterEach(async ({}, testInfo) => {
  await testInfo.attach('blocked-discovery-requests', { body: JSON.stringify(blocked), contentType: 'application/json' });
  expect(blocked, 'No discovery request may leave the exact fixture origin or mutate a service').toEqual([]);
});
async function check(page, path, options = {}) {
  return page.evaluate(async ({ path, options }) => {
    const { discoverAccountService } = await import('/src/account-discovery.js');
    const controller = new AbortController();
    const fetcher = async (...args) => { const response = await fetch(...args); if (options.cancel) setTimeout(() => controller.abort(), 10); return response; };
    try { return await discoverAccountService({ base: new URL(path, location.origin).href, origin: location.origin, signal: controller.signal, fetcher, timeoutMs: options.timeoutMs || 1000, retryDelayMs: 1 }); }
    catch (error) { return { aborted: error.name === 'AbortError' }; }
  }, { path, options });
}
test('real JSON response works with the production fetch options', async ({ page }) => {
  const { path, entry } = fixture.add('healthy'); expect((await check(page, path)).kind).toBe('ready'); expect(entry.calls).toBe(1);
});
for (const mode of ['redirect-local', 'redirect-foreign']) for (const status of [301, 302, 307, 308]) test(`${mode} ${status} is identified without following or retrying`, async ({ page }) => {
  const { path, entry } = fixture.add(mode, status); const result = await check(page, path);
  expect(result.kind).toBe('invalid'); expect(result.diagnostic).toContain('重新導向'); expect(entry.calls).toBe(1); expect(fixture.redirected).toBe(0);
});
test('a socket interruption after headers retries once and recovers', async ({ page }) => {
  const { path, entry } = fixture.add('interrupted-first'); expect((await check(page, path)).kind).toBe('ready'); expect(entry.calls).toBe(2); expect(entry.headers).toBe(1);
});
test('repeated interrupted bodies remain bounded and unverified', async ({ page }) => {
  const { path, entry } = fixture.add('interrupted'); const result = await check(page, path);
  expect(result.kind).toBe('unreachable'); expect(result.diagnostic).toContain('讀取回應'); expect(entry.calls).toBe(2); expect(entry.headers).toBe(2);
});
for (const mode of ['truncated', 'oversized']) test(`${mode} JSON stays invalid without retry`, async ({ page }) => {
  const { path, entry } = fixture.add(mode); expect((await check(page, path)).kind).toBe('invalid'); expect(entry.calls).toBe(1);
});
test('a delayed first response recovers through the bounded read-only retry', async ({ page }) => {
  const { path, entry } = fixture.add('delayed-first'); expect((await check(page, path, { timeoutMs: 100 })).kind).toBe('ready'); expect(entry.calls).toBe(2);
});
test('two delayed responses time out and cannot enable credentials', async ({ page }) => {
  const { path, entry } = fixture.add('delayed'); const result = await check(page, path, { timeoutMs: 100 });
  expect(result.kind).toBe('unreachable'); expect(result.diagnostic).toContain('逾時'); expect(entry.calls).toBe(2);
});
test('cancelling a body read prevents health retry and config fallback', async ({ page }) => {
  const { path, entry } = fixture.add('interrupted'); expect(await check(page, path, { cancel: true })).toEqual({ aborted: true }); expect(entry.calls).toBe(1); expect(entry.config).toBe(0);
});

test('direct health navigation can succeed while page policy blocks fetch; never bypass policy', async ({ page }) => {
  const { path, entry } = fixture.add('healthy');
  const direct = await page.goto(origin + path + 'health');
  expect((await direct.json()).appleAuthAvailable).toBe(true);
  await page.goto(origin + '/blocked');
  const result = await check(page, path);
  expect(result.kind).toBe('unreachable'); expect(result.diagnostic).toContain('瀏覽器無法讀取回應');
  expect(entry.calls).toBe(1); // Only the direct navigation reached the server.
  await page.goto(origin);
  expect((await check(page, path)).kind).toBe('ready');
});
