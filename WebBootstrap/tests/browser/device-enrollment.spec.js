// Synthetic Settings callback tabs against the production-built app. No Apple
// login, real profiles, real UDIDs, or external network are used.
import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve, extname } from 'node:path';
const origin='https://bootstrap.example';
const id='11111111-2222-3333-4444-555555555555';
const udid='00000000-0000000000000000';
const cookieValue='synthetic-cookie-not-a-secret';
const dist=resolve('dist');
async function fixture(context,{cookie=true}={}) {
  const calls=[];const expiry=Date.now()+120000;
  if(cookie)await context.addCookies([{name:'__Secure-tetherless-enrollment',value:cookieValue,domain:'bootstrap.example',path:`/v1/device-enrollments/${id}`,httpOnly:true,secure:true,sameSite:'Lax',expires:Math.floor(expiry/1000)}]);
  await context.route('**/*',async route=>{
    const req=route.request(),url=new URL(req.url());
    if(url.origin!==origin){await route.abort();throw Error('Unexpected external request');}
    const path=url.pathname;
    if(path==='/health')return route.fulfill({json:{protocol:1,appleAuthAvailable:true,profileServiceAvailable:true}});
    if(path==='/config.json')return route.fulfill({json:{accountServiceUrl:null,officialRelease:null}});
    if(path.startsWith('/v1/')){
      calls.push({path,method:req.method()});
      if(path!==`/v1/device-enrollments/${id}`||req.method()!=='GET')return route.fulfill({status:409,json:{error:'unexpected'}});
      const authorized=(await req.allHeaders()).cookie?.includes(`__Secure-tetherless-enrollment=${cookieValue}`);
      return route.fulfill(authorized?{json:{state:'received',device:{udid},expiresInSeconds:Math.max(0,Math.floor((expiry-Date.now())/1000))}}:{status:401,json:{error:'unauthorized'}});
    }
    const file=resolve(dist,'.'+(path==='/'?'/index.html':path));
    if(!file.startsWith(dist+'/'))return route.abort();
    const type={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.wasm':'application/wasm'}[extname(file)]||'application/octet-stream';
    return route.fulfill({body:readFileSync(file),contentType:type});
  });
  return {calls,expiry};
}
for(const order of ['original-first','callback-first']) test(`Settings callback ${order} can read without consuming another tab's result`,async({context})=>{
  const {calls,expiry}=await fixture(context);
  const original=await context.newPage();
  await original.addInitScript(({id,expiry})=>sessionStorage.setItem('tetherless-device-enrollment',JSON.stringify({id,expiresAt:expiry})),{id,expiry});
  const callback=await context.newPage();
  const first=order==='original-first'?original:callback,second=order==='original-first'?callback:original;
  const open=async page=>{await page.goto(origin+(page===callback?`/#device-collected=${id}`:'/'));await expect(page.locator('#account-udid')).toHaveValue(udid);};
  await open(first);await open(second);
  for(const page of [first,second]){
    await expect(page.locator('#device-route')).toHaveValue('new');await expect(page.locator('#account-form')).toBeVisible();
    await expect(page.locator('#account-status')).toContainText('重新選取');expect(new URL(page.url()).hash).toBe('');
    const stored=await page.evaluate(()=>JSON.parse(sessionStorage.getItem('tetherless-device-enrollment')));
    expect(Object.keys(stored).sort()).toEqual(['expiresAt','id']);expect(stored.expiresAt).toBeLessThanOrEqual(expiry);
  }
  expect(calls).toEqual([{path:`/v1/device-enrollments/${id}`,method:'GET'},{path:`/v1/device-enrollments/${id}`,method:'GET'}]);
});
test('callback in another cookie context shows recovery guidance, not existing-device/login reset',async({context,page})=>{
  const {calls}=await fixture(context,{cookie:false});await page.goto(`${origin}/#device-collected=${id}`);
  await expect(page.locator('#device-status')).toContainText('原瀏覽器');await expect(page.locator('#device-route')).toHaveValue('new');await expect(page.locator('#account-form')).toBeHidden();await expect(page.locator('#retry-device')).toBeVisible();
  expect(calls).toEqual([{path:`/v1/device-enrollments/${id}`,method:'GET'}]);
});
