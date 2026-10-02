import {request} from 'node:http';
import {performance} from 'node:perf_hooks';
import {budgets} from './budgets.mjs';

// Fetch a complete metrics response. Both deadlines are configurable transport inputs.
export function fetchMetrics(url, limits=budgets, notify=()=>{}) {
  return new Promise((resolve,reject)=>{
    const started=performance.now();let settled=false,response=null;
    const event=(phase,extra={})=>notify({phase,elapsedMs:performance.now()-started,...extra});
    const req=request(url,{method:'GET',agent:false},res=>{
      response=res;event('headers',{status:res.statusCode});const chunks=[];
      res.on('data',chunk=>chunks.push(chunk));
      res.on('aborted',()=>finish(new Error('incomplete_response')));
      res.on('error',finish);
      res.on('end',()=>{
        if(res.statusCode!==200||!res.complete)return finish(new Error('incomplete_response'));
        event('response_complete',{bytes:chunks.reduce((n,c)=>n+c.length,0)});
        finish(null,Buffer.concat(chunks).toString('utf8'));
      });
    });
    const finish=(error,body)=>{
      if(settled)return;settled=true;clearTimeout(watchdog);
      if(error){event('abort',{reason:error.message});response?.destroy();req.destroy();reject(error);}
      else resolve(body);
    };
    // This absolute guard covers connect, first final response, and every body read.
    const watchdog=setTimeout(()=>finish(new Error('request_deadline')),limits.requestTimeoutMs);
    req.on('socket',socket=>{
      socket.setTimeout(limits.connectTimeoutMs);
      socket.on('timeout',()=>finish(new Error('socket_timeout')));
      socket.once('connect',()=>{
        event('connected');
      });
    });
    req.on('error',finish);event('dispatch');req.end();
  });
}
