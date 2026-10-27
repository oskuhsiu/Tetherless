// Node-side assertions for the owned native fixture. No custom Mach-O parser.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';
import { ZipReader, Uint8ArrayReader, Uint8ArrayWriter } from '@zip.js/zip.js';

const fixture = new URL('../fixtures/owned-signing-test/', import.meta.url);
export const OWNED_IPA = Object.freeze({
  filename: 'Signing-test-app-not-Tetherless.ipa',
  sha256: 'fda8c913af9d6f39f8a4351bd94d7953bb99b2b25506e67a3e7d943dafaf8111',
  size: 14853,
  bundleId: 'org.tetherless.signingtest.r37503567286',
  sourceCommit: 'cfd8c6ede2c85970344e9e9c0f19cc672a95df71',
  sourceSha256: '4db8c444bf899d3a18f9a58b43834e199734986290b588b1114f5bcf2b28b76a',
  root: 'Payload/SigningTest.app/',
});
export const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');

export async function readIpaFiles(bytes) {
  const reader = new ZipReader(new Uint8ArrayReader(bytes));
  try {
    const entries = (await reader.getEntries()).filter(entry => !entry.directory);
    assert.equal(new Set(entries.map(entry => entry.filename)).size, entries.length);
    const files = new Map();
    for (const entry of entries) files.set(entry.filename, Buffer.from(await entry.getData(new Uint8ArrayWriter())));
    return files;
  } finally { await reader.close(); }
}

export async function loadOwnedIpa() {
  const bytes = readFileSync(new URL(OWNED_IPA.filename, fixture));
  assert.equal(bytes.length, OWNED_IPA.size);
  assert.equal(sha256(bytes), OWNED_IPA.sha256);
  const provenance = JSON.parse(readFileSync(new URL('provenance.json', fixture), 'utf8'));
  assert.deepEqual(provenance.ipa, { filename: OWNED_IPA.filename, sha256: OWNED_IPA.sha256, size_bytes: OWNED_IPA.size });
  assert.equal(provenance.identity.source_commit, OWNED_IPA.sourceCommit);
  assert.equal(provenance.identity.bundle_identifier, OWNED_IPA.bundleId);
  assert.equal(provenance.identity.run_id, '37503567286');
  assert.equal(provenance.identity.run_attempt, '1');
  assert.equal(provenance.signing.signature_classification, 'no-code-signature; no Apple identity or provisioning');
  assert.equal(provenance.signing.apple_developer_signed, false);
  assert.equal(provenance.source_snapshot.sha256, OWNED_IPA.sourceSha256);
  const source = readFileSync(new URL('signing-test-source.tar', fixture));
  assert.equal(source.length, provenance.source_snapshot.size_bytes);
  assert.equal(sha256(source), OWNED_IPA.sourceSha256);
  const files = await readIpaFiles(bytes);
  assert.deepEqual([...files.keys()].sort(), provenance.app_manifest.map(entry => OWNED_IPA.root + entry.path).sort());
  for (const entry of provenance.app_manifest) {
    const data = files.get(OWNED_IPA.root + entry.path);
    assert.equal(data.length, entry.size_bytes);
    assert.equal(sha256(data), entry.sha256);
  }
  assert.deepEqual(JSON.parse(files.get(OWNED_IPA.root + 'BuildIdentity.json')), provenance.identity);
  return { bytes, files, provenance };
}

// Check the actual downloaded ZIP, not a status label. Synthetic signing changes
// the executable and adds a profile/resource envelope; original metadata stays exact.
export async function verifyOwnedSignedOutput(bytes, input, profile) {
  assert(!bytes.equals(input.bytes));
  assert(profile instanceof Uint8Array && profile.length > 0);
  const files = await readIpaFiles(bytes), root = OWNED_IPA.root;
  assert.deepEqual([...files.keys()].sort(), [...input.files.keys(), root + 'embedded.mobileprovision', root + '_CodeSignature/CodeResources'].sort());
  for (const name of ['Info.plist', 'BuildIdentity.json']) assert.deepEqual(files.get(root + name), input.files.get(root + name));
  assert.notDeepEqual(files.get(root + 'SigningTest'), input.files.get(root + 'SigningTest'));
  assert.deepEqual(files.get(root + 'embedded.mobileprovision'), Buffer.from(profile));

  const resources = new JSDOM(files.get(root + '_CodeSignature/CodeResources').toString('utf8'), { contentType: 'text/xml' });
  try {
    const dict = resources.window.document.querySelector('plist > dict');
    function value(parent, name) {
      assert(parent && parent.tagName === 'dict');
      const keys = [...parent.children].filter(node => node.tagName === 'key' && node.textContent === name);
      assert.equal(keys.length, 1, `Expected one resource key: ${name}`);
      return keys[0].nextElementSibling;
    }
    function digest(node, name, algorithm) {
      assert.equal(node?.tagName, 'data');
      assert.deepEqual(Buffer.from(node.textContent.replace(/\s/g, ''), 'base64'), createHash(algorithm).update(files.get(root + name)).digest());
    }
    const legacy = value(dict, 'files'), modern = value(dict, 'files2');
    for (const name of ['BuildIdentity.json', 'Info.plist', 'embedded.mobileprovision']) digest(value(legacy, name), name, 'sha1');
    for (const name of ['BuildIdentity.json', 'embedded.mobileprovision']) {
      const entry = value(modern, name);
      digest(value(entry, 'hash'), name, 'sha1');
      digest(value(entry, 'hash2'), name, 'sha256');
    }
  } finally { resources.window.close(); }
  return {
    inputSha256: sha256(input.bytes), outputSha256: sha256(bytes), outputSize: bytes.length,
    bundleId: OWNED_IPA.bundleId, nativeSourceCommit: OWNED_IPA.sourceCommit,
    executableChanged: true, originalMetadataUnchanged: true, exactSyntheticProfile: true,
    resourceDigestsVerified: true, appleTrustVerified: false, installationVerified: false,
  };
}
