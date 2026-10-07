// SPDX-License-Identifier: AGPL-3.0-only
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, readFile, chmod, lstat, rm, symlink, link, unlink } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { execFileSync, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { exportBuildInfo, FILES, MAX_FILE_BYTES } from './export-build-info.mjs';

const COMMIT = '80587620c7e2852259a075900827a9f05a527ffa';
async function fixture(t) {
  const parent = await mkdtemp(join(tmpdir(), 'tetherless-readonly-build-info-'));
  const root = join(parent, 'build-info'); await mkdir(root);
  const original = new Map();
  for (const name of FILES) {
    const bytes = Buffer.from(name === 'source-commit.txt' ? `${COMMIT}\n` : `synthetic ${name}\t1.0\n`);
    original.set(name, bytes); await writeFile(join(root, name), bytes); await chmod(join(root, name), 0o444);
  }
  // A tempting unrelated file must not be enumerated, read or exported.
  await writeFile(join(root, 'unrelated-private-file.txt'), 'SYNTHETIC-PRIVATE-SENTINEL');
  await chmod(join(root, 'unrelated-private-file.txt'), 0o000);
  await chmod(root, 0o555);
  t.after(async () => { await chmod(root, 0o700); await rm(parent, { recursive: true, force: true }); });
  return { parent, root, original };
}
async function replace(root, name, contents, mode = 0o444) {
  await chmod(root, 0o755); await unlink(join(root, name)); await writeFile(join(root, name), contents);
  await chmod(join(root, name), mode); await chmod(root, 0o555);
}

test('exports exact bytes and hashes from 0555 directory/0444 files without changing modes', async t => {
  const { root, original } = await fixture(t);
  const exported = await exportBuildInfo(COMMIT, root);
  assert.equal(exported.schemaVersion, 1); assert.equal(exported.sourceCommit, COMMIT);
  assert.deepEqual(exported.files.map(f => f.path), FILES);
  assert.equal(exported.totalBytes, [...original.values()].reduce((sum, b) => sum + b.length, 0));
  for (const record of exported.files) {
    const expected = original.get(record.path);
    assert.equal(record.bytes, expected.length); assert.equal(record.encoding, 'base64');
    assert.deepEqual(Buffer.from(record.content, 'base64'), expected);
    assert.equal(record.sha256, createHash('sha256').update(expected).digest('hex'));
    assert.equal((await lstat(join(root, record.path))).mode & 0o777, 0o444);
    assert.deepEqual(await readFile(join(root, record.path)), expected);
  }
  assert.equal((await lstat(root)).mode & 0o777, 0o555);
  assert.ok(!JSON.stringify(exported).includes('SYNTHETIC-PRIVATE-SENTINEL'));
  assert.deepEqual(await exportBuildInfo(COMMIT, root), exported);
});
test('rejects malformed or mismatched build source and exports nothing', async t => {
  const { root } = await fixture(t);
  for (const expected of ['', 'main', 'a'.repeat(39), 'g'.repeat(40), 'a'.repeat(40)]) {
    await assert.rejects(exportBuildInfo(expected, root));
  }
  await replace(root, 'source-commit.txt', `${COMMIT}\nEXTRA`);
  await assert.rejects(exportBuildInfo(COMMIT, root));
});
test('rejects a missing allowlisted receipt', async t => {
  const { root } = await fixture(t);
  await chmod(root, 0o755); await unlink(join(root, FILES[1])); await chmod(root, 0o555);
  await assert.rejects(exportBuildInfo(COMMIT, root));
});
test('rejects symlink, hardlink and nonregular receipt substitutions', async t => {
  const { root, parent } = await fixture(t);
  const name = FILES[1]; const file = join(root, name);
  const outside = join(parent, 'outside.txt'); await writeFile(outside, 'synthetic outside'); await chmod(outside, 0o444);
  await chmod(root, 0o755); await unlink(file); await symlink(outside, file); await chmod(root, 0o555);
  await assert.rejects(exportBuildInfo(COMMIT, root));
  await chmod(root, 0o755); await unlink(file); await link(outside, file); await chmod(root, 0o555);
  await assert.rejects(exportBuildInfo(COMMIT, root));
  await chmod(root, 0o755); await unlink(file); await mkdir(file); await chmod(file, 0o555); await chmod(root, 0o555);
  await assert.rejects(exportBuildInfo(COMMIT, root));
});
test('rejects writable files or root and a symlinked root', async t => {
  const { root, parent } = await fixture(t);
  await chmod(join(root, FILES[1]), 0o644); await assert.rejects(exportBuildInfo(COMMIT, root));
  await chmod(join(root, FILES[1]), 0o444); await chmod(root, 0o755); await assert.rejects(exportBuildInfo(COMMIT, root));
  await chmod(root, 0o555); const alias = join(parent, 'alias'); await symlink(root, alias);
  await assert.rejects(exportBuildInfo(COMMIT, alias));
});
test('enforces per-file, nonempty and cumulative export bounds', async t => {
  const { root } = await fixture(t);
  await replace(root, FILES[1], Buffer.alloc(MAX_FILE_BYTES + 1, 65));
  await assert.rejects(exportBuildInfo(COMMIT, root));
  await replace(root, FILES[1], Buffer.alloc(0)); await assert.rejects(exportBuildInfo(COMMIT, root));
  for (const name of FILES.slice(1, 5)) await replace(root, name, Buffer.alloc(MAX_FILE_BYTES, 65));
  await assert.rejects(exportBuildInfo(COMMIT, root));
});


test('a substituted FIFO is rejected without waiting for a writer', { timeout: 2000 }, async t => {
  const { root } = await fixture(t); const file = join(root, FILES[1]);
  await chmod(root, 0o755); await unlink(file);
  execFileSync('mkfifo', ['-m', '444', file]); await chmod(root, 0o555);
  await assert.rejects(exportBuildInfo(COMMIT, root));
});


test('CLI rejects invalid invocation with no payload or raw diagnostic details', () => {
  const script = fileURLToPath(new URL('./export-build-info.mjs', import.meta.url));
  for (const args of [[], ['INVALID-SYNTHETIC-COMMIT'], [COMMIT, '/arbitrary/path']]) {
    const result = spawnSync(process.execPath, [script, ...args], { encoding: 'utf8' });
    assert.equal(result.status, 1); assert.equal(result.stdout, '');
    assert.equal(result.stderr, 'Build-info export failed validation or reading.\n');
  }
});

test('Docker context permits only the pinned public owned IPA after blanket artifact exclusions', async () => {
  const owned = 'WebBootstrap/tests/fixtures/owned-signing-test/Signing-test-app-not-Tetherless.ipa';
  const contents = await readFile(new URL('../Dockerfile.dockerignore', import.meta.url), 'utf8');
  const rules = contents.split(/\r?\n/).map(line => line.trim()).filter(line => line && !line.startsWith('#'));
  // Closed contract for the current ordered rules, not a general dockerignore
  // emulator. Docker's last matching rule wins. Broad inclusions precede the
  // blanket artifact denials; only these two exact public paths follow them.
  const baseline = [
    '**', '!LICENSE', '!WebBootstrap/', '!WebBootstrap/**', '!Tools/',
    '!Tools/WebBootstrapService/', '!Tools/WebBootstrapService/README.md',
    '!Tools/WebBootstrapService/Cargo.toml', '!Tools/WebBootstrapService/Cargo.lock',
    '!Tools/WebBootstrapService/src/', '!Tools/WebBootstrapService/src/**',
    '!Tools/WebBootstrapService/tests/', '!Tools/WebBootstrapService/tests/**',
    '!Tools/WebBootstrapService/deployment/', '!Tools/WebBootstrapService/deployment/**',
    '**/node_modules', '**/dist', '**/target', '**/.toolchain', '**/.env*',
    '**/.git', '**/*secret*', '**/*.pem', '**/*.p8', '**/*.mobileprovision',
    '**/.npmrc', '**/.netrc', '**/.git-credentials', '**/*.key', '**/*.p12',
    '**/*.pfx', '**/*.ipa', '**/test-results', '**/playwright-report', '**/playwright-gate-report', '**/qa-evidence',
    '!Tools/WebBootstrapService/tests/fixtures/request.pem',
  ];
  assert.deepEqual(rules, [...baseline, `!${owned}`]);
  const postIpaExceptions = rules.slice(rules.indexOf('**/*.ipa') + 1).filter(rule => rule.startsWith('!'));
  assert.deepEqual(postIpaExceptions, ['!Tools/WebBootstrapService/tests/fixtures/request.pem', `!${owned}`]);
  for (const unrelated of [
    'private.ipa', 'WebBootstrap/private.ipa',
    owned.replace('Signing-test-app-not-Tetherless.ipa', 'another.ipa'),
    owned.replace('.ipa', '-signed.ipa'),
    owned.replace('owned-signing-test/', 'other/'),
    'WebBootstrap/public/Signing-test-app-not-Tetherless.ipa',
    'Tools/WebBootstrapService/tests/fixtures/Signing-test-app-not-Tetherless.ipa',
  ]) assert.equal(postIpaExceptions.includes(`!${unrelated}`), false, unrelated);
  const bytes = await readFile(new URL('../../../../' + owned, import.meta.url));
  assert.equal(bytes.length, 14853);
  assert.equal(createHash('sha256').update(bytes).digest('hex'), 'fda8c913af9d6f39f8a4351bd94d7953bb99b2b25506e67a3e7d943dafaf8111');
});

test('Docker uses the owned fixture in the frontend test builder without copying test inputs into runtime', async () => {
  const dockerfile = await readFile(new URL('../Dockerfile', import.meta.url), 'utf8');
  const stages = dockerfile.split(/^FROM /m).slice(1);
  const frontend = stages.find(stage => stage.split('\n')[0].endsWith(' AS frontend'));
  const runtime = stages.find(stage => stage.split('\n')[0].endsWith(' AS runtime'));
  assert(frontend && runtime);
  const copies = stage => stage.split('\n').filter(line => line.startsWith('COPY '));
  assert.deepEqual(copies(frontend), [
    'COPY WebBootstrap/package.json WebBootstrap/package-lock.json ./',
    'COPY WebBootstrap/ ./',
  ]);
  assert(frontend.indexOf('COPY WebBootstrap/ ./') < frontend.indexOf('RUN npm test && npm run build'));
  assert.match(frontend, /^RUN npm test && npm run build \\/m);
  assert.deepEqual(copies(runtime), [
    'COPY --from=backend /src/Tools/WebBootstrapService/target/release/tetherless-web-bootstrap-service /app/',
    'COPY --from=frontend /src/WebBootstrap/dist /app/frontend',
    'COPY --from=frontend /build-info /app/build-info',
    'COPY --from=backend /build-info /app/build-info',
    'COPY LICENSE /app/licenses/AGPL-3.0.txt',
    'COPY Tools/WebBootstrapService/README.md /app/licenses/account-service-notices.md',
    'COPY Tools/WebBootstrapService/deployment/*.mjs /app/deployment/',
  ]);
  assert.doesNotMatch(runtime, /^ADD /m);
});
