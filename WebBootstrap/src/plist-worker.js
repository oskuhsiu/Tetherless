import { parse } from './vendor/binary-plist.js';
self.onmessage = ({ data }) => {
  try { self.postMessage({ ok: true, result: parse(data) }); }
  catch { self.postMessage({ ok: false, error: 'The binary property list is invalid or exceeds metadata resource limits.' }); }
};
