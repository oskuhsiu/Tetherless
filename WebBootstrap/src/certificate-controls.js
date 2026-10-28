import { createIdentity, importRecovery, importP12InWorker, exportRecovery, exportP12, downloadLocal } from './certificate-recovery.js';
const $ = id => document.getElementById(id);
const option = (text, value) => { const item = document.createElement('option'); item.textContent = text; item.value = value; return item; };
const controls = ['identity-source', 'identity-file', 'identity-import-password', 'prepare-identity', 'identity-create-consent'];
export function setupCertificateControls({ request, getSession, getTeam, canPrepare, isMutating = () => false, onRevoked = () => {} }) {
  let identity, identitySource, saved = false, epoch = 0, preparing = false, frozen = false, certificates = [], profiles = [], importer, managementBusy = false, teamWasDisabled = false;
  const status = text => { $('identity-status').textContent = text; };
  function resetList() {
    certificates = []; $('certificate-choice').replaceChildren(option('請先讀取憑證清單', '')); $('certificate-choice').disabled = true; $('list-certificates').disabled = false;
    $('certificate-description').textContent = ''; $('revoke-consent').checked = false; $('revoke-consent').disabled = true; $('revoke-certificate').disabled = true;
  }
  function reset() {
    importer?.abort(); importer = undefined; epoch++; identity = undefined; identitySource = undefined; saved = false; preparing = false; frozen = false; profiles = []; managementBusy = false;
    $('provision-form').insertBefore($('certificate-lifecycle'), $('provision-consent').closest('label'));
    for (const id of controls) $(id).disabled = false;
    for (const id of ['identity-import-password', 'identity-export-password', 'identity-file']) $(id).value = '';
    for (const id of ['recovery-saved', 'identity-create-consent']) $(id).checked = false;
    $('recovery-saved').disabled = true;
    for (const id of ['export-signing-p12', 'export-recovery', 'export-profiles']) $(id).hidden = true;
    $('certificate-management').hidden = false; resetList(); status('此分頁的簽署身分已清除。先前若已下載恢復檔，下次請匯入同一檔案與密碼；不要直接建立新身分。');
  }
  function freeze(value) { frozen = value; for (const id of controls) $(id).disabled = value; $('identity-create-consent').disabled = value || $('identity-source').value !== 'new'; $('recovery-saved').disabled = value || !saved; }
  function managementLock(value) {
    managementBusy = value;
    if (value) { teamWasDisabled = $('team').disabled; $('team').disabled = true; }
    else $('team').disabled = teamWasDisabled;
    for (const id of controls) $(id).disabled = value || frozen;
    $('identity-create-consent').disabled = value || frozen || $('identity-source').value !== 'new';
    $('list-certificates').disabled = value;
    if (value) { $('certificate-choice').disabled = true; $('revoke-consent').disabled = true; $('revoke-certificate').disabled = true; }
  }
  const password = () => $('identity-export-password').value;
  $('prepare-identity').onclick = async () => {
    if (!canPrepare() || frozen || preparing || managementBusy) return;
    const team = getTeam(); if (!team) return status('請先選擇 Apple Team');
    const current = ++epoch; preparing = true; $('prepare-identity').disabled = true; $('recovery-saved').checked = false;
    try {
      if (password().length < 12 || password().length > 1024) throw new Error('請輸入至少 12 個字元的備份密碼');
      const source = $('identity-source').value, file = $('identity-file').files[0], importPassword = $('identity-import-password').value;
      let prepared;
      if (source === 'new') prepared = identity && identitySource === 'new' && identity.teamId === team ? identity : await createIdentity(team);
      else if (source === 'p12') { importer = new AbortController(); prepared = await importP12InWorker(file, importPassword, team, importer.signal); }
      else if (source === 'recovery') prepared = await importRecovery(file, importPassword);
      else throw new Error('請選擇有效的身分來源');
      if (prepared.teamId !== team) throw new Error('恢復檔的 Team 與目前選取 Team 不符；不能換 Team 重用');
      const blob = await exportRecovery(prepared, password());
      if (current !== epoch || !canPrepare() || getTeam() !== team) return;
      identity = prepared; identitySource = source; saved = true; downloadLocal(blob, 'tetherless-recovery.json');
      $('recovery-saved').disabled = false; $('export-recovery').hidden = false; $('export-signing-p12').hidden = !identity.cert;
      status('已要求瀏覽器下載加密恢復檔。請先確認實際儲存成功並保存密碼，再勾選保存確認。下次可匯入此檔案重用同一把私鑰。');
    } catch (error) { if (current === epoch) status(error.message); }
    finally { if (current === epoch) { preparing = false; $('prepare-identity').disabled = frozen; $('identity-import-password').value = ''; } }
  };
  for (const id of ['identity-source', 'identity-file']) $(id).onchange = () => {
    if (frozen || managementBusy) return; importer?.abort(); importer = undefined; epoch++; preparing = false; $('prepare-identity').disabled = false; identity = undefined; identitySource = undefined; saved = false;
    $('recovery-saved').checked = false; $('recovery-saved').disabled = true; $('identity-create-consent').checked = false;
    $('identity-create-consent').disabled = $('identity-source').value !== 'new';
    for (const id of ['export-signing-p12', 'export-recovery', 'export-profiles']) $(id).hidden = true;
  };
  $('export-recovery').onclick = async () => { const retained = identity, current = epoch; if (!retained) return; try { const blob = await exportRecovery(retained, password()); if (current === epoch) downloadLocal(blob, 'tetherless-recovery.json'); } catch (error) { if (current === epoch) status(error.message); } };
  $('export-signing-p12').onclick = () => { if (!identity) return; try { downloadLocal(exportP12(identity, password()), 'tetherless-signing.p12'); status('已要求下載加密 P12；請確認儲存並保存匯出密碼。P12 不會延長憑證或 profiles 的有效期限。'); } catch (error) { status(error.message); } };
  $('export-profiles').onclick = () => { for (let i = 0; i < profiles.length; i++) downloadLocal(profiles[i], `tetherless-${i}.mobileprovision`); status('已要求下載各個 profiles；瀏覽器可能要求允許多檔下載。請確認所有檔案已保存。'); };
  $('list-certificates').onclick = async () => {
    const session = getSession(), team = getTeam(), current = epoch;
    if (!session || !team || preparing || managementBusy || isMutating()) return;
    resetList(); managementLock(true);
    try {
      const result = await request(`v1/sessions/${session}/teams/${encodeURIComponent(team)}/certificates`, { maxResponseBytes: 1024 * 1024 });
      if (current !== epoch || session !== getSession() || team !== getTeam()) return;
      if (result.teamId !== team || !Array.isArray(result.certificates) || result.certificates.length > 1000) throw new Error('憑證清單格式無效');
      const seen = new Set();
      for (const cert of result.certificates) {
        if (!cert || typeof cert.id !== 'string' || !cert.id || cert.id.length > 256 || seen.has(cert.id) || (cert.serial != null && (typeof cert.serial !== 'string' || cert.serial.length > 256)) || (cert.confirmationToken != null && (typeof cert.confirmationToken !== 'string' || cert.confirmationToken.length > 256))) throw new Error('憑證清單缺少可核對的識別資訊');
        seen.add(cert.id);
        for (const name of ['name', 'machineName', 'expiresAt', 'status']) if (cert[name] != null && (typeof cert[name] !== 'string' || cert[name].length > 512 || /[\x00-\x1f\x7f]/.test(cert[name]))) throw new Error('憑證清單格式無效');
      }
      certificates = result.certificates;
      $('certificate-choice').replaceChildren(option('請明確選擇一張憑證', ''), ...certificates.map(c => option(`${c.name || '未提供名稱'} · serial ${c.serial} · ID ${c.id}`, c.id)));
      $('certificate-choice').disabled = !certificates.length;
      $('certificate-status').textContent = `Apple 目前回傳 ${certificates.length} 張憑證；不是完整歷史，也無法據此判定待處理 CSR。`;
    } catch (error) { if (current === epoch) $('certificate-status').textContent = error.message; }
    finally { if (current === epoch) managementLock(false); }
  };
  $('certificate-choice').onchange = () => {
    if (managementBusy) return;
    const cert = certificates.find(c => c.id === $('certificate-choice').value);
    $('revoke-consent').checked = false; $('revoke-consent').disabled = !cert?.serial || !cert?.confirmationToken; $('revoke-certificate').disabled = true;
    $('certificate-description').textContent = cert ? `Team ${getTeam()}；ID ${cert.id}；serial ${cert.serial}；名稱 ${cert.name || '未提供'}；機器名稱 ${cert.machineName || '未提供'}；到期 ${cert.expiresAt || '未提供'}；狀態 ${cert.status || '未提供'}。名稱不是建立者的證明。` : '';
  };
  $('revoke-consent').onchange = () => { if (managementBusy) return; const cert = certificates.find(c => c.id === $('certificate-choice').value); $('revoke-certificate').disabled = !$('revoke-consent').checked || !cert?.serial || !cert?.confirmationToken || isMutating(); };
  $('revoke-certificate').onclick = async () => {
    const session = getSession(), team = getTeam(), current = epoch, cert = certificates.find(c => c.id === $('certificate-choice').value);
    if (!session || !team || !cert?.serial || !cert?.confirmationToken || managementBusy || isMutating() || !$('revoke-consent').checked || $('revoke-certificate').disabled) return;
    managementLock(true); $('revoke-certificate').disabled = true; $('revoke-consent').checked = false; $('revoke-consent').disabled = true; $('certificate-choice').disabled = true;
    try {
      const result = await request(`v1/sessions/${session}/teams/${encodeURIComponent(team)}/certificates/revoke`, { method: 'POST', body: JSON.stringify({ certificateId: cert.id, certificateSerial: cert.serial, confirmationToken: cert.confirmationToken, consent: 'revoke-selected-development-certificate' }), maxResponseBytes: 65536 });
      if (current !== epoch || session !== getSession()) return;
      if (result.revoked !== true || result.certificateId !== cert.id || result.teamId !== team) throw new Error('撤銷回應未確認指定憑證，結果不確定');
      resetList(); onRevoked();
    } catch (error) { if (current === epoch) { resetList(); $('certificate-status').textContent = `${error.message} 請先重讀憑證清單確認結果；不會自動重送撤銷。`; } }
    finally { if (current === epoch) managementLock(false); }
  };
  return {
    reset, freeze, get isManaging() { return managementBusy; },
    selection() { if (managementBusy) throw new Error('請先等待憑證清單／撤銷操作完成；未開始新申請'); if (identitySource === 'new' && !identity?.cert && !$('identity-create-consent').checked) throw new Error('若要首次建立憑證，請另行勾選申請新憑證授權；尚未送出任何申請'); if (!identity || !saved || !$('recovery-saved').checked || identity.teamId !== getTeam()) throw new Error('請先下載加密恢復檔，確認已保存，再繼續'); return { identity, certificateIntent: identitySource === 'new' && $('identity-create-consent').checked ? 'createOrReuse' : 'reuseOnly' }; },
    certificateReady() { $('export-signing-p12').hidden = false; $('export-recovery').hidden = false; status('憑證已取得，現在可以下載加密 P12／更新恢復檔；即使下一步 profiles 失敗也能保留原私鑰重試。'); },
    materialReady(value) { $('certificate-management').hidden = true; profiles = value; $('export-profiles').hidden = !profiles.length; $('signing-panel').prepend($('certificate-lifecycle')); },
  };
}
