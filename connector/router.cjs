// Loopback-only path router. Other app requests keep their existing destination.
const http = require('node:http');
const net = require('node:net');
const crypto = require('node:crypto');
const PREFIX = '/smartseat-engine/';

function createRouter({ enginePort=8766, existingPort=8765, gatewayPort=8768 }={}) {
  const clientSalt=crypto.randomBytes(32);
  const server=http.createServer((req,res)=>{
    if(req.url==='/smartseat-engine/router-health'&&['GET','HEAD'].includes(req.method)){
      res.writeHead(200,{'content-type':'application/json','cache-control':'no-store'});
      return res.end(req.method==='HEAD'?'':'{"ok":true,"app":"smartseat-router"}');
    }
    const engine=req.url.startsWith(PREFIX);
    const gateway=req.url==='/smartseat'||req.url.startsWith('/smartseat?')||req.url.startsWith('/smartseat/');
    const path=engine?req.url.slice(PREFIX.length-1):req.url;
    if(engine&&!/^\/api\/[a-zA-Z0-9_/-]+(?:\?.*)?$/.test(path)){
      res.writeHead(404,{'content-type':'application/json'});return res.end('{"detail":"Engine API route not found."}');
    }
    const headers={...req.headers};
    if(engine)headers.host='127.0.0.1:'+enginePort;
    if(gateway){
      headers.host='127.0.0.1:'+gatewayPort;
      // ngrok appends the verified client IP last; never trust the client prefix.
      const forwarded=String(headers['x-forwarded-for']||'').split(',').at(-1).trim();
      const client=net.isIP(forwarded)?forwarded:req.socket.remoteAddress;
      headers['x-forwarded-for']=client;
      headers['x-smartseat-client-key']=crypto.createHmac('sha256',clientSalt).update(client).digest('hex');
    }
    const upstream=http.request({hostname:'127.0.0.1',port:engine?enginePort:gateway?gatewayPort:existingPort,path,method:req.method,headers},response=>{
      response.on('error',()=>res.destroy());response.on('aborted',()=>res.destroy());
      res.writeHead(response.statusCode,response.headers);response.pipe(res);
    });
    upstream.on('error',()=>{if(!res.headersSent)res.writeHead(502,{'content-type':'application/json'});res.end('{"detail":"Local application is offline."}');});
    req.on('aborted',()=>upstream.destroy());res.on('close',()=>upstream.destroy());req.pipe(upstream);
  });
  // Preserve existing application's WebSocket upgrades as well as ordinary HTTP/SSE.
  server.on('upgrade',(req,socket,head)=>{
    if(req.url.startsWith(PREFIX)||req.url==='/smartseat'||req.url.startsWith('/smartseat?')||req.url.startsWith('/smartseat/')){socket.end('HTTP/1.1 404 Not Found\r\n\r\n');return;}
    const upstream=net.connect(existingPort,'127.0.0.1',()=>{
      upstream.write(`${req.method} ${req.url} HTTP/${req.httpVersion}\r\n`);
      for(let i=0;i<req.rawHeaders.length;i+=2)upstream.write(`${req.rawHeaders[i]}: ${req.rawHeaders[i+1]}\r\n`);
      upstream.write('\r\n');if(head.length)upstream.write(head);socket.pipe(upstream).pipe(socket);
    });
    upstream.on('error',()=>socket.destroy());socket.on('error',()=>upstream.destroy());socket.on('close',()=>upstream.destroy());
  });
  return server;
}
if(require.main===module)createRouter().listen(8767,'127.0.0.1',()=>console.log('SmartSeat connector router: 127.0.0.1:8767'));
module.exports={createRouter};
