const xml = (value) => String(value).replace(/[<>&'\"]/g, (c) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', "'": '&apos;', '"': '&quot;' }[c]));
export function publicHttps(value) {
  let url; try { url = new URL(value); } catch { throw new Error('Enter a full public HTTPS URL.'); }
  if (url.protocol !== 'https:' || url.username || url.password || url.hash || url.hostname === 'localhost' || url.hostname.endsWith('.localhost') || url.hostname.endsWith('.local') || !url.hostname.includes('.') || /^(?:127\.|10\.|192\.168\.|169\.254\.|172\.(?:1[6-9]|2\d|3[01])\.)/.test(url.hostname) || url.hostname.includes(':')) throw new Error('Use a public HTTPS URL without credentials or fragments.');
  return url.href;
}
export function createManifest({ ipaUrl, bundleId, version, title }) {
  return `<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0"><dict><key>items</key><array><dict><key>assets</key><array><dict><key>kind</key><string>software-package</string><key>url</key><string>${xml(publicHttps(ipaUrl))}</string></dict></array><key>metadata</key><dict><key>bundle-identifier</key><string>${xml(bundleId)}</string><key>bundle-version</key><string>${xml(version)}</string><key>kind</key><string>software</string><key>title</key><string>${xml(title)}</string></dict></dict></array></dict></plist>\n`;
}
export function installLink(manifestUrl) { return `itms-services://?action=download-manifest&url=${encodeURIComponent(publicHttps(manifestUrl))}`; }
