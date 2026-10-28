/* Tetherless local-only adapter for pinned node-forge 1.4.2. No network API. */
(function () {
  'use strict';
  function randomBytes(count) {
    if (!Number.isSafeInteger(count) || count < 0 || count > 65536) throw new Error('randomUnavailable');
    const bytes = nativeSecureRandom(count);
    if (!bytes || bytes.length !== count) throw new Error('randomUnavailable');
    return String.fromCharCode.apply(null, Array.from(bytes));
  }
  // Override both sync interfaces. No entropy fallback to time/Math.random.
  forge.random.getBytesSync = randomBytes;
  forge.random.getBytes = function (count, callback) {
    if (callback !== undefined) throw new Error('asyncRandomUnsupported');
    return randomBytes(count);
  };
  // Every imported encrypted SafeContents/key bag eventually reaches these
  // mature KDFs, including nested containers. Bound work BEFORE each call.
  let work = 0;
  function charge(iterations, length) {
    if (!Number.isSafeInteger(iterations) || iterations < 1 || iterations > 1000000 ||
        !Number.isSafeInteger(length) || length < 1 || length > 64) throw new Error('workLimit');
    work += iterations * Math.ceil(length / 20);
    if (work > 1000000) throw new Error('workLimit');
  }
  const originalPBKDF2 = forge.pkcs5.pbkdf2;
  forge.pkcs5.pbkdf2 = function (password, salt, iterations, length, md, callback) {
    if (callback !== undefined || typeof md === 'function' || salt.length > 128) throw new Error('workLimit');
    charge(iterations, length);
    return originalPBKDF2(password, salt, iterations, length, md);
  };
  const originalPKCS12 = forge.pbe.generatePkcs12Key;
  function limitedPKCS12(password, salt, id, iterations, length, md) {
    if (!salt || salt.length() > 128) throw new Error('workLimit');
    charge(iterations, length);
    return originalPKCS12(password, salt, id, iterations, length, md);
  }
  forge.pbe.generatePkcs12Key = limitedPKCS12;
  forge.pki.pbe.generatePkcs12Key = limitedPKCS12;
  forge.pkcs12.generateKey = limitedPKCS12;
  function boundRSA(key) {
    if (!key || !key.n || !key.e || key.n.bitLength() < 2048 || key.n.bitLength() > 4096 ||
        key.e.bitLength() > 32 || key.e.compareTo(new forge.jsbn.BigInteger('3')) < 0 || key.e.isEven()) throw new Error('rsaWorkLimit');
    for (const name of ['d', 'p', 'q', 'dP', 'dQ', 'qInv']) {
      if (!key[name] || key[name].signum() <= 0 || key[name].bitLength() > 4096) throw new Error('rsaWorkLimit');
    }
  }
  globalThis.tetherlessValidateP12 = function (base64, password) {
    work = 0;
    if (typeof password !== 'string' || password.length > 1024 || base64.length > 65536) throw new Error('invalidInput');
    const root = forge.asn1.fromDer(forge.util.decode64(base64), {strict:true, maxDepth:32});
    if (!Array.isArray(root.value) || root.value.length !== 3 || !root.value[2]) throw new Error('unauthenticatedContainer');
    const parsed = forge.pkcs12.pkcs12FromAsn1(root, true, password);
    const keys = [...(parsed.getBags({bagType:forge.pki.oids.pkcs8ShroudedKeyBag})[forge.pki.oids.pkcs8ShroudedKeyBag] || []),
      ...(parsed.getBags({bagType:forge.pki.oids.keyBag})[forge.pki.oids.keyBag] || [])];
    const certs = parsed.getBags({bagType:forge.pki.oids.certBag})[forge.pki.oids.certBag] || [];
    if (keys.length !== 1 || !keys[0].key || certs.length !== 1) throw new Error('invalidIdentity');
    const key = keys[0].key;
    boundRSA(key);
    const matches = certs.filter(b => b.cert && !b.cert.publicKey.n.compareTo(key.n) && !b.cert.publicKey.e.compareTo(key.e));
    if (matches.length !== 1) throw new Error('invalidIdentity');
    return 'valid';
  };
  globalThis.tetherlessEncryptP12 = function (certificateBase64, privateKeyBase64, password) {
    work = 0;
    if (typeof password !== 'string' || password.length < 12 || password.length > 1024 || !/^[\x20-\x7e]+$/.test(password)) throw new Error('invalidInput');
    const cert = forge.pki.certificateFromAsn1(forge.asn1.fromDer(forge.util.decode64(certificateBase64), true));
    const key = forge.pki.privateKeyFromAsn1(forge.asn1.fromDer(forge.util.decode64(privateKeyBase64), true));
    boundRSA(key);
    if (key.n.compareTo(cert.publicKey.n) || key.e.compareTo(cert.publicKey.e)) throw new Error('keyMismatch');
    const pfx = forge.pkcs12.toPkcs12Asn1(key, [cert], password,
      {algorithm: 'aes256', count: 100000, prfAlgorithm: 'sha256', saltSize: 16, useMac: true, generateLocalKeyId: true});
    const bytes = forge.asn1.toDer(pfx).getBytes();
    // A successful same-password parse alone does not prove encryption.
    // Require the encrypted bag; no unencrypted keyBag is acceptable.
    const parsed = forge.pkcs12.pkcs12FromAsn1(forge.asn1.fromDer(bytes, true), true, password);
    const encrypted = parsed.getBags({bagType: forge.pki.oids.pkcs8ShroudedKeyBag})[forge.pki.oids.pkcs8ShroudedKeyBag] || [];
    const bare = parsed.getBags({bagType: forge.pki.oids.keyBag})[forge.pki.oids.keyBag] || [];
    if (encrypted.length !== 1 || bare.length !== 0 || !encrypted[0].key || encrypted[0].key.n.compareTo(key.n)) throw new Error('invalidOutput');
    return forge.util.encode64(bytes);
  };
})();
