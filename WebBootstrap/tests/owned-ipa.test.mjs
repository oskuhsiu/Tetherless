import test from 'node:test';
import assert from 'node:assert/strict';
import forge from 'node-forge';
import { JSDOM } from 'jsdom';
import { ZipWriter, Uint8ArrayReader, Uint8ArrayWriter } from '@zip.js/zip.js';
import { createGuidedService, GUIDED_APPS, SYNTHETIC, syntheticProvision } from './browser/guided-service.mjs';
import { OWNED_IPA, loadOwnedIpa, readIpaFiles, verifyOwnedSignedOutput } from './browser/owned-ipa.mjs';
import { makeSignedFixture } from './fixtures.mjs';
import { inspectIpa, inspectInputs } from '../src/material.js';

async function authenticated(appName) {
  const service = createGuidedService(appName);
  const login = await service.handle('v1/sessions', 'POST', JSON.stringify({ appleId: SYNTHETIC.appleId, password: SYNTHETIC.password }));
  const path = `v1/sessions/${login.sessionId}`, auth = `Bearer ${login.sessionToken}`;
  await service.handle(path + '/2fa', 'POST', JSON.stringify({ action: 'submitCode', code: SYNTHETIC.code }), auth);
  await service.handle(path + `/teams/${SYNTHETIC.teamId}/devices`, 'GET', '', auth);
  return { service, provision: body => service.handle(path + '/provision', 'POST', JSON.stringify(body), auth) };
}
function requestFor(appName, csrPem = '') {
  return { apps: [GUIDED_APPS[appName]], teamId: SYNTHETIC.teamId, device: { udid: SYNTHETIC.udid, name: 'My iPhone', existingOnly: true }, machineName: 'Tetherless Web', consent: 'use-existing-device-register-app-ids-and-issue-certificate', csrPem };
}

test('owned IPA: exact unsigned native input, source archive and BuildIdentity remain pinned', async () => {
  const input = await loadOwnedIpa(), dom = new JSDOM();
  globalThis.DOMParser = dom.window.DOMParser;
  try {
    const result = await inspectIpa(new File([input.bytes], OWNED_IPA.filename));
    assert.equal(result.bundles.length, 1);
    assert.equal(result.bundles[0].id, OWNED_IPA.bundleId);
    assert.equal(result.bundles[0].name, GUIDED_APPS['owned-signing-test'].name);
  } finally { delete globalThis.DOMParser; dom.window.close(); }
});

test('owned IPA: fixture selection is a closed two-app choice and keeps the synthetic default', async () => {
  for (const invalid of ['', 'arbitrary', '__proto__', 'constructor', OWNED_IPA.bundleId, {}, null]) {
    assert.throws(() => createGuidedService(invalid));
    assert.throws(() => syntheticProvision('', invalid));
  }
  assert(Object.isFrozen(GUIDED_APPS));
  for (const app of Object.values(GUIDED_APPS)) assert(Object.isFrozen(app));
  const original = await authenticated();
  await assert.rejects(original.provision(requestFor('owned-signing-test')));
  const owned = await authenticated('owned-signing-test');
  await assert.rejects(owned.provision(requestFor('synthetic')));
  assert.equal(original.service.provisioningBodies.length, 0);
  assert.equal(owned.service.provisioningBodies.length, 0);
});

test('owned IPA: second fixture retains exact credentials, Team, device and mutation-plan checks', async () => {
  const { service, provision } = await authenticated('owned-signing-test');
  for (const login of [{ appleId: 'someone@example.com', password: SYNTHETIC.password }, { appleId: SYNTHETIC.appleId, password: 'wrong' }]) {
    await assert.rejects(service.handle('v1/sessions', 'POST', JSON.stringify(login)));
  }
  const mutations = [
    body => { body.teamId = 'OTHERTEAM1'; },
    body => { body.device.udid = '11111111-1111111111111111'; },
    body => { body.device.name = 'Another device'; },
    body => { body.device.existingOnly = false; },
    body => { body.apps = [{ bundleId: 'org.unrelated.app', name: 'Other' }]; },
    body => { body.apps[0].name = 'Another app'; },
    body => { body.apps.push(GUIDED_APPS.synthetic); },
    body => { body.consent = 'register-device-app-ids-and-issue-certificate'; },
    body => { body.consent = ''; },
    body => { body.machineName = 'Another machine'; },
    body => { body.appGroup = { identifier: 'group.unrelated' }; },
  ];
  for (const mutate of mutations) {
    const body = structuredClone(requestFor('owned-signing-test'));
    mutate(body);
    await assert.rejects(provision(body));
  }
  assert.equal(service.provisioningBodies.length, 0);
  assert.equal(service.profiles.length, 0);
});

