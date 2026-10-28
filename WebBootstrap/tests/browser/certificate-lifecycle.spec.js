// Production-built UI + real loopback HTTP and WebCrypto. Every identity/account/
// certificate/profile is synthetic; no Apple service or real credential is used.
import { test, expect } from '@playwright/test';
import http from 'node:http';
import { readFileSync } from 'node:fs';
import { resolve, extname } from 'node:path';
import forge from 'node-forge';
import { makeIpa } from '../fixtures.mjs';
import { importRecovery, importP12 } from '../../src/certificate-recovery.js';
const password='synthetic-backup-password', team='TESTTEAM01', udid='00000000-0000000000000000';
let server;
test.afterEach(async()=>{if(server){const old=server;server=undefined;old.closeAllConnections();await new Promise(r=>old.close(r));}});
async function fixture(context,{holdCertificate=false,ttl=600}={}) {
  const dist=resolve('dist'), calls=[],blocked=[],certificates=new Map();let sessions=0,profiles=0,issued=0,releaseCertificate;
  const held=new Promise(r=>releaseCertificate=r),issuer=forge.pki.rsa.generateKeyPair(2048);
  const issuerCert=forge.pki.createCertificate();issuerCert.publicKey=issuer.publicKey;issuerCert.serialNumber='01';issuerCert.validity.notBefore=new Date('2020-01-01');issuerCert.validity.notAfter=new Date('2035-01-01');issuerCert.setSubject([{name:'commonName',value:'SYNTHETIC NOT APPLE'}]);issuerCert.setIssuer(issuerCert.subject.attributes);issuerCert.sign(issuer.privateKey,forge.md.sha256.create());
  const profileFor=(cert,request)=>{
    const der=forge.util.encode64(forge.asn1.toDer(forge.pki.certificateToAsn1(cert)).getBytes());
    const xml=`<?xml version="1.0"?><plist version="1.0"><dict><key>Name</key><string>SYNTHETIC NOT APPLE</string><key>UUID</key><string>00000000-1111-2222-3333-444444444444</string><key>ExpirationDate</key><date>2035-01-01T00:00:00Z</date><key>TeamIdentifier</key><array><string>${team}</string></array><key>ApplicationIdentifierPrefix</key><array><string>${team}</string></array><key>ProvisionedDevices</key><array><string>${udid}</string></array><key>LocalProvision</key><true/><key>DeveloperCertificates</key><array><data>${der}</data></array><key>Entitlements</key><dict><key>application-identifier</key><string>${team}.${request.apps[0].bundleId}</string><key>com.apple.developer.team-identifier</key><string>${team}</string><key>get-task-allow</key><true/></dict></dict></plist>`;
    const cms=forge.pkcs7.createSignedData();cms.content=forge.util.createBuffer(xml,'utf8');cms.addCertificate(issuerCert);cms.addSigner({key:issuer.privateKey,certificate:issuerCert,digestAlgorithm:forge.pki.oids.sha256});cms.sign();return forge.util.encode64(forge.asn1.toDer(cms.toAsn1()).getBytes());
  };
  server=http.createServer(async(req,res)=>{
    const path=req.url;res.setHeader('Cache-Control','no-store');const json=(status,body)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(body));};
    if(path==='/health')return json(200,{protocol:1,certificateLifecycle: 1, appleAuthAvailable:true,profileServiceAvailable:false});
    if(path==='/config.json')return json(200,{accountServiceUrl:null,officialRelease:null});
    if(path.startsWith('/v1/')){
      let raw='';for await(const piece of req){raw+=piece;if(raw.length>100000)return json(413,{error:'invalidRequest'});}let body;try{body=raw?JSON.parse(raw):undefined;}catch{return json(400,{error:'invalidRequest'});}
      calls.push({path,method:req.method,body});
      if(path==='/v1/sessions'&&req.method==='POST')return json(202,{sessionId:`synthetic-${++sessions}`,sessionToken:'synthetic-token',expiresInSeconds:ttl});
      if(req.method==='DELETE')return json(200,{ok:true});
      if(/\/v1\/sessions\/synthetic-\d+$/.test(path))return json(200,{state:'authenticated'});
      if(path.endsWith('/teams'))return json(200,{teams:[{id:team,name:'Synthetic NOT APPLE',type:'personal'}]});
      if(path.endsWith('/devices'))return json(200,{teamId:team,devices:[{udid,name:'Synthetic device',status:'active',selectable:true}]});
      if(path.endsWith('/certificates'))return json(200,{teamId:team,certificates:[{id:'SYNTHETIC-CERT',serial:'01',name:'Synthetic NOT APPLE',machineName:'Tetherless Web',expiresAt:'2035-01-01',status:'issued',confirmationToken:'synthetic-once'}]});
      if(path.endsWith('/revoke'))return json(200,{revoked:true,certificateId:'SYNTHETIC-CERT',teamId:team});
      if(path.endsWith('/certificate')||path.endsWith('/provision')){
        const csr=forge.pki.certificationRequestFromPem(body.csrPem),key=csr.publicKey.n.toString(16);let cert=certificates.get(key);
        if(!cert&&path.endsWith('/certificate')&&body.certificateIntent==='createOrReuse'){
          cert=forge.pki.createCertificate();cert.publicKey=csr.publicKey;cert.serialNumber='01';cert.validity.notBefore=new Date('2020-01-01');cert.validity.notAfter=new Date('2035-01-01');cert.setSubject([{name:'commonName',value:'Synthetic NOT APPLE'},{name:'organizationalUnitName',value:team}]);cert.setIssuer(issuerCert.subject.attributes);cert.sign(issuer.privateKey,forge.md.sha256.create());certificates.set(key,cert);issued++;
        }
        if(!cert)return json(409,{error:'certificateMissing'});
        if(path.endsWith('/certificate')&&holdCertificate)await held;
        const output={teamId:team,certificateDerBase64:forge.util.encode64(forge.asn1.toDer(forge.pki.certificateToAsn1(cert)).getBytes()),certificateSerial:'01',certificateReused:issued===0};
        if(path.endsWith('/provision')){profiles++;if(profiles===1)return json(409,{error:'profileMismatch'});output.profiles=[{bundleId:body.apps[0].bundleId,profileBase64:profileFor(cert,body)}];}
        return json(200,output);
      }
      return json(404,{error:'notFound'});
    }
    const file=resolve(dist,'.'+(path==='/'?'/index.html':path));if(!file.startsWith(dist+'/'))return json(404,{error:'notFound'});
    try{const data=readFileSync(file);res.writeHead(200,{'Content-Type':{'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.wasm':'application/wasm'}[extname(file)]||'application/octet-stream'});res.end(data);}catch{return json(404,{error:'notFound'});}
  });
  await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin=`http://127.0.0.1:${server.address().port}`;
  await context.route('**/*',route=>{const url=new URL(route.request().url());if(url.origin!==origin){blocked.push(url.href);return route.abort();}return route.continue();});
  await context.routeWebSocket('**/*',socket=>{blocked.push(socket.url());socket.close();});
  return {origin,calls,blocked,releaseCertificate,get issued(){return issued;}};
}
async function login(page,origin){
  await page.goto(origin);await page.locator('#ipa').setInputFiles({name:'Synthetic.ipa',mimeType:'application/octet-stream',buffer:Buffer.from(await makeIpa())});
  await page.locator('#apple-id').fill('synthetic@example.invalid');await page.locator('#apple-password').fill('synthetic-not-real');await page.locator('#login-consent').check();await page.locator('#login-button').click();
  await expect(page.locator('#existing-device')).toBeEnabled();await page.locator('#existing-device').selectOption(udid);
}
async function prepare(page){
  await page.locator('#identity-export-password').fill(password);const download=page.waitForEvent('download');await page.locator('#prepare-identity').click();const file=await download;
  expect(file.suggestedFilename()).toBe('tetherless-recovery.json');return file;
}
async function submit(page){await page.locator('#recovery-saved').check();await page.locator('#identity-create-consent').check();await page.locator('#provision-consent').check();await page.locator('#provision-button').click();}

