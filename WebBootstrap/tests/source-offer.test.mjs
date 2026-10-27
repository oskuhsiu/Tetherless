import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const script = fileURLToPath(new URL('../scripts/copy-notices.mjs', import.meta.url));
const original = await readFile(new URL('../public/licenses.html', import.meta.url), 'utf8');
async function build(t, sourceCommit, html = original) {
  const cwd = await mkdtemp(join(tmpdir(), 'tetherless-source-offer-'));
  t.after(() => rm(cwd, { recursive: true, force: true }));
  await mkdir(join(cwd, 'licenses')); await mkdir(join(cwd, 'dist'));
  for (const [path, text] of [['dist/licenses.html', html], ['THIRD_PARTY_NOTICES.md', 'fixture'], ['runtime-lock.json', '{}']]) {
    await writeFile(join(cwd, path), text);
  }
  const env = { ...process.env }; delete env.SOURCE_COMMIT;
  if (sourceCommit !== undefined) env.SOURCE_COMMIT = sourceCommit;
  const result = spawnSync(process.execPath, [script], { cwd, env, encoding: 'utf8' });
  return { ...result, html: await readFile(join(cwd, 'dist/licenses.html'), 'utf8') };
}

test('production source offer is stamped with one exact immutable source and license pair', async t => {
  const commit = 'a1'.repeat(20); const result = await build(t, commit);
  assert.equal(result.status, 0, result.stderr);
  assert.ok(result.html.includes(`https://github.com/oskuhsiu/Tetherless/tree/${commit}`));
  assert.ok(result.html.includes(`https://github.com/oskuhsiu/Tetherless/blob/${commit}/LICENSE`));
  assert.equal(result.html.split('Source for this deployed version').length, 2);
  assert.ok(!result.html.includes('<!-- DEPLOYED_SOURCE -->'));
  assert.ok(result.html.includes('./licenses/Tetherless-AGPL-3.0.txt'));
  assert.ok(result.html.includes('./THIRD_PARTY_NOTICES.md'));
});

test('source stamping rejects empty, mutable, malformed and injectable build identities', async t => {
  for (const commit of ['', 'main', 'unrecorded', 'a'.repeat(39), 'A'.repeat(40), 'g'.repeat(40), '"><script>fixture</script>']) {
    const result = await build(t, commit);
    assert.notEqual(result.status, 0); assert.equal(result.html, original);
  }
});

test('source stamping fails on a missing or duplicated marker, while unversioned local builds retain notices', async t => {
  for (const html of [original.replace('<!-- DEPLOYED_SOURCE -->', ''), original + '<!-- DEPLOYED_SOURCE -->']) {
    const result = await build(t, 'a'.repeat(40), html); assert.notEqual(result.status, 0);
  }
  const local = await build(t, undefined); assert.equal(local.status, 0, local.stderr); assert.equal(local.html, original);
});
