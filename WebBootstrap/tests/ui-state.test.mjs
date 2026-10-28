// DOM emulation + mocked worker/service. These are not browser or Apple acceptance tests.
import test from 'node:test'; import assert from 'node:assert/strict'; import { readFileSync } from 'node:fs'; import { JSDOM } from 'jsdom';
import forge from 'node-forge';
import { makeIpa, makeMaterial, makeSignedFixture } from './fixtures.mjs';
const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const tick = () => new Promise((r) => setTimeout(r, 10));
async function until(fn) { for (let i=0;i<200;i++) { if(fn()) return; await tick(); } throw new Error('Condition did not become true'); }
async function environment({ service = false, profileService = service, config = { accountServiceUrl: null, officialRelease: null }, deviceRoute = 'new', pageUrl = 'http://127.0.0.1:8787/', storedEnrollment, fetcher } = {}) {
  const dom = new JSDOM(html, { url: pageUrl, pretendToBeVisual: true });
  for (const key of ['document', 'location', 'DOMParser', 'window', 'sessionStorage']) globalThis[key] = key === 'window' ? dom.window : dom.window[key];
  if (storedEnrollment !== undefined) dom.window.sessionStorage.setItem('tetherless-device-enrollment', storedEnrollment);
  const calls = [];
  const fakeFetch = async (url, options = {}) => { calls.push({ url: String(url), options }); if (fetcher) { const result = await fetcher(String(url), options); if (result) return result; } if (String(url).endsWith('/health')) return Response.json({ protocol: 1, appleAuthAvailable: service, profileServiceAvailable: profileService }); if (String(url).endsWith('/config.json')) return Response.json(config); return Response.json({ error:'unexpected' }, { status: 404 }); };
  globalThis.fetch = async (url, options) => { const response = await fakeFetch(url, options); if (!response.url) Object.defineProperty(response, 'url', { value: String(url) }); return response; };
  class MockWorker { static all=[]; constructor() { MockWorker.all.push(this); } postMessage(data) { this.data=data; } terminate() { this.terminated=true; } succeed() { this.onmessage?.({data:{phase:'done',bytes:fixture.signed}}); } }
  globalThis.Worker = MockWorker;
  await import(`../src/main.js?test=${Math.random()}`); await tick();
  if (service && deviceRoute === 'new') { dom.window.document.getElementById('device-route').value='new'; dom.window.document.getElementById('device-route').dispatchEvent(new dom.window.Event('change')); }
  const $ = (id) => dom.window.document.getElementById(id);
  const setFiles = (id, values) => Object.defineProperty($(id), 'files', { configurable:true, value:values });
  return { dom, $, calls, MockWorker, setFiles, dispose() { $('clear').click(); dom.window.close(); } };
}
let fixture;
test.before(async()=>{const m=makeMaterial();fixture={ipa:new File([await makeIpa()],'Fixture.ipa'),p12:new File([m.p12],'test.p12'),profile:new File([m.profile],'test.mobileprovision'),password:m.password, material:m};fixture.signed=await makeSignedFixture(fixture.ipa,m);});
function fill(e) { e.$('files-mode').click(); e.setFiles('ipa',[fixture.ipa]);e.setFiles('p12',[fixture.p12]);e.setFiles('profiles',[fixture.profile]);e.$('password').value=fixture.password;e.$('rights').checked=true; }
test('DOM mock: static page never enables Apple credential entry', async()=>{const e=await environment();try{e.$('account-mode').click();assert(e.$('account-form').hidden);assert(!e.$('account-panel').hidden);assert.equal(e.dom.window.localStorage.length,0);}finally{e.dispose();}});
test('DOM mock: rights check precedes worker creation', async()=>{const e=await environment();try{e.$('sign').click();assert(e.$('status').textContent.includes('確認你有權'));assert.equal(e.MockWorker.all.length,0);}finally{e.dispose();}});
test('DOM mock: cancel terminates worker and stale completion cannot resurrect output', async()=>{const e=await environment();try{fill(e);e.$('sign').click();await until(()=>e.MockWorker.all.length===1);const worker=e.MockWorker.all[0];e.$('cancel').click();assert(worker.terminated);worker.succeed();await tick();assert(e.$('result').hidden);assert(!e.$('sign').disabled);assert(e.$('status').textContent.includes('已取消'));}finally{e.dispose();}});
test('DOM mock: repeated click starts only one worker and clear removes output', async()=>{const e=await environment();try{fill(e);e.$('sign').click();e.$('sign').click();await until(()=>e.MockWorker.all.length===1);e.MockWorker.all[0].succeed();await until(()=>!e.$('result').hidden);assert.equal(e.MockWorker.all.length,1);assert(e.$('status').textContent.includes('尚未驗證'));e.$('clear').click();assert(e.$('result').hidden);assert.equal(e.$('password').value,'');}finally{e.dispose();}});
test('DOM mock: same-origin service health exposes explicit consent, and cancellation deletes a late session', async()=>{let release;const start=new Promise(r=>release=r);const e=await environment({service:true,fetcher:async(url,opts)=>{if(url.endsWith('/v1/sessions')&&opts.method==='POST'){await start;return Response.json({sessionId:'synthetic-id',sessionToken:'synthetic-token',state:'starting',expiresInSeconds:600},{status:202});}if(opts.method==='DELETE')return Response.json({ok:true});}});try{assert(!e.$('prelogin-device').hidden);e.$('app-source').value='custom'; e.$('app-source').dispatchEvent(new e.dom.window.Event('change')); e.setFiles('ipa',[fixture.ipa]); e.$('account-udid').value='00000000-0000000000000000'; e.$('continue-device').click(); e.$('apple-id').value='test@example.invalid';e.$('apple-password').value='synthetic-not-a-secret';e.$('login-consent').checked=true;e.$('account-form').dispatchEvent(new e.dom.window.Event('submit',{cancelable:true}));await until(()=>e.calls.some(c=>c.url.endsWith('/v1/sessions')&&c.options.method==='POST'));assert.equal(e.$('apple-password').value,'');e.$('clear').click();release();await until(()=>e.calls.some(c=>c.options.method==='DELETE'));assert(e.$('provision-form').hidden);assert(e.calls.every(c=>!c.url.includes('synthetic-token')));assert(e.calls.filter(c=>c.options.method==='DELETE').every(c=>c.options.redirect==='error' && c.options.credentials==='same-origin'));}finally{release();e.dispose();}});
test('DOM mock: empty 202 two-factor response succeeds but cannot overwrite later cancellation', async()=>{let release;const pending=new Promise(r=>release=r);const e=await environment({service:true,fetcher:async(url,opts)=>{if(url.endsWith('/v1/sessions')&&opts.method==='POST')return Response.json({sessionId:'synthetic-id',sessionToken:'synthetic-token',state:'starting',expiresInSeconds:600},{status:202});if(url.endsWith('/v1/sessions/synthetic-id')&&(!opts.method||opts.method==='GET'))return Response.json({state:'awaitingTwoFactor',challenge:{retry:false}});if(url.endsWith('/2fa')){await pending;return new Response(null,{status:202});}if(opts.method==='DELETE')return new Response(null,{status:204});}});try{e.$('app-source').value='custom'; e.$('app-source').dispatchEvent(new e.dom.window.Event('change')); e.setFiles('ipa',[fixture.ipa]); e.$('account-udid').value='00000000-0000000000000000'; e.$('continue-device').click(); e.$('apple-id').value='test@example.invalid';e.$('apple-password').value='synthetic-not-a-secret';e.$('login-consent').checked=true;e.$('account-form').dispatchEvent(new e.dom.window.Event('submit',{cancelable:true}));await until(()=>!e.$('two-factor').hidden);e.$('verification-code').value='123456';e.$('two-factor').dispatchEvent(new e.dom.window.Event('submit',{cancelable:true}));await tick();e.$('clear').click();release();await tick();assert(e.$('account-status').textContent.includes('已取消'));assert(!e.$('account-status').textContent.includes('等待 Apple'));}finally{release();e.dispose();}});
test('DOM mock: enrollment keeps only ID/expiry, survives pagehide, and resumes after persisted pageshow', async()=>{let received=false;const id='11111111-2222-3333-4444-555555555555';const e=await environment({service:true,fetcher:async(url,opts)=>{if(url.endsWith('/v1/device-enrollments')&&opts.method==='POST')return Response.json({enrollmentId:id,profileUrl:`http://127.0.0.1:8787/v1/device-enrollments/${id}/profile/synthetic-capability`,expiresInSeconds:600},{status:201});if(url.includes('/v1/device-enrollments/')&&opts.method!=='DELETE')return Response.json({state:received?'received':'awaitingDevice',device:received?{udid:'00000000-0000000000000000'}:null,verification:'untrustedDeviceMetadata'});if(opts.method==='DELETE')return new Response(null,{status:204});}});try{e.$('device-consent').checked=true;e.$('collect-device').click();await until(()=>!e.$('device-profile-link').hidden);const stored=JSON.parse(e.dom.window.sessionStorage.getItem('tetherless-device-enrollment'));assert.deepEqual(Object.keys(stored).sort(),['expiresAt','id']);e.dom.window.dispatchEvent(new e.dom.window.PageTransitionEvent('pagehide',{persisted:true}));assert(e.dom.window.sessionStorage.getItem('tetherless-device-enrollment'));assert(!e.calls.some(c=>c.url.includes('/device-enrollments/')&&c.options.method==='DELETE'));received=true;e.dom.window.dispatchEvent(new e.dom.window.PageTransitionEvent('pageshow',{persisted:true}));await until(()=>e.$('account-udid').value==='00000000-0000000000000000');assert.equal(e.dom.window.sessionStorage.length,1);assert(e.calls.filter(c=>c.url.includes('/device-enrollments/')).every(c=>c.options.credentials==='same-origin' && c.options.redirect==='error'));}finally{e.dispose();}});
function submit(e, id) { e.$(id).dispatchEvent(new e.dom.window.Event('submit', { cancelable:true })); }
function loginInputs(e) { e.$('app-source').value='custom'; e.$('app-source').dispatchEvent(new e.dom.window.Event('change')); e.setFiles('ipa',[fixture.ipa]); e.$('account-udid').value='00000000-0000000000000000'; e.$('continue-device').click(); e.$('apple-id').value='test@example.invalid'; e.$('apple-password').value='synthetic-not-a-secret'; e.$('login-consent').checked=true; }
function sessionFetcher(extra = () => {}, teams = [{id:'TESTTEAM01',name:'Test Team',type:'personal'}]) { return async (url, opts) => {
  const result = await extra(url, opts); if (result) return result;
  if (url.endsWith('/v1/sessions') && opts.method === 'POST') return Response.json({sessionId:'synthetic-id',sessionToken:'synthetic-token',expiresInSeconds:600});
  if (url.endsWith('/v1/sessions/synthetic-id') && opts.method !== 'DELETE') return Response.json({state:'authenticated'});
  if (url.endsWith('/teams')) return Response.json({teams});
  if (opts.method === 'DELETE') return new Response(null,{status:204});
}; }
test('DOM mock: progressive default hides technical fields and unconfigured login is guarded even if submitted directly', async()=>{
  const e=await environment();try{
    assert(e.$('manual-panel').hidden); assert(e.$('signing-panel').hidden); assert(e.$('install-panel').hidden); assert(!e.$('app-selection').hidden); assert.equal(e.$('app-source').value,'custom'); assert(e.$('login-button').disabled);
    assert(e.$('release-status').textContent.includes('尚未綁定')); e.$('login-consent').checked=true; submit(e,'account-form'); await tick();
    assert(!e.calls.some(c=>c.options.method==='POST'));
  }finally{e.dispose();}
});
test('DOM mock: external configured service is a named outbound link, never local credential collection', async()=>{
  const e=await environment({config:{accountServiceUrl:'https://service.example/signing/',officialRelease:null}});try{
    assert(e.$('account-form').hidden); assert.equal(e.$('service-link').href,'https://service.example/signing/'); assert(e.$('account-unavailable').textContent.includes('https://service.example')); assert(!e.calls.some(c=>c.url.startsWith('https://service.example')));
  }finally{e.dispose();}
});
test('DOM mock: available service still requires consent and an explicitly selected app before any session',async()=>{
  const e=await environment({service:true});try{
    submit(e,'account-form'); await tick(); assert(!e.calls.some(c=>c.options.method==='POST'));
    e.$('account-udid').value='00000000-0000000000000000'; e.$('continue-device').click(); e.$('login-consent').checked=true; submit(e,'account-form'); await tick(); assert(e.$('login-button').disabled);
    assert(e.$('ipa-prerequisite-status').textContent.includes('尚未選擇')); assert(!e.$('account-app-prerequisite').hidden); assert(!e.calls.some(c=>c.options.method==='POST'));
  }finally{e.dispose();}
});
test('DOM mock: single Team is automatic, pre-login device identification is retained, and missing UDID opens entry',async()=>{
  const e=await environment({service:true,fetcher:sessionFetcher()});try{
    assert(!e.$('prelogin-device').hidden); loginInputs(e); submit(e,'account-form'); await until(()=>!e.$('provision-form').hidden);
    assert(e.$('account-form').hidden); assert(e.$('team-choice').hidden); assert(!e.$('team-summary').hidden); assert(e.$('device-collection').hidden); assert(!e.$('guided-preparation').hidden);
    submit(e,'provision-form'); assert(!e.calls.some(c=>c.url.endsWith('/provision')));
    e.$('account-udid').value=''; e.$('provision-consent').checked=true; submit(e,'provision-form'); assert(e.$('device-details').open); assert(e.$('account-status').textContent.includes('有效'));
  }finally{e.dispose();}
});
test('DOM mock: multiple Teams remain a visible choice and unavailable profile service exposes manual device entry',async()=>{
  const e=await environment({service:true,profileService:false,fetcher:sessionFetcher(undefined,[{id:'TEAM1',name:'One',type:'personal'},{id:'TEAM2',name:'Two',type:'organization'}])});try{
    loginInputs(e); submit(e,'account-form'); await until(()=>!e.$('provision-form').hidden); assert(!e.$('team-choice').hidden); assert(e.$('device-collection').hidden); assert(e.$('device-details').open);
  }finally{e.dispose();}
});
test('DOM mock: manual mode and return preserve chosen files but invalidate output and rights',async()=>{
  const e=await environment();try{
    fill(e); e.$('sign').click(); await until(()=>e.MockWorker.all.length===1); e.MockWorker.all[0].succeed(); await until(()=>!e.$('result').hidden);
    e.$('account-mode').click(); assert(e.$('result').hidden); assert(e.$('install-panel').hidden); assert(!e.$('rights').checked); assert.equal(e.$('ipa').files[0],fixture.ipa); assert.equal(e.$('p12').files[0],fixture.p12);
    e.$('files-mode').click(); assert.equal(e.$('profiles').files[0],fixture.profile); assert(!e.$('manual-panel').hidden);
  }finally{e.dispose();}
});
test('DOM mock: provisioning retry keeps original CSR, IPA and selection; return cancels and clears it',async()=>{
  let bodies=[];
  const e=await environment({service:true,fetcher:sessionFetcher((url,opts)=>{if(url.endsWith('/provision')){bodies.push(opts.body); return Response.json({error:'provisioningUncertain'},{status:503});}})});try{
    loginInputs(e); submit(e,'account-form'); await until(()=>!e.$('provision-form').hidden); e.$('account-udid').value='00000000-0000000000000000'; e.$('provision-consent').checked=true; submit(e,'provision-form'); await until(()=>bodies.length===1 && !e.$('provision-button').disabled);
    assert(e.$('ipa').disabled); assert(e.$('app-source').disabled); assert(e.$('team').disabled); assert(e.$('provision-button').textContent.includes('同一私鑰'));
    submit(e,'provision-form'); await until(()=>bodies.length===2 && !e.$('provision-button').disabled); assert.equal(bodies[0],bodies[1]);
    e.$('logout').click(); assert(e.$('provision-form').hidden); assert(!e.$('prelogin-device').hidden); assert.equal(e.$('apple-id').value,''); assert(!e.$('provision-consent').checked); assert(!e.$('ipa').disabled);
  }finally{e.dispose();}
});
test('DOM mock: approved provisioning automatically starts local signing without another sign click',async()=>{
  const original=forge.pki.rsa.generateKeyPair;
  const p12=forge.pkcs12.pkcs12FromAsn1(forge.asn1.fromDer(fixture.material.p12.toString('binary')),false,fixture.password);
  const privateKey=p12.getBags({bagType:forge.pki.oids.pkcs8ShroudedKeyBag})[forge.pki.oids.pkcs8ShroudedKeyBag][0].key;
  const cert=forge.pki.certificateFromPem(fixture.material.certPem);
  forge.pki.rsa.generateKeyPair=(_opts,callback)=>callback(null,{privateKey,publicKey:cert.publicKey});
  const e=await environment({service:true,fetcher:sessionFetcher((url)=>{if(url.endsWith('/provision'))return Response.json({certificateDerBase64:forge.util.encode64(forge.asn1.toDer(forge.pki.certificateToAsn1(cert)).getBytes()),profiles:[{profileBase64:fixture.material.profile.toString('base64')}]});})});try{
    loginInputs(e); submit(e,'account-form'); await until(()=>!e.$('provision-form').hidden); e.$('account-udid').value='00000000-0000000000000000'; e.$('provision-consent').checked=true; submit(e,'provision-form'); await until(()=>e.MockWorker.all.length===1);
    assert(e.$('account-panel').hidden); assert(!e.$('signing-panel').hidden); assert(e.$('cancel').hidden===false);
    e.MockWorker.all[0].succeed(); await until(()=>!e.$('result').hidden); assert(!e.$('install-panel').hidden); assert(e.$('install-panel').textContent.includes('尚未實機驗證')); assert(e.$('install-link').hidden);
    e.$('clear').click(); assert(e.$('result').hidden); assert(e.$('install-panel').hidden);
  }finally{forge.pki.rsa.generateKeyPair=original;e.dispose();}
});
test('DOM mock: late cancelled inspection cannot erase the retry password',async()=>{
  let release; const pending=new Promise(r=>release=r); const delayed=new File([await fixture.ipa.arrayBuffer()],'Delayed.ipa');
  let reading=false; const original=delayed.slice.bind(delayed); delayed.slice=(...args)=>{const part=original(...args);part.arrayBuffer=async()=>{reading=true;await pending;throw new Error('Synthetic delayed inspection failure');};return part;};
  const e=await environment();try{
    fill(e); e.setFiles('ipa',[delayed]); e.$('sign').click(); await until(()=>reading); assert.equal(e.MockWorker.all.length,0); e.$('cancel').click(); e.$('password').value='new-retry-password'; release(); await tick(); await tick(); assert.equal(e.$('password').value,'new-retry-password'); assert(e.$('result').hidden);
  }finally{release();e.dispose();}
});
test('DOM mock: revoking consent during official acquisition cannot transmit credentials',async()=>{
  const raw=new Uint8Array(await fixture.ipa.arrayBuffer()); const sha256=Buffer.from(await crypto.subtle.digest('SHA-256',raw)).toString('hex');
  const officialRelease={repository:'oskuhsiu/Tetherless',tag:'v-test',assetId:'123',assetName:'Tetherless.ipa',assetUrl:'https://github.com/oskuhsiu/Tetherless/releases/download/v-test/Tetherless.ipa',size:raw.length,sha256,sourceCommit:'a'.repeat(40),buildRunId:'1',buildHeadSha:'b'.repeat(40),runAttempt:1};
  let release; const pending=new Promise(r=>release=r);
  const e=await environment({service:true,profileService:false,config:{officialRelease},fetcher:async(url)=>{if(url===officialRelease.assetUrl){await pending;return new Response(raw);}}});try{
    e.$('apple-id').value='synthetic@example.invalid';e.$('apple-password').value='synthetic';e.$('login-consent').checked=true;submit(e,'account-form');await until(()=>e.calls.some(c=>c.url===officialRelease.assetUrl));assert(e.$('account-form').inert);
    e.$('login-consent').checked=false;release();await until(()=>!e.$('login-button').disabled);assert(!e.calls.some(c=>c.options.method==='POST'));assert(e.$('account-status').textContent.includes('授權已取消'));
  }finally{release();e.dispose();}
});
test('DOM mock: profile round trip completes before credentials, resumes to login, and never posts a session early',async()=>{
  let received=false;const id='11111111-2222-3333-4444-555555555555';
  const e=await environment({service:true,fetcher:async(url,opts)=>{
    if(url.endsWith('/v1/device-enrollments')&&opts.method==='POST')return Response.json({enrollmentId:id,profileUrl:`http://127.0.0.1:8787/v1/device-enrollments/${id}/profile/synthetic`,expiresInSeconds:600});
    if(url.includes('/v1/device-enrollments/')&&opts.method!=='DELETE')return Response.json({state:received?'received':'awaitingDevice',device:received?{udid:'00000000-0000000000000000'}:null});
    if(opts.method==='DELETE')return new Response(null,{status:204});
  }});try{
    assert(!e.$('prelogin-device').hidden);assert(e.$('account-form').hidden);e.$('device-consent').checked=true;e.$('collect-device').click();await until(()=>!e.$('device-profile-link').hidden);
    e.dom.window.dispatchEvent(new e.dom.window.PageTransitionEvent('pagehide',{persisted:true}));received=true;e.dom.window.dispatchEvent(new e.dom.window.PageTransitionEvent('pageshow',{persisted:true}));await until(()=>!e.$('account-form').hidden);
    assert(e.$('prelogin-device').hidden);assert.equal(e.$('account-udid').value,'00000000-0000000000000000');assert(!e.calls.some(c=>c.url.endsWith('/v1/sessions')));assert.equal(e.dom.window.sessionStorage.length,1);
  }finally{e.dispose();}
});
test('DOM mock: protected same-origin service requests carry same-origin cookies and reject redirects',async()=>{
  const e=await environment({service:true,profileService:false,fetcher:sessionFetcher()});try{
    loginInputs(e);submit(e,'account-form');await until(()=>!e.$('provision-form').hidden);e.$('logout').click();await tick();
    const serviceCalls=e.calls.filter(c=>new URL(c.url).origin==='http://127.0.0.1:8787');assert(serviceCalls.length>=5);assert(serviceCalls.every(c=>c.options.credentials==='same-origin' && c.options.redirect===(new URL(c.url).pathname.endsWith('/health') ? 'manual' : 'error')));
    assert(serviceCalls.filter(c=>c.url.includes('/v1/sessions')).every(c=>!c.url.includes('synthetic-token')));
  }finally{e.dispose();}
});
test('DOM mock: exact inspected bundle IDs/App Group are shown before consent and pinned through provisioning',async()=>{
  let body;
  const e=await environment({service:true,profileService:false,fetcher:sessionFetcher((url,opts)=>{if(url.endsWith('/provision')){body=JSON.parse(opts.body);return Response.json({error:'provisioningUncertain'},{status:503});}})});try{
    loginInputs(e);e.setFiles('ipa',[new File([await makeIpa({bundleId:'org.tetherless.Tetherless'})],'Tetherless.ipa')]);submit(e,'account-form');await until(()=>!e.$('provision-form').hidden);
    assert(e.$('provision-plan').textContent.includes('App IDs：\norg.tetherless.Tetherless'));assert(e.$('provision-plan').textContent.includes('App Group：group.org.tetherless.Tetherless'));assert(e.$('ipa').disabled);assert(e.$('app-source').disabled);assert.equal(body,undefined);
    // Even a synthetic DOM replacement cannot change the reviewed session IPA.
    e.setFiles('ipa',[fixture.ipa]);e.$('provision-consent').checked=true;submit(e,'provision-form');await until(()=>body);
    assert.equal(body.apps[0].bundleId,'org.tetherless.Tetherless');assert.equal(body.appGroup.identifier,'group.org.tetherless.Tetherless');
  }finally{e.dispose();}
});
function existingLogin(e,ipa=fixture.ipa){e.$('app-source').value='custom';e.$('app-source').dispatchEvent(new e.dom.window.Event('change'));e.setFiles('ipa',[ipa]);e.$('apple-id').value='test@example.invalid';e.$('apple-password').value='synthetic-not-a-secret';e.$('login-consent').checked=true;submit(e,'account-form');}
const registeredDevice={udid:'00000000-0000000000000000',name:'Already registered iPhone',status:'active',selectable:true};
function chooseExisting(e,udid=registeredDevice.udid){e.$('existing-device').value=udid;e.$('existing-device').dispatchEvent(new e.dom.window.Event('change'));}
test('DOM mock: existing-device default logs in first, requires explicit active selection, and never registers a new device',async()=>{
  let provision;
  const e=await environment({service:true,deviceRoute:'existing',fetcher:sessionFetcher((url,opts)=>{
    if(url.endsWith('/teams/TESTTEAM01/devices'))return Response.json({teamId:'TESTTEAM01',devices:[registeredDevice,{...registeredDevice,udid:'11111111-1111111111111111',status:'disabled',selectable:false}]});
    if(url.endsWith('/provision')){provision=JSON.parse(opts.body);return Response.json({error:'deviceNotAvailable'},{status:409});}
  })});try{
    assert(!e.$('account-form').hidden);assert(e.$('prelogin-device').hidden);assert.equal(e.$('device-route').value,'existing');existingLogin(e);await until(()=>e.$('existing-device').options.length===2);
    assert.equal(e.$('existing-device').value,'');assert(e.$('provision-button').disabled);assert(e.$('provision-consent').disabled);submit(e,'provision-form');assert.equal(provision,undefined);
    chooseExisting(e);assert(e.$('existing-device-summary').textContent.includes('未驗證'));assert(!e.$('provision-consent').checked);e.$('provision-consent').checked=true;submit(e,'provision-form');await until(()=>provision);
    assert.equal(provision.device.existingOnly,true);assert.equal(provision.device.udid,registeredDevice.udid);assert.equal(provision.device.name,registeredDevice.name);assert.equal(provision.consent,'use-existing-device-register-app-ids-and-issue-certificate');
    await until(()=>!e.$('provision-button').disabled);assert(e.$('account-status').textContent.includes('不會改成新增裝置'));assert(!e.calls.some(c=>c.url.includes('/device-enrollments')));
  }finally{e.dispose();}
});
test('DOM mock: existing-device list errors and empty results stay blocked and permit a read-only retry',async()=>{
  let attempts=0;
  const e=await environment({service:true,deviceRoute:'existing',fetcher:sessionFetcher(url=>{if(url.endsWith('/devices')){attempts++;return attempts===1?Response.json({error:'appleRequestFailed'},{status:502}):Response.json({teamId:'TESTTEAM01',devices:[]});}})});try{
    existingLogin(e);await until(()=>e.$('existing-status').textContent.includes('無法讀取'));assert(e.$('provision-button').disabled);e.$('reload-devices').click();await until(()=>attempts===2&&!e.$('reload-devices').disabled);assert(e.$('existing-status').textContent.includes('沒有可用'));assert(e.$('provision-button').disabled);assert(!e.calls.some(c=>c.url.endsWith('/provision')));
  }finally{e.dispose();}
});
test('DOM mock: Team changes clear device selection/consent and ignore a late old-Team response',async()=>{
  let release;const pending=new Promise(r=>release=r);let held=false;
  const e=await environment({service:true,deviceRoute:'existing',fetcher:sessionFetcher(async url=>{
    if(url.endsWith('/teams/TESTTEAM01/devices')){held=true;await pending;return Response.json({teamId:'TESTTEAM01',devices:[registeredDevice]});}
    if(url.endsWith('/teams/TESTTEAM02/devices'))return Response.json({teamId:'TESTTEAM02',devices:[{...registeredDevice,udid:'22222222-2222222222222222',name:'Second Team phone'}]});
  },[{id:'TESTTEAM01',name:'One',type:'personal'},{id:'TESTTEAM02',name:'Two',type:'organization'}])});try{
    existingLogin(e);await until(()=>!e.$('provision-form').hidden);assert.equal(e.$('team').value,'');e.$('team').value='TESTTEAM01';e.$('team').dispatchEvent(new e.dom.window.Event('change'));await until(()=>held);
    e.$('provision-consent').checked=true;e.$('team').value='TESTTEAM02';e.$('team').dispatchEvent(new e.dom.window.Event('change'));assert(!e.$('provision-consent').checked);await until(()=>e.$('existing-device').options.length===2);release();await tick();
    assert(e.$('existing-device').textContent.includes('Second Team phone'));assert(!e.$('existing-device').textContent.includes('Already registered'));chooseExisting(e,'22222222-2222222222222222');e.$('provision-consent').checked=true;e.$('reload-devices').click();assert(!e.$('provision-consent').checked);assert.equal(e.$('existing-device').value,'');
  }finally{release();e.dispose();}
});
test('DOM mock: cancellation and oversized existing-device responses cannot restore selection or enable provisioning',async()=>{
  let release;const pending=new Promise(r=>release=r);let held=false;
  const e=await environment({service:true,deviceRoute:'existing',fetcher:sessionFetcher(async url=>{if(url.endsWith('/devices')){held=true;await pending;return new Response('x'.repeat(512*1024+1));}})});try{
    existingLogin(e);await until(()=>held);e.$('logout').click();release();await tick();assert(e.$('provision-form').hidden);assert.equal(e.$('existing-device').options.length,1);assert(!e.$('provision-consent').checked);
    existingLogin(e);await until(()=>e.$('existing-status').textContent.includes('超過允許大小'));assert(e.$('provision-button').disabled);
  }finally{release();e.dispose();}
});
test('DOM mock: existing-device App Group consent and uncertain retry preserve the exact original selection/request',async()=>{
  const bodies=[];
  const e=await environment({service:true,deviceRoute:'existing',fetcher:sessionFetcher((url,opts)=>{
    if(url.endsWith('/devices'))return Response.json({teamId:'TESTTEAM01',devices:[registeredDevice]});
    if(url.endsWith('/provision')){bodies.push(opts.body);return Response.json({error:'provisioningUncertain'},{status:503});}
  })});try{
    existingLogin(e,new File([await makeIpa({bundleId:'org.tetherless.Tetherless'})],'Tetherless.ipa'));await until(()=>!e.$('existing-device').disabled);chooseExisting(e);e.$('provision-consent').checked=true;submit(e,'provision-form');await until(()=>bodies.length===1&&!e.$('provision-button').disabled);
    assert(e.$('existing-device').disabled);assert(e.$('team').disabled);assert(e.$('reload-devices').disabled);const body=JSON.parse(bodies[0]);assert.equal(body.consent,'use-existing-device-register-app-ids-app-group-and-issue-certificate');assert.equal(body.device.existingOnly,true);assert.equal(body.appGroup.identifier,'group.org.tetherless.Tetherless');
    submit(e,'provision-form');await until(()=>bodies.length===2&&!e.$('provision-button').disabled);assert.equal(bodies[0],bodies[1]);
  }finally{e.dispose();}
});
test('DOM mock: switching from an empty new-device name to existing route passes native form validation; new route restores it',async()=>{
  let posted=false;
  const e=await environment({service:true,profileService:false,deviceRoute:'new',fetcher:sessionFetcher((url)=>{
    if(url.endsWith('/devices'))return Response.json({teamId:'TESTTEAM01',devices:[registeredDevice]});
    if(url.endsWith('/provision')){posted=true;return Response.json({error:'provisioningUncertain'},{status:503});}
  })});try{
    e.$('device-name').value='';e.$('device-route').value='existing';e.$('device-route').dispatchEvent(new e.dom.window.Event('change'));
    existingLogin(e);await until(()=>!e.$('existing-device').disabled);chooseExisting(e);e.$('provision-consent').checked=true;
    assert(e.$('device-name').disabled);assert(e.$('account-udid').disabled);assert(e.$('provision-form').checkValidity());e.$('provision-form').requestSubmit();await until(()=>posted);
    e.$('logout').click();e.$('device-route').value='new';e.$('device-route').dispatchEvent(new e.dom.window.Event('change'));loginInputs(e);submit(e,'account-form');await until(()=>!e.$('provision-form').hidden);e.$('provision-consent').checked=true;
    assert(!e.$('device-name').disabled);assert(!e.$('provision-form').checkValidity());e.$('device-name').value='My iPhone';assert(e.$('provision-form').checkValidity());
  }finally{e.dispose();}
});
test('DOM mock: a new document resumes only a valid previously-started enrollment without a new collection or Apple login',async()=>{
  const id='11111111-2222-3333-4444-555555555555';
  const e=await environment({service:true,deviceRoute:'existing',storedEnrollment:JSON.stringify({id,expiresAt:Date.now()+300000}),fetcher:async(url,opts)=>{
    if(url.includes(`/device-enrollments/${id}`)&&opts.method!=='DELETE')return Response.json({state:'received',device:{udid:registeredDevice.udid}});
    if(opts.method==='DELETE')return new Response(null,{status:204});
  }});try{
    await until(()=>e.$('account-udid').value===registeredDevice.udid);assert.equal(e.$('device-route').value,'new');assert(!e.$('account-form').hidden);assert.equal(e.dom.window.sessionStorage.length,1);
    assert(e.calls.some(c=>c.url.includes(`/device-enrollments/${id}`)&&!c.options.method));assert(!e.calls.some(c=>c.options.method==='POST'));
  }finally{e.dispose();}
});
test('DOM mock: a new document rejects malformed, expired, nonfinite or over-TTL enrollment state without restoring the new-device route',async()=>{
  const id='11111111-2222-3333-4444-555555555555';
  for(const stored of ['{bad',JSON.stringify({id,expiresAt:Date.now()-1}),JSON.stringify({id,expiresAt:null}),JSON.stringify({id,expiresAt:'later'}),JSON.stringify({id,expiresAt:Date.now()+900000}),JSON.stringify({id,expiresAt:Date.now()+300000,secret:'not-accepted'})]){
    const e=await environment({service:true,deviceRoute:'existing',storedEnrollment:stored});try{
      assert.equal(e.$('device-route').value,'existing');assert(!e.$('account-form').hidden);assert.equal(e.dom.window.sessionStorage.length,0);assert(!e.calls.some(c=>c.url.includes('/device-enrollments/')));
    }finally{e.dispose();}
  }
});
test('DOM mock: discovery cancellation fences a late health reply and recheck preserves a newer active session', async () => {
  let release, attempts = 0; const pending = new Promise(resolve => release = resolve);
  const e = await environment({ deviceRoute: 'existing', fetcher: sessionFetcher(async url => {
    if (url.endsWith('/health')) { if (++attempts === 1) await pending; return Response.json({ protocol: 1, appleAuthAvailable: true }); }
    if (url.endsWith('/devices')) return Response.json({ teamId: 'TESTTEAM01', devices: [registeredDevice] });
  }) });
  try {
    assert(e.$('account-form').hidden); e.$('cancel-service-check').click(); e.$('recheck-service').click(); e.$('recheck-service').click();
    await until(() => !e.$('account-form').hidden); assert.equal(attempts, 2); existingLogin(e); await until(() => !e.$('provision-form').hidden);
    release(); await tick(); e.$('recheck-service').click(); await tick();
    assert(!e.$('provision-form').hidden); assert(e.$('account-form').hidden); assert.equal(attempts, 2); assert(!e.calls.some(call => call.options.method === 'DELETE'));
  } finally { release(); e.dispose(); }
});
test('DOM mock: pagehide fences pending discovery; persisted pageshow rechecks after interrupted failure', async () => {
  let release, attempts = 0; const pending = new Promise(resolve => release = resolve);
  const e = await environment({ deviceRoute: 'existing', fetcher: async url => {
    if (url.endsWith('/health')) { if (++attempts === 1) await pending; return Response.json({ protocol: 1, appleAuthAvailable: true }); }
  } });
  try {
    e.dom.window.dispatchEvent(new e.dom.window.PageTransitionEvent('pagehide', { persisted: true })); release(); await tick(); assert(e.$('account-form').hidden);
    e.dom.window.dispatchEvent(new e.dom.window.PageTransitionEvent('pageshow', { persisted: true })); await until(() => !e.$('account-form').hidden); assert.equal(attempts, 2);
  } finally { release(); e.dispose(); }
});
test('DOM mock: manual route cancellation prevents stale discovery from reopening credentials', async () => {
  let release; const pending = new Promise(resolve => release = resolve);
  const e = await environment({ fetcher: async url => { if (url.endsWith('/health')) { await pending; return Response.json({ protocol: 1, appleAuthAvailable: true }); } } });
  try { e.$('files-mode').click(); release(); await tick(); assert(!e.$('manual-panel').hidden); assert(e.$('account-form').hidden); e.$('account-mode').click(); assert(e.$('account-form').hidden); assert(!e.$('recheck-service').hidden); }
  finally { release(); e.dispose(); }
});
test('DOM mock: selected invalid IPA remains locally rejected before any credentials are sent', async () => {
  const e = await environment({ service: true, deviceRoute: 'existing' });
  try {
    assert(!e.$('account-app-prerequisite').hidden); assert(e.$('login-button').disabled); assert.equal(e.$('app-source').value, 'custom');
    e.setFiles('ipa', [new File(['not zip'], 'Invalid.ipa')]); e.$('ipa').dispatchEvent(new e.dom.window.Event('change'));
    assert(!e.$('login-button').disabled); assert(e.$('ipa-prerequisite-status').textContent.includes('仍會檢查'));
    e.$('apple-id').value = 'test@example.invalid'; e.$('apple-password').value = 'synthetic'; e.$('login-consent').checked = true; submit(e, 'account-form');
    await until(() => !e.$('account-form').inert); assert(!e.calls.some(call => call.url.endsWith('/v1/sessions')));
    e.setFiles('ipa', []); e.$('ipa').dispatchEvent(new e.dom.window.Event('change')); assert(e.$('login-button').disabled);
  } finally { e.dispose(); }
});
test('DOM mock: UI initialization errors stay closed and are never mislabeled as connection failures', async () => {
  const e = await environment({ service: true, deviceRoute: 'existing' });
  try {
    const { setupAccount } = await import('../src/account.js');
    const account = setupAccount({ getIpa: () => undefined, onState: phase => { if (phase === 'login') throw new Error('Synthetic render failure'); } });
    await until(() => e.$('account-unavailable').textContent.includes('介面未能完成初始化'));
    assert(e.$('account-form').hidden); assert(!e.$('account-unavailable').textContent.includes('無法連線')); assert.equal(account.phase, 'unavailable'); assert(!e.$('recheck-service').disabled);
  } finally { e.dispose(); }
});

