import { inspectInputs, verifyEmbeddedProfiles } from './material.js';
import { signLocally } from './signer.js';
import { createManifest, installLink } from './ota.js';
import { setupAccount } from './account.js';
const el = (id) => document.getElementById(id);
let controller, generation = 0, outputUrl, output, metadata, generated;
const account = setupAccount({ getIpa: () => el('ipa').files[0], onMaterial: (value) => { resetResult(); generated = value; el('status').textContent = '已取得簽署資料，可以繼續本機簽署'; } });
function status(text) { el('status').textContent = text; }
function resetResult() {
  if (outputUrl) URL.revokeObjectURL(outputUrl);
  outputUrl = undefined; output = undefined; metadata = undefined;
  el('result').hidden = true; el('install-link').hidden = true; el('ota-status').textContent = '';
}
function setBusy(busy) {
  for (const id of ['sign', 'ipa', 'p12', 'profiles', 'password', 'udid', 'rights', 'account-mode', 'files-mode']) el(id).disabled = busy;
  el('cancel').hidden = !busy;
}
function mode(accountMode) {
  el('account-mode').setAttribute('aria-pressed', String(accountMode)); el('files-mode').setAttribute('aria-pressed', String(!accountMode));
  el('account-panel').hidden = !accountMode; el('files-panel').hidden = accountMode;
}
el('account-mode').onclick = () => mode(true); el('files-mode').onclick = () => mode(false);
for (const id of ['ipa', 'p12', 'profiles', 'password', 'udid']) el(id).addEventListener('change', () => { resetResult(); if (id === 'ipa') generated = undefined; });
el('cancel').onclick = () => { generation++; controller?.abort(); controller = undefined; setBusy(false); resetResult(); status('已取消，沒有保留簽署輸出'); };
function clearAll({ preserveEnrollment = false } = {}) {
  generation++; controller?.abort(); controller = undefined; generated = undefined; resetResult(); setBusy(false);
  for (const id of ['ipa', 'p12', 'profiles', 'password', 'udid', 'ipa-url', 'manifest-url']) el(id).value = '';
  el('rights').checked = false; account.clear({ preserveEnrollment }); status('已清除這次資料。JavaScript 記憶體無法保證立即抹除；關閉分頁可釋放執行環境。');
}
el('clear').onclick = clearAll;
window.addEventListener('pagehide', () => clearAll({ preserveEnrollment: true }));
el('sign').onclick = async () => {
  if (controller) return;
  if (!el('rights').checked) return status('請先確認你有權使用 IPA 與簽署資料');
  const accountMode = el('account-mode').getAttribute('aria-pressed') === 'true';
  const inputs = accountMode ? { ipa: el('ipa').files[0], ...generated } : { ipa: el('ipa').files[0], p12: el('p12').files[0], profiles: [...el('profiles').files], password: el('password').value, udid: el('udid').value.trim() };
  if (!inputs.ipa || !inputs.p12 || !inputs.profiles?.length) return status(accountMode ? '請先完成帳號登入與簽署資料建立，或切換到已有憑證路徑' : '請選擇 IPA、P12 與至少一個 profile');
  const current = ++generation; controller = new AbortController(); const signal = controller.signal;
  resetResult(); setBusy(true); status('檢查 IPA 界限與簽署資料…');
  try {
    const checked = await inspectInputs(inputs, new Date(), signal);
    if (signal.aborted || current !== generation) return;
    status(`正在本機簽署 ${checked.bundles.length} 個 app bundles…請保持分頁開啟`);
    const signed = await signLocally(inputs, { signal });
    if (signal.aborted || current !== generation) return;
    status('確認每個 App bundle 內的 profile…');
    await verifyEmbeddedProfiles(signed, checked, inputs.profiles);
    if (signal.aborted || current !== generation) return;
    metadata = checked; output = signed; outputUrl = URL.createObjectURL(signed);
    el('download').href = outputUrl; el('download').download = inputs.ipa.name.replace(/\.ipa$/i, '') + '-signed.ipa';
    el('summary').textContent = `${checked.bundles.map((b) => b.id).join('\n')}\nTeam: ${checked.team}\n${(signed.size / 1024 / 1024).toFixed(1)} MiB · 最早 profile 到期：${checked.profiles.map((p) => p.expires).sort()[0]}`;
    el('result').hidden = false; status('已產生簽署 IPA。尚未驗證 iOS 安裝或 App 啟動。');
  } catch (error) { if (current === generation) status(error.name === 'AbortError' ? '已取消' : `無法完成：${error.message}`); }
  finally { inputs.password = ''; el('password').value = ''; if (current === generation) { controller = undefined; setBusy(false); } }
};
function downloadText(text, filename) {
  const url = URL.createObjectURL(new Blob([text], { type: 'application/xml' })); const link = document.createElement('a'); link.href = url; link.download = filename; link.click(); setTimeout(() => URL.revokeObjectURL(url), 60000);
}
function requireAdHoc() {
  if (!output || !metadata || metadata.profiles.some((p) => p.kind !== 'ad-hoc')) throw new Error('這個 OTA 輔助只適用於已在此分頁簽署完成的 registered-device Ad Hoc profiles；免費／development profiles 不會被視為成功首裝。');
  if (!el('udid').value.trim() && !generated?.udid) throw new Error('請先填寫 UDID，再重新簽署以比對裝置。');
  return metadata.bundles[0];
}
el('manifest').onclick = () => { try { const app = requireAdHoc(); downloadText(createManifest({ ipaUrl: el('ipa-url').value, bundleId: app.id, version: app.version, title: app.name }), 'manifest.plist'); el('ota-status').textContent = '已產生 manifest。請自行上傳至你的 HTTPS 主機，再填寫下方網址。尚未檢查遠端內容。'; } catch (e) { el('ota-status').textContent = e.message; } };
el('make-install').onclick = () => { try { requireAdHoc(); el('install-link').href = installLink(el('manifest-url').value); el('install-link').hidden = false; el('ota-status').textContent = '連結只會請 iOS 開始讀取 manifest；此頁無法確認遠端檔案或安裝結果。'; } catch (e) { el('install-link').hidden = true; el('ota-status').textContent = e.message; } };
