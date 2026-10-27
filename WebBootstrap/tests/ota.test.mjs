import test from 'node:test'; import assert from 'node:assert/strict';
import { publicHttps, createManifest, installLink } from '../src/ota.js';
for (const value of ['http://public.example/a.ipa', 'blob:https://example.com/id', 'https://localhost/a', 'https://127.0.0.1/a', 'https://10.0.0.1/a', 'https://user:pass@example.com/a', 'https://example.com/a#secret']) test(`rejects unsuitable OTA URL ${value}`, () => assert.throws(() => publicHttps(value)));
test('escapes manifest content and URL XML', () => { const text = createManifest({ ipaUrl: 'https://example.com/a.ipa?x=1&y=2', bundleId: 'org.test.A', version: '1', title: '<unsafe>' }); assert(text.includes('&lt;unsafe&gt;')); assert(text.includes('x=1&amp;y=2')); });
test('uses HTTPS manifest in itms-services link', () => assert.equal(installLink('https://example.com/m.plist'), 'itms-services://?action=download-manifest&url=https%3A%2F%2Fexample.com%2Fm.plist'));