// No accept filter: iOS file providers may not map .ipa to application/zip.
// DOM selection does not prove the native iOS picker; real-device acceptance remains separate.
test('DOM mock: both IPA pickers allow unknown provider types and explain Actions vs Releases', async () => {
  const e = await environment();
  try {
    for (const id of ['ipa', 'release-file']) {
      assert.equal(e.$(id).type, 'file');
      assert.equal(e.$(id).hasAttribute('accept'), false);
    }
    assert(e.$('app-source').querySelector('[value="official"]').disabled);
    assert.equal(e.$('app-source').value, 'custom');
    assert(e.$('release-status').textContent.includes('不會自動列出 Actions'));
    assert(e.$('app-selection').textContent.includes('不是外層 ZIP'));
    assert(e.$('login-button').disabled);
  } finally { e.dispose(); }
});

test('DOM mock: legacy callback without lookup ID gives recovery guidance, never defaults to existing', async()=>{
  const e=await environment({service:true,deviceRoute:'existing',pageUrl:'http://127.0.0.1:8787/#device-collected'});
  try {
    assert.equal(e.dom.window.location.hash,'');
    assert.equal(e.$('device-route').value,'new');
    assert(e.$('account-form').hidden);
    assert(!e.$('prelogin-device').hidden);
    assert(e.$('device-status').textContent.includes('原瀏覽器'));
    assert(!e.calls.some(c=>c.url.includes('/device-enrollments/')));
  } finally {e.dispose();}
});
test('DOM mock: new callback tab reads with cookie authorization, keeps server TTL and never starts Apple requests', async()=>{
  const id='11111111-2222-3333-4444-555555555555';
  const e=await environment({service:true,deviceRoute:'existing',pageUrl:`http://127.0.0.1:8787/#device-collected=${id}`,fetcher:async(url,opts)=>{
    if(url.endsWith(`/device-enrollments/${id}`)&&!opts.method)return Response.json({state:'received',device:{udid:registeredDevice.udid},expiresInSeconds:123});
    if(opts.method==='DELETE')return new Response(null,{status:204});
  }});try{
    await until(()=>e.$('account-udid').value===registeredDevice.udid);
    assert.equal(e.dom.window.location.hash,'');assert.equal(e.$('device-route').value,'new');assert(!e.$('account-form').hidden);
    const stored=JSON.parse(e.dom.window.sessionStorage.getItem('tetherless-device-enrollment'));
    assert.deepEqual(Object.keys(stored).sort(),['expiresAt','id']);assert(stored.expiresAt<=Date.now()+123000);
    assert.equal(e.$('ipa').files.length,0);assert(e.$('login-button').disabled);assert(e.$('account-status').textContent.includes('重新選取'));
    assert(!e.calls.some(c=>c.options.method==='POST'||c.options.method==='DELETE'));
    const reads=e.calls.filter(c=>c.url.includes('/device-enrollments/'));assert.equal(reads.length,1);assert.equal(reads[0].options.credentials,'same-origin');
  }finally{e.dispose();}
});
test('DOM mock: callback cookie failure and expired result explain original browser rather than silently restarting',async()=>{
  const id='11111111-2222-3333-4444-555555555555';
  for(const status of [401,404,410]){
    const e=await environment({service:true,deviceRoute:'existing',pageUrl:`http://127.0.0.1:8787/#device-collected=${id}`,fetcher:async(url)=>url.includes('/device-enrollments/')?Response.json({error:'unavailable'},{status}):undefined});
    try{await until(()=>e.$('device-status').textContent.includes(String(status)));assert(e.$('device-status').textContent.includes('原瀏覽器'));assert.equal(e.$('device-route').value,'new');assert(e.$('account-form').hidden);assert(!e.calls.some(c=>c.options.method==='POST'));assert.equal(e.dom.window.sessionStorage.length,0);}finally{e.dispose();}
  }
});
test('DOM mock: invalid callback fragments and conflicting pending ID never read or cancel another enrollment',async()=>{
  const id='11111111-2222-3333-4444-555555555555';
  for(const hash of ['#device-collected=not-a-uuid',`#device-collected=${id}&token=malicious`,`#device-collected=${id}`]){
    const conflict=hash===`#device-collected=${id}`;
    const stored=conflict?JSON.stringify({id:'99999999-2222-3333-4444-555555555555',expiresAt:Date.now()+120000}):undefined;
    const e=await environment({service:true,deviceRoute:'existing',pageUrl:`http://127.0.0.1:8787/${hash}`,storedEnrollment:stored});
    try{assert.equal(e.dom.window.location.hash,'');assert(!e.calls.some(c=>c.url.includes('/device-enrollments/')));assert(e.$('account-form').hidden);assert(e.$('device-status').textContent.includes('原瀏覽器'));if(conflict)assert.equal(e.dom.window.sessionStorage.getItem('tetherless-device-enrollment'),stored);}finally{e.dispose();}
  }
});

