// SPDX-License-Identifier: AGPL-3.0-only
import { test } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import crypto, { createHash } from 'node:crypto';
import { syncBuiltinESMExports } from 'node:module';
import { createProxy, readConfig } from '../proxy.mjs';
import { gateCSP } from '../gate-page.mjs';

// Isolated test process only: even gate cookies are public deterministic fixtures.
// Keep the production entropy source unchanged; never use these in a deployment.
let cookieFixture = 0;
crypto.randomBytes = size => { assert.equal(size, 32); return Buffer.alloc(size, ++cookieFixture); };
syncBuiltinESMExports();

const SOURCE = 'a'.repeat(40);
const CODE = 'A'.repeat(43); // Synthetic fixture only, never a usable deployment code.
const BASE = { FRONTEND_ORIGIN: 'https://bootstrap.example.com',
  TETHERLESS_PUBLIC_HOST: 'bootstrap.example.com', PORT: '10000',
  TETHERLESS_TEST_ACCESS_SHA256: createHash('sha256').update(CODE).digest('hex'),
  TETHERLESS_FRONTEND_DIR: '/synthetic/frontend' };
const env = (now = Date.now()) => ({ ...BASE, TETHERLESS_TEST_EXPIRES_AT: new Date(now + 3600000).toISOString().replace('.000Z', 'Z').replace(/\.\d{3}Z$/, 'Z') });
function request(port, path = '/', { method = 'GET', headers = {}, data = '' } = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request({ hostname: '127.0.0.1', port, path, method,
      headers: { host: BASE.TETHERLESS_PUBLIC_HOST, ...headers } }, res => {
      const chunks = [];
      res.on('data', c => chunks.push(c));
      res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, body: Buffer.concat(chunks).toString() }));
    });
    req.on('error', reject); req.end(data);
  });
}
async function harness(t, { now = Date.now, delay = 0, rootStatus = 200, spoofMarker = false, accessMode, hold } = {}) {
  const received = [];
  const upstream = http.createServer((req, res) => {
    const chunks = [];
    req.on('data', c => chunks.push(c));
    req.on('end', async () => {
      received.push({ method: req.method, path: req.url, headers: req.headers, body: Buffer.concat(chunks).toString() });
      if (req.url === '/v1/slow' && hold) await hold;
      if (['/v1/slow', '/'].includes(req.url) && delay) await new Promise(r => setTimeout(r, delay));
      res.writeHead(req.url === '/' ? rootStatus : 200, { 'content-type': 'application/json', 'set-cookie': 'enrollment=fixture; Secure; HttpOnly',
        'content-security-policy': "default-src 'self'", 'connection': 'keep-alive',
        ...(spoofMarker ? { 'x-tetherless-test-access': 'granted' } : {}) });
      res.end(JSON.stringify({ ok: true }));
    });
  });
  await new Promise(resolve => upstream.listen(0, '127.0.0.1', resolve));
  const configuration = { ...env(now()), ...(accessMode === undefined ? {} : {
    TETHERLESS_PREVIEW_ACCESS_MODE: accessMode, TETHERLESS_TEST_ACCESS_SHA256: undefined }) };
  const proxy = createProxy(readConfig(configuration, now(), SOURCE), { upstreamPort: upstream.address().port, now });
  await new Promise(resolve => proxy.listen(0, '127.0.0.1', resolve));
  t.after(async () => { proxy.closeAllConnections(); upstream.closeAllConnections(); await Promise.all([
    new Promise(resolve => proxy.close(resolve)), new Promise(resolve => upstream.close(resolve))]); });
  const call = (path, options) => request(proxy.address().port, path, options);
  const unlock = async (code = CODE) => call('/_test/access', { method: 'POST',
    headers: { origin: BASE.FRONTEND_ORIGIN, 'content-type': 'application/x-www-form-urlencoded' }, data: `code=${code}` });
  return { proxy, received, call, unlock };
}

