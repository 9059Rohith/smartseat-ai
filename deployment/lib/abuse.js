// Best-effort per-instance guard; managed Auth and Vercel edge protections remain active.
const crypto = require('node:crypto');
const POLICIES = {
  'auth/sign-in': [10, 300000], 'auth/sign-up': [3, 600000],
  'auth/forgot-password': [3, 1800000], 'auth/connect-engine': [8, 300000],
  'auth/google': [20, 60000],
};

function createGuard({clock=Date.now,maxBuckets=3000,trustProxy=process.env.VERCEL==='1',log=console.warn}={}) {
  const salt=crypto.randomBytes(32), buckets=new Map();
  function take(identity,action,limit,window,now){
    const key=crypto.createHmac('sha256',salt).update(identity+'\0'+action).digest('hex');
    let bucket=buckets.get(key);
    if(!bucket||bucket.until<=now){
      if(!bucket&&buckets.size>=maxBuckets){
        for(const [id,value] of buckets)if(value.until<=now)buckets.delete(id);
        if(buckets.size>=maxBuckets)return {status:429,retryAfter:60,detail:'SmartSeat is busy. Please try again shortly.'};
      }
      bucket={count:0,until:now+window,warned:false};buckets.set(key,bucket);
    }
    if(bucket.count>=limit){
      if(!bucket.warned){log(JSON.stringify({event:'request_throttled',action}));bucket.warned=true;}
      return {status:429,retryAfter:Math.max(1,Math.ceil((bucket.until-now)/1000)),detail:'Too many requests. Please wait before trying again.'};
    }
    bucket.count++;return null;
  }
  return (req,route)=>{
    const declared=req.headers['content-length'];
    if(declared&&(!/^\d+$/.test(String(declared))))return {status:400,detail:'Invalid request length.'};
    if(Number(declared)>65536)return {status:413,detail:'This request is too large.'};
    if(req.body!==undefined){
      const body=typeof req.body==='string'||Buffer.isBuffer(req.body)?req.body:JSON.stringify(req.body);
      if(Buffer.byteLength(body)>65536)return {status:413,detail:'This request is too large.'};
    }
    const forwarded=trustProxy?req.headers['x-forwarded-for']:null;
    const identity=typeof forwarded==='string'?forwarded.split(',')[0].trim():req.socket?.remoteAddress||'unknown';
    const now=clock();
    const general=take(identity,'all_requests',600,60000,now);if(general)return general;
    const policy=POLICIES[route];
    if(policy)return take(identity,route,...policy,now);
    if(!['GET','HEAD','OPTIONS'].includes(req.method))return take(identity,'workspace_changes',120,60000,now);
    return null;
  };
}
module.exports={createGuard};
