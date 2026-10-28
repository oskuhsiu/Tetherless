import forge from 'node-forge';
const raw = value => forge.util.binary.raw.decode(value);
const fail = () => { throw new Error('CSR 格式、演算法或原生簽章驗證未通過'); };
// Only bounded DER framing is handled here. PKCS#1 DigestInfo/padding verification
// belongs exclusively to platform WebCrypto, never node-forge's RSA verifier.
function item(bytes, offset) {
  const start = offset, tag = bytes[offset++]; if (offset >= bytes.length) fail();
  let size = bytes[offset++];
  if (size & 128) {
    const count = size & 127; if (!count || count > 4 || offset + count > bytes.length || bytes[offset] === 0) fail();
    size = 0; for (let i = 0; i < count; i++) size = size * 256 + bytes[offset++];
    if (size < 128) fail();
  }
  if (offset + size > bytes.length) fail();
  return { tag, start, body: offset, end: offset + size };
}
export async function verifyCsrNative(pem) {
  if (!globalThis.crypto?.subtle?.importKey || !globalThis.crypto?.subtle?.verify) throw new Error('此瀏覽器沒有可用的原生 CSR 驗證，未接受簽署身分');
  if (typeof pem !== 'string' || pem.length > 32768) fail();
  try {
    const decoded = forge.pem.decode(pem);
    if (decoded.length !== 1 || decoded[0].type !== 'CERTIFICATE REQUEST') fail();
    const der = raw(decoded[0].body), outer = item(der, 0), criFrame = item(der, outer.body);
    if (outer.tag !== 48 || outer.end !== der.length || criFrame.tag !== 48 || criFrame.end > outer.end) fail();
    const root = forge.asn1.fromDer(decoded[0].body, { strict: true, parseAllBytes: true, decodeBitStrings: false, maxDepth: 32 });
    const sequence = node => node?.tagClass === forge.asn1.Class.UNIVERSAL && node.type === forge.asn1.Type.SEQUENCE && node.constructed === true;
    if (!sequence(root) || forge.asn1.toDer(root).getBytes() !== decoded[0].body || !Array.isArray(root.value) || root.value.length !== 3) fail();
    const [cri, algorithm, signature] = root.value;
    if (!sequence(cri) || !Array.isArray(cri.value) || cri.value.length !== 4 || cri.value[0].type !== forge.asn1.Type.INTEGER || cri.value[0].value !== '\x00') fail();
    if (!sequence(algorithm) || !Array.isArray(algorithm.value) || ![1, 2].includes(algorithm.value.length) || algorithm.value[0].type !== forge.asn1.Type.OID || forge.asn1.derToOid(algorithm.value[0].value) !== forge.pki.oids.sha256WithRSAEncryption) fail();
    if (algorithm.value.length === 2 && (algorithm.value[1].type !== forge.asn1.Type.NULL || algorithm.value[1].value !== '')) fail();
    if (signature.tagClass !== forge.asn1.Class.UNIVERSAL || signature.constructed || signature.value?.length <= 1 || signature.type !== forge.asn1.Type.BITSTRING || typeof signature.value !== 'string' || signature.value.charCodeAt(0) !== 0) fail();
    const key = await crypto.subtle.importKey('spki', raw(forge.asn1.toDer(cri.value[2]).getBytes()), { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' }, false, ['verify']);
    // Verify the original, unmodified CertificationRequestInfo DER bytes.
    if (!await crypto.subtle.verify('RSASSA-PKCS1-v1_5', key, raw(signature.value.slice(1)), der.slice(criFrame.start, criFrame.end))) fail();
    return forge.pki.certificationRequestFromPem(pem);
  } catch { fail(); }
}
