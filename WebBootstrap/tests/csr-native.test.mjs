import test from 'node:test';
import assert from 'node:assert/strict';
import forge from 'node-forge';
import { verifyCsrNative } from '../src/csr-native.js';
import { createIdentity, exportRecovery, importRecovery, importP12 } from '../src/certificate-recovery.js';
import { makeMaterial } from './fixtures.mjs';
let identity;
test.before(async()=>{identity=await createIdentity('TESTTEAM01');});
const rootOf=pem=>forge.asn1.fromDer(forge.pem.decode(pem)[0].body,{decodeBitStrings:false});
const pemOf=root=>forge.pem.encode({type:'CERTIFICATE REQUEST',body:forge.asn1.toDer(root).getBytes()});
test('native CSR: valid SHA256 proof verifies and original CSR remains byte-identical through recovery',async()=>{
  const csr=await verifyCsrNative(identity.csrPem);assert(csr.publicKey.n.equals(identity.keys.publicKey.n));
  const restored=await importRecovery(await exportRecovery(identity,'synthetic-password-123'),'synthetic-password-123');assert.equal(restored.csrPem,identity.csrPem);
});
test('native CSR: tampered signature, altered CRI and unsupported signature algorithms fail closed',async()=>{
  const badSignature=rootOf(identity.csrPem);badSignature.value[2].value=badSignature.value[2].value.slice(0,-1)+String.fromCharCode(badSignature.value[2].value.at(-1).charCodeAt(0)^1);
  const badMessage=rootOf(identity.csrPem);badMessage.value[0].value[1].value[0].value[0].value[1].value='changed subject';
  const sha1=rootOf(identity.csrPem);sha1.value[1].value[0].value=forge.asn1.oidToDer(forge.pki.oids.sha1WithRSAEncryption).getBytes();
  for(const root of [badSignature,badMessage,sha1])await assert.rejects(verifyCsrNative(pemOf(root)),/原生簽章驗證/);
});
test('native CSR: malformed nested DigestAlgorithm is rejected by patched Forge and platform',async()=>{
  const a=forge.asn1,n=(type,value)=>a.create(a.Class.UNIVERSAL,type,Array.isArray(value),value),root=rootOf(identity.csrPem);
  const md=forge.md.sha256.create();md.update(a.toDer(root.value[0]).getBytes());const digest=md.digest().getBytes();
  const malformed=n(a.Type.SEQUENCE,[n(a.Type.SEQUENCE,[n(a.Type.OID,a.oidToDer(forge.pki.oids.sha256).getBytes()),n(a.Type.NULL,''),n(a.Type.OCTETSTRING,'extra nested data')]),n(a.Type.OCTETSTRING,digest)]);
  const signature=identity.keys.privateKey.sign(a.toDer(malformed).getBytes(),'NONE');
  // Historical Forge 1.4.0 accepted this synthetic structure (recorded separately).
  // Both pinned patched Forge and platform now reject it; product code continues
  // to rely on WebCrypto and never falls back to this dependency verifier.
  assert.throws(()=>identity.keys.publicKey.verify(digest,signature),/DigestInfo/);
  root.value[2].value='\x00'+signature;
  await assert.rejects(verifyCsrNative(pemOf(root)),/原生簽章驗證/);
  await assert.rejects(importRecovery(await exportRecovery({...identity,csrPem:pemOf(root)},'synthetic-password-123'),'synthetic-password-123'),/不相符/);
});
test('native CSR: create/import entry points never call Forge CSR verify',async()=>{
  const create=forge.pki.createCertificationRequest,parse=forge.pki.certificationRequestFromPem;let calls=0;
  const trap=csr=>{csr.verify=()=>{calls++;throw new Error('Affected Forge verifier must not run');};return csr;};
  forge.pki.createCertificationRequest=(...args)=>trap(create(...args));forge.pki.certificationRequestFromPem=(...args)=>trap(parse(...args));
  try{
    const generated=await createIdentity('TESTTEAM01');await importRecovery(await exportRecovery(generated,'synthetic-password-123'),'synthetic-password-123');
    const material=makeMaterial();await importP12(new File([material.p12],'synthetic.p12'),material.password,'TESTTEAM01');assert.equal(calls,0);
  }finally{forge.pki.createCertificationRequest=create;forge.pki.certificationRequestFromPem=parse;}
});
test('native CSR: unavailable platform API is rejected without fallback to Forge',async()=>{
  const verify=crypto.subtle.verify;
  try{crypto.subtle.verify=undefined;await assert.rejects(verifyCsrNative(identity.csrPem),/沒有可用的原生/);await assert.rejects(createIdentity('TESTTEAM01'),/沒有可用的原生/);}
  finally{crypto.subtle.verify=verify;}
});
test('native CSR: framing, extra roots, trailing bytes and noncanonical length fail closed',async()=>{
  for(const pem of [identity.csrPem+identity.csrPem,forge.pem.encode({type:'CERTIFICATE REQUEST',body:forge.pem.decode(identity.csrPem)[0].body+'\x00'}),forge.pem.encode({type:'CERTIFICATE REQUEST',body:'\x30\x80\x00\x00'})])await assert.rejects(verifyCsrNative(pem));
});
