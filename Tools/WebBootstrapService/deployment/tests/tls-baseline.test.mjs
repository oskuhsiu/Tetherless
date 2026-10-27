// SPDX-License-Identifier: AGPL-3.0-only
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { X509Certificate } from 'node:crypto';
import { rootCertificates } from 'node:tls';

const read = path => readFile(new URL(path, import.meta.url), 'utf8');

test('Docker and CI retain the reviewed Node security pin and all-stage system CA floor', async () => {
  const docker = await read('../Dockerfile');
  const images = JSON.parse(await read('../base-images.json'));
  const node = images.images.find(image => image.tag.includes('/node:'));
  assert.equal(node.tag, 'docker.io/library/node:24.22.1-trixie-slim');
  assert.equal(node.indexDigest, 'sha256:43b9ba1142b8dcf33fa8f922ca1be85714adc444e0586c7cf7726daaeabc1bea');
  const stages = docker.split(/^FROM /m).slice(1);
  assert.equal(stages.length, 3);
  for (const stage of stages) {
    assert.match(stage, /apt-get update && apt-get install/);
    assert.match(stage, /dpkg --compare-versions .* ge '20250419\+deb13u1'/);
    assert.match(stage, /&& update-ca-certificates/);
  }
  for (const name of ['frontend', 'runtime']) {
    assert.ok(docker.includes(`FROM ${node.tag.replace('docker.io/library/', '')}@${node.indexDigest} AS ${name}`));
  }
  for (const name of ['web-bootstrap.yml', 'web-bootstrap-deployment.yml']) {
    assert.match(await read(`../../../../.github/workflows/${name}`), /node-version: '24\.22\.1'/);
  }
});

test('Cargo resolver lock retains patched verifier and both bundled root sets', async () => {
  const lock = await read('../../Cargo.lock');
  const versions = name => [...lock.matchAll(new RegExp(`name = "${name}"\\nversion = "([^"]+)"`, 'g'))].map(match => match[1]);
  assert.deepEqual(versions('rustls-webpki'), ['0.103.16']);
  assert.deepEqual(versions('webpki-root-certs'), ['1.0.10']);
  assert.deepEqual(versions('webpki-roots'), ['0.26.11', '1.0.10']);
  // The compatibility crate delegates to the updated root set, not a second old bundle.
  assert.match(lock, /name = "webpki-roots"\nversion = "0.26.11"[\s\S]*?dependencies = \[\n "webpki-roots 1.0.10",\n\]/);
});

test('actual Node bundled root set omits the two distrusted CA identities', () => {
  assert.equal(process.versions.node, '24.22.1');
  assert.ok(rootCertificates.length > 0);
  for (const pem of rootCertificates) {
    const certificate = new X509Certificate(pem);
    assert.doesNotMatch(certificate.subject, /emSign ECC Root CA - G3|AAA Certificate Services/);
  }
  // This root inventory test is not a deployed HTTP-client chain-rejection test.
});
