// Presentation only. Account/service, consent and signing remain independently gated.
export function journeyView({ manual = false, accountPhase = 'checking', signing = false, material = false, output = false } = {}) {
  const preparing = ['authenticated', 'provisioning', 'provisionRetry'].includes(accountPhase);
  const step = output ? 'install' : signing || material || preparing || accountPhase === 'twoFactor' ? 'verify' : 'login';
  return {
    step, account: !manual && !signing && !material && !output,
    preparation: !manual && preparing, manual,
    app: manual || preparing,
    signing: manual || signing || material || output,
    install: output,
    title: accountPhase === 'device' ? '先確認這支 iPhone' : accountPhase === 'checking' ? '使用 Apple 帳號' : accountPhase === 'unavailable' ? '登入服務尚未啟用' : accountPhase === 'external' ? '前往登入服務' : accountPhase === 'twoFactor' ? '確認是你本人' : preparing ? '確認後，交給我們準備' : accountPhase === 'authenticating' ? '正在登入 Apple…' : '使用 Apple 帳號',
    stage: step === 'login' ? '第 1 步 · 登入' : step === 'verify' ? '第 2 步 · 必要確認' : '第 3 步 · 安裝指引',
  };
}
