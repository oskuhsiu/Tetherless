import test from 'node:test';
import assert from 'node:assert/strict';
import forge from 'node-forge';
import { createIdentity, exportRecovery, importRecovery, exportP12, importP12, acceptCertificate, checkP12Work } from '../src/certificate-recovery.js';
const password = 'synthetic-recovery-password';
let identity;
test.before(async () => { identity = await createIdentity('TESTTEAM01'); });
function certificate(who = identity, { team = who.teamId, before = '2020-01-01', after = '2035-01-01' } = {}) {
  const cert = forge.pki.createCertificate(); cert.publicKey = who.keys.publicKey; cert.serialNumber = '01';
  cert.validity.notBefore = new Date(before); cert.validity.notAfter = new Date(after);
  cert.setSubject([{name:'commonName',value:'SYNTHETIC NOT APPLE'}, {name:'organizationalUnitName',value:team}]); cert.setIssuer(cert.subject.attributes); cert.sign(who.keys.privateKey, forge.md.sha256.create());
  return forge.util.encode64(forge.asn1.toDer(forge.pki.certificateToAsn1(cert)).getBytes());
}
test('recovery: encrypted round trip retains exact CSR and key; no private plaintext in export', async () => {
  const file = await exportRecovery(identity, password), text = await file.text();
  assert(!text.includes('PRIVATE KEY')); assert(!text.includes(identity.csrPem)); assert(!text.includes('TESTTEAM01'));
  const restored = await importRecovery(file, password);
  assert.equal(restored.csrPem, identity.csrPem); assert(restored.keys.privateKey.n.equals(identity.keys.privateKey.n));
  assert.equal(restored.teamId, identity.teamId);
});
test('recovery: wrong password, tamper, unsupported costs, oversized and null files fail closed', async () => {
  const file = await exportRecovery(identity, password);
  await assert.rejects(importRecovery(file, 'wrong-password-long'));
  const wrapper = JSON.parse(await file.text()); wrapper.ciphertext = (wrapper.ciphertext[0] === 'A' ? 'B' : 'A') + wrapper.ciphertext.slice(1);
  await assert.rejects(importRecovery(new Blob([JSON.stringify(wrapper)]), password));
  wrapper.iterations = 2147483647; await assert.rejects(importRecovery(new Blob([JSON.stringify(wrapper)]), password));
  await assert.rejects(importRecovery(new Blob(['null']), password), /版本/);
  await assert.rejects(importRecovery(new Blob([new Uint8Array(1024 * 1024 + 1)]), password), /大小/);
  await assert.rejects(exportRecovery(identity, 'short'));
});
test('recovery: imported CSR must be signed by the retained private key', async () => {
  const other = await createIdentity('TESTTEAM01');
  const file = await exportRecovery({ ...identity, csrPem: other.csrPem }, password);
  await assert.rejects(importRecovery(file, password), /不相符/);
});
test('recovery: rejects damaged private exponent even when intact CRT can sign', async () => {
  const badKey = forge.pki.privateKeyFromPem(forge.pki.privateKeyToPem(identity.keys.privateKey));
  badKey.d = badKey.d.add(new forge.jsbn.BigInteger('1'));
  const file = await exportRecovery({ ...identity, keys: { ...identity.keys, privateKey: badKey } }, password);
  await assert.rejects(importRecovery(file, password), /不相符/);
});
test('certificate: key, Team, expiry and future validity checked without claiming Apple trust chain', async () => {
  const other = await createIdentity('TESTTEAM01');
  for (const encoded of [certificate(other), certificate(identity,{team:'OTHERTEAM'}), certificate(identity,{after:'2020-01-02'}), certificate(identity,{before:'2034-01-01'})]) assert.throws(() => acceptCertificate(identity,encoded));
  acceptCertificate(identity,certificate());
  const restored = await importRecovery(await exportRecovery(identity,password),password);
  assert.equal(restored.certificateDerBase64,identity.certificateDerBase64);
});
test('P12: encrypted export imports exact key and Team; wrong password or other Team rejected', async () => {
  acceptCertificate(identity,certificate());
  const p12 = exportP12(identity,password); assert.equal(p12.type,'application/x-pkcs12');
  const restored = await importP12(p12,password,'TESTTEAM01'); assert(restored.keys.publicKey.n.equals(identity.keys.publicKey.n));
  await assert.rejects(importP12(p12,'wrong-password-long','TESTTEAM01'));
  await assert.rejects(importP12(p12,password,'OTHERTEAM'));
  assert.throws(() => exportP12(identity,undefined));
});
test('P12: rejects pathological MAC and KDF iteration counts before decrypting', () => {
  const a = forge.asn1, node = (type,value) => a.create(a.Class.UNIVERSAL,type,Array.isArray(value),value);
  const tooMuch = node(a.Type.INTEGER, '\x7f\xff\xff\xff');
  assert.throws(() => checkP12Work(node(a.Type.SEQUENCE, [node(a.Type.INTEGER,'\x03'),node(a.Type.SEQUENCE,[]),node(a.Type.SEQUENCE,[node(a.Type.SEQUENCE,[]),node(a.Type.OCTETSTRING,'salt'),tooMuch])])));
  assert.throws(() => checkP12Work(node(a.Type.SEQUENCE,[node(a.Type.OID,a.oidToDer('1.2.840.113549.1.5.12').getBytes()),node(a.Type.SEQUENCE,[node(a.Type.OCTETSTRING,'salt'),tooMuch])])));
});
test('P12: emitted PBES2 explicitly uses HMAC-SHA256 PRF and 100000 iterations for Apple interoperability', async () => {
  acceptCertificate(identity,certificate());
  const file=exportP12(identity,password),root=forge.asn1.fromDer(forge.util.binary.raw.encode(new Uint8Array(await file.arrayBuffer()))),params=[];
  function walk(node){
    if(Array.isArray(node.value)){
      if(node.value[0]?.type===forge.asn1.Type.OID&&forge.asn1.derToOid(node.value[0].value)==='1.2.840.113549.1.5.12')params.push(node.value[1]);
      node.value.forEach(walk);
    }else if(node.type===forge.asn1.Type.OCTETSTRING&&typeof node.value==='string'&&node.value.charCodeAt(0)===48){let nested;try{nested=forge.asn1.fromDer(node.value);}catch{return;}walk(nested);}
  }
  walk(root);assert.equal(params.length,1);
  assert.equal(forge.asn1.derToInteger(params[0].value[1].value),100000);
  assert.equal(forge.asn1.derToOid(params[0].value[3].value[0].value),'1.2.840.113549.2.9');
});
test('P12: new exports reject non-ASCII/control passwords; Unicode recovery still round trips unchanged',async()=>{
  acceptCertificate(identity,certificate());
  for(const rejected of ['合成測試密碼非真實使用者','synthetic-password-🔐','synthetic-password-\n'])assert.throws(()=>exportP12(identity,rejected),/ASCII/);
  const unicode='合成測試密碼非真實使用者';const restored=await importRecovery(await exportRecovery(identity,unicode),unicode);
  assert.equal(restored.csrPem,identity.csrPem);assert.equal(restored.teamId,identity.teamId);
});
