// SPDX-License-Identifier: AGPL-3.0-only
// All randomness is replaced by public deterministic bytes. No browser/real code.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash, webcrypto } from 'node:crypto';
import vm from 'node:vm';
import { gatePage, gateCSP } from '../gate-page.mjs';
const SOURCE = 'a'.repeat(40);
const NOW = Date.parse('2026-10-07T05:00:00Z');
const END = Date.parse('2026-10-08T04:00:00Z');
const scriptOf = html => html.match(/<script>([\s\S]*?)<\/script>/)[1];
const html = gatePage(SOURCE, END);
const settle = () => new Promise(resolve => setImmediate(resolve));
function deferred() { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; }
async function fixture({ byte = 0, secure = true, random = true, digest = webcrypto.subtle.digest.bind(webcrypto.subtle), fetch: send } = {}) {
  const nodes = new Map();
  for (const id of ['generate-code', 'open-test', 'access-code', 'test-access-sha256', 'gate-status', 'test-expiry', 'access-form']) {
    nodes.set(id, { value: '', textContent: '', disabled: true, dateTime: new Date(END).toISOString(), handlers: new Map(),
      addEventListener(event, listener) { this.handlers.set(event, listener); } });
  }
  const events = new Map(), timers = new Map(), calls = [], randomBuffers = [], digestBuffers = [], navigation = [];
  let time = NOW, timerId = 0, firstDigest;
  const context = { document: { getElementById: id => nodes.get(id) },
    window: { addEventListener: (event, listener) => events.set(event, listener) },
    isSecureContext: secure, Uint8Array, TextEncoder, URLSearchParams, AbortController,
    btoa: text => Buffer.from(text, 'binary').toString('base64'),
    Date: class extends Date { static now() { return time; } },
    crypto: { getRandomValues: random ? bytes => { randomBuffers.push(bytes); bytes.fill(byte); return bytes; } : undefined,
      subtle: { digest: (algorithm, bytes) => { digestBuffers.push(bytes); const result = digest(algorithm, bytes); if (digestBuffers.length === 1) firstDigest = result; return result; } } },
    fetch: async (path, options) => { calls.push({ path, options }); return send ? send(path, options) : { status: 401, redirected: false, url: 'https://bootstrap.example.com/_test/access', headers: new Headers() }; },
    location: { origin: 'https://bootstrap.example.com', assign: path => navigation.push(path) },
    setTimeout: (fn, ms) => { const id = ++timerId; timers.set(id, { fn, ms }); return id; },
    clearTimeout: id => timers.delete(id),
  };
  vm.runInNewContext(scriptOf(html), context);
  await Promise.resolve(firstDigest).catch(() => {});
  await settle();
  const fire = (id, event = 'click', trusted = true) => nodes.get(id).handlers.get(event)?.({ isTrusted: trusted, preventDefault() {} });
  return { nodes, events, timers, calls, randomBuffers, digestBuffers, navigation, fire, context, setTime: value => { time = value; } };
}
const codeFor = byte => Buffer.alloc(32, byte).toString('base64url');
const digestFor = byte => createHash('sha256').update(codeFor(byte), 'utf8').digest('hex');

