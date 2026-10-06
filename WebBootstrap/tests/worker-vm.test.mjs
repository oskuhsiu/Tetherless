// Executes the actual public worker adapter and pinned WASM with synthetic
// FileReaderSync/Blob shims. This is NOT browser, Web Worker, CSP, or Safari QA.
// Copy into WebBootstrap/tests/, or set WEB_BOOTSTRAP_ROOT to run elsewhere.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import vm from 'node:vm';

const root = process.env.WEB_BOOTSTRAP_ROOT
  ? resolve(process.env.WEB_BOOTSTRAP_ROOT)
  : fileURLToPath(new URL('../', import.meta.url));
const { makeIpa, makeMaterial } = await import(pathToFileURL(resolve(root, 'tests/fixtures.mjs')).href);

class MemoryBlob {
  constructor(bytes) { this.bytes = Uint8Array.from(bytes); this.size = this.bytes.byteLength; }
  slice(start = 0, end = this.size) { return new MemoryBlob(this.bytes.slice(start, end)); }
}

test('VM/shim only: actual public worker signs through WORKERFS at a project subpath', async () => {
  const material = makeMaterial();
  const ipa = await makeIpa();
  const messages = [], loaded = [];
  const self = {
    location: new URL('https://static.example/tetherless/sign-worker.js'),
    postMessage(data, transfer) { messages.push({ data, transfer }); },
  };
  const sandbox = {
    self, URL, WebAssembly, TextDecoder, TextEncoder, performance,
    setTimeout, clearTimeout, crypto, console,
    WorkerGlobalScope: class {},
    FileReaderSync: class {
      readAsArrayBuffer(blob) { return blob.bytes.slice().buffer; }
    },
    fetch: async (url) => {
      loaded.push(String(url));
      assert.equal(String(url), 'https://static.example/tetherless/wasm/zsign-mobile.wasm');
      return new Response(readFileSync(resolve(root, 'public/wasm/zsign-mobile.wasm')), {
        headers: { 'Content-Type': 'application/wasm' },
      });
    },
  };
  vm.createContext(sandbox);
  sandbox.importScripts = (url) => {
    loaded.push(String(url));
    assert.equal(String(url), 'https://static.example/tetherless/wasm/zsign-mobile.js');
    vm.runInContext(readFileSync(resolve(root, 'public/wasm/zsign-mobile.js'), 'utf8'), sandbox);
  };
  vm.runInContext(readFileSync(resolve(root, 'public/sign-worker.js'), 'utf8'), sandbox);
  await self.onmessage({ data: {
    ipa: new MemoryBlob(ipa), p12: new MemoryBlob(material.p12),
    profiles: [new MemoryBlob(material.profile)], password: material.password,
  } });
  assert.deepEqual(loaded, [
    'https://static.example/tetherless/wasm/zsign-mobile.js',
    'https://static.example/tetherless/wasm/zsign-mobile.wasm',
  ]);
  assert.deepEqual(messages.map(({ data }) => data.phase), ['signing', 'done']);
  const done = messages.at(-1);
  assert(done.data.bytes.byteLength > 1000);
  assert.deepEqual([...done.data.bytes.slice(0, 4)], [0x50, 0x4b, 0x03, 0x04]);
  assert(!Buffer.from(done.data.bytes).equals(Buffer.from(ipa)));
  assert.equal(done.transfer.length, 1);
  assert.equal(done.transfer[0], done.data.bytes.buffer);
});
