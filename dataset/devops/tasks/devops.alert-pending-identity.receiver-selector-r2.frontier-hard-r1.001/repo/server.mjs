import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {contentTypeFor,isDocumentPath,resolveAsset} from './src/server/staticFiles.js';
import {createServiceProxy,serviceOrigin} from './src/server/serviceProxy.js';
const ROOT=dirname(fileURLToPath(import.meta.url));
const forward=process.env.CUA_SWE_EXTERNAL_SERVICE_ORIGIN ? createServiceProxy(serviceOrigin(process.env)) : async()=>({status:503,type:'application/json',body:JSON.stringify({error:'Evaluator is not connected'})});
const PUBLIC_API=new Set(['catalog','configure','snapshot','scenario','target','advance','replay','reset']);
const options={host:'127.0.0.1',port:55100};
for(let i=2;i<process.argv.length;i++){
 if(process.argv[i]==='--host')options.host=process.argv[++i];
 else if(process.argv[i]==='--port')options.port=Number(process.argv[++i]);
}
function send(r,status,type,body){r.writeHead(status,{'content-type':type,'cache-control':'no-store','content-length':Buffer.byteLength(body)});r.end(body);}
createServer(async(req,res)=>{
 try{
  const url=new URL(req.url,'http://local.invalid');
  if(url.pathname.startsWith('/api/')){
   if(!PUBLIC_API.has(url.pathname.slice(5)))return send(res,404,'text/plain','not found');
   const a=await forward(req,url.pathname.slice(4),url.search);return send(res,a.status,a.type,a.body);
  }
  const asset=resolveAsset(ROOT,url.pathname);
  if(asset){try{return send(res,200,contentTypeFor(asset),await readFile(asset));}catch{return send(res,404,'text/plain','not found');}}
  if(isDocumentPath(url.pathname))return send(res,200,'text/html',await readFile(new URL('./index.html',import.meta.url)));
  send(res,404,'text/plain','not found');
 }catch(e){send(res,500,'application/json',JSON.stringify({error:'application_error',detail:String(e.message)}));}
}).listen(options.port,options.host);
