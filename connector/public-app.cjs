// Loopback-only public UI/gateway. The router exposes only /smartseat/ over HTTPS.
const http=require('node:http'),fs=require('node:fs'),path=require('node:path');
const BASE='/smartseat/';
const CSP="default-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'";
function createPublicApp({root,handler}={}){
 root=path.resolve(root||path.join(__dirname,'../local/public-runtime'));
 handler=handler||require('../deployment/api/engine');
 const server=http.createServer(async(req,res)=>{
  res.status=n=>{res.statusCode=n;return res};res.json=data=>{res.setHeader('Content-Type','application/json');res.end(JSON.stringify(data));return res};
  res.send=data=>{res.end(data);return res};res.redirect=(status,url)=>{res.statusCode=status;res.setHeader('Location',url);res.end();return res};
  res.setHeader('X-Content-Type-Options','nosniff');res.setHeader('Referrer-Policy','no-referrer');res.setHeader('Content-Security-Policy',CSP);res.setHeader('X-Frame-Options','DENY');res.setHeader('Cache-Control','no-store');
  try{
   const parsed=new URL(req.url,'http://loopback.invalid'),pathname=decodeURIComponent(parsed.pathname);
   if(pathname==='/smartseat')return res.redirect(303,BASE+parsed.search);
   if(!pathname.startsWith(BASE))return res.status(404).json({detail:'Application route not found.'});
   const relative=pathname.slice(BASE.length);
   if(relative==='gateway-health'&&['GET','HEAD'].includes(req.method))return res.json({ok:true,app:'smartseat-gateway'});
   if(relative.startsWith('api/')){
    const route=relative.slice(4);if(!/^[a-zA-Z0-9_/-]+$/.test(route)||route.includes('..'))return res.status(404).json({detail:'API route not found.'});
    const maximum=route==='media/analyze'&&req.method==='POST'?1048576:65536;
    let size=0,rejected=false,chunks=[];
    await new Promise((resolve,reject)=>{
     req.on('data',chunk=>{size+=chunk.length;if(size>maximum){chunks=[];if(!rejected){rejected=true;res.status(413).json({detail:'This request is too large.'})}}else if(!rejected)chunks.push(chunk)});
     req.on('end',resolve);req.on('error',reject);req.on('aborted',()=>reject(new Error('Request interrupted')));
    });
    if(rejected)return;
    req.body=['GET','HEAD'].includes(req.method)?undefined:Buffer.concat(chunks).toString('utf8');
    req.query=Object.fromEntries(parsed.searchParams);req.query.route=route;req.url='/api/'+route+parsed.search;
    return await handler(req,res);
   }
   if(!['GET','HEAD'].includes(req.method))return res.status(405).json({detail:'Method not allowed.'});
   const file=relative||'index.html';
   if(file.split('/').some(part=>part.startsWith('.'))||!(file==='index.html'||file==='favicon.svg'||file.startsWith('assets/')))return res.status(404).json({detail:'Asset not found.'});
   const resolved=path.resolve(root,file);if(!resolved.startsWith(root+path.sep))return res.status(404).json({detail:'Asset not found.'});
   const stat=await fs.promises.stat(resolved).catch(()=>null);if(!stat?.isFile())return res.status(404).json({detail:'Asset not found.'});
   const types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml','.webp':'image/webp','.ttf':'font/ttf','.png':'image/png','.jpg':'image/jpeg','.json':'application/json'};
   res.setHeader('Content-Type',types[path.extname(file)]||'application/octet-stream');res.setHeader('Content-Length',stat.size);
   if(file!=='index.html')res.setHeader('Cache-Control','public, max-age=3600');
   if(req.method==='HEAD')return res.end();
   const stream=fs.createReadStream(resolved);stream.on('error',()=>res.destroy());res.on('close',()=>stream.destroy());stream.pipe(res);
  }catch{if(!res.headersSent)res.status(502).json({detail:'SmartSeat gateway is temporarily unavailable.'});else res.destroy()}
 });
 server.requestTimeout=20000;server.headersTimeout=10000;server.maxConnections=64;return server;
}
if(require.main===module){
 const root=path.resolve(__dirname,'..'),config=JSON.parse(fs.readFileSync(path.join(root,'local/public-connection.json'))),cloud=JSON.parse(fs.readFileSync(path.join(root,'local/cloud-env-private.json')));
 const origin=new URL(config.public_app_origin);if(origin.protocol!=='https:'||origin.pathname!=='/'||origin.username||origin.password||origin.search||origin.hash||origin.host!==new URL(config.engine_origin).host)throw new Error('Unexpected public app origin');
 process.env.SUPABASE_URL=cloud.SUPABASE_URL;process.env.SUPABASE_PUBLISHABLE_KEY=cloud.SUPABASE_PUBLISHABLE_KEY;
 process.env.SMARTSEAT_CLOUD_AUTH='1';process.env.SMARTSEAT_PUBLIC_ORIGIN=origin.origin;process.env.SMARTSEAT_APP_BASE='/smartseat';
 process.env.SMARTSEAT_RUNTIME='local';process.env.SMARTSEAT_LOCAL_ENGINE_PORT=String(config.engine_port||8766);
 const port=config.gateway_port||8768;createPublicApp().listen(port,'127.0.0.1',()=>console.log('SmartSeat public gateway listening on loopback '+port));
}
module.exports={createPublicApp};
