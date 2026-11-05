const {test}=require('node:test');
const assert=require('node:assert/strict');
const {createGuard}=require('../../deployment/lib/abuse');
const request=(ip='127.0.0.1',headers={})=>({method:'POST',socket:{remoteAddress:ip},headers,body:{email:'test@example.invalid'}});

test('auth attempts are bounded and the window really expires',()=>{
  let now=1000;const guard=createGuard({clock:()=>now,log:()=>{}});
  for(let i=0;i<10;i++)assert.equal(guard(request(),'auth/sign-in'),null);
  const blocked=guard(request(),'auth/sign-in');assert.equal(blocked.status,429);assert.ok(blocked.retryAfter>0);
  now+=300001;assert.equal(guard(request(),'auth/sign-in'),null);
});
test('forged proxy headers cannot bypass local caller limits',()=>{
  const guard=createGuard({trustProxy:false,log:()=>{}});
  for(let i=0;i<10;i++)assert.equal(guard(request('127.0.0.1',{'x-forwarded-for':'192.0.2.'+i}),'auth/sign-in'),null);
  assert.equal(guard(request('127.0.0.1',{'x-forwarded-for':'192.0.2.200'}),'auth/sign-in').status,429);
});
test('separate trusted platform clients are independent',()=>{
  const guard=createGuard({trustProxy:true,log:()=>{}});
  for(let i=0;i<10;i++)guard(request('proxy',{'x-forwarded-for':'192.0.2.1'}),'auth/sign-in');
  assert.equal(guard(request('proxy',{'x-forwarded-for':'192.0.2.2'}),'auth/sign-in'),null);
});
test('actual oversized UTF-8 bodies are rejected even with a false Content-Length',()=>{
  const guard=createGuard({log:()=>{}});const req=request();req.body={x:'字'.repeat(30000)};req.headers['content-length']='2';
  assert.equal(guard(req,'auth/sign-up').status,413);
});
test('saturated memory does not evict a blocked identity to let it bypass limits',()=>{
  const guard=createGuard({maxBuckets:2,log:()=>{}});
  for(let i=0;i<10;i++)guard(request('first'),'auth/sign-in');
  assert.equal(guard(request('second'),'auth/sign-in').status,429);
  assert.equal(guard(request('first'),'auth/sign-in').status,429);
});
