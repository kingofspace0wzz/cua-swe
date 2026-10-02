import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve,dirname} from 'node:path';import {fileURLToPath} from 'node:url';
import {collectTarget} from './src/collector.mjs';
const root=dirname(fileURLToPath(import.meta.url));const origin=process.env.CUA_SWE_EXTERNAL_SERVICE_ORIGIN;
if(!origin)throw new Error('CUA_SWE_EXTERNAL_SERVICE_ORIGIN required');
let port=56510,host='127.0.0.1';for(let i=2;i<process.argv.length;i++){if(process.argv[i]==='--port')port=Number(process.argv[++i]);else if(process.argv[i]==='--host')host=process.argv[++i];}
let running=false;const resultLog=[];
function send(r,status,type,body){r.writeHead(status,{'content-type':type,'cache-control':'no-store'});r.end(body);}
createServer(async(q,r)=>{try{
 const u=new URL(q.url,'http://app.invalid');
 if(u.pathname==='/api/activation-board'){
  const a=await fetch(origin+'/activation-board.png');const body=Buffer.from(await a.arrayBuffer());
  return send(r,a.status,'image/png',body);
 }
 if(u.pathname==='/api/deadline-matrix'){
  const a=await fetch(origin+'/deadline-matrix.png');const body=Buffer.from(await a.arrayBuffer());
  return send(r,a.status,'image/png',body);
 }
 if(u.pathname==='/api/run'&&q.method==='POST'){
  if(running)return send(r,409,'application/json','{"error":"checks still running"}');
  running=true;const init=await fetch(origin+'/begin',{method:'POST'});const {targets}=await init.json();
  Promise.allSettled(targets.map(t=>collectTarget(origin,t))).then(rows=>{resultLog.push(rows.map(x=>x.status));running=false;}).catch(()=>{running=false;});
  return send(r,200,'application/json','{"started":true}');
 }
 if(u.pathname==='/api/reset'&&q.method==='POST'){
  if(running)return send(r,409,'application/json','{"error":"checks still running"}');
  const a=await fetch(origin+'/reset',{method:'POST'});return send(r,a.status,'application/json',await a.text());
 }
 if(u.pathname==='/api/snapshot'){
  const a=await fetch(origin+'/snapshot');return send(r,a.status,'application/json',await a.text());
 }
 let p=null;
 if(u.pathname==='/'||u.pathname==='/index.html')p=resolve(root,'dist/index.html');
 else if(/^\/src\/[a-zA-Z0-9_/-]+\.(mjs|css)$/.test(u.pathname)&&!u.pathname.includes('..'))p=resolve(root,'dist'+u.pathname);
 if(!p)return send(r,404,'text/plain','not found');
 try{return send(r,200,p.endsWith('.html')?'text/html':p.endsWith('.css')?'text/css':'text/javascript',await readFile(p));}
 catch{return send(r,404,'text/plain','not found');}
 }catch(e){send(r,500,'application/json',JSON.stringify({error:e.message}));}
}).listen(port,host);
