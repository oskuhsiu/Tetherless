// DOM emulation + mocked worker/service. These are not browser or Apple acceptance tests.
import test from 'node:test'; import assert from 'node:assert/strict'; import { readFileSync } from 'node:fs'; import { JSDOM } from 'jsdom';
import forge from 'node-forge';
import { makeIpa, makeMaterial, makeSignedFixture } from './fixtures.mjs';
const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const tick = () => new Promise((r) => setTimeout(r, 10));
async function until(fn) { for (let i=0;i<200;i++) { if(fn()) return; await tick(); } throw new Error('Condition did not become true'); }
async function environment({ service = false, profileService = service, config = { accountServiceUrl: null, officialRelease: null }, deviceRoute = 'new', storedEnrollment, fetcher } = {}) {
  const dom = new JSDOM(html, { url: 'http://127.0.0.1:8787/', pretendToBeVisual: true });
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
test('DOM mock: enrollment keeps only ID/expiry, survives pagehide, and resumes after persisted pageshow', async()=>{let received=false;const id='11111111-2222-3333-4444-555555555555';const e=await environment({service:true,fetcher:async(url,opts)=>{if(url.endsWith('/v1/device-enrollments')&&opts.method==='POST')return Response.json({enrollmentId:id,profileUrl:`http://127.0.0.1:8787/v1/device-enrollments/${id}/profile/synthetic-capability`,expiresInSeconds:600},{status:201});if(url.includes('/v1/device-enrollments/')&&opts.method!=='DELETE')return Response.json({state:received?'received':'awaitingDevice',device:received?{udid:'00000000-0000000000000000'}:null,verification:'untrustedDeviceMetadata'});if(opts.method==='DELETE')return new Response(null,{status:204});}});try{e.$('device-consent').checked=true;e.$('collect-device').click();await until(()=>!e.$('device-profile-link').hidden);const stored=JSON.parse(e.dom.window.sessionStorage.getItem('tetherless-device-enrollment'));assert.deepEqual(Object.keys(stored).sort(),['expiresAt','id']);e.dom.window.dispatchEvent(new e.dom.window.PageTransitionEvent('pagehide',{persisted:true}));assert(e.dom.window.sessionStorage.getItem('tetherless-device-enrollment'));assert(!e.calls.some(c=>c.url.i…4264 tokens truncated…法讀取'));assert(e.$('provision-button').disabled);e.$('reload-devices').click();await until(()=>attempts===2&&!e.$('reload-devices').disabled);assert(e.$('existing-status').textContent.includes('沒有可用'));assert(e.$('provision-button').disabled);assert(!e.calls.some(c=>c.url.endsWith('/provision')));
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
    await until(()=>e.$('account-udid').value===registeredDevice.udid);assert.equal(e.$('device-route').value,'new');assert(!e.$('account-form').hidden);assert.equal(e.dom.window.sessionStorage.length,0);
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
