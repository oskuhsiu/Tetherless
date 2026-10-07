// SPDX-License-Identifier: AGPL-3.0-only
// PUBLIC DETERMINISTIC FIXTURES ONLY. Never point this harness at a deployment.
import assert from 'node:assert/strict';
import http from 'node:http';
import crypto, { createHash } from 'node:crypto';
import { syncBuiltinESMExports } from 'node:module';
import { createProxy, readConfig } from '../../../Tools/WebBootstrapService/deployment/proxy.mjs';

export const ORIGIN = 'https://bootstrap.example.com';
export const GATE_URL = `${ORIGIN}/_test/access`;
export const FIXTURE_NOW = Date.parse('2030-01-01T00:00:00Z');
export const FIXTURE_EXPIRY = '2030-01-01T01:00:00Z';
export const PUBLIC_BYTES = Array.from({ length: 32 }, (_, i) => i);
export const PUBLIC_CODE = Buffer.from(PUBLIC_BYTES).toString('base64url');
export const PUBLIC_DIGEST = createHash('sha256').update(PUBLIC_CODE).digest('hex');
const PLACEHOLDER_DIGEST = createHash('sha256').update('PUBLIC UNCONFIGURED FIXTURE').digest('hex');
const SOURCE = 'a'.repeat(40);

// Isolated synthetic test process only, including the proxy's session cookies.
// Playwright also uses randomBytes for IDs; unique public counters support it
// without ever delegating to the real entropy API. Production stays unchanged.
let randomFixture = 0;
crypto.randomBytes = (size, callback) => {
  assert.ok(Number.isInteger(size) && size >= 0 && size <= 1024 * 1024);
  const bytes = Buffer.alloc(size, 0x50);
  let counter = BigInt(++randomFixture);
  for (let i = 0; i < Math.min(size, 8); i += 1) { bytes[i] = Number(counter & 255n); counter >>= 8n; }
  if (typeof callback === 'function') { queueMicrotask(() => callback(null, bytes)); return; }
  return bytes;
};
syncBuiltinESMExports();

async function listen(server) {
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  return server.address().port;
}
async function close(server) {
  if (!server?.listening) return;
  const done = new Promise(resolve => server.close(resolve));
  server.closeAllConnections();
  await done;
}
function bridge(port, path, method, headers, body) {
  return new Promise((resolve, reject) => {
    const request = http.request({ hostname: '127.0.0.1', port, path, method, headers, timeout: 5_000 }, response => {
      const chunks = [];
      response.on('data', chunk => chunks.push(chunk));
      response.on('error', reject);
      response.on('end', () => resolve({ status: response.statusCode,
        headers: response.headers, body: Buffer.concat(chunks) }));
    });
    request.on('timeout', () => request.destroy(new Error('Synthetic loopback request timed out')));
    request.on('error', reject);
    request.end(body);
  });
}

