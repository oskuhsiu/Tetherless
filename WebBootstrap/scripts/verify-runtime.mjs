import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
const lock = JSON.parse(readFileSync(new URL('../runtime-lock.json', import.meta.url)));
for (const [path, expected] of Object.entries(lock.files)) {
  const actual = createHash('sha256').update(readFileSync(new URL(`../${path}`, import.meta.url))).digest('hex');
  if (actual !== expected) throw new Error(`Runtime mismatch: ${path}`);
}
console.log(`Verified ${Object.keys(lock.files).length} pinned runtime assets (${lock.commit}). This is hash verification, not a reproducible rebuild.`);
const vendor = JSON.parse(readFileSync(new URL('../src/vendor/vendor-notices.json', import.meta.url)));
const patched = createHash('sha256').update(readFileSync(new URL('../src/vendor/binary-plist.js', import.meta.url))).digest('hex');
if (patched !== vendor.patched_sha256) throw new Error('Bounded binary-plist adapter differs from its recorded source hash.');