test('configuration is fail-closed and contains no credentials in errors', () => {
  const good = env();
  for (const commit of [undefined, '', 'unrecorded', 'a'.repeat(39), 'a'.repeat(41), '../main', 'g'.repeat(40)]) {
    assert.throws(() => readConfig(good, Date.now(), commit));
  }
  assert.equal(readConfig(good, Date.now(), SOURCE).host, BASE.TETHERLESS_PUBLIC_HOST);
  for (const override of [{ FRONTEND_ORIGIN: 'http://bootstrap.example.com' },
    { FRONTEND_ORIGIN: 'https://bootstrap.example.com/' }, { FRONTEND_ORIGIN: 'https://user:secret@bootstrap.example.com' },
    { TETHERLESS_PUBLIC_HOST: 'other.example.com' }, { PORT: '8787' }, { PORT: '80' },
    { PORT: '10000junk' }, { TETHERLESS_TEST_ACCESS_SHA256: '' },
    { TETHERLESS_TEST_EXPIRES_AT: '2000-01-01T00:00:00Z' },
    { TETHERLESS_TEST_EXPIRES_AT: '2099-01-01T00:00:00Z' }, { TETHERLESS_FRONTEND_DIR: 'relative' }]) {
    assert.throws(() => readConfig({ ...good, ...override }, Date.now(), SOURCE), e => !e.message.includes('secret'));
  }
});
test('gate is visible and CSP-compatible, APIs remain denied, exact health only is public', async t => {
  const h = await harness(t);
  const gate = await h.call('/'); assert.equal(gate.status, 200); assert.match(gate.body, /Test access code/);
  assert.equal(gate.headers['content-security-policy'], gateCSP);
  assert.equal(gate.headers['x-tetherless-test-access'], undefined);
  assert.match(gate.body, /id="generate-code"/);
  assert.match(gate.body, /id="test-access-sha256"[^>]*><\/output>/);
  assert.ok(!gate.body.includes(BASE.TETHERLESS_TEST_ACCESS_SHA256));
  assert.ok(gate.body.includes(`https://github.com/oskuhsiu/Tetherless/tree/${SOURCE}`));
  assert.ok(gate.body.includes(`https://github.com/oskuhsiu/Tetherless/blob/${SOURCE}/LICENSE`));
  assert.ok(!gate.body.includes('/tree/main'));
  assert.equal((await h.call('/_test/access')).body, gate.body);
  for (const path of ['/v1/sessions', '/wasm/zsign-mobile.wasm', '/health/', '/health?x=1']) {
    assert.notEqual((await h.call(path)).status, 200);
  }
  assert.equal((await h.call('/health')).status, 200);
  assert.equal((await h.call('/health', { headers: { host: 'wrong.example.com', 'x-forwarded-host': BASE.TETHERLESS_PUBLIC_HOST } })).status, 403);
  assert.equal(h.received.length, 1);
});
test('code requires explicit same-origin POST, strong length, and bounded attempts', async t => {
  const h = await harness(t);
  assert.equal((await h.call('/_test/access', { method: 'POST', data: `code=${CODE}` })).status, 403);
  assert.equal((await h.unlock('weak')).status, 401);
  assert.equal((await h.unlock('B'.repeat(43))).status, 401);
  for (let i = 0; i < 4; i++) assert.equal((await h.unlock('bad')).status, 401);
  assert.equal((await h.unlock()).status, 429);
  assert.equal(h.received.length, 0);
});
test('gate cookie is secure, bounded, separate from Apple auth and stripped upstream', async t => {
  const h = await harness(t);
  const opened = await h.unlock(); assert.equal(opened.status, 303);
  assert.equal(opened.headers.location, '/');
  const set = opened.headers['set-cookie'][0];
  for (const flag of ['Path=/', 'Secure', 'HttpOnly', 'SameSite=Lax', 'Max-Age=1800']) assert.ok(set.includes(flag));
  const cookie = set.split(';')[0];
  const answer = await h.call('/v1/sessions/fixture', { headers: { cookie: `${cookie}; enrollment=fixture`,
    authorization: 'Bearer SYNTHETIC-ONLY', origin: BASE.FRONTEND_ORIGIN,
    'x-forwarded-for': '1.2.3.4', 'x-forwarded-host': 'hostile.example.com', forwarded: 'host=hostile.example.com' } });
  assert.equal(answer.status, 200);
  assert.equal(answer.headers['content-security-policy'], "default-src 'self'");
  assert.equal(answer.headers['cache-control'], 'no-store');
  assert.equal(h.received[0].headers.host, BASE.TETHERLESS_PUBLIC_HOST);
  assert.equal(h.received[0].headers.origin, BASE.FRONTEND_ORIGIN);
  assert.equal(h.received[0].headers.authorization, 'Bearer SYNTHETIC-ONLY');
  assert.equal(h.received[0].headers.cookie, 'enrollment=fixture');
  assert.equal(h.received[0].headers['x-forwarded-for'], undefined);
  assert.equal(h.received[0].headers.forwarded, undefined);
  assert.deepEqual(answer.headers['set-cookie'], ['enrollment=fixture; Secure; HttpOnly']);
  assert.equal((await h.call('/v1/sessions/fixture', { headers: { cookie: `${cookie}; ${cookie}` } })).status, 401);
});
test('only exact no-Origin enrollment callback bypasses gate; mutation and gate window stay bounded', async t => {
  let time = Date.now(); const h = await harness(t, { now: () => time });
  const callback = '/v1/device-enrollments/12345678-1234-4234-8234-123456789012/callback';
  assert.equal((await h.call(callback, { method: 'POST', data: 'synthetic CMS only' })).status, 200);
  for (const path of [callback + '/', callback.replace('callback', 'profile/fixture'), callback.replace('12345678', 'invalid')]) {
    assert.equal((await h.call(path, { method: 'POST' })).status, 401);
  }
  assert.equal((await h.call(callback, { method: 'POST', headers: { origin: BASE.FRONTEND_ORIGIN } })).status, 401);
  time += 3600001;
  assert.equal((await h.call(callback, { method: 'POST' })).status, 410);
  assert.equal((await h.unlock()).status, 410);
  assert.equal((await h.call('/health')).status, 200);
  const closed = await h.call('/'); assert.equal(closed.status, 410);
  assert.ok(closed.body.includes(`/tree/${SOURCE}`));
  assert.ok(closed.body.includes(`/blob/${SOURCE}/LICENSE`));
  assert.match(closed.body, /disabled/);
});
test('cookies expire in memory and at most four browser gates can exist', async t => {
  let time = Date.now(); const h = await harness(t, { now: () => time });
  let cookie;
  for (let i = 0; i < 4; i++) { const r = await h.unlock(); assert.equal(r.status, 303); cookie = r.headers['set-cookie'][0].split(';')[0]; }
  assert.equal((await h.unlock()).status, 429);
  time += 1800001;
  assert.equal((await h.call('/v1/sessions/fixture', { headers: { cookie } })).status, 401);
  assert.equal((await h.unlock()).status, 303);
});
test('request bodies and login attempts are bounded and never retried', async t => {
  const h = await harness(t); const opened = await h.unlock(); const cookie = opened.headers['set-cookie'][0].split(';')[0];
  const headers = { cookie, origin: BASE.FRONTEND_ORIGIN, 'content-type': 'application/json' };
  const large = await h.call('/v1/fixture', { method: 'POST', headers, data: 'x'.repeat(32769) });
  assert.equal(large.status, 413);
  assert.equal(h.received.length, 0);
  for (let i = 0; i < 3; i++) assert.equal((await h.call('/v1/sessions', { method: 'POST', headers, data: '{"fixture":true}' })).status, 200);
  assert.equal((await h.call('/v1/sessions', { method: 'POST', headers, data: '{}' })).status, 429);
  assert.equal(h.received.length, 3);
  assert.equal(h.received[0].body, '{"fixture":true}');
});
test('hop-by-hop nominations cannot remove Host, Origin or authorization gates', async t => {
  const h = await harness(t);
  for (const connection of ['origin', 'authorization', 'cookie', 'host', 'content-length']) {
    assert.equal((await h.call('/health', { headers: { connection } })).status, 400);
  }
  assert.equal(h.received.length, 0);
});