test('owned IPA: exact native input passes synthetic CSR/material checks and real offline WASM output verification', async () => {
  const input = await loadOwnedIpa(), dom = new JSDOM();
  globalThis.DOMParser = dom.window.DOMParser;
  try {
    const keys = forge.pki.rsa.generateKeyPair(2048), csr = forge.pki.createCertificationRequest();
    csr.publicKey = keys.publicKey;
    csr.setSubject([{ name: 'commonName', value: 'Tetherless browser signing' }]);
    csr.sign(keys.privateKey, forge.md.sha256.create());
    const { service, provision } = await authenticated('owned-signing-test');
    const response = await provision(requestFor('owned-signing-test', forge.pki.certificationRequestToPem(csr)));
    const cert = forge.pki.certificateFromAsn1(forge.asn1.fromDer(forge.util.decode64(response.certificateDerBase64)));
    assert(cert.publicKey.n.equals(keys.publicKey.n));
    assert(cert.publicKey.e.equals(keys.publicKey.e));
    const password = 'synthetic-memory-only';
    const p12 = Buffer.from(forge.asn1.toDer(forge.pkcs12.toPkcs12Asn1(keys.privateKey, [cert], password, { algorithm: '3des' })).getBytes(), 'binary');
    const profile = service.profiles[0], ipa = new File([input.bytes], OWNED_IPA.filename);
    const checked = await inspectInputs({ ipa, p12: new File([p12], 'synthetic.p12'), profiles: [new File([profile], 'synthetic.mobileprovision')], password, udid: SYNTHETIC.udid });
    assert.equal(checked.bundles[0].id, OWNED_IPA.bundleId);
    assert.equal(checked.team, SYNTHETIC.teamId);
    const signed = Buffer.from(await makeSignedFixture(ipa, { p12, profile, password }));
    const proof = await verifyOwnedSignedOutput(signed, input, profile);
    assert.equal(proof.appleTrustVerified, false);
    assert.equal(proof.installationVerified, false);
    await assert.rejects(verifyOwnedSignedOutput(input.bytes, input, profile));
    await assert.rejects(verifyOwnedSignedOutput(signed, input, Buffer.from('incorrect profile')));

    // Negative controls: output checks must reject a copied executable, modified
    // source identity, an extra file, and stale resource hashes.
    const files = await readIpaFiles(signed), root = OWNED_IPA.root;
    for (const [name, data] of [
      [root + 'SigningTest', input.files.get(root + 'SigningTest')],
      [root + 'BuildIdentity.json', Buffer.from('{}')],
      [root + 'unexpected.txt', Buffer.from('unexpected')],
      [root + '_CodeSignature/CodeResources', Buffer.from(files.get(root + '_CodeSignature/CodeResources').toString().replace(/<data>[\s\S]*?<\/data>/, '<data>AAAA</data>'))],
    ]) {
      const changed = new Map(files); changed.set(name, data);
      const zip = new ZipWriter(new Uint8ArrayWriter(), { level: 1, useWebWorkers: false });
      for (const [path, bytes] of changed) await zip.add(path, new Uint8ArrayReader(bytes));
      await assert.rejects(verifyOwnedSignedOutput(Buffer.from(await zip.close()), input, profile));
    }
    assert.deepEqual((await loadOwnedIpa()).bytes, input.bytes);
  } finally { delete globalThis.DOMParser; dom.window.close(); }
});
