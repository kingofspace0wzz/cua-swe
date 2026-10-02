import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createReceiver} from './src/receiver.mjs';
const root=dirname(fileURLToPath(import.meta.url));
const origin=process.env.CUA_SWE_EXTERNAL_SERVICE_ORIGIN;
if(!origin)throw new Error('CUA_SWE_EXTERNAL_SERVICE_ORIGIN required');
let port=57152,host='127.0.0.1';
for(let i=2;i<process.argv.length;i++){if(process.argv[i]==='--port')port=Number(process.argv[++i]);else if(process.argv[i]==='--host')host=process.argv[++i];}
const receiver=createReceiver(origin);
function send(r,status,type,body){r.writeHead(status,{'content-type':type,'cache-control':'no-store'});r.end(body);}
createServer(async(q,r)=>{try{
 const u=new URL(q.url,'http://app.invalid');
 if(q.method==='POST'&&['/api/seed','/api/run','/api/reset'].includes(u.pathname)){
  const result=u.pathname==='/api/reset'?await receiver.reset():await receiver.begin(u.pathname==='/api/seed');
  return send(r,200,'application/json',JSON.stringify(result));
 }
 if(u.pathname==='/api/snapshot'){
  const response=await fetch(origin+'/snapshot');const result=await response.json();
  return send(r,response.status,'application/json',JSON.stringify({...result,worker:receiver.status()}));
 }
 let path=null;
 if(u.pathname==='/'||u.pathname==='/index.html')path=resolve(root,'dist/index.html');
 else if(/^\/src\/[a-zA-Z0-9_/-]+\.(mjs|css)$/.test(u.pathname)&&!u.pathname.includes('..'))path=resolve(root,'dist'+u.pathname);
 if(!path)return send(r,404,'text/plain','not found');
 try{return send(r,200,path.endsWith('.html')?'text/html':path.endsWith('.css')?'text/css':'text/javascript',await readFile(path));}
 catch{return send(r,404,'text/plain','not found');}
 }catch(e){send(r,500,'application/json',JSON.stringify({error:e.message}));}
}).listen(port,host);