test('health checks cannot exhaust a public quota and starve platform liveness', async t => {
  const h = await harness(t);
  for (let i = 0; i < 125; i++) assert.equal((await h.call('/health')).status, 200);
});

test('authorization is checked again after slow body input', async t => {
  let time = Date.now(); const h = await harness(t, { now: () => time });
  const opened = await h.unlock(); const cookie = opened.headers['set-cookie'][0].split(';')[0];
  const result = new Promise((resolve, reject) => {
    const req = http.request({ hostname: '127.0.0.1', port: h.proxy.address().port, path: '/v1/synthetic-mutation', method: 'POST',
      headers: { host: BASE.TETHERLESS_PUBLIC_HOST, origin: BASE.FRONTEND_ORIGIN, cookie, 'content-type': 'application/json' } }, res => {
      res.resume(); res.on('end', () => resolve(res.statusCode));
    });
    req.on('error', reject); req.write('{"fixture":');
    setTimeout(() => { time += 3600001; req.end('true}'); }, 20);
  });
  assert.equal(await result, 410); assert.equal(h.received.length, 0);
});

test('new gate cookie cannot be issued after expiry during body input', async t => {
  let time = Date.now(); const h = await harness(t, { now: () => time });
  const result = new Promise((resolve, reject) => {
    const req = http.request({ hostname: '127.0.0.1', port: h.proxy.address().port, path: '/_test/access', method: 'POST',
      headers: { host: BASE.TETHERLESS_PUBLIC_HOST, origin: BASE.FRONTEND_ORIGIN, 'content-type': 'application/x-www-form-urlencoded' } }, res => {
      res.resume(); res.on('end', () => resolve({ status: res.statusCode, cookies: res.headers['set-cookie'] }));
    });
    req.on('error', reject); req.write('code=');
    setTimeout(() => { time += 3600001; req.end(CODE); }, 20);
  });
  assert.deepEqual(await result, { status: 410, cookies: undefined }); assert.equal(h.received.length, 0);
});