test('DOM mock: unknown 2FA blocks code and direct submit until a method is requested', async () => {
  let unknown = true; const actions = [];
  const e = await environment({ service: true, fetcher: sessionFetcher((url, opts) => {
    if (url.endsWith('/v1/sessions/synthetic-id') && opts.method !== 'DELETE') return Response.json({ state: 'awaitingTwoFactor', challenge: { unknown, numbers: [], retry: false } });
    if (url.endsWith('/2fa')) { const body = JSON.parse(opts.body); actions.push(body.action); if (body.action === 'sendToDevices') unknown = false; return new Response(null, { status: 202 }); }
  }) });
  try {
    loginInputs(e); submit(e, 'account-form'); await until(() => !e.$('two-factor').hidden);
    assert(e.$('verification-code').disabled); assert(e.$('verify-button').disabled); assert(e.$('account-status').textContent.includes('尚未確定驗證方式'));
    assert(e.$('two-factor').querySelector('details').open); assert.equal(e.$('resend-code').closest('details').open, true); assert(!e.$('resend-code').hidden);
    e.$('verification-code').value = '123456'; submit(e, 'two-factor'); await tick(); assert.deepEqual(actions, []);
    e.$('resend-code').click(); await until(() => !e.$('verification-code').disabled);
    assert.deepEqual(actions, ['sendToDevices']); e.$('verification-code').value = '123456'; submit(e, 'two-factor'); await until(() => actions.length === 2);
    assert.deepEqual(actions, ['sendToDevices', 'submitCode']);
    e.$('logout').click(); assert(!e.$('verification-code').disabled); assert.equal(e.$('verification-code').value, ''); assert(e.$('two-factor').hidden); assert.equal(e.$('two-factor').querySelector('details').open, false);
  } finally { e.dispose(); }
});
test('DOM mock: safe diagnostic is visible on failed login and cancellation clears it', async () => {
  const e = await environment({ service: true, fetcher: sessionFetcher((url, opts) => {
    if (url.endsWith('/v1/sessions/synthetic-id') && opts.method !== 'DELETE') return Response.json({ state: 'failed', error: 'appleAuthenticationFailed', diagnostic: { stage: 'appleLogin', kind: 'appleRejected', upstream: 'apple', appleCode: -21669, httpStatus: 403, message: 'PRIVATE_RESPONSE', token: 'PRIVATE_TOKEN' } });
  }) });
  try {
    loginInputs(e); submit(e, 'account-form'); await until(() => e.$('account-status').textContent.includes('診斷：'));
    const text = e.$('account-status').textContent; assert(text.includes('來源：Apple 服務／Apple 代碼 -21669／HTTP 403')); assert(text.includes('不能單獨判定')); assert(!text.includes('PRIVATE'));
    e.$('logout').click(); assert(!e.$('account-status').textContent.includes('診斷：')); assert.equal(e.$('apple-id').value, '');
  } finally { e.dispose(); }
});

