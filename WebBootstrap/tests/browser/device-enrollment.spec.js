// Synthetic Settings callback tabs against the production-built app. No Apple
// login, real profiles, real UDIDs, or external network are used. A real loopback
// HTTPS transport observes Cookie at the server, not WebKit's pre-cookie route hook.
import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve, extname } from 'node:path';
import https from 'node:https';
import forge from 'node-forge';
const id='11111111-2222-3333-4444-555555555555';
const udid='00000000-0000000000000000';
const cookieValue='synthetic-cookie-not-a-secret';
const dist=resolve('dist');
// The exception applies only to this isolated self-signed loopback fixture.
// Every request is fenced to its exact origin; production TLS policy is unchanged.
test.use({ignoreHTTPSErrors:true});
let server;
test.afterEach(async()=>{if(server){const current=server;server=undefined;current.closeAllConnections();await new Promise(r=>current.close(r));}});
async function fixture(context,{cookie=true,now=Date.now}={}) {
  const calls=[],blocked=[];const expiry=now()+120000;
  const keys=forge.pki.rsa.generateKeyPair(2048),cert=forge.pki.createCertificate();
  cert.publicKey=keys.publicKey;cert.serialNumber='01';cert.validity.notBefore=new Date(Date.now()-60000);cert.validity.notAfter=new Date(Date.now()+3600000);
  cert.setSubject([{name:'commonName',value:'SYNTHETIC LOOPBACK TEST NOT PRODUCTION'}]);cert.setIssuer(cert.subject.attributes);cert.setExtensions([{name:'subjectAltName',altNames:[{type:7,ip:'127.0.0.1'}]}]);cert.sign(keys.privateKey,forge.md.sha256.create());
  server=https.createServer({key:forge.pki.privateKeyToPem(keys.privateKey),cert:forge.pki.certificateToPem(cert)},(req,res)=>{
    const path=req.url;res.setHeader('Cache-Control','no-store');
    const json=(status,body)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(body));};
    if(req.method!=='GET')return json(409,{error:'unexpectedMethod'});
    if(path==='/fixture/authorize'){
      if(cookie)res.setHeader('Set-Cookie',`__Secure-tetherless-enrollment=${cookieValue}; Path=/v1/device-enrollments/${id}; Max-Age=120; Secure; HttpOnly; SameSite=Lax`);
      res.writeHead(200,{'Content-Type':'text/html'});return res.end('<title>Synthetic cookie setup only</title>');
    }
    if(path==='/health')return json(200,{protocol:1,appleAuthAvailable:true,profileServiceAvailable:true});
    if(path==='/config.json')return json(200,{accountServiceUrl:null,officialRelease:null});
    if(path.startsWith('/v1/')){
      calls.push({path,method:req.method});
      if(path!==`/v1/device-enrollments/${id}`)return json(409,{error:'unexpected'});
      const authorized=req.headers.cookie?.split(';').map(v=>v.trim()).includes(`__Secure-tetherless-enrollment=${cookieValue}`);
      return authorized?json(200,{state:'received',device:{udid},expiresInSeconds:Math.max(0,Math.floor((expiry-now())/1000))}):json(401,{error:'unauthorized'});
    }
    const file=resolve(dist,'.'+(path==='/'?'/index.html':path));
    if(!file.startsWith(dist+'/'))return json(404,{error:'notFound'});
    const type={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.wasm':'application/wasm'}[extname(file)]||'application/octet-stream';
    try{const body=readFileSync(file);res.writeHead(200,{'Content-Type':type});res.end(body);}catch{return json(404,{error:'notFound'});}
  });
  await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin=`https://127.0.0.1:${server.address().port}`;
  await context.route('**/*',async route=>{const req=route.request(),url=new URL(req.url());if(url.origin!==origin||req.method()!=='GET'){blocked.push(req.url());return route.abort('blockedbyclient');}return route.continue();});
  await context.routeWebSocket('**/*',socket=>{blocked.push(socket.url());socket.close();});
  const setup=await context.newPage();await setup.goto(origin+'/fixture/authorize');await setup.close();
  const cookies=await context.cookies(origin+`/v1/device-enrollments/${id}`);
  expect(cookies.some(c=>c.name==='__Secure-tetherless-enrollment'&&c.value===cookieValue&&c.path===`/v1/device-enrollments/${id}`&&c.expires>Date.now()/1000&&c.httpOnly&&c.secure&&c.sameSite==='Lax')).toBe(cookie);
  return {calls,blocked,expiry,origin};
}
for(const order of ['original-first','callback-first']) test(`Settings callback ${order} can read without consuming another tab's result`,async({context})=>{
  // One logical timestamp for the server TTL and both pages: reconstructing a
  // remaining TTL after network delay cannot reproduce the exact server clock.
  // Keep HTTPS, cookies and timers real; do not relax the exact expiry bound.
  const fixedNow=Date.now();
  const {calls,blocked,expiry,origin}=await fixture(context,{now:()=>fixedNow});
  const original=await context.newPage();
  await original.clock.setFixedTime(fixedNow);
  await original.addInitScript(({id,expiry})=>sessionStorage.setItem('tetherless-device-enrollment',JSON.stringify({id,expiresAt:expiry})),{id,expiry});
  const callback=await context.newPage();
  await callback.clock.setFixedTime(fixedNow);
  const first=order==='original-first'?original:callback,second=order==='original-first'?callback:original;
  const open=async page=>{await page.goto(origin+(page===callback?`/#device-collected=${id}`:'/'));await expect(page.locator('#account-udid')).toHaveValue(udid);};
  await open(first);await open(second);
  for(const page of [first,second]){
    await expect(page.locator('#device-route')).toHaveValue('new');await expect(page.locator('#account-form')).toBeVisible();
    await expect(page.locator('#account-status')).toContainText('重新選取');expect(new URL(page.url()).hash).toBe('');
    const stored=await page.evaluate(()=>JSON.parse(sessionStorage.getItem('tetherless-device-enrollment')));
    expect(Object.keys(stored).sort()).toEqual(['expiresAt','id']);expect(stored.expiresAt).toBeLessThanOrEqual(expiry);
  }
  expect(calls).toEqual([{path:`/v1/device-enrollments/${id}`,method:'GET'},{path:`/v1/device-enrollments/${id}`,method:'GET'}]);expect(blocked).toEqual([]);
});
test('callback in another cookie context shows recovery guidance, not existing-device/login reset',async({context,page})=>{
  const {calls,blocked,origin}=await fixture(context,{cookie:false});await page.goto(`${origin}/#device-collected=${id}`);
  await expect(page.locator('#device-status')).toContainText('原瀏覽器');await expect(page.locator('#device-route')).toHaveValue('new');await expect(page.locator('#account-form')).toBeHidden();await expect(page.locator('#retry-device')).toBeVisible();
  expect(calls).toEqual([{path:`/v1/device-enrollments/${id}`,method:'GET'}]);expect(blocked).toEqual([]);
});
