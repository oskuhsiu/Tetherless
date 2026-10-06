// SPDX-License-Identifier: AGPL-3.0-only
// Execute INSIDE the built container with --network none, synthetic config only.
// No account-creation, 2FA, provisioning or other Apple route is invoked.
import assert from 'node:assert/strict';
import http from 'node:http';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
const code = 'Z'.repeat(43);
const host = 'bootstrap.example.com';
const origin = `https://${host}`;
assert.equal(process.env.TETHERLESS_PUBLIC_HOST, host);
assert.equal(process.env.FRONTEND_ORIGIN, origin);
assert.equal(process.env.TETHERLESS_TEST_ACCESS_SHA256, createHash('sha256').update(code).digest('hex'));
function request(path, { method = 'GET', headers = {}, data = '' } = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request({ hostname: '127.0.0.1', port: Number(process.env.PORT ?? 10000), path, method,
      headers: { host, ...headers }, timeout: 5000 }, res => {
      const chunks = []; res.on('data', c => chunks.push(c));
      res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, bytes: Buffer.concat(chunks), body: Buffer.concat(chunks).toString() }));
    });
    req.on('error', reject); req.on('timeout', () => req.destroy()); req.end(data);
  });
}
let ready = false;
for (let i = 0; i < 100; i++) {
  try { if ((await request('/health')).status === 200) { ready = true; break; } } catch {}
  await new Promise(r => setTimeout(r, 100));
}
assert.ok(ready, 'Production entrypoint must become ready');
const health = await request('/health'); const status = JSON.parse(health.body);
assert.equal(status.service, 'tetherless-web-bootstrap');
assert.equal(status.accountBackendPin, 'dd442588370060b8776b1276a1acd717b6668b26');
assert.equal(status.liveAppleAcceptance, false); assert.equal(status.profileServiceAvailable, true);
assert.equal((await request('/health', { headers: { host: 'hostile.example.com' } })).status, 403);
assert.equal((await request('/v1/sessions/absent')).status, 401);
const gate = await request('/');
assert.match(gate.body, /Test access code/);
const sourceCommit = (await readFile('/app/build-info/source-commit.txt', 'utf8')).trim();
assert.match(sourceCommit, /^[a-f0-9]{40}$/);
assert.ok(gate.body.includes(`https://github.com/oskuhsiu/Tetherless/tree/${sourceCommit}`));
assert.ok(gate.body.includes(`https://github.com/oskuhsiu/Tetherless/blob/${sourceCommit}/LICENSE`));
const unlock = await request('/_test/access', { method: 'POST', data: `code=${code}`,
  headers: { origin, 'content-type': 'application/x-www-form-urlencoded' } });
assert.equal(unlock.status, 303);
const gateCookie = unlock.headers['set-cookie'][0];
for (const flag of ['Secure', 'HttpOnly', 'SameSite=Lax', 'Path=/']) assert.ok(gateCookie.includes(flag));
const cookie = gateCookie.split(';')[0];
const html = await request('/', { headers: { cookie } });
assert.equal(html.status, 200); assert.equal(html.body, await readFile('/app/frontend/index.html', 'utf8'));
assert.equal(html.headers['cache-control'], 'no-store');
assert.equal(html.headers['content-security-policy'], undefined, 'Do not override frontend meta CSP');
const wasm = await request('/wasm/zsign-mobile.wasm', { headers: { cookie } });
assert.equal(wasm.status, 200);
assert.equal(createHash('sha256').update(wasm.bytes).digest('hex'), '6487f181de6cf1cdfaf4e7497bb6c177fb95235a3e72f11ae57695452c0b4090');
const headers = { cookie, origin, 'content-type': 'application/json' };
assert.equal((await request('/v1/device-enrollments', { method: 'POST', headers: { cookie, 'content-type': 'application/json' }, data: '{}' })).status, 403);
assert.equal((await request('/v1/device-enrollments', { method: 'POST', headers: { ...headers, origin: 'https://hostile.example.com' }, data: '{}' })).status, 403);
const enrollment = await request('/v1/device-enrollments', { method: 'POST', headers, data: '{"consent":"collect-device-udid"}' });
assert.equal(enrollment.status, 201);
const record = JSON.parse(enrollment.body);
assert.equal(record.verification, 'untrustedDeviceMetadata');
assert.ok(record.profileUrl.startsWith(`${origin}/v1/device-enrollments/${record.enrollmentId}/profile/`));
assert.equal((await request(new URL(record.profileUrl).pathname, { headers: { cookie } })).status, 200);
assert.equal((await request(`/v1/device-enrollments/${record.enrollmentId}/callback`, { method: 'POST',
  headers: { 'content-type': 'application/pkcs7-signature' }, data: 'synthetic malformed CMS' })).status, 400);
const enrollmentCookie = enrollment.headers['set-cookie'][0].split(';')[0];
assert.equal((await request(`/v1/device-enrollments/${record.enrollmentId}`, { method: 'DELETE', headers: { ...headers, cookie: `${cookie}; ${enrollmentCookie}` } })).status, 204);
console.log('Offline production-container smoke passed: real health/static/WASM, gate, Host/Origin and synthetic local enrollment. No Apple account route called.');