test('DOM mock: provider disclosure is explicit before unchecked login consent; it sends no credentials automatically', async () => {
  const e = await environment({ service: true, deviceRoute: 'existing' });
  try {
    const privacy = e.$('account-form').querySelector('.privacy').textContent;
    for (const text of ['mac-ani.jkcoxson.com', '隨機 Anisette 識別碼', '不是實機 UDID', '不透明 token', '不會收到 Apple 密碼、2FA 或簽署私鑰', '第三方資料保留期限未知']) assert(privacy.includes(text));
    assert(!privacy.includes('ani.stikstore.app'));
    assert(e.$('login-consent').closest('label').textContent.includes('mac-ani.jkcoxson.com')); assert(!e.$('login-consent').checked);
    submit(e, 'account-form'); await tick(); assert(!e.calls.some(call => call.options.method === 'POST'));
  } finally { e.dispose(); }
});

test('DOM mock: Teams failure is terminal; one explicit retry keeps the same session and makes no mutation', async () => {
  const reads = []; let calls = 0;
  const e = await environment({ service: true, fetcher: sessionFetcher((url, opts) => {
    if (url.endsWith('/teams')) { reads.push({url, authorization:opts.headers.Authorization}); if (++calls === 1) return Response.json({error:'appleRequestFailed',diagnostic:{stage:'developerTeams',kind:'developerRejected',upstream:'apple',appleCode:1234,message:'PRIVATE'}},{status:502}); }
  }) });
  try {
    loginInputs(e); submit(e,'account-form'); await until(()=>e.$('journey-title').textContent==='Team 讀取失敗');
    assert(e.$('two-factor').hidden); assert(e.$('verify-button').disabled); assert(e.$('resend-code').disabled); assert(e.$('send-sms').disabled); assert(e.$('provision-form').hidden);
    assert(e.$('account-status').textContent.includes('Apple 代碼 1234')); assert(!e.$('account-status').textContent.includes('PRIVATE')); assert(!e.$('retry-teams').hidden); assert(e.$('ipa').disabled);
    submit(e,'two-factor'); await e.$('resend-code').onclick(); await e.$('send-sms').onclick(); await tick(); assert.equal(calls,1); assert(!e.calls.some(c=>c.url.endsWith('/2fa')));
    e.$('retry-teams').click(); e.$('retry-teams').click(); await until(()=>!e.$('provision-form').hidden);
    assert.equal(calls,2); assert.deepEqual(reads[0],reads[1]); assert(e.$('retry-teams').hidden);
    assert.equal(e.calls.filter(c=>c.url.endsWith('/v1/sessions')&&c.options.method==='POST').length,1); assert(!e.calls.some(c=>c.url.endsWith('/provision')));
  } finally { e.dispose(); }
});
test('DOM mock: repeated Teams failure exhausts manual retry, and original expiry clears it without relogin', async () => {
  let reads=0;
  const e = await environment({service:true,fetcher:sessionFetcher((url,opts)=>{
    if(url.endsWith('/v1/sessions')&&opts.method==='POST')return Response.json({sessionId:'synthetic-id',sessionToken:'synthetic-token',expiresInSeconds:1});
    if(url.endsWith('/teams')) {reads++;return Response.json({error:'appleRequestFailed',diagnostic:{stage:'developerTeams',kind:'upstreamTimeout',upstream:'unknown'}},{status:504});}
  })});
  try{
    loginInputs(e);submit(e,'account-form');await until(()=>!e.$('retry-teams').hidden);e.$('retry-teams').click();await until(()=>reads===2&&e.$('journey-title').textContent==='Team 讀取失敗');
    assert(e.$('retry-teams').hidden);e.$('retry-teams').onclick();await tick();assert.equal(reads,2);
    await until(()=>e.$('account-status').textContent.includes('session 已到期'));assert(e.$('retry-teams').hidden);assert(e.$('two-factor').hidden);assert.equal(e.$('apple-id').value,'');
    assert.equal(e.calls.filter(c=>c.url.endsWith('/v1/sessions')&&c.options.method==='POST').length,1);
  }finally{e.dispose();}
});
test('DOM mock: unauthorized Teams response disables retry; cancelled late read cannot revive preparation', async () => {
  const e = await environment({service:true,fetcher:sessionFetcher(url=>url.endsWith('/teams')?Response.json({error:'expired'},{status:410}):undefined)});
  try{loginInputs(e);submit(e,'account-form');await until(()=>e.$('journey-title').textContent==='Team 讀取失敗');assert(e.$('retry-teams').hidden);assert(e.$('account-status').textContent.includes('session 已到期'));}finally{e.dispose();}
  let release;const held=new Promise(resolve=>release=resolve);let reads=0;
  const f = await environment({service:true,fetcher:sessionFetcher(async url=>{if(url.endsWith('/teams')){if(++reads===1)return Response.json({error:'appleRequestFailed'},{status:502});await held;}})});
  try{loginInputs(f);submit(f,'account-form');await until(()=>!f.$('retry-teams').hidden);f.$('retry-teams').click();await until(()=>reads===2);f.$('logout').click();release();await tick();await tick();assert(f.$('provision-form').hidden);assert(f.$('retry-teams').hidden);assert(f.$('account-status').textContent.includes('已取消'));}finally{release();f.dispose();}
});
test('DOM mock: late 2FA response cannot overwrite terminal Teams failure or reenable verification', async () => {
  let verified=false, release; const held=new Promise(resolve=>release=resolve); let submissions=0;
  const e=await environment({service:true,fetcher:sessionFetcher(async(url,opts)=>{
    if(url.endsWith('/v1/sessions/synthetic-id')&&opts.method!=='DELETE')return Response.json({state:verified?'authenticated':'awaitingTwoFactor',challenge:{unknown:false,numbers:[]}});
    if(url.endsWith('/2fa')){submissions++;verified=true;await held;return new Response(null,{status:202});}
    if(url.endsWith('/teams'))return Response.json({error:'appleRequestFailed',diagnostic:{stage:'developerTeams',kind:'upstreamTimeout'}},{status:504});
  })});
  try{
    loginInputs(e);submit(e,'account-form');await until(()=>!e.$('two-factor').hidden);e.$('verification-code').value='123456';submit(e,'two-factor');submit(e,'two-factor');
    await until(()=>e.$('journey-title').textContent==='Team 讀取失敗');const failure=e.$('account-status').textContent;release();await tick();await tick();
    assert.equal(submissions,1);assert.equal(e.$('account-status').textContent,failure);assert(e.$('verify-button').disabled);assert(e.$('two-factor').hidden);
  }finally{release();e.dispose();}
});
