// SPDX-License-Identifier: AGPL-3.0-only
// Uses the actual optimized service and built frontend. NEVER sends valid Apple
// credentials, starts an Apple login, or invokes certificate/provisioning APIs.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFile, access, mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const binary = process.env.TETHERLESS_INTEGRATION_BINARY;
const frontend = process.env.TETHERLESS_INTEGRATION_FRONTEND;
const CODE = 'Z'.repeat(43); // Public synthetic fixture, not an operator credential.
const host = 'bootstrap.example.com';
const origin = `https://${host}`;
function request(port, path, { method = 'GET', headers = {}, data = '' } = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request({ hostname: '127.0.0.1', port, path, method,
      headers: { host, ...headers }, timeout: 5000 }, res => {
      const chunks = [];
      res.on('data', c => chunks.push(c));
      res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, bytes: Buffer.concat(chunks),
        body: Buffer.concat(chunks).toString() }));
    });
    req.on('error', reject); req.on('timeout', () => req.destroy()); req.end(data);
  });
}
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function freePort() {
  const s = http.createServer(); await new Promise(r => s.listen(0, '127.0.0.1', r));
  const port = s.address().port; await new Promise(r => s.close(r)); return port;
}

test('actual release backend, production supervisor and built frontend, without Apple traffic',
  { skip: !binary || !frontend ? 'Set TETHERLESS_INTEGRATION_BINARY and TETHERLESS_INTEGRATION_FRONTEND to run real integration' : false }, async () => {
  await access(binary); await access(`${frontend}/index.html`);
  const port = await freePort();
  const fixtureDir = await mkdtemp(join(tmpdir(), 'tetherless-source-identity-fixture-'));
  const sourceFile = join(fixtureDir, 'source-commit.txt');
  await writeFile(sourceFile, 'a'.repeat(40) + '\n');
  const env = { PATH: process.env.PATH, FRONTEND_ORIGIN: origin, TETHERLESS_PUBLIC_HOST: host,
    PORT: String(port), TETHERLESS_FRONTEND_DIR: frontend, TETHERLESS_SERVICE_BINARY: binary, TETHERLESS_SOURCE_COMMIT_FILE: sourceFile,
    TETHERLESS_TEST_ACCESS_SHA256: createHash('sha256').update(CODE).digest('hex'),
    TETHERLESS_TEST_EXPIRES_AT: new Date(Date.now() + 3600000).toISOString().replace(/\.\d{3}Z$/, 'Z') };
  let child;
  let output = '';
  async function start() {
    child = spawn(process.execPath, [fileURLToPath(new URL('../entrypoint.mjs', import.meta.url))], { env, stdio: ['ignore', 'pipe', 'pipe'] });
    child.stdout.on('data', b => { output += b; }); child.stderr.on('data', b => { output += b; });
    for (let i = 0; i < 100; i++) {
      if (child.exitCode !== null) throw new Error('Supervisor exited before readiness');
      try { if ((await request(port, '/health')).status === 200) return; } catch {}
      await sleep(100);
    }
    throw new Error('Supervisor did not become ready');
  }
  async function stop() {
    if (!child || child.exitCode !== null) return;
    const exited = new Promise(resolve => child.once('exit', (code, signal) => resolve({ code, signal })));
    child.kill('SIGTERM'); const result = await exited;
    assert.equal(result.code, 0); assert.equal(result.signal, null);
  }
  try {
    await start();
    const health = await request(port, '/health');
    const status = JSON.parse(health.body);
    assert.equal(status.protocol, 1); assert.equal(status.appleAuthAvailable, true);
    assert.equal(status.profileServiceAvailable, true); assert.equal(status.liveAppleAcceptance, false);
    assert.equal(status.accountBackendPin, 'dd442588370060b8776b1276a1acd717b6668b26');
    assert.equal(health.headers['cache-control'], 'no-store');
    assert.equal((await request(port, '/health', { headers: { host: 'hostile.example.com' } })).status, 403);
    assert.equal((await request(port, '/v1/sessions/absent')).status, 401);
    const gate = await request(port, '/'); assert.match(gate.body, /Test access code/);
    assert.ok(gate.body.includes('https://github.com/oskuhsiu/Tetherless/tree/' + 'a'.repeat(40)));
    assert.ok(gate.body.includes('/blob/' + 'a'.repeat(40) + '/LICENSE'));
    const unlock = await request(port, '/_test/access', { method: 'POST', data: `code=${CODE}`,
      headers: { origin, 'content-type': 'application/x-www-form-urlencoded' } });
    assert.equal(unlock.status, 303); const cookie = unlock.headers['set-cookie'][0].split(';')[0];
    const page = await request(port, '/', { headers: { cookie } }); assert.equal(page.status, 200);
    assert.equal(page.body, await readFile(`${frontend}/index.html`, 'utf8'));
    const wasm = await request(port, '/wasm/zsign-mobile.wasm', { headers: { cookie } });
    assert.equal(wasm.status, 200);
    assert.equal(createHash('sha256').update(wasm.bytes).digest('hex'), '6487f181de6cf1cdfaf4e7497bb6c177fb95235a3e72f11ae57695452c0b4090');
    const apiHeaders = { cookie, origin, 'content-type': 'application/json' };
    assert.equal((await request(port, '/v1/device-enrollments', { method: 'POST', headers: { cookie, 'content-type': 'application/json' }, data: '{}' })).status, 403);
    assert.equal((await request(port, '/v1/device-enrollments', { method: 'POST', headers: { ...apiHeaders, origin: 'https://hostile.example.com' }, data: '{}' })).status, 403);
    // No account-create or account mutation endpoint is invoked in this smoke.
    assert.equal((await request(port, '/v1/sessions/absent', { headers: apiHeaders })).status, 404);
    // Existing local-only enrollment creation is safe: no Apple API is contacted.
    const enrollment = await request(port, '/v1/device-enrollments', { method: 'POST', headers: apiHeaders, data: '{"consent":"collect-device-udid"}' });
    assert.equal(enrollment.status, 201);
    const record = JSON.parse(enrollment.body);
    assert.equal(record.verification, 'untrustedDeviceMetadata');
    assert.ok(record.profileUrl.startsWith(`${origin}/v1/device-enrollments/${record.enrollmentId}/profile/`));
    assert.ok(enrollment.headers['set-cookie'][0].includes('Secure'));
    const profile = await request(port, new URL(record.profileUrl).pathname, { headers: { cookie } });
    assert.equal(profile.status, 200); assert.match(profile.body, /Profile Service/);
    const callback = await request(port, `/v1/device-enrollments/${record.enrollmentId}/callback`, { method: 'POST', headers: { 'content-type': 'application/pkcs7-signature' }, data: 'not CMS' });
    assert.equal(callback.status, 400); // Correctly reaches existing nonce/CMS validator, not a mock success.
    const enrollmentCookie = enrollment.headers['set-cookie'][0].split(';')[0];
    const cancelled = await request(port, `/v1/device-enrollments/${record.enrollmentId}`, { method: 'DELETE', headers: { ...apiHeaders, cookie: `${cookie}; ${enrollmentCookie}` } });
    assert.equal(cancelled.status, 204);
    await stop(); await start();
    assert.equal((await request(port, '/v1/sessions/absent', { headers: { cookie } })).status, 401);
    await stop();
    assert.ok(!output.includes(CODE)); assert.ok(!output.includes(env.TETHERLESS_TEST_ACCESS_SHA256));
    assert.ok(!output.includes(cookie)); assert.ok(!output.includes(record.enrollmentId));
    assert.ok(!output.includes('password')); assert.ok(!output.includes('appleId'));
    assert.deepEqual(output.trim().split('\n'), [
      'Tetherless bounded test service ready. Request logging is disabled.',
      'Tetherless bounded test service ready. Request logging is disabled.',
    ]);
  } finally { await stop(); await rm(fixtureDir, { recursive: true, force: true }); }
});
