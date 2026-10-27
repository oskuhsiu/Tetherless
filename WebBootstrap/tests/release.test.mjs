import test from 'node:test';
import assert from 'node:assert/strict';
import { validateRelease, acquireRelease, verifyReleaseFile, MAX_RELEASE_BYTES } from '../src/release.js';
const bytes = new TextEncoder().encode('synthetic release bytes, not an installable app');
const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(b => b.toString(16).padStart(2, '0')).join('');
const manifest = { repository: 'oskuhsiu/Tetherless', tag: 'v-test', assetId: '123', assetName: 'Tetherless-unsigned.ipa', assetUrl: 'https://github.com/oskuhsiu/Tetherless/releases/download/v-test/Tetherless-unsigned.ipa', size: bytes.length, sha256: hash, sourceCommit: 'a'.repeat(40), buildRunId: '12345', buildHeadSha: 'b'.repeat(40), runAttempt: 1 };
test('release: a complete pinned identity is required; no latest fallback', () => {
  assert.throws(() => validateRelease(null), /尚未綁定/);
  for (const key of Object.keys(manifest)) { const bad = { ...manifest }; delete bad[key]; assert.throws(() => validateRelease(bad), key); }
  assert.deepEqual(validateRelease(manifest), manifest);
  assert.throws(() => validateRelease({ ...manifest, repository: 'someone/Tetherless' }));
  assert.throws(() => validateRelease({ ...manifest, assetId: 123 }));
  assert.throws(() => validateRelease({ ...manifest, buildRunId: 12345 }));
  for (const runAttempt of [0, -1, 1.1, '1', Infinity]) assert.throws(() => validateRelease({ ...manifest, runAttempt }));
});
test('release: rejects unbounded size, wrong origin, asset path, credentials and query', () => {
  for (const size of [0, -1, MAX_RELEASE_BYTES + 1, 1.1, Infinity]) assert.throws(() => validateRelease({ ...manifest, size }));
  for (const assetUrl of ['https://evil.invalid/a.ipa', manifest.assetUrl + '?token=x', manifest.assetUrl.replace('/v-test/', '/latest/'), manifest.assetUrl.replace('https://', 'https://user:pass@')]) assert.throws(() => validateRelease({ ...manifest, assetUrl }));
});
test('release: direct acquisition checks exact digest/size without credentials or referrer', async () => {
  let options; const file = await acquireRelease(manifest, { fetcher: async (url, opts) => { assert.equal(url, manifest.assetUrl); options = opts; return new Response(bytes); } });
  assert.equal(file.name, manifest.assetName); assert.equal(file.size, bytes.length);
  assert.equal(options.credentials, 'omit'); assert.equal(options.referrerPolicy, 'no-referrer'); assert.equal(options.mode, 'cors');
});
test('release: locally selected official file must match the pinned digest', async () => {
  await verifyReleaseFile(new File([bytes], 'downloaded.ipa'), manifest);
  const wrong = bytes.slice(); wrong[0] ^= 1;
  await assert.rejects(verifyReleaseFile(new File([wrong], 'downloaded.ipa'), manifest), /SHA-256/);
  await assert.rejects(verifyReleaseFile(new File([bytes.slice(1)], 'downloaded.ipa'), manifest), /大小/);
});
test('release: CORS failure explains local exact-file fallback; 404 is not success', async () => {
  await assert.rejects(acquireRelease(manifest, { fetcher: async () => { throw new TypeError('Failed to fetch'); } }), /CORS/);
  await assert.rejects(acquireRelease(manifest, { fetcher: async () => new Response('missing', { status: 404 }) }), /404/);
});
test('release: oversize stream is cancelled before accepting bytes', async () => {
  let cancelled = false;
  const stream = new ReadableStream({ pull(c) { c.enqueue(new Uint8Array(bytes.length + 1)); }, cancel() { cancelled = true; } });
  await assert.rejects(acquireRelease(manifest, { fetcher: async () => new Response(stream) }), /超過/); assert(cancelled);
});
test('release: declared size mismatch fails and abort cancels a pending stream', async () => {
  await assert.rejects(acquireRelease(manifest, { fetcher: async () => new Response(bytes, { headers: { 'content-length': String(bytes.length + 1) } }) }), /大小/);
  const controller = new AbortController(); let started; const ready = new Promise(r => started = r); let cancelled = false;
  const promise = acquireRelease(manifest, { signal: controller.signal, fetcher: async () => new Response(new ReadableStream({ start() { started(); }, cancel() { cancelled = true; } })) });
  await ready; await new Promise(r => setTimeout(r, 5)); controller.abort(); await assert.rejects(promise, { name: 'AbortError' }); assert(cancelled);
});
test('release: reject unexpected redirect destination and truncated streams', async () => {
  const response = new Response(bytes); Object.defineProperty(response, 'url', { value: 'https://evil.invalid/a' });
  await assert.rejects(acquireRelease(manifest, { fetcher: async () => response }), /非預期/);
  await assert.rejects(acquireRelease(manifest, { fetcher: async () => new Response(bytes.slice(1)) }), /大小/);
});
test('release: download cap is the existing parser input budget, with a clear early oversize error',async()=>{
  const { LIMITS } = await import('../src/archive.js');assert.equal(MAX_RELEASE_BYTES,LIMITS.input);assert.equal(MAX_RELEASE_BYTES,150*1024*1024);
  let fetched=false;await assert.rejects(acquireRelease({...manifest,size:MAX_RELEASE_BYTES+1},{fetcher:async()=>{fetched=true;return new Response(bytes);}}),/150 MiB/);assert(!fetched);
});
