const {test}=require('node:test');const assert=require('node:assert/strict');
const http=require('node:http'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {createRouter}=require('../../connector/router.cjs');
const listen=server=>new Promise(r=>server.listen(0,'127.0.0.1',()=>r('http://127.0.0.1:'+server.address().port)));

test('public app prefix reaches gateway while all unrelated paths retain existing app',async t=>{
 const existing=http.createServer((q,s)=>s.end('existing:'+q.url)),gateway=http.createServer((q,s)=>s.end('gateway:'+q.url));
 await listen(existing);await listen(gateway);t.after(()=>existing.close());t.after(()=>gateway.close());
 const router=createRouter({existingPort:existing.address().port,gatewayPort:gateway.address().port});const base=await listen(router);t.after(()=>router.close());
 assert.equal(await(await fetch(base+'/smartseat/')).text(),'gateway:/smartseat/');
 assert.equal(await(await fetch(base+'/smartseat?x=1')).text(),'gateway:/smartseat?x=1');
 assert.equal(await(await fetch(base+'/api/state')).text(),'existing:/api/state');
});

test('router replaces forged identity with salted last-hop ngrok client identity',async t=>{
 const gateway=http.createServer((q,s)=>s.end(JSON.stringify({key:q.headers['x-smartseat-client-key'],ip:q.headers['x-forwarded-for']})));
 await listen(gateway);t.after(()=>gateway.close());const router=createRouter({gatewayPort:gateway.address().port});const base=await listen(router);t.after(()=>router.close());
 const get=async prefix=>(await fetch(base+'/smartseat/api/me',{headers:{'x-smartseat-client-key':'forged','x-forwarded-for':prefix+', 203.0.113.8'}})).json();
 const a=await get('192.0.2.1'),b=await get('192.0.2.99');assert.match(a.key,/^[a-f0-9]{64}$/);assert.equal(a.key,b.key);assert.equal(a.ip,'203.0.113.8');
});

test('local proxy limits separate real clients and ignore non-loopback forged identity',()=>{
 const {createGuard}=require('../../deployment/lib/abuse');const guard=createGuard({trustLoopbackProxy:true,log:()=>{}});
 const req=key=>({method:'POST',socket:{remoteAddress:'127.0.0.1'},headers:{'x-smartseat-client-key':key.repeat(64)},body:{}});
 for(let i=0;i<10;i++)assert.equal(guard(req('a'),'auth/sign-in'),null);
 assert.equal(guard(req('a'),'auth/sign-in').status,429);assert.equal(guard(req('b'),'auth/sign-in'),null);
 const outside=createGuard({trustLoopbackProxy:true,log:()=>{}});
 for(let i=0;i<10;i++)outside({...req('a'),socket:{remoteAddress:'192.0.2.1'}},'auth/sign-in');
 assert.equal(outside({...req('b'),socket:{remoteAddress:'192.0.2.1'}},'auth/sign-in').status,429);
});

test('cloud redirects and engine cookies stay within app prefix; loopback engine must be explicit',()=>{
 const cloud=require('../../deployment/lib/cloud-auth');const original={...process.env};
 try{
  process.env.SMARTSEAT_APP_BASE='/smartseat';process.env.SMARTSEAT_PUBLIC_ORIGIN='https://restaurant.example';
  assert.equal(typeof cloud.appPath,'function');assert.equal(cloud.appPath('/?auth_error=x'),'/smartseat/?auth_error=x');
  const res={getHeader:()=>[],setHeader(k,v){this.value=v}};
  cloud.appendCookies(res,['smartseat_session=proof; Path=/; HttpOnly; SameSite=Strict; Secure']);
  assert.match(res.value[0],/Path=\/smartseat\//);assert.match(res.value[0],/HttpOnly/);
  process.env.SMARTSEAT_RUNTIME='local';process.env.SMARTSEAT_LOCAL_ENGINE_PORT='8766';
  assert.equal(cloud.engineURL('state').href,'http://127.0.0.1:8766/api/state');
 }finally{for(const k of Object.keys(process.env))if(!(k in original))delete process.env[k];Object.assign(process.env,original)}
});

test('public runtime serves only bundled assets and bounded same-origin API bodies',async t=>{
 const file=path.resolve(__dirname,'../../connector/public-app.cjs');assert.ok(fs.existsSync(file),'public application server must exist');
 const {createPublicApp}=require(file),root=fs.mkdtempSync(path.join(os.tmpdir(),'smartseat-public-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 fs.writeFileSync(path.join(root,'index.html'),'<title>SmartSeat AI</title>');fs.writeFileSync(path.join(root,'.env'),'private');
 const server=createPublicApp({root,handler:async(q,s)=>s.json({route:q.query.route,body:JSON.parse(q.body||'{}')})});const base=await listen(server);t.after(()=>server.close());
 assert.match(await(await fetch(base+'/smartseat/')).text(),/SmartSeat AI/);
 const canonical=await fetch(base+'/smartseat?x=1',{redirect:'manual'});assert.equal(canonical.headers.get('location'),'/smartseat/?x=1');
 assert.equal((await fetch(base+'/smartseat/.env')).status,404);
 assert.equal((await fetch(base+'/smartseat/private.sqlite3')).status,404);
 const response=await fetch(base+'/smartseat/api/media/analyze',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({image:'a'.repeat(100000)})});
 assert.equal(response.status,200);assert.equal((await response.json()).route,'media/analyze');
 assert.equal((await fetch(base+'/smartseat/api/queue',{method:'POST',body:'x'.repeat(70000)})).status,413);
});

test('client base paths keep API, Google and public assets within the correct app',async()=>{
 const {pathsFor}=await import('../../web/src/paths.mjs');
 const prefix=pathsFor('/smartseat/');assert.equal(prefix.api('/auth/google'),'/smartseat/api/auth/google');
 assert.equal(prefix.asset('/assets/scene.webp'),'/smartseat/assets/scene.webp');assert.equal(pathsFor('/').api('/state'),'/api/state');
 assert.throws(()=>pathsFor('//external/'));assert.throws(()=>pathsFor('https://external/'));
});
