import { cpSync } from 'node:fs';
cpSync('licenses', 'dist/licenses', { recursive: true });
for (const path of ['THIRD_PARTY_NOTICES.md', 'runtime-lock.json']) cpSync(path, `dist/${path}`);