test('exact CSP hashes allow only reviewed script/style and same-origin gate traffic', () => {
  for (const tag of ['script', 'style']) {
    const value = html.match(new RegExp(`<${tag}>([\\s\\S]*?)<\\/${tag}>`))[1];
    assert.ok(gateCSP.includes(`${tag}-src 'sha256-${createHash('sha256').update(value).digest('base64')}'`));
  }
  assert.match(gateCSP, /default-src 'none'/); assert.match(gateCSP, /connect-src 'self'/);
  assert.doesNotMatch(gateCSP, /unsafe-inline|unsafe-eval|https:|\*/);
  assert.match(html, /id="access-code"[^>]*type="password" readonly/);
  assert.match(html, /雲端 Chrome/); assert.match(html, /其他瀏覽器/);
  assert.match(html, /2026-10-08T04:00:00Z/);
  assert.doesNotMatch(scriptOf(html), /localStorage|sessionStorage|indexedDB|clipboard|console\.|sendBeacon|XMLHttpRequest|document\.cookie|innerHTML/);
  const closed = gatePage(SOURCE, END, true);
  assert.doesNotMatch(closed, /<script>/); assert.match(closed, /測試期限已結束/);
  assert.ok(closed.includes(`/tree/${SOURCE}`)); assert.ok(closed.includes(`/blob/${SOURCE}/LICENSE`));
});
test('initial load and untrusted Generate/Open never request randomness or transmit', async () => {
  const h = await fixture();
  assert.equal(h.randomBuffers.length, 0); assert.equal(h.calls.length, 0);
  assert.equal(h.digestBuffers.length, 1); assert.equal(h.digestBuffers[0].length, 0);
  assert.equal(h.nodes.get('generate-code').disabled, false); assert.equal(h.nodes.get('open-test').disabled, true);
  await h.fire('generate-code', 'click', false); await h.fire('open-test', 'click', false);
  assert.equal(h.randomBuffers.length, 0); assert.equal(h.calls.length, 0);
});
for (const byte of [0, 127, 255]) test(`fixture ${byte}: base64url32 → 43-char UTF8 string SHA256; raw buffers are cleared`, async () => {
  const h = await fixture({ byte }); await h.fire('generate-code');
  assert.equal(h.nodes.get('access-code').value, codeFor(byte));
  assert.equal(h.nodes.get('test-access-sha256').textContent, digestFor(byte));
  assert.equal(h.nodes.get('generate-code').disabled, true); assert.equal(h.nodes.get('open-test').disabled, false);
  assert.equal(h.calls.length, 0); assert.equal(h.randomBuffers.length, 1);
  assert.ok(h.randomBuffers[0].every(value => value === 0)); assert.ok(h.digestBuffers[1].every(value => value === 0));
  for (const node of h.nodes.values()) assert.ok(!node.textContent.includes(codeFor(byte)));
});
test('repeated Generate preserves the original code and verifier, including in-flight double click', async () => {
  const hold = deferred(); let count = 0;
  const h = await fixture({ digest: (algorithm, bytes) => ++count === 1 ? webcrypto.subtle.digest(algorithm, bytes) : hold.promise });
  const first = h.fire('generate-code'); await h.fire('generate-code');
  assert.equal(h.randomBuffers.length, 1);
  hold.resolve(await webcrypto.subtle.digest('SHA-256', new TextEncoder().encode(codeFor(0)))); await first;
  await h.fire('generate-code');
  assert.equal(h.randomBuffers.length, 1); assert.equal(h.nodes.get('test-access-sha256').textContent, digestFor(0));
});
test('unavailable or incorrect WebCrypto fails closed without fallback randomness', async () => {
  for (const options of [{ secure: false }, { random: false }, { digest: async () => new Uint8Array(32).buffer }, { digest: async () => { throw new Error('synthetic failure'); } }]) {
    const h = await fixture(options); await h.fire('generate-code');
    assert.equal(h.nodes.get('generate-code').disabled, true); assert.equal(h.randomBuffers.length, 0); assert.equal(h.calls.length, 0);
  }
});
test('failed generation publishes neither secret nor verifier and permits a fresh explicit try', async () => {
  let count = 0;
  const h = await fixture({ digest: (algorithm, bytes) => ++count === 2 ? Promise.reject(new Error('synthetic failure')) : webcrypto.subtle.digest(algorithm, bytes) });
  await h.fire('generate-code'); assert.equal(h.nodes.get('access-code').value, ''); assert.equal(h.nodes.get('test-access-sha256').textContent, '');
  assert.equal(h.nodes.get('generate-code').disabled, false);
  await h.fire('generate-code'); assert.equal(h.nodes.get('test-access-sha256').textContent, digestFor(0));
});
test('401/429/503/network failures retain code, never navigate or automatically retry', async () => {
  for (const status of [401, 429, 503, 'network']) {
    const h = await fixture({ fetch: async () => { if (status === 'network') throw new Error('synthetic'); return { status }; } });
    await h.fire('generate-code'); await h.fire('open-test', 'click', false); assert.equal(h.calls.length, 0);
    await h.fire('open-test'); assert.equal(h.calls.length, 1); assert.equal(h.navigation.length, 0);
    assert.equal(h.nodes.get('access-code').value, codeFor(0)); assert.equal(h.nodes.get('test-access-sha256').textContent, digestFor(0));
    const { path, options } = h.calls[0];
    assert.equal(path, '/_test/access'); assert.equal(options.method, 'POST');
    assert.equal(options.credentials, 'same-origin'); assert.equal(options.mode, 'same-origin');
    assert.equal(options.cache, 'no-store'); assert.equal(options.redirect, 'follow');
    assert.equal(options.body.toString(), `code=${codeFor(0)}`);
    assert.equal(options.headers['content-type'], 'application/x-www-form-urlencoded');
    assert.equal(Object.keys(options.headers).length, 1);
    assert.equal(h.nodes.get('open-test').disabled, false);
  }
});
test('Open rejects direct success, wrong destination, missing root proof and failed redirect response', async () => {
  const good = { status: 200, redirected: true, url: 'https://bootstrap.example.com/', headers: new Headers({ 'x-tetherless-test-access': 'granted' }) };
  for (const override of [{ redirected: false }, { url: 'https://hostile.example.com/' }, { url: 'https://bootstrap.example.com/?code=bad' }, { status: 503 }, { headers: new Headers() }]) {
    const h = await fixture({ fetch: async () => ({ ...good, ...override }) });
    await h.fire('generate-code'); await h.fire('open-test'); assert.equal(h.navigation.length, 0);
    assert.equal(h.nodes.get('access-code').value, codeFor(0));
  }
  const h = await fixture({ fetch: async () => good }); await h.fire('generate-code'); await h.fire('open-test');
  assert.deepEqual(h.navigation, ['/']);
});
test('in-flight duplicate Open submits once and timeout retains the original credential', async () => {
  const h = await fixture({ fetch: (_path, options) => new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(new Error('synthetic abort')))) });
  await h.fire('generate-code'); const pending = h.fire('open-test'); await h.fire('open-test');
  assert.equal(h.calls.length, 1); assert.equal(h.nodes.get('open-test').disabled, true);
  [...h.timers.values()].find(timer => timer.ms === 20000).fn(); await pending;
  assert.equal(h.nodes.get('access-code').value, codeFor(0)); assert.equal(h.nodes.get('open-test').disabled, false); assert.equal(h.calls.length, 1);
});
test('pagehide prevents a late hash result from restoring a departed page', async () => {
  const hold = deferred(); let count = 0;
  const h = await fixture({ digest: (algorithm, bytes) => ++count === 1 ? webcrypto.subtle.digest(algorithm, bytes) : hold.promise });
  const pending = h.fire('generate-code'); h.events.get('pagehide')();
  hold.resolve(await webcrypto.subtle.digest('SHA-256', new TextEncoder().encode(codeFor(0)))); await pending;
  assert.equal(h.nodes.get('access-code').value, ''); assert.equal(h.nodes.get('test-access-sha256').textContent, '');
});
test('expiry during generation cannot publish a new code and expiry during Open cannot navigate', async () => {
  const hold = deferred(); let count = 0;
  const h = await fixture({ digest: (algorithm, bytes) => ++count === 1 ? webcrypto.subtle.digest(algorithm, bytes) : hold.promise });
  const pending = h.fire('generate-code'); h.setTime(END);
  hold.resolve(await webcrypto.subtle.digest('SHA-256', new TextEncoder().encode(codeFor(0)))); await pending;
  assert.equal(h.nodes.get('access-code').value, ''); assert.equal(h.nodes.get('generate-code').disabled, true);
  const response = deferred(); const second = await fixture({ fetch: () => response.promise });
  await second.fire('generate-code'); const opening = second.fire('open-test'); second.setTime(END);
  response.resolve({ status: 200, redirected: true, url: 'https://bootstrap.example.com/', headers: new Headers({ 'x-tetherless-test-access': 'granted' }) }); await opening;
  assert.equal(second.navigation.length, 0); assert.equal(second.nodes.get('open-test').disabled, true);
});
test('pagehide removes field and verifier; warning protects ordinary navigation until verified success', async () => {
  const h = await fixture(); await h.fire('generate-code'); let prevented = false;
  h.events.get('beforeunload')({ preventDefault() { prevented = true; } }); assert.ok(prevented);
  h.events.get('pagehide')(); assert.equal(h.nodes.get('access-code').value, ''); assert.equal(h.nodes.get('test-access-sha256').textContent, '');
  prevented = false; h.events.get('beforeunload')({ preventDefault() { prevented = true; } }); assert.equal(prevented, false);
});
