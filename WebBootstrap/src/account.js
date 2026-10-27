import forge from 'node-forge';
import { inspectIpa } from './material.js';
import { discoverAccountService } from './account-discovery.js';
import { tetherlessGroup } from './tetherless-identity.js';
import { setupRegisteredDevices } from './registered-devices.js';
import { setupDeviceEnrollment } from './device-enrollment.js';
const $ = (id) => document.getElementById(id);
const safeErrors = { deviceNotAvailable: '所選裝置不再可用或不屬於此 Team。請取消原申請後重新選擇；不會改成新增裝置', invalidRequest: '請求或 Team 無效，請重新確認選擇', appleAuthenticationFailed: 'Apple 登入失敗，請重新開始', expired: '登入 session 已到期，請重新登入', certificateLimit: '憑證名額不足。此服務不會自動撤銷其他憑證', busy: '原申請仍在處理中，請稍後只查詢原申請結果', profileMismatch: 'Apple profile 與 Team、裝置、App 或共享群組不符，未提供簽署資料', certificateMismatch: 'Apple 憑證與此分頁 CSR 不符', appleRequestFailed: 'Apple 請求未完成，請確認帳號狀態', authenticationFailed: 'Apple 登入失敗，請重新開始', sessionExpired: '登入 session 已到期，請重新登入', wrongState: '這次操作的狀態已改變。請先取消 session 再重新開始；不要重複建立憑證', certificateCapacity: '憑證名額不足。此服務不會自動撤銷其他憑證', provisioningUncertain: 'Apple 操作結果不確定。保留此分頁的原私鑰；此服務不會再次建立憑證', provisioningFailed: 'Apple provisioning 未完成。請檢查 Team 與裝置狀態；若結果不確定，不要重複送出' };
export function setupAccount({ getIpa, ensureIpa = async () => getIpa(), onMaterial, onState = () => {}, onInvalidate = () => {}, canSubmit = () => true }) {
  let session, aborter, generation = 0, expiryTimer, busy = false, pendingProvision, serviceAvailable = false, profileAvailable = false, phase = 'checking', selectedPlan, teamIds = new Set();
  let discovery, discoveryGeneration = 0;
  const existingRoute = () => $('device-route').value === 'existing';
  const state = (value) => { phase = value; onState(value); };
  const validUdid = () => /^(?:[0-9A-Fa-f]{40}|[0-9A-Fa-f]{8}-[0-9A-Fa-f]{16})$/.test($('account-udid').value.trim());
  function showLogin() {
    $('account-form').inert = false; $('device-details').hidden = false;
    const needsDevice = serviceAvailable && !existingRoute() && profileAvailable && !validUdid();
    $('device-route-choice').hidden = !serviceAvailable; $('device-route').disabled = false;
    $('device-route-hint').textContent = existingRoute() ? '先登入 Apple，再選擇帳號中已啟用的裝置。不會自動新增裝置，也不代表驗證了目前 iPhone 的身分。' : '這條路徑會明確註冊新裝置。若需往返 iOS「設定」安裝描述檔，請先完成再登入；往返會清除登入 session，可能需要重新登入。';
    $('prelogin-device').hidden = !needsDevice; $('account-form').hidden = !serviceAvailable || needsDevice;
    if (needsDevice) { $('prelogin-device-slot').append($('device-collection'), $('device-details')); $('device-collection').hidden = false; state('device'); }
    else state(serviceAvailable ? 'login' : $('service-link').hidden ? 'unavailable' : 'external');
  }
  const say = (text) => { $('account-status').textContent = text; };
  const base = new URL('.', document.baseURI);
  const devices = setupDeviceEnrollment(base, { enabled: () => serviceAvailable && !existingRoute() && profileAvailable && !session && !busy, onReceived: () => { if (!session) showLogin(); } });
  $('continue-device').onclick = () => { if (!validUdid()) { $('device-details').open = true; return say('請取得或輸入有效的 iPhone UDID'); } devices.clear(); showLogin(); say('裝置資料已準備好，請登入 Apple。稍後仍須確認並授權註冊。'); };
  window.addEventListener('pageshow', (event) => { if (event.persisted) { if (serviceAvailable) devices.resume(); else void checkService(); } });
  const route = (path) => { const url = new URL(path.replace(/^\//, ''), base); if (url.origin !== location.origin) throw new Error('登入服務必須與此頁同源'); return url.href; };
  function headers() { return { 'Content-Type': 'application/json', ...(session ? { Authorization: `Bearer ${session.sessionToken}` } : {}) }; }
  async function request(path, options = {}) {
    const { signal: extraSignal, maxResponseBytes, ...fetchOptions } = options;
    const signals = [AbortSignal.timeout(150000)]; if (aborter) signals.push(aborter.signal); if (extraSignal) signals.push(extraSignal);
    const response = await fetch(route(path), { ...fetchOptions, headers: headers(), credentials: 'same-origin', redirect: 'error', cache: 'no-store', referrerPolicy: 'no-referrer', signal: AbortSignal.any(signals) });
    let text;
    if (maxResponseBytes && response.body) {
      const reader = response.body.getReader(), parts = []; let size = 0;
      try { while (true) { const { done, value } = await reader.read(); if (done) break; size += value.byteLength; if (size > maxResponseBytes) throw new Error('裝置清單回應超過允許大小'); parts.push(value); } }
      catch (error) { await reader.cancel().catch(() => {}); throw error; } finally { reader.releaseLock(); }
      const bytes = new Uint8Array(size); let offset = 0; for (const part of parts) { bytes.set(part, offset); offset += part.byteLength; } text = new TextDecoder().decode(bytes);
    } else text = await response.text();
    let body; try { body = text ? JSON.parse(text) : {}; } catch { throw new Error('簽署服務沒有傳回有效回應'); }
    if (!response.ok) { const code = body.error || body.code; throw new Error(safeErrors[code] || `簽署服務回應 ${response.status}。請檢查狀態，勿重複提交不確定的操作。`); }
    return body;
  }
  const registered = setupRegisteredDevices({ request, getSessionId: () => session?.sessionId, getTeamId: () => teamIds.has($('team').value) ? $('team').value : '', onSelection: (device) => { $('provision-consent').checked = false; if (existingRoute()) { $('provision-consent').disabled = !device; $('provision-button').disabled = !device; } } });
  $('device-route').onchange = () => { if ($('device-route').disabled) return; clear(); };
  $('team').onchange = () => { if ($('team').disabled || pendingProvision) return; $('provision-consent').checked = false; if (existingRoute()) void registered.load(); };
  function clear({ preserveEnrollment = false, preserveDevice = false } = {}) {
    cancelDiscovery();
    const retainedUdid = preserveDevice ? $('account-udid').value : '';
    if (preserveEnrollment) devices.pause(); else { devices.clear(); $('device-status').textContent = ''; }
    pendingProvision = undefined; selectedPlan = undefined; teamIds.clear(); registered.freeze(false); registered.clear(); onInvalidate();
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
        if (!Array.isArray(teams) || !teams.length || teams.length > 1000 || teams.some(team => typeof team.id !== 'string' || !/^[A-Za-z0-9]{1,64}$/.test(team.id)) || new Set(teams.map(team => team.id)).size !== teams.length) throw new Error('此帳號沒有可用的 Apple Team');
        teamIds = new Set(teams.map(team => team.id));
        $('team').replaceChildren(...teams.map((team) => { const option = document.createElement('option'); option.value = team.id; option.textContent = `${team.name} · ${team.type} · ${team.id}`; return option; }));
        if (teams.length > 1) { const placeholder = document.createElement('option'); placeholder.value = ''; placeholder.textContent = '請選擇 Apple Team'; placeholder.selected = true; $('team').prepend(placeholder); $('team').value = ''; }
        $('team-choice').hidden = teams.length === 1; $('team-summary').hidden = teams.length !== 1; $('team-summary').textContent = teams.length === 1 ? `使用 ${teams[0].name} · ${teams[0].type} · ${teams[0].id}` : '';
        $('provision-device-slot').append($('device-details')); $('device-collection').hidden = true; $('prelogin-device').hidden = true; $('device-details').open = true; $('device-details').hidden = existingRoute(); $('device-name').disabled = existingRoute(); $('account-udid').disabled = existingRoute(); $('registered-device-panel').hidden = !existingRoute();
        $('provision-consent-text').textContent = existingRoute() ? '我確認所選已註冊裝置與 Team 正確，有權使用所選 IPA，並同意使用此装置、建立上方 App IDs／App Group、開發憑證及 profiles。這會占用 Apple Team 名額；不新增裝置或自動撤銷其他憑證。' : '我確認新裝置與 Team 正確，有權使用所選 IPA，並同意註冊此裝置、建立上方 App IDs／App Group、開發憑證及 profiles。這會占用 Apple Team 名額；不會自動撤銷其他憑證。';
        $('provision-plan').textContent = `${selectedPlan.ipa.name}\nApp IDs：\n${selectedPlan.bundles.map((bundle) => bundle.id).join('\n')}\n${selectedPlan.appGroup ? `App Group：${selectedPlan.appGroup.identifier}` : '此 IPA 不需要 Tetherless 共用 App Group'}\n${existingRoute() ? '使用下方明確選取的已註冊裝置，不新增裝置。' : '另會註冊下方裝置。'}建立開發憑證並取得上述 App IDs 的 profiles。`;
        $('provision-form').hidden = false; state('authenticated'); say('確認所選裝置與以下授權後，將自動取得簽署資料並在本機準備 App。'); if (existingRoute()) await registered.load(); return;
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
    event.preventDefault(); if (!serviceAvailable || phase !== 'login' || busy || session || !canSubmit() || !$('login-consent').checked) return;
    busy = true; const current = ++generation; aborter = new AbortController(); $('login-button').disabled = true; $('account-form').inert = true; $('logout').hidden = false; $('device-route').disabled = true; state('authenticating'); say('正在確認安裝包…');
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
    let selection = pendingProvision?.selection;
    if (!selection) {
      if (!teamIds.has($('team').value)) return say('請先選擇 Apple Team');
      if (existingRoute()) {
        const device = registered.selection(); if (!device) return say('請明確選擇此 Team 的可用已註冊裝置');
        selection = { teamId: device.teamId, deviceName: device.name, udid: device.udid, existingOnly: true };
      } else {
        const udid = $('account-udid').value.trim(); if (!validUdid()) { $('device-details').open = true; return say('請輸入有效的裝置 UDID'); }
        selection = { teamId: $('team').value, deviceName: $('device-name').value.trim(), udid, existingOnly: false };
      }
    }
    registered.freeze(true);
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
        pendingProvision = { keys, ipa, udid: selection.udid, selection, body: JSON.stringify({ consent: selection.existingOnly ? (appGroup ? 'use-existing-device-register-app-ids-app-group-and-issue-certificate' : 'use-existing-device-register-app-ids-and-issue-certificate') : (appGroup ? 'register-device-app-ids-app-group-and-issue-certificate' : 'register-device-app-ids-and-issue-certificate'), ...(appGroup ? { appGroup } : {}), teamId: selection.teamId, device: { udid: selection.udid, name: selection.deviceName, ...(selection.existingOnly ? { existingOnly: true } : {}) }, csrPem: forge.pki.certificationRequestToPem(csr), machineName: 'Tetherless Web', apps: bundles.map((b) => ({ bundleId: b.id, name: Array.from(b.name.replace(/[\x00-\x1f\x7f]/g, '')).slice(0, 32).join('') || b.id })) }) };
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
    } catch (error) { if (current === generation) { state(pendingProvision ? 'provisionRetry' : 'authenticated'); if (!pendingProvision) { registered.freeze(false); } if (!pendingProvision) { for (const id of ['team', 'provision-consent']) $(id).disabled = false; $('device-name').disabled = existingRoute(); $('account-udid').disabled = existingRoute(); } $('provision-button').disabled = false; $('provision-button').textContent = pendingProvision ? '查詢原申請結果（保留同一私鑰）' : '同意並準備 App'; say(`${error.message}\n原私鑰與申請內容僅留在此分頁。再次按鈕只傳送相同申請以取得快取結果；不會產生另一把私鑰或自動重新申請憑證。取消、分頁關閉或 10 分鐘 session 到期後會遺失這把私鑰。`); } }
  };
  function cancelDiscovery() {
    if (!discovery) return;
    discoveryGeneration++; discovery.abort(); discovery = undefined;
    $('recheck-service').hidden = false; $('recheck-service').disabled = false;
    $('cancel-service-check').hidden = true;
    $('account-unavailable').textContent = '已取消確認登入服務。你可以重新檢查；確認前不會收集 Apple 密碼。';
  }
  function discoveryUiFailure() {
    serviceAvailable = false; profileAvailable = false; phase = 'unavailable';
    $('account-form').hidden = true; $('device-route-choice').hidden = true; $('prelogin-device').hidden = true;
    $('cancel-service-check').hidden = true; $('recheck-service').hidden = false; $('recheck-service').disabled = false;
    $('account-unavailable').hidden = false;
    $('account-unavailable').textContent = '登入介面未能完成初始化。尚未開放輸入帳號密碼，請重新載入此頁。';
  }
  async function checkService() {
    // No later discovery can replace a verified origin or interrupt a session.
    if (discovery || serviceAvailable || session || busy) return;
    const current = ++discoveryGeneration, controller = new AbortController(); discovery = controller;
    try {
      $('recheck-service').hidden = false; $('recheck-service').disabled = true;
      $('cancel-service-check').hidden = false; $('account-unavailable').hidden = false;
      $('service-link').hidden = true; $('account-form').hidden = true;
      $('account-unavailable').textContent = '正在確認登入服務…最多重試一次，確認前不會收集 Apple 密碼。'; state('checking');
    } catch { controller.abort(); discovery = undefined; discoveryUiFailure(); return; }
    let result;
    try { result = await discoverAccountService({ base, origin: location.origin, signal: controller.signal }); }
    catch (error) { if (controller.signal.aborted || current !== discoveryGeneration) return; result = { kind: 'internal' }; }
    if (current !== discoveryGeneration || controller.signal.aborted || session || busy) return;
    discovery = undefined; $('cancel-service-check').hidden = true; $('recheck-service').disabled = false;
    // DOM/lifecycle failures are not network failures. Keep collection closed if
    // applying a verified discovery result cannot initialize the UI.
    try {
      if (result.kind === 'ready') {
        profileAvailable = result.profileAvailable;
        $('service-origin').textContent = location.origin; $('device-service-origin').textContent = location.origin;
        $('device-collection').hidden = true;
        if (profileAvailable && devices.hasPending()) $('device-route').value = 'new';
        serviceAvailable = true; showLogin(); devices.resume();
        $('account-unavailable').hidden = true; $('recheck-service').hidden = true; return;
      }
      const message = result.kind === 'internal' ? '登入服務檢查未能完成初始化。請重新載入此頁。' : result.kind === 'unreachable' ? '目前無法連線到登入服務。可能是網路或服務暫時中斷；你可以重新檢查。'
        : result.kind === 'invalid' ? '登入服務回應未通過驗證，無法確認此頁可安全登入。請聯絡服務管理者，或稍後重新檢查。'
        : '此站尚未啟用 Apple 登入服務。請由服務管理者完成設定後重新檢查。';
      $('account-unavailable').textContent = `${message} 此頁不收集 Apple 密碼。${result.diagnostic ? ` 檢查結果：${result.diagnostic}。` : ''}`;
      if (result.externalUrl) {
        const url = new URL(result.externalUrl); $('service-link').href = url.href; $('service-link').rel = 'noreferrer'; $('service-link').hidden = false;
        $('account-unavailable').textContent += ` 已設定的服務位於 ${url.origin}；前往該站後仍須確認服務可用性與資料授權。`;
      }
      state(result.externalUrl ? 'external' : 'unavailable');
    } catch { discoveryUiFailure(); }
  }
  $('recheck-service').onclick = () => { void checkService(); };
  $('cancel-service-check').onclick = () => { cancelDiscovery(); showLogin(); };
  void checkService();
  return { clear, get phase() { return phase; } };
}
