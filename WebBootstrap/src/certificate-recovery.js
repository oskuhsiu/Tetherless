import forge from 'node-forge';
import { verifyCsrNative } from './csr-native.js';

// Versioned, client-only recovery format. No localStorage, IndexedDB or server custody.
const LIMIT = 1024 * 1024;
const iterations = 310000;
const enc = new TextEncoder(), dec = new TextDecoder();
const b64 = (bytes) => forge.util.encode64(forge.util.binary.raw.encode(bytes));
function bytes(value, maximum = LIMIT) {
  if (typeof value !== 'string' || value.length > maximum * 2 || !/^[A-Za-z0-9+/]*={0,2}$/.test(value)) throw new Error('恢復檔格式無效');
  return forge.util.binary.raw.decode(forge.util.decode64(value));
}
export async function createIdentity(teamId) {
  if (!/^[A-Za-z0-9]{1,64}$/.test(teamId)) throw new Error('請先選擇有效的 Team');
  const keys = await new Promise((resolve, reject) => forge.pki.rsa.generateKeyPair({ bits: 2048, workers: 0 }, (error, pair) => error ? reject(error) : resolve(pair)));
  const identity = identityFromKey(keys.privateKey, teamId);
  await verifyCsrNative(identity.csrPem); return identity;
}
function identityFromKey(privateKey, teamId, certificateDerBase64) {
  if (!/^[A-Za-z0-9]{1,64}$/.test(teamId)) throw new Error('無效的 Team');
  const one = new forge.jsbn.BigInteger('1');
  const { n, e, d, p, q, dP, dQ, qInv } = privateKey;
  if (![n, e, d, p, q, dP, dQ, qInv].every(value => value && value.compareTo(one) > 0) || n.bitLength() < 2048 || n.bitLength() > 4096) throw new Error('私鑰參數無效');
  const pm = p.subtract(one), qm = q.subtract(one), lcm = pm.multiply(qm).divide(pm.gcd(qm));
  if (!n.equals(p.multiply(q)) || !e.multiply(d).mod(lcm).equals(one) || !dP.equals(d.mod(pm)) || !dQ.equals(d.mod(qm)) || !qInv.multiply(q).mod(p).equals(one)) throw new Error('私鑰參數不一致');
  const publicKey = forge.pki.rsa.setPublicKey(privateKey.n, privateKey.e);
  if (privateKey.n.bitLength() < 2048 || privateKey.n.bitLength() > 4096) throw new Error('只接受 2048 至 4096 位元 RSA 私鑰');
  const csr = forge.pki.createCertificationRequest(); csr.publicKey = publicKey;
  csr.setSubject([{ name: 'commonName', value: 'Tetherless browser signing' }]); csr.sign(privateKey, forge.md.sha256.create());
  const identity = { teamId, keys: { privateKey, publicKey }, csrPem: forge.pki.certificationRequestToPem(csr) };
  if (certificateDerBase64) acceptCertificate(identity, certificateDerBase64);
  return identity;
}
export function acceptCertificate(identity, encoded) {
  const der = bytes(encoded, 65536);
  const cert = forge.pki.certificateFromAsn1(forge.asn1.fromDer(forge.util.binary.raw.encode(der)));
  if (!cert.publicKey.n?.equals(identity.keys.publicKey.n) || !cert.publicKey.e?.equals(identity.keys.publicKey.e)) throw new Error('憑證不符合此恢復檔的私鑰');
  const team = cert.subject.getField('OU')?.value;
  if (team !== identity.teamId) throw new Error('憑證的 Team 與此恢復檔不符');
  if (!Number.isFinite(+cert.validity.notBefore) || !Number.isFinite(+cert.validity.notAfter) || cert.validity.notBefore > new Date() || cert.validity.notAfter <= new Date()) throw new Error('憑證已到期，不能用於新簽署');
  identity.certificateDerBase64 = encoded; identity.cert = cert;
  return cert;
}
async function derive(password, salt, usages) {
  if (typeof password !== 'string' || password.length < 12 || password.length > 1024) throw new Error('恢復檔密碼需要 12 至 1024 個字元；請保存在你自己的密碼管理器');
  const material = await crypto.subtle.importKey('raw', enc.encode(password), 'PBKDF2', false, ['deriveKey']);
  return crypto.subtle.deriveKey({ name: 'PBKDF2', hash: 'SHA-256', salt, iterations }, material, { name: 'AES-GCM', length: 256 }, false, usages);
}
export async function exportRecovery(identity, password) {
  const salt = crypto.getRandomValues(new Uint8Array(16)), iv = crypto.getRandomValues(new Uint8Array(12));
  const payload = enc.encode(JSON.stringify({ version: 1, teamId: identity.teamId, privateKeyPem: forge.pki.privateKeyToPem(identity.keys.privateKey), csrPem: identity.csrPem, ...(identity.certificateDerBase64 ? { certificateDerBase64: identity.certificateDerBase64 } : {}) }));
  const ciphertext = await crypto.subtle.encrypt({ name: 'AES-GCM', iv, additionalData: enc.encode('Tetherless recovery v1') }, await derive(password, salt, ['encrypt']), payload);
  return new Blob([JSON.stringify({ format: 'tetherless-recovery', version: 1, kdf: 'PBKDF2-SHA256', iterations, cipher: 'AES-256-GCM', salt: b64(salt), iv: b64(iv), ciphertext: b64(new Uint8Array(ciphertext)) })], { type: 'application/json' });
}
export async function importRecovery(file, password) {
  if (!file || file.size > LIMIT || !file.size) throw new Error('恢復檔超過大小限制或為空');
  let wrapper; try { wrapper = JSON.parse(await file.text()); } catch { throw new Error('恢復檔格式無效'); }
  if (!wrapper || Array.isArray(wrapper) || wrapper.format !== 'tetherless-recovery' || wrapper.version !== 1 || wrapper.kdf !== 'PBKDF2-SHA256' || wrapper.iterations !== iterations || wrapper.cipher !== 'AES-256-GCM') throw new Error('不支援此恢復檔版本');
  const salt = bytes(wrapper.salt, 16), iv = bytes(wrapper.iv, 12); if (salt.length !== 16 || iv.length !== 12) throw new Error('恢復檔格式無效');
  let payload;
  try { payload = JSON.parse(dec.decode(await crypto.subtle.decrypt({ name: 'AES-GCM', iv, additionalData: enc.encode('Tetherless recovery v1') }, await derive(password, salt, ['decrypt']), bytes(wrapper.ciphertext)))); }
  catch { throw new Error('恢復檔密碼不正確，或檔案已損壞'); }
  if (!payload || Array.isArray(payload) || payload.version !== 1 || !/^[A-Za-z0-9]{1,64}$/.test(payload.teamId) || typeof payload.privateKeyPem !== 'string' || payload.privateKeyPem.length > 32768 || typeof payload.csrPem !== 'string' || payload.csrPem.length > 32768) throw new Error('恢復檔內容無效');
  try {
    const identity = identityFromKey(forge.pki.privateKeyFromPem(payload.privateKeyPem), payload.teamId, payload.certificateDerBase64);
    const csr = await verifyCsrNative(payload.csrPem);
    if ( !csr.publicKey.n.equals(identity.keys.publicKey.n) || !csr.publicKey.e.equals(identity.keys.publicKey.e)) throw new Error();
    identity.csrPem = payload.csrPem; return identity;
  } catch { throw new Error('恢復檔的私鑰、CSR 或憑證不相符'); }
}
// Reject pathological KDF work before invoking node-forge's synchronous decoder.
// PKCS#12 MAC iteration and supported PBES/PBKDF2 parameter integers are bounded.
export function checkP12Work(root) {
  const integer = node => {
    if (!node || node.type !== forge.asn1.Type.INTEGER || typeof node.value !== 'string' || node.value.length > 4 || !node.value.length || node.value.charCodeAt(0) >= 128) throw new Error('P12 KDF 參數無效');
    let value = 0; for (const char of node.value) value = value * 256 + char.charCodeAt(0);
    if (value < 1 || value > 1000000) throw new Error('P12 KDF 工作量超過上限');
  };
  if (root.value?.[2]?.value?.[2]) integer(root.value[2].value[2]);
  let nodes = 0, algorithms = 0;
  function visit(node, depth = 0) {
    if (++nodes > 10000 || depth > 32) throw new Error('P12 結構超過上限');
    if (Array.isArray(node.value)) {
      const [oid, parameters] = node.value;
      if (oid?.type === forge.asn1.Type.OID) {
        const id = forge.asn1.derToOid(oid.value);
        if (id === '1.2.840.113549.1.5.12' || id.startsWith('1.2.840.113549.1.12.1.')) {
          if (++algorithms > 32) throw new Error('P12 KDF 數量超過上限');
          integer(parameters?.value?.[1]);
        }
      }
      for (const child of node.value) visit(child, depth + 1);
    } else if (node.type === forge.asn1.Type.OCTETSTRING && typeof node.value === 'string' && node.value.charCodeAt(0) === 48) {
      // AuthenticatedSafe and unencrypted SafeContents are nested DER OCTETs.
      let inner; try { inner = forge.asn1.fromDer(node.value); } catch { return; }
      visit(inner, depth + 1);
    }
  }
  visit(root);
}
export async function importP12(file, password, teamId) {
  if (typeof password !== 'string' || password.length > 1024) throw new Error('P12 密碼過長');
  if (!file || file.size > LIMIT || !file.size) throw new Error('P12 超過大小限制或為空');
  try {
    const asn1 = forge.asn1.fromDer(forge.util.binary.raw.encode(new Uint8Array(await file.arrayBuffer())));
    checkP12Work(asn1);
    const p12 = forge.pkcs12.pkcs12FromAsn1(asn1, password);
    const keyBags = [...(p12.getBags({ bagType: forge.pki.oids.pkcs8ShroudedKeyBag })[forge.pki.oids.pkcs8ShroudedKeyBag] || []), ...(p12.getBags({ bagType: forge.pki.oids.keyBag })[forge.pki.oids.keyBag] || [])];
    if (keyBags.length !== 1 || !keyBags[0].key) throw new Error();
    const identity = identityFromKey(keyBags[0].key, teamId);
    const certs = (p12.getBags({ bagType: forge.pki.oids.certBag })[forge.pki.oids.certBag] || []).map(b => b.cert).filter(c => c?.publicKey.n?.equals(identity.keys.publicKey.n));
    if (certs.length !== 1) throw new Error();
    acceptCertificate(identity, forge.util.encode64(forge.asn1.toDer(forge.pki.certificateToAsn1(certs[0])).getBytes())); await verifyCsrNative(identity.csrPem); return identity;
  } catch { throw new Error('P12 密碼、私鑰、有效憑證或 Team 不符'); }
}
export function exportP12(identity, password) {
  if (!identity.cert || typeof password !== 'string' || password.length < 12 || password.length > 1024) throw new Error('請先取得相符憑證，並輸入至少 12 個字元的匯出密碼');
  if (!/^[\x20-\x7e]{12,1024}$/.test(password)) throw new Error('P12 匯出密碼請使用至少 12 個可列印英文字母、數字或 ASCII 符號；中文／Unicode 密碼目前與 iOS 匯入不相容。恢復檔原密碼不受影響');
  const encoded = forge.asn1.toDer(forge.pkcs12.toPkcs12Asn1(identity.keys.privateKey, [identity.cert], password, { algorithm: 'aes256', count: 100000, prfAlgorithm: 'sha256' })).getBytes();
  return new File([forge.util.binary.raw.decode(encoded)], 'tetherless-signing.p12', { type: 'application/x-pkcs12' });
}
export function downloadLocal(blob, name) {
  const url = URL.createObjectURL(blob), link = document.createElement('a'); link.href = url; link.download = name; link.rel = 'noreferrer'; document.body.append(link); link.click(); link.remove();
  // Keep the object URL alive while the browser starts its download, then release it.
  setTimeout(() => URL.revokeObjectURL(url), 60000).unref?.();
}