test('certificate backup gate, early P12 on profile failure, same-key reload recovery and real WASM signing',async({context,page})=>{
  const f=await fixture(context);await login(page,f.origin);
  await page.locator('#provision-consent').check();await page.locator('#provision-button').click();await expect(page.locator('#account-status')).toContainText('恢復檔');expect(f.calls.filter(c=>c.path.endsWith('/certificate'))).toHaveLength(0);
  const backup=await prepare(page),backupPath=await backup.path();const recovered=await importRecovery(new Blob([readFileSync(backupPath)]),password);
  await page.locator('#provision-button').click();expect(f.calls.filter(c=>c.path.endsWith('/certificate'))).toHaveLength(0);
  await submit(page);await expect(page.locator('#account-status')).toContainText('profile');await expect(page.locator('#export-signing-p12')).toBeVisible();
  const p12Download=page.waitForEvent('download');await page.locator('#export-signing-p12').click();const p12File=await p12Download;
  const p12=await importP12(new Blob([readFileSync(await p12File.path())]),password,team);expect(p12.keys.publicKey.n.toString(16)).toBe(recovered.keys.publicKey.n.toString(16));expect(f.issued).toBe(1);
  await page.reload();await login(page,f.origin);await page.locator('#identity-source').selectOption('recovery');await page.locator('#identity-file').setInputFiles(backupPath);await page.locator('#identity-import-password').fill(password);await prepare(page);
  await expect(page.locator('#identity-create-consent')).toBeDisabled();await page.locator('#recovery-saved').check();await page.locator('#provision-consent').check();await page.locator('#provision-button').click();
  await expect(page.locator('#result')).toBeVisible({timeout:60000});await expect(page.locator('#export-signing-p12')).toBeVisible();await expect(page.locator('#export-profiles')).toBeVisible();
  const certCalls=f.calls.filter(c=>c.path.endsWith('/certificate'));expect(certCalls).toHaveLength(2);expect(certCalls[1].body.csrPem).toBe(certCalls[0].body.csrPem);expect(certCalls[1].body.certificateIntent).toBe('reuseOnly');expect(f.issued).toBe(1);
  for(const call of f.calls.filter(c=>c.path.endsWith('/certificate')||c.path.endsWith('/provision'))){expect(JSON.stringify(call.body)).not.toContain('PRIVATE KEY');expect(JSON.stringify(call.body)).not.toContain(password);}
  expect(await page.evaluate(()=>[localStorage.length,sessionStorage.length])).toEqual([0,0]);expect(f.blocked).toEqual([]);
});

