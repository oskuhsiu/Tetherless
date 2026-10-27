import { LIMITS } from './archive.js';
// A reviewed, pinned config is the trust root. Never infer "latest" from GitHub.
export const OFFICIAL_REPOSITORY = 'oskuhsiu/Tetherless';
export const MAX_RELEASE_BYTES = LIMITS.input;
export function validateRelease(value) {
  if (!value || typeof value !== 'object') throw new Error('尚未綁定已驗證的 Tetherless 官方安裝包');
  const { repository, tag, assetId, assetName, assetUrl, size, sha256, sourceCommit, buildRunId, buildHeadSha, runAttempt } = value;
  if (repository !== OFFICIAL_REPOSITORY || !tag || typeof tag !== 'string' || tag.length > 128 || ['.', '..'].includes(tag) || /[\x00-\x1f\x7f]/.test(tag) || typeof assetName !== 'string' || !/^[A-Za-z0-9_.-]+\.ipa$/.test(assetName)) throw new Error('官方版本資訊無效');
  if (Number.isSafeInteger(size) && size > MAX_RELEASE_BYTES) throw new Error(`官方安裝包超過目前瀏覽器支援的 ${MAX_RELEASE_BYTES / 1024 / 1024} MiB 上限，尚未採用檔案`);
  if (!Number.isSafeInteger(runAttempt) || runAttempt < 1 || typeof assetId !== 'string' || typeof buildRunId !== 'string' || !/^[1-9][0-9]{0,19}$/.test(assetId) || !/^[1-9][0-9]{0,19}$/.test(buildRunId) || !/^[a-f0-9]{40}$/.test(sourceCommit) || !/^[a-f0-9]{40}$/.test(buildHeadSha) || !/^[a-f0-9]{64}$/.test(sha256) || !Number.isSafeInteger(size) || size < 1 || size > MAX_RELEASE_BYTES) throw new Error('官方版本缺少有效的來源、建置或檔案校驗資訊');
  const expected = `https://github.com/${repository}/releases/download/${encodeURIComponent(tag)}/${encodeURIComponent(assetName)}`;
  if (assetUrl !== expected) throw new Error('官方安裝包網址與指定 GitHub Release 不符');
  return Object.freeze({ repository, tag, assetId: String(assetId), assetName, assetUrl, size, sha256, sourceCommit, buildRunId: String(buildRunId), buildHeadSha, runAttempt });
}
export async function verifyReleaseFile(file, manifest, signal) {
  const release = validateRelease(manifest);
  signal?.throwIfAborted();
  if (file.size !== release.size) throw new Error('安裝包大小與官方版本資訊不符');
  const bytes = await file.arrayBuffer(); signal?.throwIfAborted();
  const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map((b) => b.toString(16).padStart(2, '0')).join('');
  signal?.throwIfAborted();
  if (digest !== release.sha256) throw new Error('安裝包 SHA-256 不符，未採用這個檔案');
  return file;
}
export async function acquireRelease(manifest, { signal, fetcher = fetch, onProgress = () => {} } = {}) {
  const release = validateRelease(manifest);
  const timeout = AbortSignal.timeout(120000);
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout;
  let response;
  combined.throwIfAborted();
  try { response = await fetcher(release.assetUrl, { signal: combined, credentials: 'omit', cache: 'no-store', referrerPolicy: 'no-referrer', mode: 'cors' }); }
  catch (error) { if (combined.aborted) throw combined.reason; throw new Error('GitHub 安裝包無法直接讀取，可能是 CORS 或網路限制。請下載同一版本後選取檔案，仍會核對 SHA-256'); }
  if (!response.ok || !response.body) throw new Error(`官方 Release 安裝包無法取得（HTTP ${response.status}）`);
  const final = new URL(response.url || release.assetUrl);
  if (final.protocol !== 'https:' || final.username || final.password || final.port || !['github.com', 'release-assets.githubusercontent.com'].includes(final.hostname)) { await response.body.cancel(); throw new Error('GitHub 下載重新導向非預期的位置'); }
  const declared = response.headers.get('content-length');
  if (declared !== null && (!/^[0-9]+$/.test(declared) || Number(declared) !== release.size)) { await response.body.cancel(); throw new Error('安裝包回應大小與官方版本資訊不符'); }
  const reader = response.body.getReader(), chunks = []; let received = 0;
  const abort = () => { void reader.cancel().catch(() => {}); }; combined.addEventListener('abort', abort, { once: true });
  try {
    while (true) { combined.throwIfAborted(); const { done, value } = await reader.read(); combined.throwIfAborted(); if (done) break; received += value.byteLength; if (received > release.size || received > MAX_RELEASE_BYTES) throw new Error('官方安裝包超過允許的下載大小'); chunks.push(value); onProgress(received, release.size); }
  } catch (error) { await reader.cancel().catch(() => {}); throw error; }
  finally { combined.removeEventListener('abort', abort); reader.releaseLock(); }
  return verifyReleaseFile(new File(chunks, release.assetName, { type: 'application/zip' }), release, combined);
}
