// Only a non-secret enrollment ID/expiry survive the Settings round trip.
// The service holds the short-lived capability in an HttpOnly, Secure cookie.
export function setupDeviceEnrollment(base) {
  const $ = (id) => document.getElementById(id), key = 'tetherless-device-enrollment';
  let enrollment, generation = 0, controller, expiryTimer;
  const route = (path) => new URL(path, base).href;
  function removeStored() { try { sessionStorage.removeItem(key); } catch {} }
  function pause() { generation++; controller?.abort(); clearTimeout(expiryTimer); }
  function clear() {
    pause(); removeStored();
    if (enrollment) fetch(route(`v1/device-enrollments/${encodeURIComponent(enrollment.id)}`), { method: 'DELETE', credentials: 'same-origin', keepalive: true, referrerPolicy: 'no-referrer' }).catch(() => {});
    enrollment = undefined; $('device-profile-link').hidden = true; $('cancel-device').hidden = true; $('collect-device').disabled = false; $('device-consent').checked = false;
  }
  async function poll(current) {
    expiryTimer = setTimeout(() => { clear(); $('device-status').textContent = 'UDID 收集已到期，請重新開始'; }, Math.max(0, enrollment.expiresAt - Date.now()));
    while (current === generation && enrollment) {
      const response = await fetch(route(`v1/device-enrollments/${encodeURIComponent(enrollment.id)}`), { signal: controller.signal, credentials: 'same-origin', cache: 'no-store', referrerPolicy: 'no-referrer' });
      if (!response.ok) throw new Error('UDID 收集 session 已到期或無法讀取，請重新開始');
      const state = await response.json(); if (current !== generation) break;
      if (state.state === 'received' && state.device?.udid) {
        const udid = state.device.udid; if (!/^(?:[0-9A-Fa-f]{40}|[0-9A-Fa-f]{8}-[0-9A-Fa-f]{16})$/.test(udid)) throw new Error('服務傳回無效的 UDID');
        $('account-udid').value = udid; clear(); $('device-status').textContent = `收到 UDID：${udid}\n這是尚未驗證信任來源的裝置回傳資料；請確認是這支 iPhone，再登入並同意註冊此裝置。`; break;
      }
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
  }
  async function observe(current) { try { await poll(current); } catch (error) { if (current === generation) { clear(); $('device-status').textContent = error.name === 'AbortError' ? '已取消' : error.message; } } }
  $('cancel-device').onclick = () => { clear(); $('device-status').textContent = '已取消 UDID 收集'; };
  $('collect-device').onclick = async () => {
    if (!$('device-consent').checked || $('collect-device').disabled) { $('device-status').textContent = '請先同意將指定裝置資料傳送給此服務'; return; }
    $('collect-device').disabled = true; const current = ++generation; controller = new AbortController();
    try {
      const response = await fetch(route('v1/device-enrollments'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ consent: 'collect-device-udid' }), signal: controller.signal, credentials: 'same-origin', cache: 'no-store', referrerPolicy: 'no-referrer' });
      if (!response.ok) throw new Error('無法準備描述檔；請稍後重新開始');
      const result = await response.json();
      if (current !== generation) { if (result.enrollmentId) fetch(route(`v1/device-enrollments/${encodeURIComponent(result.enrollmentId)}`), { method: 'DELETE', credentials: 'same-origin' }).catch(() => {}); return; }
      const profileUrl = new URL(result.profileUrl, base);
      if (!/^[a-zA-Z0-9-]{16,100}$/.test(result.enrollmentId) || profileUrl.origin !== location.origin || !profileUrl.pathname.startsWith('/v1/device-enrollments/')) throw new Error('服務傳回非預期的描述檔網址');
      enrollment = { id: result.enrollmentId, expiresAt: Date.now() + Math.min(600, result.expiresInSeconds || 600) * 1000 };
      try { sessionStorage.setItem(key, JSON.stringify(enrollment)); } catch { throw new Error('瀏覽器無法保留描述檔往返狀態。請手動填入已知 UDID'); }
      $('device-profile-link').href = profileUrl.href; $('device-profile-link').hidden = false; $('cancel-device').hidden = false;
      $('device-status').textContent = '描述檔已備妥。此分頁僅暫存非機密的收集編號／期限；授權存在 10 分鐘 HttpOnly cookie。請在這支 iPhone 下載並完成 iOS 提示，再返回此分頁';
      await observe(current);
    } catch (error) { if (current === generation) { clear(); $('device-status').textContent = error.name === 'AbortError' ? '已取消' : error.message; } }
  };
  function resume() {
    pause();
    let stored; try { stored = JSON.parse(sessionStorage.getItem(key)); } catch { removeStored(); return; }
    if (!stored || !/^[a-zA-Z0-9-]{16,100}$/.test(stored.id) || stored.expiresAt <= Date.now() || stored.expiresAt > Date.now() + 600000) { removeStored(); return; }
    enrollment = stored; const current = ++generation; controller = new AbortController(); $('collect-device').disabled = true; $('cancel-device').hidden = false;
    $('device-status').textContent = '正在讀取剛才的裝置回傳結果…'; void observe(current);
  }
  return { clear, pause, resume };
}
