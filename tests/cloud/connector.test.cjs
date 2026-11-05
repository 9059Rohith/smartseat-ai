const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { createRouter } = require('../../connector/router.cjs');

test('dedicated engine paths reach SmartSeat; existing app paths and streams stay intact', async t => {
  const serve = async handler => { const server=http.createServer(handler);await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));t.after(()=>new Promise(resolve=>server.close(resolve)));return server.address().port; };
  const existing=await serve((req,res)=>{res.setHeader('content-type','text/event-stream');res.write('existing:'+req.url);res.end(':stream-end');});
  const engine=await serve((req,res)=>{res.setHeader('set-cookie','smartseat_session=proof; Secure; HttpOnly');res.end('engine:'+req.url+':'+req.headers.origin);});
  const router=createRouter({existingPort:existing,enginePort:engine});await new Promise(resolve=>router.listen(0,'127.0.0.1',resolve));t.after(()=>new Promise(resolve=>router.close(resolve)));
  const base='http://127.0.0.1:'+router.address().port;
  assert.equal(await (await fetch(base+'/api/status?x=1')).text(),'existing:/api/status?x=1:stream-end');
  const response=await fetch(base+'/smartseat-engine/api/state?x=2',{headers:{origin:'https://smartseat.example'}});
  assert.equal(await response.text(),'engine:/api/state?x=2:https://smartseat.example');
  assert.match(response.headers.get('set-cookie'),/HttpOnly/);
  assert.equal((await fetch(base+'/smartseat-engine/private-file')).status,404);
});

test('gateway keeps the dedicated path when building upstream URLs',()=>{
  process.env.SMARTSEAT_ENGINE_ORIGIN='https://engine.example/smartseat-engine';
  const {engineURL}=require('../../deployment/lib/cloud-auth');
  assert.equal(engineURL('analytics?start=1&end=2').href,'https://engine.example/smartseat-engine/api/analytics?start=1&end=2');
});

test('router identity stays verifiable when the camera engine is offline',async t=>{
  const router=createRouter({enginePort:1});await new Promise(resolve=>router.listen(0,'127.0.0.1',resolve));t.after(()=>new Promise(resolve=>router.close(resolve)));
  const response=await fetch('http://127.0.0.1:'+router.address().port+'/smartseat-engine/router-health');
  assert.equal(response.status,200);assert.equal((await response.json()).app,'smartseat-router');
});

test('an interrupted upstream stream closes the downstream so clients can reconnect',async t=>{
  const upstream=http.createServer((req,res)=>{res.writeHead(200,{'content-type':'text/event-stream'});res.write('data: ready\n\n');setTimeout(()=>res.destroy(),25);});
  await new Promise(resolve=>upstream.listen(0,'127.0.0.1',resolve));t.after(()=>upstream.close());
  const router=createRouter({existingPort:upstream.address().port});await new Promise(resolve=>router.listen(0,'127.0.0.1',resolve));t.after(()=>router.closeAllConnections());t.after(()=>router.close());
  const response=await fetch('http://127.0.0.1:'+router.address().port+'/events',{signal:AbortSignal.timeout(1000)});
  await assert.rejects(response.text(),/terminated|other side closed/i);
});

test('saved owner reports remain readable when the real connector returns an offline HTTP error',async t=>{
  const originalFetch=global.fetch;t.after(()=>{global.fetch=originalFetch;});
  global.fetch=async()=>new Response('{"detail":"Local application is offline."}',{status:502,headers:{'content-type':'application/json'}});
  const {report}=require('../../deployment/lib/cloud-data');
  const query={select(){return this;},eq(){return this;},async maybeSingle(){return {data:{payload:{seatings:3,daily:[]},source_at:'2026-11-05T10:00:00Z'},error:null};}};
  const result=await report({url:'/api/analytics?period=week',headers:{}},{jar:{smartseat_session:'test-proof'},supabase:{from:()=>query}},{id:'test-workspace'});
  assert.equal(result.status,200);assert.equal(result.data.cached,true);assert.equal(result.data.seatings,3);assert.equal(result.data.synced_at,'2026-11-05T10:00:00Z');
});
