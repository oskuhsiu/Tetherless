import test from 'node:test';
import assert from 'node:assert/strict';
import { discoverAccountService } from '../src/account-discovery.js';
const base = 'https://service.example/Tetherless/';
const health = { protocol: 1, appleAuthAvailable: true, profileServiceAvailable: true };
function reply(url, body, { status = 200, type = 'application/json', finalUrl = url, redirected = false } = {}) {
  const response = new Response(typeof body === 'string' ? body : JSON.stringify(body), { status, headers: { 'content-type': type } });
  Object.defineProperties(response, { url: { value: finalUrl }, redirected: { value: redirected } }); return response;
}
async function check(handler, options = {}) {
  const calls = [];
  const result = await discoverAccountService({ base, origin: 'https://service.example', signal: new AbortController().signal, timeoutMs: 20, retryDelayMs: 1,
    fetcher: async (url, opts) => { calls.push({ url, opts }); return url.endsWith('/config.json') ? reply(url, { accountServiceUrl: null }) : handler(url, opts, calls.filter(c => c.url.endsWith('/health')).length); }, ...options });
  return { result, calls };
}
test('health capability is exact and same-origin; request safety is retained', async () => {
  const { result, calls } = await check(url => reply(url, health)); assert.deepEqual(result, { kind: 'ready', profileAvailable: true }); assert.equal(calls.length, 1);
  assert.equal(calls[0].url, `${base}health`); assert.equal(calls[0].opts.redirect, 'error'); assert.equal(calls[0].opts.credentials, 'same-origin'); assert.equal(calls[0].opts.cache, 'no-store'); assert(calls[0].opts.signal);
});
for (const first of ['network', 'timeout', '503']) test(`${first} retries once then accepts a real verified response`, async () => {
  const { result, calls } = await check((url, opts, count) => {
    if (count > 1) return reply(url, health);
    if (first === 'network') throw new TypeError('synthetic fetch failure');
    if (first === '503') return reply(url, 'down', { status: 503, type: 'text/plain' });
    return new Promise((_, reject) => { const keepAlive = setTimeout(() => {}, 100); opts.signal.addEventListener('abort', () => { clearTimeout(keepAlive); reject(opts.signal.reason); }, { once: true }); });
  });
  assert.equal(result.kind, 'ready'); assert.equal(calls.filter(c => c.url.endsWith('/health')).length, 2);
});
test('persistent transient failures are bounded to two attempts, and never expose a service', async () => {
  const { result, calls } = await check(() => { throw new TypeError('offline'); }); assert.equal(result.kind, 'unreachable'); assert.equal(calls.length, 3);
});
for (const [name, body, options, kind = 'invalid'] of [
  ['HTML', '<html>not health</html>', { type: 'text/html' }], ['broken JSON', '{', {}], ['null', null, {}], ['false', false, {}], ['zero', 0, {}], ['array', [], {}],
  ['wrong protocol', { ...health, protocol: '1' }, {}], ['truthy auth', { ...health, appleAuthAvailable: 'true' }, {}], ['missing auth', { protocol: 1 }, {}],
  ['unconfigured', { ...health, appleAuthAvailable: false }, {}, 'unconfigured'], ['not found', {}, { status: 404 }, 'unconfigured'], ['forbidden', {}, { status: 403 }, 'unreachable'],
  ['foreign response', health, { finalUrl: 'https://foreign.example/health' }], ['redirected', health, { redirected: true }], ['oversized', ' '.repeat(16385), {}],
]) test(`${name} fails closed without automatic health retry`, async () => {
  const { result, calls } = await check(url => reply(url, body, options)); assert.equal(result.kind, kind); assert.equal(calls.filter(c => c.url.endsWith('/health')).length, 1);
});
test('foreign base cannot fetch discovery or enable credential collection', async () => {
  const { result, calls } = await check(() => { throw new Error('must not fetch'); }, { base: 'https://foreign.example/' }); assert.deepEqual(result, { kind: 'invalid' }); assert.equal(calls.length, 0);
});
test('cancellation during retry backoff stops all remaining reads', async () => {
  const controller = new AbortController(); let calls = 0;
  await assert.rejects(discoverAccountService({ base, origin: 'https://service.example', signal: controller.signal, retryDelayMs: 200,
    fetcher: async url => { calls++; setTimeout(() => controller.abort(), 1); return reply(url, {}, { status: 503 }); } }), { name: 'AbortError' });
  assert.equal(calls, 1);
});
test('configured external service is only a link and is never queried', async () => {
  const calls = [];
  const result = await discoverAccountService({ base, origin: 'https://service.example', signal: new AbortController().signal,
    fetcher: async url => { calls.push(url); return reply(url, url.endsWith('/health') ? { protocol: 1, appleAuthAvailable: false } : { accountServiceUrl: 'https://other.example/' }); } });
  assert.equal(result.kind, 'unconfigured'); assert.equal(result.externalUrl, 'https://other.example/'); assert.match(result.diagnostic, /HTTP 200/); assert(calls.every(url => new URL(url).origin === 'https://service.example'));
});
test('discovery works without AbortSignal.timeout, any or throwIfAborted', async () => {
  const originals = [AbortSignal.timeout, AbortSignal.any, AbortSignal.prototype.throwIfAborted];
  try {
    AbortSignal.timeout = undefined; AbortSignal.any = undefined; AbortSignal.prototype.throwIfAborted = undefined;
    const { result } = await check(url => reply(url, health)); assert.equal(result.kind, 'ready');
  } finally { [AbortSignal.timeout, AbortSignal.any, AbortSignal.prototype.throwIfAborted] = originals; }
});
test('safe diagnostic contains only the public origin, health path and classified result', async () => {
  const { result } = await check(url => reply(url, { error: 'secret-response-must-not-be-displayed' }, { status: 403 }), { origin: 'https://service.example/?private=value#fragment' });
  assert.equal(result.diagnostic, '頁面 https://service.example；/Tetherless/health：HTTP 403；服務回應未成功');
  assert(!result.diagnostic.includes('secret')); assert(!result.diagnostic.includes('private'));
});
