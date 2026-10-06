// SPDX-License-Identifier: AGPL-3.0-only
// Run through docker exec with this script mounted read-only at /verification.
// Export only known nonsecret build receipts. Never copy image ownership/modes
// onto the runner, inspect environment variables, or enumerate arbitrary files.
import { constants } from 'node:fs';
import { lstat, open } from 'node:fs/promises';
import { join, isAbsolute } from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';

export const FILES = Object.freeze([
  'source-commit.txt',
  'backend-cargo.txt',
  'backend-rustc.txt',
  'backend-debian-packages.txt',
  'frontend-node.txt',
  'frontend-npm.txt',
  'frontend-debian-packages.txt',
  'runtime-debian-packages.txt',
]);
export const MAX_FILE_BYTES = 512 * 1024;
export const MAX_TOTAL_BYTES = 2 * 1024 * 1024;
function rejected() { throw new Error('Build-info export rejected'); }

async function readReceipt(root, name) {
  const file = await open(join(root, name), constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const before = await file.stat();
    if (!before.isFile() || before.nlink !== 1 || before.size < 1 ||
        before.size > MAX_FILE_BYTES || (before.mode & 0o222) !== 0) rejected();
    // A bounded read also catches growth after stat without allocating its size.
    const buffer = Buffer.alloc(MAX_FILE_BYTES + 1);
    let length = 0;
    while (length < buffer.length) {
      const { bytesRead } = await file.read(buffer, length, buffer.length - length, null);
      if (bytesRead === 0) break;
      length += bytesRead;
    }
    const after = await file.stat();
    if (length !== before.size || length > MAX_FILE_BYTES || after.size !== before.size ||
        after.mtimeMs !== before.mtimeMs || after.ctimeMs !== before.ctimeMs) rejected();
    const bytes = buffer.subarray(0, length);
    return { path: name, bytes: length, sha256: createHash('sha256').update(bytes).digest('hex'),
      encoding: 'base64', content: bytes.toString('base64') };
  } finally { await file.close(); }
}

// The root argument is an explicit fixture seam. CLI always uses /app/build-info.
export async function exportBuildInfo(expectedCommit, root = '/app/build-info') {
  if (!/^[a-f0-9]{40}$/.test(expectedCommit ?? '') || !isAbsolute(root)) rejected();
  const directory = await lstat(root);
  if (!directory.isDirectory() || directory.isSymbolicLink() || (directory.mode & 0o222) !== 0) rejected();
  const records = [];
  let totalBytes = 0;
  for (const name of FILES) {
    const record = await readReceipt(root, name);
    if (name === 'source-commit.txt' &&
        Buffer.from(record.content, 'base64').toString('utf8') !== `${expectedCommit}\n`) rejected();
    totalBytes += record.bytes;
    if (totalBytes > MAX_TOTAL_BYTES) rejected();
    records.push(record);
  }
  return { schemaVersion: 1, sourceCommit: expectedCommit, totalBytes, files: records };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  try {
    if (process.argv.length !== 3) rejected();
    const result = await exportBuildInfo(process.argv[2]);
    // Construct everything first: no partial payload on validation/read failure.
    process.stdout.write(`${JSON.stringify(result)}\n`);
  } catch {
    process.stderr.write('Build-info export failed validation or reading.\n');
    process.exitCode = 1;
  }
}
