import forge from 'node-forge';
import { inspectIpa } from './material.js';
import { publicHttps } from './ota.js';
import { tetherlessGroup } from './tetherless-identity.js';
import { setupDeviceEnrollment } from './device-enrollment.js';
const $ = (id) => document.getElementById(id);
const safeErrors = { appleAuthenticationFailed: 'Apple 登入失敗，請重新開始', expired: '登入 session 已到期，請重新登入', certificateLimit: '憑證名額不足。此服務不會自動撤銷其他憑證', busy: '原申請仍在處理中，請稍後只查詢原申請結果', profileMismatch: 'Apple profile 與 Team、裝置、App 或共享群組不符，未提供簽署資料', certificateMismatch: 'Apple 憑證與此分頁 CSR 不符', appleRequestFailed: 'Apple 請求未完成，請確認帳號狀態', authenticationFailed: 'Apple 登入失敗，請重新開始', sessionExpired: '登入 session 已到期，請重新登入', wrongState: '這次操作的狀態已改變。請先取消 session 再重新開始；不要重複建立憑證', certificateCapacity: '憑證名額不足。此服務不會自動撤銷其他憑證', provisioningUncertain: 'Apple 操作結果不確定。保留此分頁的原私鑰；此服務不會再次建立憑證', provisioningFailed: 'Apple provisioning 未完成。請檢查 Team 與裝置狀態；若結果不確定，不要重複送出' };
export function setupAccount({ getIpa, ensureIpa = async () => getIpa(), onMaterial, onState = () => {}, onInvalidate = () => {} }) {
  let session, aborter, generation = 0, expiryTimer, busy = false, pendingProvision, serviceAvailable = false, profileAvailable = false, phase = 'checking', selectedPlan;
  const state = (value) => { phase = value; onState(value); };
  const validUdid = () => /^(?:[0-9A-Fa-f]{40}|[0-9A-Fa-f]{8}-[0-9A-Fa-f]{16})$/.test($('account-udid').value.trim());
  function showLogin() {
    $('account-form').inert = false;
    const needsDevice = serviceAvailable && profileAvailable && !validUdid();
    $('prelogin-device').hidden = !needsDevice; $('account-form').hidden = !serviceAvailable || needsDevice;
    if (needsDevice) { $('prelogin-device-slot').append($('device-collection'), $('device-details')); $('device-collection').hidden = false; state('device'); }
    else state(serviceAvailable ? 'login' : $('service-link').hidden ? 'unavailable' : 'external');
  }
  const say = (text) => { $('account-status').textContent = text; };
  const base = new URL('.', document.baseURI);
  const devices = setupDeviceEnrollment(base, { enabled: () => serviceAvailable && profileAvailable && !session && !busy, onReceived: () => { if (!session) showLogin(); } });
  $('continue-device').onclick = () => { if (!validUdid()) { $('device-details').open = true; return say('請取得或輸入有效的 iPhone UDID'); } devices.clear(); showLogin(); say('裝置資料已準備好，請登入 Apple。稍後仍須確認並授權註冊。'); };
  window.addEventListener('pageshow', (event) => { if (event.persisted && serviceAvailable) devices.resume(); });
  const route = (path) => { const url = new URL(path.replace(/^\//, ''), base); if (url.origin !== location.origin) throw new Error('登入服務必須與此頁同源'); return url.href; };
  function headers() { return { 'Content-Type': 'application/json', ...(session ? { Authorization: `Bearer ${session.sessionToken}` } : {}) }; }
  async function request(path, options = {}) {
    const response = await fetch(route(path), { ...options, headers: headers(), credentials: 'same-origin', redirect: 'error', cache: 'no-store', referrerPolicy: 'no-referrer', signal: aborter ? AbortSignal.any([aborter.signal, AbortSignal.timeout(150000)]) : AbortSignal.timeout(150000) });
    const text = await response.text();
    let body; try { body = text ? JSON.parse(text) : {}; } catch { throw new Error('簽署服務沒有傳回有效回應'); }
    if (!response.ok) { const code = body.error || body.code; throw new Error(safeErrors[code] || `簽署服務回應 ${response.status}。請檢查狀態，勿重複提交不確定的操作。`); }
    return body;
  }
  function clear({ preserveEnrollment = false, preserveDevice = false } = {}) {
    const retainedUdid = preserveDevice ? $('account-udid').value : '';
    if (preserveEnrollment) devices.pause(); else { devices.clear(); $('device-status').textContent = ''; }
    pendingProvision = undefined; selectedPlan = undefined; onInvalidate();
    generation++; aborter?.abort(); aborter = undefined; busy = false; clearTimeout(expiryTimer);
    if (session) { const { sessionId, sessionToken } = session; fetch(route(`v1/sessions/${encodeURIComponent(sessionId)}`), { method: 'DELETE', headers: { Authorization: `Bearer ${sessionToken}` }, credentials: 'same-origin', redirect: 'error', keepalive: true, referrerPolicy: 'no-referrer' }).catch(() => {}); }
    session = undefined;
    for (const id of ['apple-password', 'verification-code', 'apple-id', 'account-udid']) $(id).value = '';
    $('account-udid').value = retainedUdid;
    for (const id of ['login-consent', 'provision-consent']) $(id).checked = false;
    for (const id of ['two-factor', 'provision-form', 'logout']) $(id).hidden = true;
    $('send-sms').disabled = false; $('verify-button').disabled = false; $('login-button').disabled = !serviceAvailable; $('provision-button').disabled = false; $('provision-button').textContent = '同意並準備 App'; $('account-form').inert = false;
    for (const id of ['team', 'device-name', 'account-udid', 'provision-consent']) $(id).disabled = false;
    showLogin();
    say('登入 session 已取消；伺服器也會在最長 10 分鐘後清除未完成 session');
  }
  $('logout').onclick = clear;
  async function poll(current) {
    while (current === generation && session) {
      const result = await request(`v1/sessions/${session.sessionId}`);
      if (current !== generation) return;
      if (result.state === 'authenticated') {
        $('two-factor').hidden = true; const { teams } = await request(`v1/sessions/${session.sessionId}/teams`); if (current !== generation) return;
        if (!Array.isArray(teams) || !teams.length) throw new Error('此帳號沒有可用的 Apple Team');
        $('team').replaceChildren(...teams.map((team) => { const option = document.createElement('option'); option.value = team.id; option.textContent = `${team.name} · ${team.type} · ${team.id}`; return option; }));
        $('team-choice').hidden = teams.length === 1; $('team-summary').hidden = teams.length !== 1; $('team-summary').textContent = teams.length === 1 ? `使用 ${teams[0].name} · ${teams[0].type} · ${teams[0].id}` : '';
        $('provision-device-slot').append($('device-details')); $('device-collection').hidden = true; $('prelogin-device').hidden = true; $('device-details').open = true;
        $('provision-plan').textContent = `${selectedPlan.ipa.name}\nApp IDs：\n${selectedPlan.bundles.map((bundle) => bundle.id).join('\n')}\n${selectedPlan.appGroup ? `App Group：${selectedPlan.appGroup.identifier}` : '此 IPA 不需要 Tetherless 共用 App Group'}\n另會註冊下方裝置、建立開發憑證並取得上述 App IDs 的 profiles。`;
        $('provision-form').hidden = false; state('authenticated'); say('確認這支 iPhone 與以下授權後，將自動取得簽署資料並在本機準備 App。'); return;
      }
      if (result.state === 'failed') throw new Error(safeErrors[result.error] || 'Apple 登入未完成，請取消後重新登入');
      if (result.state === 'awaitingTwoFactor') {
        $('account-form').hidden = true; $('two-factor').hidden = false; state('twoFactor');
        const numbers = result.challenge?.numbers || []; const selected = $('phone-choice').value;
        $('sms-options').hidden = !numbers.length;
        $('phone-choice').replaceChildren(...numbers.map((number) => { const option = document.createElement('option'); option.value = String(number.id); option.textContent = `電話號碼末兩碼 ${number.lastTwoDigits}`; return option; }));
        if (numbers.some((number) => String(number.id) === selected)) $('phone-choice').value = selected;
        say(result.challenge?.retry ? '驗證碼未被接受，請重新輸入' : '請輸入 Apple 裝置或簡訊收到的驗證碼，也可選擇下方 Apple 提供的電話號碼要求簡訊');
      }
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }
  $('account-form').onsubmit = async (event) => {
    event.preventDefault(); if (!serviceAvailable || phase !== 'login' || busy || session || !$('login-consent').checked) return;
    busy = true; const current = ++generation; aborter = new AbortController(); $('login-button').disabled = true; $('account-form').inert = true; $('logout').hidden = false; state('authenticating'); say('正在確認安裝包…');
    try {
      const ipa = await ensureIpa(aborter.signal); if (current !== generation) return;
      if (!ipa) throw new Error('請先選擇 IPA');
      const { bundles } = await inspectIpa(ipa, undefined, aborter.signal); if (current !== generation) return;
      if (bundles.length > 16) throw new Error('帳號 provisioning 目前最多支援 16 個 app bundles');
      selectedPlan = { ipa, bundles, appGroup: tetherlessGroup(bundles) };
      if (!$('login-consent').checked) throw new Error('登入授權已取消，未傳送帳號密碼');
      const body = JSON.stringify({ appleId: $('apple-id').value.trim(), password: $('apple-password').value }); $('apple-password').value = '';
      say('正在與 Apple 建立登入 session…');
      const started = await request('v1/sessions', { method: 'POST', body });
      if (current !== generation) { if (started.sessionId && started.sessionToken) fetch(route(`v1/sessions/${encodeURIComponent(started.sessionId)}`), { method: 'DELETE', headers: { Authorization: `Bearer ${started.sessionToken}` }, credentials: 'same-origin', redirect: 'error' }).catch(() => {}); return; }
      if (!started.sessionId || !started.sessionToken) throw new Error('服務未提供有效 session');
      session = started; $('logout').hidden = false; $('account-form').inert = true; $('account-form').hidden = true;
      expiryTimer = setTimeout(() => { clear(); say('登入 session 已到期，原私鑰與未完成申請資料已清除。如 Apple 操作結果不確定，請先檢查帳號中的憑證狀態，不要直接建立新申請。'); }, Math.min(600, started.expiresInSeconds || 600) * 1000);
      await poll(current);
    } catch (error) { if (current === generation) say(error.name === 'AbortError' ? '已取消' : error.message); }
    finally { if (current === generation) { busy = false; if (!session) { $('login-button').disabled = false; $('logout').hidden = true; showLogin(); } } }
  };
  $('two-factor').onsubmit = async (event) => {
    event.preventDefault(); if (!session || $('verify-button').disabled) return;
    const current = generation;
    const code = $('verification-code').value; $('verification-code').value = '';
    if (!/^\d{6}$/.test(code)) return say('請輸入 6 位數驗證碼');
    $('verify-button').disabled = true;
    try { await request(`v1/sessions/${session.sessionId}/2fa`, { method: 'POST', body: JSON.stringify({ action: 'submitCode', code }) }); if (current === generation) say('已送出驗證碼，等待 Apple 回應…'); } catch (error) { if (current === generation) say(error.message); } finally { if (current === generation) $('verify-button').disabled = false; }
  };
  $('resend-code').onclick = async () => { if (!session) return; const current = generation; try { await request(`v1/sessions/${session.sessionId}/2fa`, { method: 'POST', body: JSON.stringify({ action: 'sendToDevices' }) }); if (current === generation) say('已要求 Apple 裝置驗證碼'); } catch (error) { if (current === generation) say(error.message); } };
  $('send-sms').onclick = async () => {
    if (!session || !$('phone-choice').options.length) return;
    const current = generation, numberId = Number($('phone-choice').value); if (!Number.isSafeInteger(numberId)) return;
    $('send-sms').disabled = true;
    try { await request(`v1/sessions/${session.sessionId}/2fa`, { method: 'POST', body: JSON.stringify({ action: 'sendSms', numberId }) }); if (current === generation) say('已要求 Apple 傳送簡訊驗證碼'); }
    catch (error) { if (current === generation) say(error.message); }
    finally { if (current === generation) $('send-sms').disabled = false; }
  };
  $('provision-form').onsubmit = async (event) => {
    event.preventDefault(); if (!session || !['authenticated', 'provisioning', 'provisionRetry'].includes(phase) || !$('provision-consent').checked || $('provision-button').disabled) return;
    const ipa = pendingProvision?.ipa || selectedPlan?.ipa; if (!ipa) return say('請先選擇 IPA');
    const udid = $('account-udid').value.trim(); if (!/^(?:[0-9A-Fa-f]{40}|[0-9A-Fa-f]{8}-[0-9A-Fa-f]{16})$/.test(udid)) { $('device-details').open = true; return say('請輸入有效的裝置 UDID'); }
    const selection = pendingProvision?.selection || { teamId: $('team').value, deviceName: $('device-name').value.trim(), udid };
    $('provision-button').disabled = true; state('provisioning'); const current = generation;
    for (const id of ['team', 'device-name', 'account-udid', 'provision-consent']) $(id).disabled = true;
    try {
      if (!pendingProvision) {
        const { bundles, appGroup } = selectedPlan;
        if (current !== generation) return;
        say(appGroup ? `使用原本的 bundle IDs 與 ${appGroup.identifier}，正在本機產生 CSR…` : '在瀏覽器產生私鑰與 CSR…');
        const keys = await new Promise((resolve, reject) => forge.pki.rsa.generateKeyPair({ bits: 2048, workers: 0 }, (error, pair) => error ? reject(error) : resolve(pair)));
        if (current !== generation) return;
        const csr = forge.pki.createCertificationRequest(); csr.publicKey = keys.publicKey; csr.setSubject([{ name: 'commonName', value: 'Tetherless browser signing' }]); csr.sign(keys.privateKey, forge.md.sha256.create());
        pendingProvision = { keys, ipa, udid: selection.udid, selection, body: JSON.stringify({ consent: appGroup ? 'register-device-app-ids-app-group-and-issue-certificate' : 'register-device-app-ids-and-issue-certificate', ...(appGroup ? { appGroup } : {}), teamId: selection.teamId, device: { udid: selection.udid, name: selection.deviceName }, csrPem: forge.pki.certificationRequestToPem(csr), machineName: 'Tetherless Web', apps: bundles.map((b) => ({ bundleId: b.id, name: Array.from(b.name.replace(/[\x00-\x1f\x7f]/g, '')).slice(0, 32).join('') || b.id })) }) };
      }
      const retained = pendingProvision, keys = retained.keys;
      say(`取得原申請結果：Team ${retained.selection.teamId}，裝置 ${retained.selection.deviceName}，UDID 結尾 ${retained.udid.slice(-4)}。請保留此分頁`);
      const response = await request(`v1/sessions/${session.sessionId}/provision`, { method: 'POST', body: retained.body });
      if (current !== generation) return;
      const cert = forge.pki.certificateFromAsn1(forge.asn1.fromDer(forge.util.decode64(response.certificateDerBase64)));
      if (!cert.publicKey.n.equals(keys.publicKey.n) || !cert.publicKey.e.equals(keys.publicKey.e)) throw new Error('服務傳回的憑證不符合此分頁的私鑰');
      const password = forge.util.encode64(forge.util.binary.raw.encode(crypto.getRandomValues(new Uint8Array(32))));
      const p12bytes = forge.util.binary.raw.decode(forge.asn1.toDer(forge.pkcs12.toPkcs12Asn1(keys.privateKey, [cert], password, { algorithm: '3des' })).getBytes());
      const p12 = new File([p12bytes], 'session.p12', { type: 'application/x-pkcs12' });
      const profiles = response.profiles.map((p, i) => new File([forge.util.binary.raw.decode(forge.util.decode64(p.profileBase64))], `session-${i}.mobileprovision`));
      pendingProvision = undefined; $('provision-form').hidden = true; state('material');
      say('已取得簽署資料，正在本機準備 App。私鑰只留在這個分頁。');
      onMaterial({ p12, profiles, password, udid: retained.udid }, ipa);
    } catch (error) { if (current === generation) { state(pendingProvision ? 'provisionRetry' : 'authenticated'); if (!pendingProvision) for (const id of ['team', 'device-name', 'account-udid', 'provision-consent']) $(id).disabled = false; $('provision-button').disabled = false; $('provision-button').textContent = pendingProvision ? '查詢原申請結果（保留同一私鑰）' : '同意並準備 App'; say(`${error.message}\n原私鑰與申請內容僅留在此分頁。再次按鈕只傳送相同申請以取得快取結果；不會產生另一把私鑰或自動重新申請憑證。取消、分頁關閉或 10 分鐘 session 到期後會遺失這把私鑰。`); } }
  };
  (async () => {
    const isPages = location.hostname === 'github.io' || location.hostname.endsWith('.github.io');
    const local = ['127.0.0.1', 'localhost'].includes(location.hostname);
    if (!isPages && (location.protocol === 'https:' || local)) {
      try { const response = await fetch(route('health'), { cache: 'no-store', credentials: 'same-origin', redirect: 'error' }); if (response.ok && response.headers.get('content-type')?.includes('application/json')) { const health = await response.json(); if (health.protocol === 1 && health.appleAuthAvailable === true) { serviceAvailable = true; profileAvailable = health.profileServiceAvailable === true; $('account-form').hidden = false; $('device-collection').hidden = true; $('account-unavailable').hidden = true; $('service-origin').textContent = location.origin; $('device-service-origin').textContent = location.origin; showLogin(); devices.resume(); return; } } } catch { /* Remain closed on static/unavailable hosts. */ }
    }
    try { const response = await fetch(new URL('config.json', base), { credentials: 'same-origin', redirect: 'error', cache: 'no-store' }); const config = await response.json(); if (config.accountServiceUrl) { const url = new URL(publicHttps(config.accountServiceUrl)); if (url.hostname === 'github.io' || url.hostname.endsWith('.github.io')) throw new Error('Static service origin'); $('service-link').href = url.href; $('service-link').rel = 'noreferrer'; $('service-link').hidden = false; $('account-unavailable').textContent = `此頁不收集 Apple 密碼。已設定的服務位於 ${url.origin}；前往該站後仍須確認服務可用性與資料授權。`; state('external'); return; } } catch { /* A missing configuration does not enable account collection. */ }
    $('account-unavailable').textContent = '登入服務尚未連接，此頁不收集 Apple 密碼。目前無法只用 Apple 帳號繼續；可展開進階選項，使用自己的憑證在本機簽署。'; state('unavailable');
  })();
  return { clear, get phase() { return phase; } };
}
