// Only a non-secret enrollment ID/expiry survive the Settings round trip.
// The service holds the short-lived capability in an HttpOnly, Secure cookie.
export function setupDeviceEnrollment(base, { enabled = () => true, onReceived = () => {} } = {}) {
  const $ = (id) => document.getElementById(id), key = 'tetherless-device-enrollment';
  let enrollment, generation = 0, controller, expiryTimer;
  // Settings may open a new tab. The ID is a lookup key, never authorization:
  // the service still requires its path-scoped HttpOnly cookie for every read.
  const returned = location.hash.startsWith('#device-collected');
  const returnedId = /^#device-collected=([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i.exec(location.hash)?.[1];
  if (returned) {
    try { window.history.replaceState(null, '', location.pathname + location.search); } catch {}
  }
  let returnedPending = returnedId ? { id: returnedId, expiresAt: Date.now() + 600000 } : undefined;
  const recoveryHint = '請回到下載描述檔時使用的原瀏覽器、原分頁繼續；不同瀏覽器不共用授權。請勿重複註冊或安裝描述檔。';
  const route = (path) => new URL(path, base).href;
  function removeStored() { returnedPending = undefined; try { sessionStorage.removeItem(key); } catch {} }
  function pause() { generation++; controller?.abort(); clearTimeout(expiryTimer); }
  function clear({ cancelRemote = true } = {}) {
    pause(); removeStored();
    if (cancelRemote && enrollment) fetch(route(`v1/device-enrollments/${encodeURIComponent(enrollment.id)}`), { method: 'DELETE', credentials: 'same-origin', redirect: 'error', keepalive: true, referrerPolicy: 'no-referrer' }).catch(() => {});
    enrollment = undefined; $('retry-device').hidden = true; $('device-profile-link').hidden = true; $('cancel-device').hidden = true; $('collect-device').disabled = false; $('device-consent').checked = false;
  }
  function scheduleExpiry() {
    clearTimeout(expiryTimer);
    expiryTimer = setTimeout(() => { clear({ cancelRemote: false }); $('device-status').textContent = '這次裝置確認已到期；未延長期限，也未重新註冊裝置。'; }, Math.max(0, enrollment.expiresAt - Date.now()));
  }
  async function poll(current) {
    scheduleExpiry();
    while (current === generation && enrollment) {
      const response = await fetch(route(`v1/device-enrollments/${encodeURIComponent(enrollment.id)}`), { signal: controller.signal, credentials: 'same-origin', redirect: 'error', cache: 'no-store', referrerPolicy: 'no-referrer' });
      if (!response.ok) throw new Error(`無法讀取裝置回傳結果（${response.status}）。${recoveryHint}`);
      const state = await response.json(); if (current !== generation) break;
      if (state.expiresInSeconds === 0) { const error = new Error('這次裝置確認已到期，未延長期限。'); error.expired = true; throw error; }
      if (Number.isFinite(state.expiresInSeconds) && state.expiresInSeconds > 0 && state.expiresInSeconds <= 600) {
        enrollment.expiresAt = Math.min(enrollment.expiresAt, Date.now() + state.expiresInSeconds * 1000);
        try { sessionStorage.setItem(key, JSON.stringify(enrollment)); } catch {}
        returnedPending = undefined; scheduleExpiry();
      } else if (returnedPending) throw new Error(`裝置回傳期限無法確認。${recoveryHint}`);
      if (state.state === 'received' && state.device?.udid) {
        const udid = state.device.udid; if (!/^(?:[0-9A-Fa-f]{40}|[0-9A-Fa-f]{8}-[0-9A-Fa-f]{16})$/.test(udid)) throw new Error('服務傳回無效的 UDID');
        $('account-udid').value = udid; $('device-details').open = true;
        // Do not consume the shared result: the original tab can finish polling
        // before Settings opens its callback tab. Keep only ID/expiry locally;
        // server metadata and the cookie retain their ORIGINAL 10-minute TTL.
        pause(); $('retry-device').hidden = true; $('device-profile-link').hidden = true; $('cancel-device').hidden = false; $('collect-device').disabled = true;
        $('device-status').textContent = `收到 UDID：${udid}\n這是尚未驗證信任來源的裝置回傳資料；請確認是這支 iPhone。尚未向 Apple 註冊裝置。若此頁未保留 IPA，請重新選取已下載的檔案，再登入並明確同意註冊；不用重裝描述檔。`; onReceived(udid); break;
      }
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
  }
  async function observe(current) { try { await poll(current); } catch (error) { if (current === generation) {
    if (error.expired) { clear({ cancelRemote: false }); $('device-status').textContent = error.message; return; }
    // A failed read in one tab must not cancel the other tab's collection.
    pause(); if (enrollment) scheduleExpiry(); $('retry-device').hidden = false; $('cancel-device').hidden = false;
    $('device-profile-link').hidden = true; $('device-status').textContent = error.name === 'AbortError' ? '讀取已中斷；可重讀原結果，不會重新收集或註冊。' : `${error.message} 請保留此分頁並按「重讀裝置回傳結果」；不會重新收集或註冊。重新整理可能遺失本次恢復線索。`;
  } } }
  $('retry-device').onclick = () => { if (enabled()) resume(); };
  $('cancel-device').onclick = () => { clear(); $('device-status').textContent = '已取消 UDID 收集'; };
  $('collect-device').onclick = async () => {
    if (!enabled() || !$('device-consent').checked || $('collect-device').disabled) { $('device-status').textContent = '請先同意將指定裝置資料傳送給此服務'; return; }
    $('collect-device').disabled = true; const current = ++generation; controller = new AbortController();
    try {
      const response = await fetch(route('v1/device-enrollments'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ consent: 'collect-device-udid' }), signal: controller.signal, credentials: 'same-origin', redirect: 'error', cache: 'no-store', referrerPolicy: 'no-referrer' });
      if (!response.ok) throw new Error('無法準備描述檔；請稍後重新開始');
      const result = await response.json();
      if (current !== generation) { if (result.enrollmentId) fetch(route(`v1/device-enrollments/${encodeURIComponent(result.enrollmentId)}`), { method: 'DELETE', credentials: 'same-origin', redirect: 'error' }).catch(() => {}); return; }
      const profileUrl = new URL(result.profileUrl, base);
      if (!/^[a-zA-Z0-9-]{16,100}$/.test(result.enrollmentId) || profileUrl.origin !== location.origin || !profileUrl.pathname.startsWith('/v1/device-enrollments/')) throw new Error('服務傳回非預期的描述檔網址');
      enrollment = { id: result.enrollmentId, expiresAt: Date.now() + Math.min(600, result.expiresInSeconds || 600) * 1000 };
      try { sessionStorage.setItem(key, JSON.stringify(enrollment)); } catch { throw new Error('瀏覽器無法保留描述檔往返狀態。請手動填入已知 UDID'); }
      $('device-profile-link').href = profileUrl.href; $('device-profile-link').hidden = false; $('cancel-device').hidden = false;
      $('device-status').textContent = '描述檔已備妥。此分頁僅暫存非機密的收集編號／期限；授權存在 10 分鐘 HttpOnly cookie。請在這支 iPhone 下載並完成 iOS 提示，再返回此分頁';
      await observe(current);
    } catch (error) { if (current === generation) { clear(); $('device-status').textContent = error.name === 'AbortError' ? '已取消' : error.message; } }
  };
  function readPending() {
    let stored; try { stored = JSON.parse(sessionStorage.getItem(key)); } catch { removeStored(); return; }
    // A return URL cannot replace another in-progress collection.
    if (stored && returnedPending && stored.id !== returnedPending.id) return;
    if (!stored && returnedPending) stored = returnedPending;
    const now = Date.now();
    if (!stored || typeof stored !== 'object' || Array.isArray(stored) || Object.keys(stored).some(name => !['id', 'expiresAt'].includes(name)) || typeof stored.id !== 'string' || !/^[a-zA-Z0-9-]{16,100}$/.test(stored.id) || !Number.isFinite(stored.expiresAt) || stored.expiresAt <= now || stored.expiresAt > now + 600000) { removeStored(); return; }
    return stored;
  }
  function resume() {
    if (!enabled()) return;
    pause();
    const stored = readPending(); if (!stored) { if (returned) $('device-status').textContent = `此頁未能恢復剛才的裝置確認。${recoveryHint}`; return; }
    enrollment = stored; $('retry-device').hidden = true; const current = ++generation; controller = new AbortController(); $('collect-device').disabled = true; $('cancel-device').hidden = false;
    $('device-status').textContent = '正在讀取剛才的裝置回傳結果…'; void observe(current);
  }
  return { clear, pause, resume, hasPending: () => Boolean(readPending()), hasReturn: () => returned };
}
