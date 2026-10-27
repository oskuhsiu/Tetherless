import test from 'node:test'; import assert from 'node:assert/strict'; import forge from 'node-forge';
import { JSDOM } from 'jsdom';
import { guidedApiPath, syntheticProvision, createGuidedService, SYNTHETIC } from './browser/guided-service.mjs';
import { makeIpa, makeSignedFixture } from './fixtures.mjs';
import { inspectInputs } from '../src/material.js';
const base='http://127.0.0.1:4173/Tetherless/';
test('guided fixture: exact local synthetic API routes only, without weakening static policy',()=>{
  for(const [path,method] of [['health','GET'],['config.json','GET'],['v1/sessions','POST'],['v1/sessions/synthetic-session-1','GET'],['v1/sessions/synthetic-session-1','DELETE'],['v1/sessions/synthetic-session-1/teams','GET'],['v1/sessions/synthetic-session-1/teams/TESTTEAM01/devices','GET'],['v1/sessions/synthetic-session-1/2fa','POST'],['v1/sessions/synthetic-session-1/provision','POST']]) assert.equal(guidedApiPath(new URL(path,base),method,base),path);
  for(const [url,method] of [['https://apple.com/v1/sessions','POST'],['http://127.0.0.1:4173/v1/sessions','POST'],[base+'v1/sessions','DELETE'],[base+'v1/sessions/real-session','GET'],[base+'v1/sessions/synthetic-session-1/provision','GET'],[base+'v1/sessions?secret=1','POST'],[base+'v1/device-enrollments','POST']]) assert.equal(guidedApiPath(url,method,base),null);
});
test('guided fixture: login and 2FA accept only exact synthetic values',async()=>{
  const service=createGuidedService();await assert.rejects(service.handle('v1/sessions','POST',JSON.stringify({appleId:'someone@example.com',password:'never-send-this'})));
  const login=await service.handle('v1/sessions','POST',JSON.stringify({appleId:SYNTHETIC.appleId,password:SYNTHETIC.password}));const auth=`Bearer ${login.sessionToken}`,path=`v1/sessions/${login.sessionId}`;
  assert.equal((await service.handle(path,'GET','',auth)).state,'awaitingTwoFactor');await assert.rejects(service.handle(path+'/2fa','POST',JSON.stringify({action:'submitCode',code:'654321'}),auth));
  await service.handle(path+'/2fa','POST',JSON.stringify({action:'submitCode',code:SYNTHETIC.code}),auth);assert.equal((await service.handle(path,'GET','',auth)).state,'authenticated');
  await assert.rejects(service.handle(path,'GET','','Bearer unexpected'));
});
test('guided fixture: CSR-matching cert/profile passes material admission and actual WASM synthetic signing',async()=>{
  const dom=new JSDOM();globalThis.DOMParser=dom.window.DOMParser;
  try{
    const keys=forge.pki.rsa.generateKeyPair(2048),csr=forge.pki.createCertificationRequest();csr.publicKey=keys.publicKey;csr.setSubject([{name:'commonName',value:'Tetherless browser signing'}]);csr.sign(keys.privateKey,forge.md.sha256.create());
    const {response,profile}=syntheticProvision(forge.pki.certificationRequestToPem(csr));const cert=forge.pki.certificateFromAsn1(forge.asn1.fromDer(forge.util.decode64(response.certificateDerBase64)));assert(cert.publicKey.n.equals(keys.publicKey.n));
    const password='synthetic-only',p12=Buffer.from(forge.asn1.toDer(forge.pkcs12.toPkcs12Asn1(keys.privateKey,[cert],password,{algorithm:'3des'})).getBytes(),'binary');
    const ipa=new File([await makeIpa()],'Fixture.ipa'),material={p12,profile,password};
    const checked=await inspectInputs({ipa,p12:new File([p12],'synthetic.p12'),profiles:[new File([profile],'synthetic.mobileprovision')],password,udid:SYNTHETIC.udid});assert.equal(checked.team,SYNTHETIC.teamId);
    const signed=await makeSignedFixture(ipa,material);assert(signed.length>0);assert.notDeepEqual(Buffer.from(signed),Buffer.from(await ipa.arrayBuffer()));
  }finally{dom.window.close();}
});
