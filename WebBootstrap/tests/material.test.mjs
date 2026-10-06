import test from 'node:test'; import assert from 'node:assert/strict'; import { JSDOM } from 'jsdom';
import { makeIpa, makeMaterial } from './fixtures.mjs';
import { inspectInputs, bundleMatches } from '../src/material.js';
globalThis.DOMParser = new JSDOM('').window.DOMParser;
let material, ipa;
test.before(async () => { material = makeMaterial(); ipa = new File([await makeIpa()], 'Fixture.ipa'); });
function inputs(overrides = {}) { return { ipa, p12: new File([material.p12], 'fixture.p12'), profiles: [new File([material.profile], 'fixture.mobileprovision')], password: material.password, ...overrides }; }
test('parses CMS profile and checks fixture key, certificate, team, bundle and UDID consistency', async () => { const m = await inspectInputs(inputs({ udid: '00000000-0000000000000000' })); assert.equal(m.team, 'TESTTEAM01'); assert.equal(m.bundles[0].id, 'org.tetherless.TestFixture'); assert.equal(m.profiles[0].kind, 'personal-team'); });
test('rejects wrong P12 password', async () => { await assert.rejects(inspectInputs(inputs({ password: 'wrong' })), /could not be opened/); });
test('rejects a profile missing the selected device', async () => { await assert.rejects(inspectInputs(inputs({ udid: '00000000-1111111111111111' })), /does not contain/); });
test('rejects an unmatched app profile', async () => { await assert.rejects(inspectInputs(inputs({ ipa: new File([await makeIpa({ bundleId: 'org.other.App' })], 'Other.ipa') })), /Missing a unique exact profile/); });
test('rejects a certificate absent from profile', async () => { const other = makeMaterial(); await assert.rejects(inspectInputs(inputs({ profiles: [new File([other.profile], 'other.mobileprovision')] })), /certificate is absent/); });
test('rejects expired profile/certificate fixture', async () => { await assert.rejects(inspectInputs(inputs(), new Date('2040-01-01')), /not currently valid/); });
test('wildcard bundle matching respects a dot separator', () => { assert(bundleMatches('org.test.*', 'org.test.Child')); assert(!bundleMatches('org.test.*', 'org.testing.App')); });
