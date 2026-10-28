import test from 'node:test';
import assert from 'node:assert/strict';
import { loginDiagnosticText } from '../src/login-diagnostics.js';

test('login diagnostic renders allowlisted labels and numeric codes, never response payloads', () => {
  const text = loginDiagnosticText({ stage: 'appleLogin', kind: 'appleRejected', appleCode: -21669, httpStatus: 403, message: 'PRIVATE_RESPONSE', url: 'https://secret.invalid/token', token: 'PRIVATE_TOKEN' });
  assert.match(text, /Apple 帳號驗證／Apple 回應拒絕／Apple 代碼 -21669／HTTP 403/);
  assert.match(text, /不能單獨判定/);
  assert.doesNotMatch(text, /PRIVATE|secret/);
});
test('unknown labels, inherited object keys and invalid values fail closed', () => {
  for (const value of [null, [], 'PRIVATE', { stage: 'PRIVATE', kind: 'unknown' }, { stage: 'task', kind: '__proto__' }, { stage: 'constructor', kind: 'unknown' }]) assert.equal(loginDiagnosticText(value), '');
  for (const appleCode of ['PRIVATE', NaN, Infinity, 1.1, Number.MAX_SAFE_INTEGER + 1]) assert.doesNotMatch(loginDiagnosticText({ stage: 'task', kind: 'unknown', appleCode }), /Apple 代碼/);
  for (const httpStatus of ['403', 0, 99, 600, 403.1, NaN]) assert.doesNotMatch(loginDiagnosticText({ stage: 'task', kind: 'unknown', httpStatus }), /HTTP [0-9]/);
});
test('each diagnostic category is represented without raw upstream strings', () => {
  for (const kind of ['appleRejected', 'anisetteUnavailable', 'httpRejected', 'networkTimeout', 'networkConnect', 'networkFailure', 'unknown', 'taskFailed']) assert.match(loginDiagnosticText({ stage: 'developerToken', kind }), /診斷：開發者登入憑證/);
});

test('upstream attribution accepts only fixed enum labels, never hosts or raw URLs', () => {
  for (const [upstream, label] of [['apple', 'Apple 服務'], ['anisette', 'Anisette 服務'], ['other', '其他上游'], ['unknown', '上游尚未識別']]) {
    const text = loginDiagnosticText({ stage: 'appleLogin', kind: 'networkFailure', upstream, url: 'https://private.invalid/token' });
    assert(text.includes(`來源：${label}`)); assert.doesNotMatch(text, /private|https:/);
  }
  for (const upstream of ['https://private.invalid/token', 'mac-ani.jkcoxson.com', 'constructor', '__proto__', ['apple'], {}, null, 403]) {
    const text = loginDiagnosticText({ stage: 'appleLogin', kind: 'networkFailure', upstream });
    assert.doesNotMatch(text, /來源：|private|iloader|constructor|__proto__/);
  }
});
