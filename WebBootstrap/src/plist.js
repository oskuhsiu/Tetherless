import { parse as parseBinaryPlist } from './vendor/binary-plist.js';
export async function parsePlist(bytes, { signal } = {}) {
  if (new TextDecoder().decode(bytes.slice(0, 8)) === 'bplist00') return parseBinary(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), signal);
  const text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  if (/<!ENTITY/i.test(text)) throw new Error('Property list entities are unsupported.');
  const xml = new DOMParser().parseFromString(text, 'application/xml');
  if (xml.querySelector('parsererror') || xml.documentElement.tagName !== 'plist' || xml.documentElement.children.length !== 1) throw new Error('Invalid property list.');
  function value(node, depth = 0) {
    if (!node || depth > 32) throw new Error('Property list is too deeply nested.');
    const children = [...node.children];
    switch (node.tagName) {
      case 'dict': {
        const out = Object.create(null);
        if (children.length % 2) throw new Error('Invalid property list dictionary.');
        for (let i = 0; i < children.length; i += 2) {
          const key = children[i].textContent;
          if (children[i].tagName !== 'key' || Object.hasOwn(out, key)) throw new Error('Duplicate property list key.');
          out[key] = value(children[i + 1], depth + 1);
        }
        return out;
      }
      case 'array': return children.map((x) => value(x, depth + 1));
      case 'true': return true;
      case 'false': return false;
      case 'date': return new Date(node.textContent);
      case 'integer': case 'real': return Number(node.textContent);
      case 'data': return Uint8Array.from(atob(node.textContent.replace(/\s/g, '')), (c) => c.charCodeAt(0));
      case 'string': return node.textContent;
      default: throw new Error('Unsupported property list value.');
    }
  }
  return value(xml.documentElement.firstElementChild);
}

function parseBinary(buffer, signal) {
  // Node tests use the same bounded parser directly; browser execution is cancellable.
  if (typeof Worker === 'undefined') return parseBinaryPlist(buffer);
  return new Promise((resolve, reject) => {
    const worker = new Worker(new URL('./plist-worker.js', import.meta.url), { type: 'module' });
    let settled = false;
    const abort = () => finish(new DOMException('Metadata parsing cancelled', 'AbortError'));
    const timer = setTimeout(() => finish(new Error('Binary metadata parsing timed out.')), 1500);
    function finish(error, value) { if (settled) return; settled = true; clearTimeout(timer); worker.terminate(); signal?.removeEventListener('abort', abort); if (error) reject(error); else resolve(value); }
    worker.onmessage = ({ data }) => data.ok ? finish(null, data.result) : finish(new Error(data.error));
    worker.onerror = () => finish(new Error('Binary metadata worker failed.'));
    signal?.addEventListener('abort', abort, { once: true });
    if (signal?.aborted) abort(); else worker.postMessage(buffer, [buffer]);
  });
}
