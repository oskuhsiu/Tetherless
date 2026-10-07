// SPDX-License-Identifier: AGPL-3.0-only
// These are harness/HTTP checks, not substitutes for the Chromium assertions.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHarness, ORIGIN, PUBLIC_CODE, PUBLIC_DIGEST, FIXTURE_EXPIRY } from './harness.mjs';
import { gateCSP } from '../../../Tools/WebBootstrapService/deployment/gate-page.mjs';

async function fixture(t, options) {
  const installed = [];
  let handler;
  let pendingResponse;
  const context = {
    async addInitScript(fn, args) { installed.push({ kind: 'init', fn, args }); },
    async routeWebSocket(pattern) { installed.push({ kind: 'websocket', pattern }); },
    async newCDPSession() { return {
      on(name, fn) { if (name === 'Fetch.requestPaused') handler = fn; },
      async send(name, value) {
        if (name === 'Fetch.enable') installed.push({ kind: 'intercept', patterns: value.patterns });
        if (name === 'Fetch.failRequest') pendingResponse({ aborted: 'blockedbyclient' });
        if (name === 'Fetch.fulfillRequest') pendingResponse({ status: value.responseCode,
          headers: Object.fromEntries(value.responseHeaders.map(header => [header.name, header.value])), body: Buffer.from(value.body, 'base64') });
      },
    }; },
    async newPage() { installed.push({ kind: 'page' }); return { on() {}, clock: { async install() {} } }; },
    async close() {},
  };
  const h = await createHarness({ async newContext() { return context; } }, options);
  t.after(() => h.close());
  async function request(path, { origin = ORIGIN, method = 'GET', headers = {}, body } = {}) {
    return new Promise(resolve => {
      pendingResponse = resolve;
      handler({ requestId: 'fixture-request', networkId: 'fixture-network', resourceType: 'Document',
        request: { url: new URL(path, origin).href, method, headers: { ...headers }, postData: body } });
    });
  }

  const open = () => request('/_test/access', { method: 'POST', headers: {
    origin: ORIGIN, 'content-type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams({ code: PUBLIC_CODE }).toString() });
  return { h, installed, request, open };
}

test('deterministic RNG init precedes page creation and all browser traffic is intercepted', async t => {
  const f = await fixture(t);
  assert.deepEqual(f.installed.map(entry => entry.kind), ['init', 'websocket', 'page', 'intercept']);
  assert.equal(f.installed[1].pattern, '**/*');
  assert.deepEqual(f.installed[3].patterns, [{ urlPattern: '*', requestStage: 'Request' }]);
  assert.deepEqual(f.installed[0].args.bytes, Array.from({ length: 32 }, (_, i) => i));
  assert.equal(PUBLIC_CODE, 'AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8');
  assert.match(PUBLIC_DIGEST, /^[a-f0-9]{64}$/);
  const response = await f.request('/_test/access');
  assert.equal(response.status, 200);
  assert.equal(response.headers['content-security-policy'], gateCSP);
  assert.ok(response.body.toString().includes(FIXTURE_EXPIRY));
  assert.deepEqual(f.h.upstreamRequests, []);
});

test('request sandbox denies external, account, query and unsupported-method traffic', async t => {
  const f = await fixture(t);
  const cases = [
    ['https://example.org/'], ['/v1/sessions'], ['/?code=PUBLIC'], ['/_test/access?debug=1'],
    ['/', { method: 'POST' }], ['/_test/access', { method: 'DELETE' }],
  ];
  for (const [path, options] of cases) assert.deepEqual(await f.request(path, options), { aborted: 'blockedbyclient' });
  assert.equal(f.h.failures.splice(0).length, cases.length); // Expected sandbox denials only.
  assert.deepEqual(f.h.requests, []);
  assert.deepEqual(f.h.upstreamRequests, []);
});

test('real proxy bridge preserves CSP, 303, secure cookie and authenticated root marker', async t => {
  const f = await fixture(t, { configured: true });
  const result = await f.open();
  assert.equal(result.status, 303);
  assert.equal(result.headers.location, '/');
  const setCookie = result.headers['set-cookie'];
  assert.match(setCookie, /^__Host-tetherless-test=[A-Za-z0-9_-]{43}; Path=\/; Secure; HttpOnly; SameSite=Lax; Max-Age=1800$/);
  const response = await f.request('/', { headers: { cookie: setCookie.split(';')[0] } });
  assert.equal(response.status, 200);
  assert.equal(response.headers['x-tetherless-test-access'], 'granted');
  assert.match(response.body.toString(), /Public synthetic test opened/);
  assert.deepEqual(f.h.upstreamRequests, [{ method: 'GET', path: '/' }]);
  assert.equal(f.h.requests[0].origin, ORIGIN);
});

test('restarting the bridge swaps only loopback services and loses old cookie authority', async t => {
  const f = await fixture(t);
  assert.equal((await f.open()).status, 401);
  await f.h.restart(true);
  const opened = await f.open();
  assert.equal(opened.status, 303);
  await f.h.restart(true);
  const readback = await f.request('/', { headers: { cookie: opened.headers['set-cookie'].split(';')[0] } });
  assert.equal(readback.status, 200);
  assert.equal(readback.headers['x-tetherless-test-access'], undefined);
  assert.match(readback.body.toString(), /generate-code/);
  assert.deepEqual(f.h.upstreamRequests, []);
});