test('cancellation after dispatch fences late certificate response without starting profiles',async({context,page})=>{
  const f=await fixture(context,{holdCertificate:true});await login(page,f.origin);await prepare(page);await submit(page);await expect.poll(()=>f.calls.filter(c=>c.path.endsWith('/certificate')).length).toBe(1);
  await page.locator('#logout').click();f.releaseCertificate();await expect(page.locator('#account-status')).toContainText('取消');await expect(page.locator('#export-signing-p12')).toBeHidden();expect(f.calls.filter(c=>c.path.endsWith('/provision'))).toHaveLength(0);expect(f.issued).toBe(1);expect(f.blocked).toEqual([]);
});

test('revocation names exact certificate, needs unchecked per-action consent, and never creates replacement',async({context,page})=>{
  const f=await fixture(context);await login(page,f.origin);await page.locator('#certificate-management summary').click();await page.locator('#list-certificates').click();await expect(page.locator('#certificate-choice')).toBeEnabled();
  await page.locator('#certificate-choice').selectOption('SYNTHETIC-CERT');await expect(page.locator('#certificate-description')).toContainText('serial 01');await expect(page.locator('#revoke-certificate')).toBeDisabled();await expect(page.locator('#revoke-consent')).not.toBeChecked();
  await page.locator('#revoke-consent').check();await page.locator('#revoke-certificate').click();await expect(page.locator('#account-status')).toContainText('沒有自動發新憑證');
  const calls=f.calls.filter(c=>c.path.endsWith('/revoke'));expect(calls).toHaveLength(1);expect(calls[0].body).toEqual({certificateId:'SYNTHETIC-CERT',certificateSerial:'01',confirmationToken:'synthetic-once',consent:'revoke-selected-development-certificate'});expect(f.issued).toBe(0);expect(f.blocked).toEqual([]);
});

test('same-session explicit profile retry and duplicate clicks keep exactly one issued certificate',async({context,page})=>{
  const f=await fixture(context);await login(page,f.origin);await prepare(page);await submit(page);await expect(page.locator('#account-status')).toContainText('profile');
  await page.locator('#provision-button').evaluate(button=>{button.click();button.click();});await expect(page.locator('#result')).toBeVisible({timeout:60000});
  const certs=f.calls.filter(c=>c.path.endsWith('/certificate')),profiles=f.calls.filter(c=>c.path.endsWith('/provision'));
  expect(certs).toHaveLength(2);expect(profiles).toHaveLength(2);expect(certs[1].body.csrPem).toBe(certs[0].body.csrPem);expect(f.issued).toBe(1);expect(f.blocked).toEqual([]);
});

test('session expiry clears memory but two new tabs can import the same saved identity without issuing again',async({context,page})=>{
  const f=await fixture(context,{ttl:30});await page.clock.install();await login(page,f.origin);const backup=await prepare(page),backupPath=await backup.path();await submit(page);await expect(page.locator('#account-status')).toContainText('profile');
  await page.clock.fastForward(31000);await expect(page.locator('#account-status')).toContainText('到期');await expect(page.locator('#identity-export-password')).toHaveValue('');await expect(page.locator('#export-signing-p12')).toBeHidden();
  const second=await context.newPage(),third=await context.newPage();
  for(const tab of [second,third]){await login(tab,f.origin);await tab.locator('#identity-source').selectOption('recovery');await tab.locator('#identity-file').setInputFiles(backupPath);await tab.locator('#identity-import-password').fill(password);await prepare(tab);await tab.locator('#recovery-saved').check();await tab.locator('#provision-consent').check();}
  await Promise.all([second.locator('#provision-button').click(),third.locator('#provision-button').click()]);
  for(const tab of [second,third])await expect(tab.locator('#result')).toBeVisible({timeout:60000});
  const certs=f.calls.filter(c=>c.path.endsWith('/certificate'));expect(certs).toHaveLength(3);expect(new Set(certs.map(c=>c.body.csrPem)).size).toBe(1);expect(certs.slice(1).every(c=>c.body.certificateIntent==='reuseOnly')).toBe(true);expect(f.issued).toBe(1);expect(f.blocked).toEqual([]);
});
