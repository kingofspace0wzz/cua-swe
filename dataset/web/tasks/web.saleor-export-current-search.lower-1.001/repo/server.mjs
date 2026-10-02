import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join } from 'node:path';

const args = process.argv.slice(2);
const port = Number(args[args.indexOf('--port') + 1] || 4173);
const host = args[args.indexOf('--host') + 1] || '127.0.0.1';
const upstream = process.env.CUA_SWE_EXTERNAL_SERVICE_ORIGIN || 'http://127.0.0.1:4311';
const types = {'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml'};
http.createServer(async (req,res) => {
  if (req.url.startsWith('/api/')) {
    const chunks=[]; for await (const chunk of req) chunks.push(chunk);
    try {
      const response=await fetch(upstream+req.url,{method:req.method,headers:{'content-type':'application/json'},body:chunks.length?Buffer.concat(chunks):undefined});
      res.writeHead(response.status,{'content-type':response.headers.get('content-type')||'application/json'});res.end(Buffer.from(await response.arrayBuffer()));
    } catch {
      res.writeHead(502,{'content-type':'application/json'});res.end('{"error":"workspace service unavailable"}');
    }
    return;
  }
  const requested=req.url==='/'?'index.html':req.url.split('?')[0].slice(1);
  try {const file=await readFile(join('dist',requested));res.writeHead(200,{'content-type':types[extname(requested)]||'application/octet-stream'});res.end(file);}
  catch {const file=await readFile(join('dist','index.html'));res.writeHead(200,{'content-type':'text/html'});res.end(file);}
}).listen(port,host);
