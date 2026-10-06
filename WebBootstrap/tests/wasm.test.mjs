import test from 'node:test'; import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs'; import vm from 'node:vm';
import { ZipReader, Uint8ArrayReader, Uint8ArrayWriter } from '@zip.js/zip.js';
import { makeIpa, makeMaterial } from './fixtures.mjs';
async function module() {
  const sandbox = { console, WebAssembly, TextDecoder, TextEncoder, URL, performance, setTimeout, clearTimeout, crypto, process };
  vm.createContext(sandbox); vm.runInContext(readFileSync(new URL('../public/wasm/zsign-mobile.js', import.meta.url), 'utf8'), sandbox);
  const logs = []; const mod = await sandbox.createZsignModule({ noInitialRun: true, wasmBinary: readFileSync(new URL('../public/wasm/zsign-mobile.wasm', import.meta.url)), print: (s) => logs.push(s), printErr: (s) => logs.push(s) });
  return { mod, logs };
}
test('pinned real WASM runtime identifies itself', async () => { const { mod, logs } = await module(); assert.equal(mod.callMain(['-v']), 0); assert(logs.join('\n').includes('wasm_28a6421')); });
test('real WASM performs certificate-backed signing and archives synthetic input', async () => {
  const { mod, logs } = await module(); const material = makeMaterial(); const ipa = await makeIpa();
  mod.FS.mkdir('/work'); mod.FS.chdir('/work'); mod.FS.writeFile('/work/input.ipa', ipa); mod.FS.writeFile('/work/signing.p12', material.p12); mod.FS.writeFile('/work/profile.mobileprovision', material.profile);
  const code = mod.callMain(['-k','/work/signing.p12','-p',material.password,'-m','/work/profile.mobileprovision','-z','1','-o','/work/signed.ipa','/work/input.ipa']);
  assert.equal(code, 0, logs.join('\n')); const bytes = new Uint8Array(mod.FS.readFile('/work/signed.ipa'));
  assert(!Buffer.from(bytes).equals(Buffer.from(ipa))); assert(logs.join('\n').includes('Archive OK'));
  const reader = new ZipReader(new Uint8ArrayReader(bytes), { useWebWorkers: false }); const entries = await reader.getEntries();
  assert(entries.some((e) => e.filename === 'Payload/Fixture.app/_CodeSignature/CodeResources'));
  const embedded = await entries.find((e) => e.filename === 'Payload/Fixture.app/embedded.mobileprovision').getData(new Uint8ArrayWriter()); assert(Buffer.from(embedded).equals(material.profile));
  const executable = await entries.find((e) => e.filename === 'Payload/Fixture.app/Fixture').getData(new Uint8ArrayWriter());
  assert(!Buffer.from(executable).equals(readFileSync(new URL('./fixtures/demo1.dylib', import.meta.url))));
  await reader.close();
});
