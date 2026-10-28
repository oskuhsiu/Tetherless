// Display only protocol-owned labels and bounded numbers, never upstream text.
const stages = Object.freeze({ accountSetup: '登入服務準備', appleLogin: 'Apple 帳號驗證', developerToken: '開發者登入憑證', developerTeams: '讀取 Apple Team', task: '登入工作' });
const kinds = Object.freeze({ appleRejected: 'Apple 回應拒絕', developerRejected: 'Apple 開發者服務回應拒絕', upstreamTimeout: '上游操作逾時', anisetteUnavailable: 'Anisette 尚未可用', httpRejected: '上游 HTTP 請求未成功', networkTimeout: '上游請求逾時', networkConnect: '上游連線未完成', networkFailure: '上游網路請求未完成', unknown: '原因尚未分類', taskFailed: '登入工作未完成' });
const upstreams = Object.freeze({ apple: 'Apple 服務', anisette: 'Anisette 服務', other: '其他上游', unknown: '上游尚未識別' });
export function loginDiagnosticText(diagnostic) {
  if (!diagnostic || typeof diagnostic !== 'object' || Array.isArray(diagnostic)) return '';
  if (!Object.hasOwn(stages, diagnostic.stage) || !Object.hasOwn(kinds, diagnostic.kind)) return '';
  const parts = [stages[diagnostic.stage], kinds[diagnostic.kind]];
  if (typeof diagnostic.upstream === 'string' && Object.hasOwn(upstreams, diagnostic.upstream)) parts.push(`來源：${upstreams[diagnostic.upstream]}`);
  if (Number.isSafeInteger(diagnostic.appleCode)) parts.push(`Apple 代碼 ${diagnostic.appleCode}`);
  if (Number.isInteger(diagnostic.httpStatus) && diagnostic.httpStatus >= 100 && diagnostic.httpStatus <= 599) parts.push(`HTTP ${diagnostic.httpStatus}`);
  return `。診斷：${parts.join('／')}。此資訊不能單獨判定密碼錯誤或 IP 遭封鎖；請勿連續重試。`;
}
