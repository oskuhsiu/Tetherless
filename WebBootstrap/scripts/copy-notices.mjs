import { cpSync, readFileSync, writeFileSync } from 'node:fs';
// Only the build may stamp the fixed repository's immutable source offer.
// Local unversioned builds retain the generic license page; Docker requires this ARG.
const sourceCommit = process.env.SOURCE_COMMIT;
if (sourceCommit !== undefined && !/^[a-f0-9]{40}$/.test(sourceCommit)) {
  throw new Error('SOURCE_COMMIT must be a full lowercase 40-hex commit');
}
cpSync('licenses', 'dist/licenses', { recursive: true });
for (const path of ['THIRD_PARTY_NOTICES.md', 'runtime-lock.json']) cpSync(path, `dist/${path}`);
if (sourceCommit !== undefined) {
  const path = 'dist/licenses.html';
  const html = readFileSync(path, 'utf8');
  const marker = '<!-- DEPLOYED_SOURCE -->';
  if (html.split(marker).length !== 2) throw new Error('Missing or duplicate source-offer placeholder');
  writeFileSync(path, html.replace(marker, `<section aria-label="Source and license"><h2>Source for this deployed version</h2><p><a href="https://github.com/oskuhsiu/Tetherless/tree/${sourceCommit}" rel="noopener noreferrer">Exact source (${sourceCommit})</a></p><p><a href="https://github.com/oskuhsiu/Tetherless/blob/${sourceCommit}/LICENSE" rel="noopener noreferrer">GNU Affero General Public License</a></p></section>`));
}
