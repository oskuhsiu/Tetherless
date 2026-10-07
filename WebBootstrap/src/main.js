import { inspectInputs, verifyEmbeddedProfiles } from './material.js';
import { signLocally } from './signer.js';
import { createManifest, installLink } from './ota.js';
import { setupAccount } from './account.js';
import { createReadDeadline } from './account-discovery.js';
import { journeyView } from './journey.js';
import { validateRelease, acquireRelease, verifyReleaseFile } from './release.js';
const el = (id) => document.getElementById(id);
let controller, generation = 0, outputUrl, output, metadata, generated, generatedIpa;
let manual = false, accountPhase = 'checking', signing = false, officialRelease, officialIpa, releaseGeneration = 0, configReady, configLoaded = false;
const custom = () => el('app-source').value === 'custom';
const canSubmitAccount = () => configLoaded && (custom() ? Boolean(el('ipa').files[0]) : Boolean(officialRelease));
const selectedIpa = () => manual || custom() ? el('ipa').files[0] : officialIpa;
const lockedPhase = () => ['authenticating', 'twoFactor', 'authenticated', 'provisioning', 'provisionRetry', 'material'].includes(accountPhase);
function render() {
  const view = journeyView({ manual, accountPhase, signing, material: Boolean(generated), output: Boolean(output) });
  el('account-panel').hidden = !view.account;
  el('guided-preparation').hidden = !view.preparation;
  el('manual-panel').hidden = !manual; el('files-panel').hidden = !manual;
  el('signing-panel').hidden = !view.signing; el('install-panel').hidden = !view.install;
  el('manual-rights').hidden = !manual;
  el('sign').hidden = !manual && (signing || Boolean(output));
  el('sign').textContent = manual ? '檢查並簽署 IPA' : '重新執行本機簽署';
  el('signing-title').textContent = signing ? '正在準備 App…' : output ? '簽署完成' : '在這個分頁簽署';
  el('journey-title').textContent = view.title; el('journey-stage').textContent = view.stage;
  el('account-mode').hidden = !manual; el('account-mode').setAttribute('aria-pressed', String(!manual));
  el('files-mode').hidden = manual; el('files-mode').setAttribute('aria-pressed', String(manual)); el('files-mode').setAttribute('aria-expanded', String(manual));
  for (const step of ['login', 'verify', 'install']) { if (view.step === step) el(`step-${step}`).setAttribute('aria-current', 'step'); else el(`step-${step}`).removeAttribute('aria-current'); }
  const showCustom = manual || custom();
  el('app-selection').hidden = !showCustom;
  const needsOwnIpa = configLoaded && !officialRelease && !manual && !lockedPhase();
  el('account-app-prerequisite').hidden = !needsOwnIpa;
  el('ipa-prerequisite-status').textContent = el('ipa').files[0] ? '已選擇 IPA。登入送出前仍會檢查檔案大小、結構與 bundle IDs；檢查失敗不會傳送帳號密碼。' : '尚未選擇 IPA，登入按鈕暫不開放。';
  (manual ? el('manual-app-slot') : view.preparation ? el('guided-app-slot') : needsOwnIpa ? el('prerequisite-app-slot') : el('custom-app-slot')).append(el('app-selection'));
  el('login-button').disabled = accountPhase !== 'login' || !canSubmitAccount();
  el('clear').hidden = !manual && !signing && !generated && !output && !['authenticating', 'twoFactor', 'authenticated', 'provisioning', 'provisionRetry'].includes(accountPhase);
  const locked = signing || ['authenticating', 'twoFactor', 'authenticated', 'provisioning', 'provisionRetry', 'material'].includes(accountPhase);
  for (const id of ['ipa', 'app-source', 'release-file']) el(id).disabled = locked;
  el('app-options').hidden = manual || signing || Boolean(output);
}
function status(text) { el('status').textContent = text; }
function resetResult() {
  if (outputUrl) URL.revokeObjectURL(outputUrl);
  outputUrl = undefined; output = undefined; metadata = undefined;
  el('result').hidden = true; el('download').removeAttribute('href'); el('install-link').hidden = true; el('install-link').removeAttribute('href'); el('ota-status').textContent = ''; render();
}
function invalidate() {
  generation++; controller?.abort(); controller = undefined; signing = false; generated = undefined; generatedIpa = undefined; resetResult(); setBusy(false);
}
const account = setupAccount({
  getIpa: selectedIpa,
  canSubmit: canSubmitAccount,
  ensureIpa: async (signal) => {
    await configReady; signal?.throwIfAborted();
    if (custom()) { if (!selectedIpa()) { el('app-options').open = true; throw new Error('請在安裝包選項中選擇你有權使用的 IPA'); } return selectedIpa(); }
    if (!officialRelease) throw new Error('官方 Tetherless 安裝包尚未就緒。登入前需要已驗證的官方版本，或明確選擇自己的 IPA');
    if (officialIpa) return officialIpa;
    const current = ++releaseGeneration;
    try {
      const file = await acquireRelease(officialRelease, { signal, onProgress: (size, total) => { if (current === releaseGeneration) el('release-status').textContent = `正在取得官方版本… ${Math.floor(size / total * 100)}%`; } });
      if (current !== releaseGeneration) throw new DOMException('已取消', 'AbortError');
      officialIpa = file; el('release-status').textContent = '官方安裝包大小與 SHA-256 已核對'; return file;
    } catch (error) { if (current === releaseGeneration) { el('release-status').textContent = error.message; el('app-options').open = true; } throw error; }
  },
  onState: (value) => { accountPhase = value; render(); },
  onInvalidate: () => { releaseGeneration++; invalidate(); },
  onMaterial: (value, ipa) => { resetResult(); generated = value; generatedIpa = ipa; el('rights').checked = true; render(); void sign(); },
});
function setBusy(busy) {
  signing = busy;
  for (const id of ['sign', 'p12', 'profiles', 'password', 'udid', 'rights', 'account-mode', 'files-mode']) el(id).disabled = busy;
  el('cancel').hidden = !busy; render();
}
function mode(useManual) {
  if (signing) return;
  account.clear(); el('rights').checked = false; el('password').value = ''; manual = useManual; resetResult(); render();
  (manual ? el('manual-panel') : el('account-panel')).scrollIntoView?.({ block: 'start' });
}
el('account-mode').onclick = () => mode(false); el('files-mode').onclick = () => mode(true);
for (const id of ['ipa', 'p12', 'profiles', 'password', 'udid']) el(id).addEventListener('change', () => { resetResult(); if (id === 'ipa' && generated) account.clear(); });
el('app-source').onchange = () => { account.clear({ preserveDevice: true }); officialIpa = undefined; render(); };
el('release-file').onchange = async () => {
  const file = el('release-file').files[0], current = ++releaseGeneration;
  officialIpa = undefined; resetResult(); if (!file) return;
  try { await verifyReleaseFile(file, officialRelease); if (current !== releaseGeneration) return; officialIpa = file; el('release-status').textContent = '選取的官方安裝包大小與 SHA-256 已核對'; }
  catch (error) { if (current === releaseGeneration) el('release-status').textContent = error.message; }
};
el('cancel').onclick = () => { generation++; controller?.abort(); controller = undefined; setBusy(false); el('password').value = ''; resetResult(); status('已取消，沒有保留簽署輸出。可使用相同資料重試。'); };
function clearAll({ preserveEnrollment = false } = {}) {
  account.clear({ preserveEnrollment }); officialIpa = undefined;
  for (const id of ['ipa', 'p12', 'profiles', 'password', 'udid', 'ipa-url', 'manifest-url', 'release-file']) el(id).value = '';
  el('rights').checked = false; render(); status('已清除這次資料。JavaScript 記憶體無法保證立即抹除；關閉分頁可釋放執行環境。');
}
el('clear').onclick = clearAll;
window.addEventListener('pagehide', () => clearAll({ preserveEnrollment: true }));
async function sign() {
  if (controller) return;
  if (!el('rights').checked) return status('請先確認你有權使用 IPA 與簽署資料');
  const inputs = !manual ? { ipa: generatedIpa, ...generated } : { ipa: el('ipa').files[0], p12: el('p12').files[0], profiles: [...el('profiles').files], password: el('password').value, udid: el('udid').value.trim() };
  if (!inputs.ipa || !inputs.p12 || !inputs.profiles?.length) return status(!manual ? '請先完成帳號登入與簽署資料建立，或切換到已有憑證路徑' : '請選擇 IPA、P12 與至少一個 profile');
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
    el('result').hidden = false; status('已產生簽署 IPA。尚未驗證 iOS 安裝或 App 啟動。'); render();
  } catch (error) { if (current === generation) status(error.name === 'AbortError' ? '已取消' : `無法完成：${error.message}`); }
  finally { inputs.password = ''; if (current === generation) { el('password').value = ''; controller = undefined; setBusy(false); } }
}
el('sign').onclick = sign;
configReady = (async () => {
  const deadline = createReadDeadline();
  try {
    const response = await fetch(new URL('config.json', document.baseURI), { credentials: 'same-origin', redirect: 'error', cache: 'no-store', signal: deadline.signal });
    if (!response.ok) throw new Error('版本設定無法讀取');
    const config = await response.json(); officialRelease = validateRelease(config.officialRelease);
    el('release-title').textContent = `Tetherless 官方版 · ${officialRelease.tag}`;
    el('release-status').textContent = '繼續時會從指定的 GitHub Release 取得安裝包，並核對大小與 SHA-256';
    el('release-identity').textContent = `${officialRelease.repository} · ${officialRelease.assetName}\n來源 ${officialRelease.sourceCommit}\n建置 ${officialRelease.buildRunId}（第 ${officialRelease.runAttempt} 次） · ${officialRelease.buildHeadSha}\nSHA-256 ${officialRelease.sha256}`;
    el('release-link').href = officialRelease.assetUrl; el('release-details').hidden = false;
  } catch (error) {
    el('release-title').textContent = 'Tetherless 官方安裝包尚未就緒'; el('release-status').textContent = `${error.message}。請先選擇自己的 IPA，再登入 Apple。`;
    el('app-source').value = 'custom'; el('app-source').querySelector('[value="official"]').disabled = true;
  } finally { deadline.clear(); configLoaded = true; render(); }
})();
render();
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

for (const id of ['ipa-url', 'manifest-url']) el(id).addEventListener('input', () => { el('install-link').hidden = true; el('install-link').removeAttribute('href'); el('ota-status').textContent = ''; });
