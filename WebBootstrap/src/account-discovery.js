import { publicHttps } from './ota.js';

// Only read-only discovery is retried, never account/session mutations. A check
// uses at most two 5-second health attempts and one 5-second config request.
const MAX_JSON_BYTES = 16 * 1024;
function checkAborted(signal) { if (signal.aborted) throw signal.reason || new DOMException('Cancelled', 'AbortError'); }
// Discovery must not introduce a dependency on AbortSignal.timeout/any.
export function createReadDeadline(parentSignal, timeoutMs = 5000) {
  const controller = new AbortController(); let timedOut = false;
  const cancel = () => controller.abort(parentSignal.reason);
  if (parentSignal?.aborted) cancel(); else parentSignal?.addEventListener('abort', cancel, { once: true });
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  return { signal: controller.signal, get timedOut() { return timedOut; }, clear() { clearTimeout(timer); parentSignal?.removeEventListener('abort', cancel); } };
}
async function readJson(response) {
  if (response.headers.get('content-type')?.split(';')[0].trim().toLowerCase() !== 'application/json') throw new Error('content-type');
  const reader = response.body?.getReader();
  if (!reader) throw new Error('empty-body');
  const parts = []; let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read(); if (done) break;
      size += value.byteLength; if (size > MAX_JSON_BYTES) throw new Error('oversized');
      parts.push(value);
    }
  } catch (error) { await reader.cancel().catch(() => {}); throw error; }
  finally { reader.releaseLock(); }
  const bytes = new Uint8Array(size); let offset = 0;
  for (const part of parts) { bytes.set(part, offset); offset += part.byteLength; }
  return JSON.parse(new TextDecoder().decode(bytes));
}
async function read(url, { fetcher, signal, timeoutMs }) {
  const deadline = createReadDeadline(signal, timeoutMs);
  try {
    let response;
    try { response = await fetcher(url.href, { credentials: 'same-origin', redirect: 'error', cache: 'no-store', referrerPolicy: 'no-referrer', signal: deadline.signal }); }
    catch (error) {
      checkAborted(signal);
      if (deadline.timedOut || error.name === 'TypeError' || error.name === 'TimeoutError') return { kind: 'unreachable', retry: true, reason: deadline.timedOut ? 'timeout' : 'network' };
      return { kind: 'unreachable', reason: 'unreadable' };
    }
    checkAborted(signal);
    if (deadline.timedOut) return { kind: 'unreachable', retry: true, reason: 'timeout' };
    if (response.redirected || response.url !== url.href || response.type === 'opaque' || response.type === 'opaqueredirect') return { kind: 'invalid', status: response.status, reason: 'origin-or-redirect' };
    if (!response.ok) return { kind: response.status === 404 ? 'unconfigured' : 'unreachable', retry: response.status >= 500 && response.status <= 599, status: response.status, reason: 'http' };
    try { const body = await readJson(response); checkAborted(signal); if (deadline.timedOut) return { kind: 'unreachable', retry: true, status: response.status, reason: 'timeout' }; return { body, status: response.status }; }
    catch (error) { checkAborted(signal); return deadline.timedOut ? { kind: 'unreachable', retry: true, status: response.status, reason: 'timeout' } : { kind: 'invalid', status: response.status, reason: error.name === 'SyntaxError' ? 'json' : ['content-type', 'empty-body', 'oversized'].includes(error.message) ? error.message : 'unreadable' }; }
  } finally { deadline.clear(); }
}
function delay(ms, signal) {
  return new Promise((resolve, reject) => {
    checkAborted(signal);
    const finish = () => { signal.removeEventListener('abort', cancel); resolve(); };
    const timer = setTimeout(finish, ms);
    const cancel = () => { clearTimeout(timer); reject(signal.reason); };
    signal.addEventListener('abort', cancel, { once: true });
  });
}
export async function discoverAccountService({ base, origin, signal, fetcher = fetch, timeoutMs = 5000, retryDelayMs = 400 }) {
  const root = new URL(base), current = new URL(origin);
  checkAborted(signal);
  // A foreign <base>, Pages or insecure non-local page may never collect secrets.
  const pages = current.hostname === 'github.io' || current.hostname.endsWith('.github.io');
  const allowed = root.origin === current.origin && !pages && (current.protocol === 'https:' || ['127.0.0.1', 'localhost'].includes(current.hostname));
  let result = { kind: 'unconfigured', reason: 'unsupported-host' };
  if (root.origin !== current.origin) return { kind: 'invalid' };
  const options = { fetcher, signal, timeoutMs };
  if (allowed) {
    for (let attempt = 0; attempt < 2; attempt++) {
      result = await read(new URL('health', root), options);
      if (Object.hasOwn(result, 'body')) {
        const health = result.body;
        if (!health || typeof health !== 'object' || Array.isArray(health) || health.protocol !== 1 || typeof health.appleAuthAvailable !== 'boolean') result = { kind: 'invalid', status: result.status, reason: 'protocol' };
        else if (!health.appleAuthAvailable) result = { kind: 'unconfigured', status: result.status, reason: 'disabled' };
        else return { kind: 'ready', profileAvailable: health.profileServiceAvailable === true };
      }
      if (!result.retry || attempt === 1) break;
      await delay(retryDelayMs, signal);
    }
  }
  const reasons = { timeout: '檢查逾時', network: '瀏覽器無法讀取回應（網路或請求遭阻擋）', unreadable: '回應無法讀取', 'origin-or-redirect': '回應來源或重新導向未通過驗證', http: '服務回應未成功', 'content-type': '回應類型不是 JSON', json: 'JSON 格式無效', 'empty-body': '沒有回應內容', oversized: '回應超過大小限制', protocol: '服務協定或登入能力欄位不符', disabled: '服務未啟用 Apple 登入', 'unsupported-host': '此頁所在位置不支援帳號登入' };
  const diagnostic = `頁面 ${current.origin}；${new URL('health', root).pathname}：${result.status ? `HTTP ${result.status}；` : ''}${reasons[result.reason]}`;
  const config = await read(new URL('config.json', root), options);
  if (config.body?.accountServiceUrl) {
    try {
      const url = new URL(publicHttps(config.body.accountServiceUrl));
      if (url.hostname !== 'github.io' && !url.hostname.endsWith('.github.io')) return { kind: result.kind, diagnostic, externalUrl: url.href };
    } catch { /* Invalid configuration never enables account collection. */ }
  }
  return { kind: result.kind, diagnostic };
}