test('response window exceeds input timeout without retrying a slow operation', { timeout: 20000 }, async t => {
  const h = await harness(t, { delay: 16000 }); const opened = await h.unlock(); const cookie = opened.headers['set-cookie'][0].split(';')[0];
  const response = await h.call('/v1/slow', { method: 'POST', headers: { cookie, origin: BASE.FRONTEND_ORIGIN }, data: 'synthetic' });
  assert.equal(response.status, 200); assert.equal(h.received.length, 1);
});


test('only authenticated successful root readback gets a non-spoofable proof marker', async t => {
  const h = await harness(t, { spoofMarker: true });
  for (const path of ['/', '/_test/access', '/health', '/v1/synthetic']) {
    assert.equal((await h.call(path)).headers['x-tetherless-test-access'], undefined);
  }
  const opened = await h.unlock(); assert.equal(opened.status, 303);
  assert.equal(opened.headers.location, '/'); assert.equal(opened.headers['x-tetherless-test-access'], undefined);
  const cookie = opened.headers['set-cookie'][0].split(';')[0];
  const root = await h.call('/', { headers: { cookie } });
  assert.equal(root.status, 200); assert.equal(root.headers['x-tetherless-test-access'], 'granted');
  for (const path of ['/health', '/v1/synthetic', '/_test/access']) {
    assert.equal((await h.call(path, { headers: { cookie } })).headers['x-tetherless-test-access'], undefined);
  }
  assert.equal((await h.call('/', { method: 'HEAD', headers: { cookie } })).headers['x-tetherless-test-access'], undefined);
  assert.equal((await h.call('/', { headers: { cookie: '__Host-tetherless-test=' + 'B'.repeat(43) } })).headers['x-tetherless-test-access'], undefined);
});
test('failed root response cannot masquerade as successful unlock even with an upstream marker', async t => {
  const h = await harness(t, { rootStatus: 503, spoofMarker: true });
  const opened = await h.unlock(); const cookie = opened.headers['set-cookie'][0].split(';')[0];
  const root = await h.call('/', { headers: { cookie } });
  assert.equal(root.status, 503); assert.equal(root.headers['x-tetherless-test-access'], undefined);
});
test('expired root readback never grants proof and closed page has no runnable Generate code', async t => {
  let time = Date.now(); const h = await harness(t, { now: () => time, delay: 40, spoofMarker: true });
  const opened = await h.unlock(); const cookie = opened.headers['set-cookie'][0].split(';')[0];
  const pending = h.call('/', { headers: { cookie } });
  setTimeout(() => { time += 3600001; }, 20);
  const root = await pending; assert.equal(root.headers['x-tetherless-test-access'], undefined);
  const closed = await h.call('/'); assert.equal(closed.status, 410);
  assert.doesNotMatch(closed.body, /<script>/); assert.match(closed.body, /測試期限已結束/);
});


