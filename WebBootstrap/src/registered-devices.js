const $ = (id) => document.getElementById(id);
const validUdid = (value) => typeof value === 'string' && /^(?:[0-9A-Fa-f]{40}|[0-9A-Fa-f]{8}-[0-9A-Fa-f]{16})$/.test(value);
export function validateDevices(body, teamId) {
  if (body?.teamId !== teamId || !Array.isArray(body.devices) || body.devices.length > 1000) throw new Error('服務傳回的裝置清單或 Team 不符');
  const seen = new Set();
  return body.devices.map((device) => {
    if (!validUdid(device?.udid) || typeof device.name !== 'string' || !device.name.trim() || new TextEncoder().encode(device.name).length > 128 || /\p{Cc}/u.test(device.name) || !['active', 'disabled', 'unknown'].includes(device.status) || typeof device.selectable !== 'boolean' || seen.has(device.udid.toLowerCase())) throw new Error('服務傳回無效或重複的裝置資料');
    seen.add(device.udid.toLowerCase());
    return { udid: device.udid, name: device.name, status: device.status, selectable: device.status === 'active' && device.selectable === true };
  });
}
export function setupRegisteredDevices({ request, getSessionId, getTeamId, onSelection }) {
  let generation = 0, controller, choices = new Map(), loadedTeam, loadedSession, frozen = false;
  function clear() {
    generation++; controller?.abort(); controller = undefined; choices.clear(); loadedTeam = undefined; loadedSession = undefined;
    const option = document.createElement('option'); option.value = ''; option.textContent = '請選擇已註冊的裝置';
    $('reload-devices').disabled = false; $('existing-device').replaceChildren(option); $('existing-device').disabled = true; $('existing-device-summary').textContent = ''; $('existing-status').textContent = '';
    onSelection(undefined);
  }
  function selection() {
    if (loadedTeam !== getTeamId() || loadedSession !== getSessionId()) return undefined;
    const device = choices.get($('existing-device').value); return device ? { ...device, teamId: loadedTeam, existingOnly: true } : undefined;
  }
  $('existing-device').onchange = () => {
    if (frozen) return;
    const device = selection(); $('existing-device-summary').textContent = device ? `${device.name}\nUDID：${device.udid}\n這是 Apple 帳號中的裝置記錄，未驗證為目前使用瀏覽器的 iPhone。` : '';
    onSelection(device);
  };
  async function load() {
    if (frozen) return;
    clear(); const sessionId = getSessionId(), teamId = getTeamId(); if (!sessionId || !teamId) { $('existing-status').textContent = '請先選擇 Apple Team'; return; }
    const current = generation; controller = new AbortController(); $('reload-devices').disabled = true; $('existing-status').textContent = '正在讀取此 Team 的已註冊裝置…';
    try {
      const result = await request(`v1/sessions/${encodeURIComponent(sessionId)}/teams/${encodeURIComponent(teamId)}/devices`, { signal: controller.signal, maxResponseBytes: 512 * 1024 });
      if (current !== generation || sessionId !== getSessionId() || teamId !== getTeamId()) return;
      const list = validateDevices(result, teamId), active = list.filter(d => d.selectable);
      choices = new Map(active.map(d => [d.udid, d])); loadedTeam = teamId; loadedSession = sessionId;
      for (const device of active) { const option = document.createElement('option'); option.value = device.udid; option.textContent = `${device.name} · ${device.udid}`; $('existing-device').append(option); }
      $('existing-device').disabled = !active.length;
      $('existing-status').textContent = active.length ? `請明確選擇 ${active.length} 個可用裝置中的一個；未自動選取。` : '此 Team 沒有可用的已註冊裝置。可重讀清單，或返回登入後明確選擇「註冊新裝置」；不會自動新增裝置。';
    } catch (error) { if (current === generation) $('existing-status').textContent = error.name === 'AbortError' ? '已取消裝置清單讀取' : `無法讀取裝置：${error.message}。未選取或新增任何裝置。`; }
    finally { if (current === generation) { controller = undefined; $('reload-devices').disabled = false; } }
  }
  $('reload-devices').onclick = () => { void load(); };
  function freeze(value) { frozen = value; $('existing-device').disabled = value || choices.size === 0; $('reload-devices').disabled = value; }
  return { clear, load, selection, freeze };
}
