// Synthetic DOM/service tests only; not iOS Settings or Apple acceptance.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';
import { setupDeviceEnrollment } from '../src/device-enrollment.js';
const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const origin = 'https://bootstrap.example/';
const id = '11111111-2222-3333-4444-555555555555';
const udid = '00000000-0000000000000000';
const key = 'tetherless-device-enrollment';
async function settle(fn) { for(let i=0;i<100;i++){if(fn())return;await new Promise(r=>setTimeout(r,5));}throw Error('Synthetic condition failed'); }
function page({ callback = false, stored } = {}) {
  const dom = new JSDOM(html,{url:origin+(callback?`#device-collected=${id}`:'')});
  for(const name of ['window','document','location','sessionStorage']) globalThis[name] = name==='window'?dom.window:dom.window[name];
  if(stored) sessionStorage.setItem(key,JSON.stringify(stored));
  let received=0;const api=setupDeviceEnrollment(origin,{onReceived:()=>received++});
  return {dom,api,get received(){return received;},activate(){for(const name of ['window','document','location','sessionStorage'])globalThis[name]=name==='window'?dom.window:dom.window[name];}};
}
for (const order of ['original-first','callback-first']) test(`synthetic two-tab ${order}: successful reads are repeatable under original server TTL; explicit cancel deletes`,async()=>{
  const calls=[];let cancelled=false;const originalExpiry=Date.now()+90000;
  globalThis.fetch=async(url,options={})=>{
    calls.push({url:String(url),options});assert.equal(options.credentials,'same-origin');
    if(options.method==='DELETE'){cancelled=true;return new Response(null,{status:204});}
    assert.equal(String(url),`${origin}v1/device-enrollments/${id}`);
    return cancelled?Response.json({error:'notFound'},{status:404}):Response.json({state:'received',device:{udid},expiresInSeconds:Math.floor((originalExpiry-Date.now())/1000)});
  };
  const first=page(order==='original-first'?{stored:{id,expiresAt:originalExpiry}}:{callback:true});
  first.api.resume();await settle(()=>first.received===1);
  assert(!cancelled);assert.equal(first.dom.window.document.getElementById('account-udid').value,udid);
  const second=page(order==='original-first'?{callback:true}:{stored:{id,expiresAt:originalExpiry}});
  second.api.resume();await settle(()=>second.received===1);
  assert(!cancelled);assert.equal(calls.length,2);assert(calls.every(c=>!c.options.method));
  for(const p of [first,second]){const saved=JSON.parse(p.dom.window.sessionStorage.getItem(key));assert.deepEqual(Object.keys(saved).sort(),['expiresAt','id']);assert(saved.expiresAt<=originalExpiry);assert.equal(p.dom.window.location.hash,'');}
  // A later Settings/pagehide cycle can clear DOM metadata and still read again.
  first.activate();first.dom.window.document.getElementById('account-udid').value='';first.api.pause();first.api.resume();await settle(()=>first.received===2);assert(!cancelled);
  first.api.clear();assert(cancelled);assert.equal(first.dom.window.sessionStorage.length,0);
  second.activate();second.api.clear();first.dom.window.close();second.dom.window.close();
});
test('synthetic failed read does not DELETE shared result; retry only GETs original ID',async()=>{
  let attempts=0;const methods=[];
  globalThis.fetch=async(url,options={})=>{methods.push(options.method||'GET');if(options.method==='DELETE')return new Response(null,{status:204});attempts++;if(attempts===1)throw new TypeError('Synthetic network interruption');return Response.json({state:'received',device:{udid},expiresInSeconds:120});};
  const p=page({callback:true});p.api.resume();await settle(()=>!document.getElementById('retry-device').hidden);
  assert.deepEqual(methods,['GET']);assert(document.getElementById('device-status').textContent.includes('重讀'));
  document.getElementById('retry-device').click();await settle(()=>p.received===1);assert.deepEqual(methods,['GET','GET']);
  p.api.clear();p.dom.window.close();
});
test('synthetic zero remaining server TTL drops local state without DELETE or registration',async()=>{
  const methods=[];globalThis.fetch=async(url,options={})=>{methods.push(options.method||'GET');return Response.json({state:'received',device:{udid},expiresInSeconds:0});};
  const p=page({callback:true});p.api.resume();await settle(()=>document.getElementById('device-status').textContent.includes('到期'));
  assert.equal(p.received,0);assert.equal(sessionStorage.length,0);assert.deepEqual(methods,['GET']);p.api.clear();p.dom.window.close();
});