test('preview access mode defaults gated, rejects unknown values and allows public without a digest', () => {
  const good = env();
  assert.equal(readConfig(good, Date.now(), SOURCE).accessMode, 'gated');
  assert.equal(readConfig({ ...good, TETHERLESS_PREVIEW_ACCESS_MODE: 'gated' }, Date.now(), SOURCE).accessMode, 'gated');
  for (const value of ['', 'PUBLIC', ' public', 'public ', 'disabled', 'false', null, false, 0]) {
    assert.throws(() => readConfig({ ...good, TETHERLESS_PREVIEW_ACCESS_MODE: value }, Date.now(), SOURCE));
  }
  assert.throws(() => readConfig({ ...good, TETHERLESS_TEST_ACCESS_SHA256: undefined }, Date.now(), SOURCE));
  for (const digest of [undefined, '', good.TETHERLESS_TEST_ACCESS_SHA256]) {
    const config = readConfig({ ...good, TETHERLESS_PREVIEW_ACCESS_MODE: 'public', TETHERLESS_TEST_ACCESS_SHA256: digest }, Date.now(), SOURCE);
    assert.equal(config.accessMode, 'public'); assert.equal(config.digest, undefined);
  }
  for (const override of [{ FRONTEND_ORIGIN: 'http://bootstrap.example.com' },
    { TETHERLESS_PUBLIC_HOST: 'wrong.example.com' }, { TETHERLESS_TEST_EXPIRES_AT: '2000-01-01T00:00:00Z' }]) {
    assert.throws(() => readConfig({ ...good, TETHERLESS_PREVIEW_ACCESS_MODE: 'public', ...override }, Date.now(), SOURCE));
  }
});

test('public root and assets need no preview cookie and never emit an upstream-spoofed granted marker', async t => {
  const h = await harness(t, { accessMode: 'public', spoofMarker: true });
  for (const path of ['/', '/licenses.html', '/wasm/zsign-mobile.wasm', '/health']) {
    const answer = await h.call(path);
    assert.equal(answer.status, 200); assert.equal(answer.headers['x-tetherless-test-access'], undefined);
    assert.doesNotMatch(answer.body, /Test access code|generate-code/);
    assert.equal(answer.headers['cache-control'], 'no-store');
  }
  assert.equal(h.received.length, 4);
  assert.ok(h.received.every(r => !r.headers.cookie));
});

test('public access endpoint only redirects GET and never generates or issues a preview cookie', async t => {
  const h = await harness(t, { accessMode: 'public' }); const before = cookieFixture;
  const get = await h.call('/_test/access');
  assert.equal(get.status, 303); assert.equal(get.headers.location, '/'); assert.equal(get.body, '');
  assert.equal(get.headers['set-cookie'], undefined); assert.equal(get.headers['x-tetherless-test-access'], undefined);
  for (const method of ['POST', 'HEAD', 'DELETE', 'OPTIONS']) {
    const answer = await h.call('/_test/access', { method, headers: { origin: BASE.FRONTEND_ORIGIN,
      'content-type': 'application/x-www-form-urlencoded' }, data: method === 'POST' ? `code=${CODE}` : '' });
    assert.equal(answer.status, 404); assert.equal(answer.headers['set-cookie'], undefined);
    assert.equal(answer.headers['x-tetherless-test-access'], undefined);
  }
  assert.equal(cookieFixture, before); assert.equal(h.received.length, 0);
});

test('public mode strips obsolete preview cookies while preserving independent authority and Origin', async t => {
  const h = await harness(t, { accessMode: 'public' });
  const obsolete = '__Host-tetherless-test=' + 'B'.repeat(43);
  assert.equal((await h.call('/v1/synthetic', { headers: { cookie: `${obsolete}; enrollment=fixture; ${obsolete}`,
    authorization: 'Bearer SYNTHETIC-ONLY', origin: BASE.FRONTEND_ORIGIN, 'x-forwarded-host': 'hostile.example.com' } })).status, 200);
  assert.equal(h.received[0].headers.cookie, 'enrollment=fixture');
  assert.equal(h.received[0].headers.authorization, 'Bearer SYNTHETIC-ONLY');
  assert.equal(h.received[0].headers.origin, BASE.FRONTEND_ORIGIN);
  assert.equal(h.received[0].headers.host, BASE.TETHERLESS_PUBLIC_HOST);
  assert.equal(h.received[0].headers['x-forwarded-host'], undefined);
  assert.equal((await h.call('/', { headers: { host: 'hostile.example.com' } })).status, 403);
  for (const connection of ['host', 'origin', 'authorization', 'cookie', 'content-length']) {
    assert.equal((await h.call('/v1/synthetic', { headers: { connection } })).status, 400);
  }
  assert.equal((await h.call('/?code=fixture')).status, 400);
  assert.equal((await h.call('/', { method: 'PUT' })).status, 405);
  assert.equal((await h.call('/', { headers: { 'x-oversized': 'x'.repeat(16384) } })).status, 400);
  assert.equal(h.received.length, 1); assert.equal(h.proxy.maxConnections, 64);
});

