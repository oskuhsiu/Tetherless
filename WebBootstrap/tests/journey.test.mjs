import test from 'node:test'; import assert from 'node:assert/strict';
import { journeyView } from '../src/journey.js';
test('journey: default and unavailable states expose no manual fields or install success', () => {
  for (const accountPhase of ['checking', 'unavailable', 'external', 'login']) { const v = journeyView({ accountPhase }); assert(v.account); assert(!v.manual); assert(!v.app); assert(!v.signing); assert(!v.install); assert.equal(v.step, 'login'); }
});
test('journey: verification and provisioning advance only their stage', () => {
  assert.equal(journeyView({ accountPhase: 'twoFactor' }).step, 'verify');
  for (const accountPhase of ['authenticated', 'provisioning', 'provisionRetry']) { const v = journeyView({ accountPhase }); assert(v.preparation); assert(v.app); assert(!v.install); }
});
test('journey: material/signing failures allow retry, never installation success', () => {
  for (const signing of [true, false]) { const v = journeyView({ material: true, signing }); assert(v.signing); assert(!v.account); assert(!v.install); }
});
test('journey: signed output reveals install guidance but never an installed state', () => {
  const v = journeyView({ output: true }); assert(v.install); assert.equal(v.step, 'install'); assert.equal(v.installed, undefined);
});
test('journey: manual mode expands controls and back returns to account', () => {
  const v = journeyView({ manual: true }); assert(v.manual); assert(v.app); assert(v.signing); assert(!v.account);
  assert(journeyView({ manual: false }).account);
});

test('unavailable discovery title does not diagnose service setup', () => { assert.equal(journeyView({ accountPhase: 'unavailable' }).title, '尚未確認登入服務'); });
