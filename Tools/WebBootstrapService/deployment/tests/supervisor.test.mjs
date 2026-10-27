// SPDX-License-Identifier: AGPL-3.0-only
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtemp, writeFile, chmod, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
const entry = fileURLToPath(new URL('../entrypoint.mjs', import.meta.url));
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function fixture(t, mode) {
  const dir = await mkdtemp(join(tmpdir(), 'tetherless-supervisor-test-'));
  t.after(() => rm(dir, { recursive: true, force: true }));
  const executable = join(dir, 'fixture.mjs'); const marker = join(dir, 'signals');
  await writeFile(join(dir, 'source-commit.txt'), mode === 'invalid-source' ? 'unrecorded\n' : 'a'.repeat(40) + '\n');
  await writeFile(join(dir, 'index.html'), '<title>synthetic frontend</title>');
  await writeFile(executable, `#!${process.execPath}\nimport http from 'node:http';\nimport fs from 'node:fs';\nconsole.log('SYNTHETIC-PRIVATE-STDOUT'); console.error('SYNTHETIC-PRIVATE-STDERR');\nfs.writeFileSync(${JSON.stringify(join(dir, 'env.json'))},JSON.stringify(Object.keys(process.env).sort()));\n${mode === 'startup-fail' ? 'process.exit(23);' : ''}\nconst s=http.createServer((q,r)=>{r.end('{"service":"tetherless-web-bootstrap"}')});\ns.listen(8787,'127.0.0.1');\nprocess.on('SIGINT',()=>{fs.writeFileSync(${JSON.stringify(marker)},'SIGINT');s.close();});\n${mode === 'exit-later' ? 'setTimeout(()=>process.exit(24),700);' : ''}\n`);
  await chmod(executable, 0o700);
  const child = spawn(process.execPath, [entry], { env: {
    PATH: process.env.PATH, FRONTEND_ORIGIN: 'https://bootstrap.example.com', TETHERLESS_PUBLIC_HOST: 'bootstrap.example.com',
    PORT: '19991', TETHERLESS_FRONTEND_DIR: dir, TETHERLESS_SERVICE_BINARY: executable, TETHERLESS_SOURCE_COMMIT_FILE: join(dir, 'source-commit.txt'),
    TETHERLESS_TEST_ACCESS_SHA256: createHash('sha256').update('X'.repeat(43)).digest('hex'),
    TETHERLESS_TEST_EXPIRES_AT: new Date(Date.now() + 3600000).toISOString().replace(/\.\d{3}Z$/, 'Z'),
    UNRELATED_PRIVATE_SECRET: 'SYNTHETIC-SHOULD-NOT-INHERIT',
  }, stdio: ['ignore', 'pipe', 'pipe'] });
  let output = ''; child.stdout.on('data', x => { output += x; }); child.stderr.on('data', x => { output += x; });
  const exit = new Promise(resolve => child.once('exit', (code, signal) => resolve({ code, signal })));
  t.after(() => { if (child.exitCode === null) child.kill('SIGTERM'); });
  return { child, exit, marker, dir, output: () => output };
}

test('supervisor forwards SIGTERM to SIGINT, suppresses child output and inherited secrets', async t => {
  const f = await fixture(t, 'normal');
  for (let i = 0; i < 100 && !f.output().includes('ready.'); i++) await sleep(50);
  assert.match(f.output(), /ready/); f.child.kill('SIGTERM'); assert.deepEqual(await f.exit, { code: 0, signal: null });
  assert.equal(await readFile(f.marker, 'utf8'), 'SIGINT');
  assert.deepEqual(JSON.parse(await readFile(join(f.dir, 'env.json'), 'utf8')), ['FRONTEND_ORIGIN', 'LANG', 'PATH', 'RUST_BACKTRACE', 'TETHERLESS_BIND', 'TETHERLESS_FRONTEND_DIR', 'TETHERLESS_PUBLIC_HOST']);
  assert.doesNotMatch(f.output(), /SYNTHETIC|PRIVATE|secret/);
});
test('backend startup failure stops supervisor without a restart', async t => {
  const f = await fixture(t, 'startup-fail'); assert.deepEqual(await f.exit, { code: 1, signal: null });
  assert.doesNotMatch(f.output(), /ready|SYNTHETIC/);
});
test('unexpected backend exit closes a ready service without a restart', async t => {
  const f = await fixture(t, 'exit-later'); assert.deepEqual(await f.exit, { code: 1, signal: null });
  assert.match(f.output(), /ready/); assert.match(f.output(), /will not restart/); assert.doesNotMatch(f.output(), /SYNTHETIC/);
});


test('invalid build source identity stops before backend creation', async t => {
  const f = await fixture(t, 'invalid-source'); assert.deepEqual(await f.exit, { code: 1, signal: null });
  assert.doesNotMatch(f.output(), /ready|SYNTHETIC/);
  await assert.rejects(readFile(join(f.dir, 'env.json'), 'utf8'), { code: 'ENOENT' });
});