test('public mode retains body limits, login-start rate and no automatic retries', async t => {
  const h = await harness(t, { accessMode: 'public', now: () => Date.parse('2030-01-01T00:00:00Z') });
  const headers = { origin: BASE.FRONTEND_ORIGIN, 'content-type': 'application/json' };
  assert.equal((await h.call('/v1/synthetic', { method: 'POST', headers, data: 'x'.repeat(32769) })).status, 413);
  assert.equal(h.received.length, 0);
  for (let i = 0; i < 3; i++) assert.equal((await h.call('/v1/sessions', { method: 'POST', headers, data: '{}' })).status, 200);
  assert.equal((await h.call('/v1/sessions', { method: 'POST', headers, data: '{}' })).status, 429);
  assert.equal(h.received.length, 3);
});

test('public mode retains general, mutation and callback quotas with separate healthy liveness', async t => {
  const now = () => Date.parse('2030-01-01T00:00:00Z');
  const all = await harness(t, { accessMode: 'public', now });
  for (let i = 0; i < 240; i++) assert.equal((await all.call('/')).status, 200);
  assert.equal((await all.call('/')).status, 429); assert.equal((await all.call('/health')).status, 200);
  const mutate = await harness(t, { accessMode: 'public', now });
  for (let i = 0; i < 30; i++) assert.equal((await mutate.call('/v1/synthetic', { method: 'POST' })).status, 200);
  assert.equal((await mutate.call('/v1/synthetic', { method: 'POST' })).status, 429);
  const callback = await harness(t, { accessMode: 'public', now });
  const path = '/v1/device-enrollments/12345678-1234-4234-8234-123456789012/callback';
  for (let i = 0; i < 10; i++) assert.equal((await callback.call(path, { method: 'POST' })).status, 200);
  assert.equal((await callback.call(path, { method: 'POST' })).status, 429);
});

test('public mode retains the sixteen active request cap without starving health', { timeout: 5000 }, async t => {
  let release; const hold = new Promise(resolve => { release = resolve; });
  const h = await harness(t, { accessMode: 'public', hold });
  const pending = Array.from({ length: 16 }, () => h.call('/v1/slow'));
  while (h.received.length < 16) await new Promise(resolve => setTimeout(resolve, 2));
  try {
    assert.equal((await h.call('/')).status, 503);
    assert.equal((await h.call('/health')).status, 200);
  } finally { release(); }
  assert.ok((await Promise.all(pending)).every(answer => answer.status === 200));
});

test('public expiry closes root with exact source links and no gate controls, including slow body input', async t => {
  let time = Date.now(); const h = await harness(t, { accessMode: 'public', now: () => time });
  const result = new Promise((resolve, reject) => {
    const req = http.request({ hostname: '127.0.0.1', port: h.proxy.address().port, path: '/v1/synthetic', method: 'POST',
      headers: { host: BASE.TETHERLESS_PUBLIC_HOST, origin: BASE.FRONTEND_ORIGIN, 'content-type': 'application/json' } }, res => {
      res.resume(); res.on('end', () => resolve(res.statusCode));
    });
    req.on('error', reject); req.write('{"fixture":');
    setTimeout(() => { time += 3600001; req.end('true}'); }, 20);
  });
  assert.equal(await result, 410); assert.equal(h.received.length, 0);
  for (const path of ['/', '/_test/access']) {
    const closed = await h.call(path); assert.equal(closed.status, 410);
    assert.match(closed.body, /測試期限已結束/);
    assert.ok(closed.body.includes(`/tree/${SOURCE}`)); assert.ok(closed.body.includes(`/blob/${SOURCE}/LICENSE`));
    assert.doesNotMatch(closed.body, /<script|<form|<input|<button|generate-code|access-code|Open test/);
    assert.equal(closed.headers['set-cookie'], undefined); assert.equal(closed.headers['x-tetherless-test-access'], undefined);
  }
  assert.equal((await h.call('/wasm/zsign-mobile.wasm')).status, 410);
  assert.equal((await h.call('/_test/access', { method: 'POST' })).status, 410);
  assert.equal((await h.call('/health')).status, 200);
});