export async function createHarness(browser, { configured = false, cryptoMode = 'normal' } = {}) {
  const failures = [];
  const requests = [];
  const responses = [];
  const upstreamRequests = [];
  let proxy;
  let port;
  let restartAfterUnlock = false;
  let holdPost;
  let releasePost;
  let closing = false;
  const upstream = http.createServer((request, response) => {
    if (request.method !== 'GET' || request.url !== '/' || request.headers.host !== new URL(ORIGIN).host ||
        request.headers.authorization || request.headers.cookie) {
      failures.push('Unexpected fake-upstream request or forwarded credential');
      response.writeHead(403); response.end(); return;
    }
    upstreamRequests.push({ method: request.method, path: request.url });
    response.writeHead(200, { 'content-type': 'text/html; charset=utf-8',
      'content-security-policy': "default-src 'none'" });
    response.end('<!doctype html><html><head><title>Public synthetic upstream</title></head><body><h1 id="synthetic-open">Public synthetic test opened</h1></body></html>');
  });
  const upstreamPort = await listen(upstream);
  async function restart(acceptFixture = configured) {
    await close(proxy);
    configured = acceptFixture;
    const config = readConfig({ FRONTEND_ORIGIN: ORIGIN, TETHERLESS_PUBLIC_HOST: new URL(ORIGIN).host,
      PORT: '10000', TETHERLESS_TEST_ACCESS_SHA256: configured ? PUBLIC_DIGEST : PLACEHOLDER_DIGEST,
      TETHERLESS_TEST_EXPIRES_AT: FIXTURE_EXPIRY, TETHERLESS_FRONTEND_DIR: '/public-synthetic-fixture' }, FIXTURE_NOW, SOURCE);
    proxy = createProxy(config, { upstreamPort, now: () => FIXTURE_NOW });
    port = await listen(proxy);
  }
  await restart();
  const context = await browser.newContext({ serviceWorkers: 'block' });
  await context.tracing?.start({ screenshots: true, snapshots: true, sources: true });
  await context.addInitScript(({ bytes, mode }) => {
    // Installed before EVERY page script; the real random API is never called.
    const state = { randomCalls: 0, digestCalls: 0, storageAttempts: [], cspViolations: [], trustedClicks: [] };
    Object.defineProperty(globalThis, '__publicGateFixture', { value: state });
    Object.defineProperty(crypto, 'getRandomValues', { configurable: true, value: target => {
      state.randomCalls += 1;
      if (!(target instanceof Uint8Array) || target.length !== bytes.length) throw new Error('Fixture supports exactly 32 bytes');
      target.set(bytes); return target;
    } });
    const digest = crypto.subtle.digest.bind(crypto.subtle);
    if (mode === 'missing') {
      Object.defineProperty(crypto, 'subtle', { configurable: true, value: undefined });
    } else {
      Object.defineProperty(crypto.subtle, 'digest', { configurable: true, value: async (algorithm, data) => {
        state.digestCalls += 1;
        if (mode === 'blocked') throw new Error('Public fixture WebCrypto denial');
        if (mode === 'deferred' && data.byteLength === 43) {
          await new Promise(resolve => { state.releaseDigest = resolve; });
        }
        return digest(algorithm, data);
      } });
    }
    const blocked = name => () => { state.storageAttempts.push(name); throw new Error('Persistence prohibited by fixture'); };
    Object.defineProperty(Storage.prototype, 'setItem', { configurable: true, value: blocked('Storage.setItem') });
    Object.defineProperty(indexedDB, 'open', { configurable: true, value: blocked('indexedDB.open') });
    Object.defineProperty(caches, 'open', { configurable: true, value: blocked('caches.open') });
    Object.defineProperty(navigator, 'sendBeacon', { configurable: true, value: blocked('sendBeacon') });
    if (navigator.clipboard) Object.defineProperty(navigator.clipboard, 'writeText', { configurable: true, value: blocked('clipboard.writeText') });
    document.addEventListener('securitypolicyviolation', event => state.cspViolations.push(event.violatedDirective));
    document.addEventListener('click', event => {
      if (event.target?.id === 'generate-code' || event.target?.id === 'open-test') {
        state.trustedClicks.push({ id: event.target.id, trusted: event.isTrusted });
      }
    }, true);
  }, { bytes: PUBLIC_BYTES, mode: cryptoMode });
  const intercept = async route => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    const permitted = url.origin === ORIGIN && !url.search && !url.hash && !url.username && !url.password &&
      ((url.pathname === '/_test/access' && ['GET', 'POST'].includes(method)) || (url.pathname === '/' && method === 'GET'));
    if (!permitted) {
      failures.push(`Blocked unexpected browser request: ${method} ${url.origin}${url.pathname}`);
      await route.abort('blockedbyclient'); return;
    }
    const headers = await request.allHeaders();
    // Chromium supplies Origin/cookies. Only virtual HTTPS authority is bridged
    // to HTTP transport; no Origin, redirect or cookie is fabricated by tests.
    if (headers.host && headers.host !== url.host) failures.push('Browser host mismatch');
    headers.host = url.host;
    const body = request.postDataBuffer();
    if (method === 'POST') {
      assert.equal(headers.origin, ORIGIN);
      assert.equal(headers['content-type']?.split(';')[0], 'application/x-www-form-urlencoded');
      assert.equal(body?.toString(), new URLSearchParams({ code: PUBLIC_CODE }).toString());
    }
    requests.push({ method, path: url.pathname, origin: headers.origin ?? null,
      resourceType: request.resourceType(), hasCookie: Boolean(headers.cookie) });
    if (method === 'POST' && holdPost) await holdPost;
    let result;
    try { result = await bridge(port, url.pathname, method, headers, body); }
    catch {
      await route.abort('connectionfailed'); return;
    }
    responses.push({ method, path: url.pathname, status: result.status,
      marker: result.headers['x-tetherless-test-access'] ?? null });
    if (restartAfterUnlock && result.status === 303) {
      restartAfterUnlock = false;
      await restart(true); // Destroy server-side cookie session before redirected GET.
    }
    const outgoing = {};
    for (const [key, value] of Object.entries(result.headers)) {
      if (value !== undefined && !['connection', 'keep-alive', 'transfer-encoding', 'content-length'].includes(key)) {
        outgoing[key] = Array.isArray(value) ? value.join('\n') : String(value);
      }
    }
    await route.fulfill({ status: result.status, headers: outgoing, body: result.body });
  };
  await context.routeWebSocket('**/*', socket => {
    failures.push('Blocked unexpected browser WebSocket');
    socket.close();
  });
  const page = await context.newPage();
  // Playwright 1.58.2 context.route auto-continues redirected requests. Chromium
  // Fetch interception is required here to keep EVERY redirect hop off-network.
  // This is transport interception only: Chromium still follows the 303, applies
  // its cookies, enforces the real CSP and decides fetch's redirected/url values.
  const session = await context.newCDPSession(page);
  const cancelled = new Set();
  session.on('Network.loadingFailed', event => { if (event.canceled) cancelled.add(event.requestId); });
  session.on('Fetch.requestPaused', event => {
    const request = event.request;
    const headers = Object.fromEntries(Object.entries(request.headers).map(([name, value]) => [name.toLowerCase(), value]));
    void intercept({
      request: () => ({ url: () => request.url, method: () => request.method,
        allHeaders: async () => headers, postDataBuffer: () => request.postData === undefined ? null : Buffer.from(request.postData),
        resourceType: () => event.resourceType.toLowerCase() }),
      abort: () => session.send('Fetch.failRequest', { requestId: event.requestId, errorReason: 'BlockedByClient' }),
      fulfill: response => session.send('Fetch.fulfillRequest', { requestId: event.requestId, responseCode: response.status,
        responseHeaders: Object.entries(response.headers).flatMap(([name, value]) => value.split('\n').map(part => ({ name, value: part }))),
        body: response.body.toString('base64') }),
    }).catch(error => {
      if (closing || cancelled.has(event.networkId)) return;
      failures.push(`Chromium fixture interception failed: ${error.message}`);
      void session.send('Fetch.failRequest', { requestId: event.requestId, errorReason: 'BlockedByClient' }).catch(() => {});
    });
  });
  await session.send('Network.enable');
  await session.send('Fetch.enable', { patterns: [{ urlPattern: '*', requestStage: 'Request' }] });
  const pageErrors = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  await page.clock.install({ time: new Date(FIXTURE_NOW) });
  return { context, page, failures, requests, responses, upstreamRequests, pageErrors, restart,
    restartAfterNextUnlock() { restartAfterUnlock = true; },
    holdNextPost() {
      holdPost = new Promise(resolve => { releasePost = resolve; });
      return () => { releasePost(); holdPost = undefined; };
    },
    async openGate() { return page.goto(GATE_URL); },
    async close({ tracePath } = {}) {
      releasePost?.();
      closing = true;
      await context.tracing?.stop(tracePath ? { path: tracePath } : {});
      await context.close();
      await Promise.all([close(proxy), close(upstream)]);
      assert.deepEqual(failures, []);
      assert.deepEqual(pageErrors, []);
    },
  };
}
