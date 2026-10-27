import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const guide = readFileSync(new URL('../public/p12-guide.html', import.meta.url), 'utf8');
const document = new JSDOM(guide).window.document;

test('P12 guide is a standalone, no-script Traditional Chinese help page', () => {
  assert.equal(document.documentElement.lang, 'zh-Hant');
  assert.equal(document.querySelectorAll('h1').length, 1);
  assert.equal(document.querySelectorAll('script, form, input, iframe').length, 0);
  assert.match(document.querySelector('meta[http-equiv="Content-Security-Policy"]').content, /default-src 'none'/);
  assert.equal(document.querySelector('link[rel="stylesheet"]').getAttribute('href'), './p12-guide.css');
  assert.ok(readFileSync(new URL('../public/p12-guide.css', import.meta.url), 'utf8').includes('prefers-reduced-motion'));
});

test('P12 guide anchors resolve and all citations are Apple primary sources', () => {
  const ids = [...document.querySelectorAll('[id]')].map(node => node.id);
  assert.equal(new Set(ids).size, ids.length);
  for (const link of document.querySelectorAll('a')) {
    const href = link.getAttribute('href');
    if (href.startsWith('#')) assert.ok(document.getElementById(href.slice(1)), href);
    else if (href.startsWith('https://')) assert.ok(['developer.apple.com', 'help.apple.com', 'support.apple.com'].includes(new URL(href).hostname), href);
    else assert.ok(['./', './licenses.html'].includes(href), href);
    if (link.target === '_blank') {
      assert.ok(link.relList.contains('noopener'));
      assert.ok(link.relList.contains('noreferrer'));
    }
  }
});

test('P12 guide covers matching material, free-team limits and installation boundary', () => {
  for (const id of ['choose-route', 'personal-team', 'existing', 'csr', 'certificate', 'export', 'identifiers', 'profiles', 'xcode-profiles', 'use-files', 'troubleshooting', 'checklist']) {
    assert.ok(document.getElementById(id), id);
  }
  for (const phrase of ['7 天', '恰好一把 RSA 私鑰', '每個 App extension', '不支援 wildcard', '2 MiB', '150 MiB', '不會替你取得 IPA', '免費 Personal Team 的 Safari 首次安裝仍未經實機驗證', '不會延長免費 profile', '並不替你建立付費 Ad Hoc', '不提供解密或 DRM 移除']) {
    assert.ok(document.body.textContent.includes(phrase), phrase);
  }
});

test('manual signing links to the guide in a separate safe tab', () => {
  const home = new JSDOM(readFileSync(new URL('../index.html', import.meta.url), 'utf8')).window.document;
  const link = home.querySelector('#manual-panel a[href="./p12-guide.html"]');
  assert.ok(link, 'Add the guide link only inside the explicit manual-signing panel');
  assert.equal(link.target, '_blank');
  assert.ok(link.relList.contains('noopener'));
  assert.ok(link.relList.contains('noreferrer'));
});
