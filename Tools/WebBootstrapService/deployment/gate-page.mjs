// SPDX-License-Identifier: AGPL-3.0-only
import { createHash } from 'node:crypto';

// Serialized verbatim into the gate with an exact CSP hash. No external assets,
// storage, telemetry, clipboard or automatic credential submission.
function gateClient() {
  'use strict';
  const byId = id => document.getElementById(id);
  const generate = byId('generate-code');
  const open = byId('open-test');
  const input = byId('access-code');
  const verifier = byId('test-access-sha256');
  const status = byId('gate-status');
  const expires = Date.parse(byId('test-expiry').dateTime);
  let ready = false;
  let busy = false;
  let epoch = 0;
  let leaving = false;
  let controller;
  const available = () => Date.now() < expires;
  const say = message => { status.textContent = message; };
  const render = () => {
    generate.disabled = !ready || busy || !available() || input.value !== '';
    open.disabled = !ready || busy || !available() || input.value === '';
  };
  byId('access-form').addEventListener('submit', event => event.preventDefault());
  window.addEventListener('beforeunload', event => {
    if (input.value && !leaving) { event.preventDefault(); event.returnValue = ''; }
  });
  window.addEventListener('pagehide', () => {
    epoch += 1;
    controller?.abort();
    input.value = '';
    verifier.textContent = '';
    busy = false;
    leaving = false;
    say('此頁未保留測試碼。請重新產生，並等候設定完成。');
    render();
  });
  setTimeout(() => {
    epoch += 1;
    controller?.abort();
    busy = false;
    say('測試期限已結束，無法開啟測試。');
    render();
  }, Math.max(0, expires - Date.now()));
  async function checkCapabilities() {
    if (globalThis.isSecureContext !== true || typeof globalThis.crypto?.getRandomValues !== 'function' ||
        typeof globalThis.crypto?.subtle?.digest !== 'function' || typeof TextEncoder !== 'function' ||
        typeof fetch !== 'function' || typeof AbortController !== 'function') {
      say('此瀏覽器缺少安全產生功能，無法產生測試碼。');
      return;
    }
    try {
      // Public fixed probe, never randomness or a credential.
      const probe = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(''));
      const hex = Array.from(new Uint8Array(probe), b => b.toString(16).padStart(2, '0')).join('');
      if (hex !== 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855') throw new Error();
      ready = true;
      say(available() ? '請由你按「產生測試碼」。不需要複製或手動輸入。' : '測試期限已結束，無法開啟測試。');
    } catch { say('安全產生功能檢查失敗，無法產生測試碼。'); }
    render();
  }
  generate.addEventListener('click', async event => {
    if (!event.isTrusted || !ready || busy || !available() || input.value !== '') return;
    busy = true;
    const ticket = ++epoch;
    render();
    say('正在產生，請保留此頁。');
    let bytes;
    let encoded;
    let candidate;
    try {
      // Only this explicit trusted gesture can request random bytes.
      bytes = crypto.getRandomValues(new Uint8Array(32));
      candidate = btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
      if (!/^[A-Za-z0-9_-]{43}$/.test(candidate)) throw new Error();
      encoded = new TextEncoder().encode(candidate);
      const hash = await crypto.subtle.digest('SHA-256', encoded);
      const hex = Array.from(new Uint8Array(hash), b => b.toString(16).padStart(2, '0')).join('');
      if (!/^[a-f0-9]{64}$/.test(hex)) throw new Error();
      if (ticket !== epoch || !available()) return;
      input.value = candidate;
      // The sole stable operator-readable output is the one-way verifier.
      verifier.textContent = hex;
      say('已產生。請保留此頁，不要重新整理或關閉。等 dot 告知設定完成後，再由你按「Open test」。');
    } catch {
      if (ticket === epoch) say('產生失敗，未保留新測試碼。可再試一次。');
    } finally {
      bytes?.fill(0);
      encoded?.fill(0);
      candidate = null;
      if (ticket === epoch) { busy = false; render(); }
    }
  });
  open.addEventListener('click', async event => {
    if (!event.isTrusted || !ready || busy || !available() || !/^[A-Za-z0-9_-]{43}$/.test(input.value)) return;
    busy = true;
    const ticket = ++epoch;
    const attempt = new AbortController();
    controller = attempt;
    const timer = setTimeout(() => attempt.abort(), 20000);
    render();
    say('正在開啟；若設定尚未完成，測試碼會留在此頁。');
    try {
      const response = await fetch('/_test/access', {
        method: 'POST', mode: 'same-origin', credentials: 'same-origin',
        cache: 'no-store', redirect: 'follow', referrerPolicy: 'no-referrer',
        headers: { 'content-type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ code: input.value }), signal: attempt.signal,
      });
      if (ticket !== epoch || !available()) return;
      // A 200 gate page after a lost cookie/restart is NOT a successful unlock.
      // The proxy emits this marker only after authenticated root readback.
      if (response.status === 200 && response.redirected && response.url === location.origin + '/' &&
          response.headers.get('x-tetherless-test-access') === 'granted') {
        leaving = true;
        location.assign('/');
        return;
      }
      say(response.status === 410 ? '測試期限已結束，無法開啟測試。' :
        response.status === 429 ? '嘗試過於頻繁。測試碼仍保留，請等一分鐘後自行重試。' :
        '尚未開啟，測試碼仍保留。請等 dot 確認設定完成後再按「Open test」。');
    } catch {
      if (ticket === epoch) say('連線尚未完成，測試碼仍保留。請等服務恢復後自行重試。');
    } finally {
      clearTimeout(timer);
      if (controller === attempt) controller = null;
      if (ticket === epoch) { busy = false; render(); }
    }
  });
  void checkCapabilities();
}

const script = `(${gateClient.toString()})();`;
const style = 'body{font-family:system-ui,sans-serif;line-height:1.6;max-width:38rem;margin:2rem auto;padding:0 1rem;color:#17293a}button,input{font:inherit;box-sizing:border-box;min-height:44px;margin:.4rem 0;padding:.5rem}input{display:block;width:100%}button{cursor:pointer}button:disabled{cursor:default}output{display:block;overflow-wrap:anywhere;font-family:monospace}p{margin:.8rem 0}h1{font-size:1.6rem}h2{font-size:1.1rem}';
const hash = value => createHash('sha256').update(value).digest('base64');
export const gateCSP = `default-src 'none'; script-src 'sha256-${hash(script)}'; script-src-attr 'none'; style-src 'sha256-${hash(style)}'; style-src-attr 'none'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'`;

export function gatePage(sourceCommit, expires, closed = false) {
  const deadline = new Date(expires).toISOString().replace('.000Z', 'Z');
  return `<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Tetherless test access</title><style>${style}</style></head><body><main><h1>Tetherless 私密測試</h1><p>請在 dot 提供的雲端 Chrome 操作頁使用此流程。由你產生測試碼，dot 只讀取雜湊完成設定；不需要複製或手動輸入。自行在其他瀏覽器開啟此頁，dot 無法讀取該頁雜湊。</p><p>測試截止：<time id="test-expiry" datetime="${deadline}">${deadline}</time>（UTC）。此碼不是 Apple Account 密碼，請勿在此輸入 Apple 密碼。</p><button id="generate-code" type="button" disabled>產生測試碼</button><form id="access-form" method="post" action="/_test/access" autocomplete="off"><label for="access-code">Test access code（已遮蔽）</label><input id="access-code" name="code" type="password" readonly required minlength="43" maxlength="43" autocomplete="off" autocapitalize="none" spellcheck="false" pattern="[A-Za-z0-9_-]{43}"><button id="open-test" type="button" disabled>Open test</button></form><p id="gate-status" role="status" aria-live="polite">${closed ? '測試期限已結束，無法開啟測試。' : '正在檢查安全產生功能…'}</p><details><summary>設定用 SHA-256 雜湊</summary><output id="test-access-sha256" aria-label="設定用 SHA-256 雜湊"></output></details><noscript>需要 JavaScript 與安全的 WebCrypto，才能產生及送出測試碼。</noscript><p>產生後，測試碼先保留在此頁記憶體；只有你按「Open test」才會送到這個服務驗證。重新整理、關閉或離開可能失去測試碼；已產生後不會再次取代。服務重新啟動會終止測試存取與 Apple 工作階段。</p><section aria-label="Source and license"><h2>Source and license</h2><p><a href="https://github.com/oskuhsiu/Tetherless/tree/${sourceCommit}" rel="noopener noreferrer">Source for this deployed version (${sourceCommit})</a></p><p><a href="https://github.com/oskuhsiu/Tetherless/blob/${sourceCommit}/LICENSE" rel="noopener noreferrer">GNU Affero General Public License</a></p></section></main>${closed ? '' : `<script>${script}</script>`}</body></html>`;
}