// Untrusted P12 KDF and ASN.1 parsing runs off the UI thread with a hard lifetime.
export function importP12InWorker(file, password, teamId, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new Error('已取消匯入'));
    let settled = false;
    const worker = new Worker(new URL('./certificate-import-worker.js', import.meta.url), { type: 'module' });
    const finish = (error, value) => { if (settled) return; settled = true; clearTimeout(timer); signal?.removeEventListener('abort', cancel); worker.terminate(); error ? reject(error) : resolve(value); };
    const cancel = () => finish(new Error('已取消匯入'));
    const timer = setTimeout(() => finish(new Error('P12 解析超過 15 秒，已停止；請檢查檔案')), 15000);
    signal?.addEventListener('abort', cancel, { once: true });
    worker.onerror = () => finish(new Error('P12 本機解析未完成'));
    worker.onmessage = async ({ data }) => {
      if (settled) return;
      if (!data || typeof data !== 'object') return finish(new Error('P12 解析回應無效'));
      if (data.error) return finish(new Error(data.error));
      try { if (data.teamId !== teamId || typeof data.privateKeyPem !== 'string' || data.privateKeyPem.length > 32768) throw new Error(); const identity = identityFromKey(forge.pki.privateKeyFromPem(data.privateKeyPem), teamId, data.certificateDerBase64); await verifyCsrNative(identity.csrPem); finish(null, identity); }
      catch { finish(new Error('P12 私鑰或 Team 不符')); }
    };
    worker.postMessage({ file, password, teamId });
  });
}
