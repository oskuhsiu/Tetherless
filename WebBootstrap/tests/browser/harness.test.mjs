// Offline checks only: no browser launch and no server/listen call.
import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, mkdir, rm, symlink } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { staticResponse } from './preview.mjs';
import { permitsLocalRequest } from './local-policy.mjs';
import { binaryInfo, makeBinaryIpa } from './binary-fixture.mjs';
import { parse } from '../../src/vendor/binary-plist.js';
import { ZipReader, Uint8ArrayReader, Uint8ArrayWriter } from '@zip.js/zip.js';
import config from '../../playwright.config.js';

const base = 'http://127.0.0.1:4173/Tetherless/';
test('request policy allows local project GET/HEAD and same-origin Blob URLs', () => {
  for (const path of ['', 'assets/index.js', 'assets/plist-worker.js', 'sign-worker.js', 'wasm/zsign-mobile.wasm', 'health', 'config.json']) {
    assert.equal(permitsLocalRequest(new URL(path, base).href, 'GET', base), true);
    assert.equal(permitsLocalRequest(new URL(path, base).href, 'HEAD', base), true);
  }
  assert.equal(permitsLocalRequest('blob:http://127.0.0.1:4173/synthetic-id', 'GET', base), true);
});
test('request policy rejects remote, wrong-origin/path, mutations, and malformed URLs', () => {
  for (const url of ['https://example.invalid/', 'https://idmsa.apple.com/', 'http://localhost:4173/Tetherless/', 'http://127.0.0.1:4174/Tetherless/', 'http://127.0.0.1:4173/sign-worker.js', 'http://127.0.0.1:4173/Tetherless-other/', 'blob:https://example.invalid/id', 'file:///tmp/test', 'ws://127.0.0.1:4173/Tetherless/', 'broken']) {
    assert.equal(permitsLocalRequest(url, 'GET', base), false, url);
  }
  assert.equal(permitsLocalRequest(base, 'POST', base), false);
  assert.equal(permitsLocalRequest(base, 'DELETE', base), false);
});
test('preview mounts identical bytes at root/subpath, correct MIME, no fallback or API', async () => {
  const root = await mkdtemp(join(tmpdir(), 'tetherless-static-test-'));
  try {
    await writeFile(join(root, 'index.html'), '<html>synthetic fixture</html>');
    await mkdir(join(root, 'wasm'));
    await writeFile(join(root, 'wasm/runtime.wasm'), Buffer.from([0, 97, 115, 109]));
    for (const prefix of ['/', '/Tetherless/']) {
      const page = await staticResponse(prefix, 'GET', root);
      assert.equal(page.status, 200);
      assert.equal(page.body.toString(), '<html>synthetic fixture</html>');
      assert.equal(page.headers['Content-Type'], 'text/html; charset=utf-8');
      const wasm = await staticResponse(`${prefix}wasm/runtime.wasm`, 'GET', root);
      assert.equal(wasm.status, 200);
      assert.equal(wasm.headers['Content-Type'], 'application/wasm');
      assert.equal((await staticResponse(prefix, 'HEAD', root)).body, '');
      assert.equal((await staticResponse(`${prefix}missing.js`, 'GET', root)).status, 404);
      assert.equal((await staticResponse(`${prefix}health`, 'GET', root)).status, 404);
      assert.equal((await staticResponse(`${prefix}v1/sessions`, 'POST', root)).status, 405);
    }
    assert.equal((await staticResponse('/Tetherless', 'GET', root)).headers.Location, '/Tetherless/');
    assert.equal((await staticResponse('/Tetherless/%2e%2e%2fsecret', 'GET', root)).status, 400);
    assert.equal((await staticResponse('/Tetherless/%00', 'GET', root)).status, 400);
    await symlink(join(root, '..'), join(root, 'escape'));
    assert.equal((await staticResponse('/escape', 'GET', root)).status, 403);
  } finally { await rm(root, { recursive: true, force: true }); }
});
test('binary fixture preserves expected metadata and the original synthetic Mach-O', async () => {
  const metadata = parse(binaryInfo.buffer.slice(binaryInfo.byteOffset, binaryInfo.byteOffset + binaryInfo.byteLength));
  assert.equal(metadata.CFBundleIdentifier, 'org.tetherless.TestFixture');
  assert.equal(metadata.CFBundleExecutable, 'Fixture');
  assert.equal(metadata.CFBundlePackageType, 'APPL');
  const zip = new ZipReader(new Uint8ArrayReader(await makeBinaryIpa()));
  try {
    const entries = await zip.getEntries();
    assert.equal(entries.length, 2);
    const info = await entries.find((e) => e.filename.endsWith('/Info.plist')).getData(new Uint8ArrayWriter());
    assert.deepEqual(Buffer.from(info), binaryInfo);
    const executable = await entries.find((e) => e.filename.endsWith('/Fixture')).getData(new Uint8ArrayWriter());
    assert.deepEqual(Buffer.from(executable), await readFile(new URL('../fixtures/demo1.dylib', import.meta.url)));
  } finally { await zip.close(); }
});
test('browser config uses both paths, locked default Chromium, bounded run and retained reports', () => {
  assert.equal(config.use.browserName, 'chromium');
  assert.equal(config.use.launchOptions, undefined);
  assert.equal(config.use.channel, undefined);
  assert.equal(config.use.serviceWorkers, 'block');
  assert.deepEqual(config.projects.map((p) => p.use.baseURL), ['http://127.0.0.1:4173/', base]);
  assert.equal(config.retries, 0);
  assert.equal(config.workers, 1);
  assert.equal(config.globalTimeout, 480000);
  assert.equal(config.webServer.reuseExistingServer, false);
  assert.equal(config.testMatch, '**/*.spec.js');
});
